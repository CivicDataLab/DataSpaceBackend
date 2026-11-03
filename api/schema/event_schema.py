"""Schema definitions for events.

Resolvers delegate metadata checks, writes, and scoping to
``api/services/event_service.py``.
"""

import datetime
import uuid
from typing import List, Optional

import strawberry
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import QuerySet
from strawberry.types import Info

from api.models import Event
from api.schema.base_mutation import BaseMutation, MutationResponse
from api.services.event_service import (
    apply_event_update,
    assert_ready_to_publish,
    create_event,
    get_scoped_events,
    set_event_status,
)
from api.types.type_event import EventResponse, TypeEvent
from api.utils.enums import EventStatus
from api.utils.graphql_telemetry import trace_resolver
from api.utils.public_links import parse_public_id
from api.utils.qs_utils import (
    FilterSpec,
    SortSpec,
    get_pagination_window,
    status_counts,
)
from authorization.permissions import (
    AllowPublishedEvents,
    ChangeEventPermission,
    CreateEventPermission,
    DeleteEventPermission,
    PublishEventPermission,
)


@strawberry.input
class CreateEventInput:
    """Fields for a new draft. Every field is optional."""

    name: Optional[str] = None
    location: Optional[str] = None
    start_date: Optional[datetime.date] = None
    end_date: Optional[datetime.date] = None
    luma_embed: Optional[str] = None


@strawberry.input
class UpdateEventInput:
    """Partial edit. ``UNSET`` means the client omitted the field."""

    id: uuid.UUID
    name: Optional[str] = strawberry.UNSET
    location: Optional[str] = strawberry.UNSET
    start_date: Optional[datetime.date] = strawberry.UNSET
    end_date: Optional[datetime.date] = strawberry.UNSET
    luma_embed: Optional[str] = strawberry.UNSET


EVENTS_TABLE_FILTER_FIELDS = [
    "id",
    "name",
    "location",
    "status",
    "start_date",
    "end_date",
    "organization",
    "organization__slug",
    "created",
    "modified",
]
EVENTS_TABLE_SORT_FIELDS = [
    "name",
    "location",
    "status",
    "start_date",
    "end_date",
    "created",
    "modified",
]


def _visible_events(info: Info) -> QuerySet:
    return get_scoped_events(
        user=info.context.user,
        organization=info.context.context.get("organization"),
    )


@strawberry.type(name="Query")
class Query:
    @strawberry.field(permission_classes=[AllowPublishedEvents])  # type: ignore[list-item]
    @trace_resolver(name="get_event", attributes={"component": "event"})
    def event(self, info: Info, event_id: uuid.UUID) -> Optional[TypeEvent]:
        """Get one event. Drafts are gated to the owner or organization."""
        try:
            return TypeEvent.from_django(Event.objects.get(id=event_id))
        except Event.DoesNotExist:
            return None

    @strawberry.field
    @trace_resolver(name="events_table", attributes={"component": "event"})
    def events_table(
        self,
        info: Info,
        filters: Optional[List[FilterSpec]] = None,
        sort_options: Optional[List[SortSpec]] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> EventResponse:
        """Events for the dashboard table, scoped like the other providers."""
        visible = _visible_events(info)
        window = get_pagination_window(
            visible,
            limit=limit,
            offset=offset,
            filters=filters,
            filtering_allowed_fields=EVENTS_TABLE_FILTER_FIELDS,
            sort_options=sort_options or [SortSpec(field="modified", direction="desc")],
            sorting_allowed_fields=EVENTS_TABLE_SORT_FIELDS,
        )
        return EventResponse(
            data=TypeEvent.from_django_list(window["data"]),
            total_items_count=window["total_items_count"],
            status_counts=status_counts(visible, filters, EVENTS_TABLE_FILTER_FIELDS),
        )

    @strawberry.field
    @trace_resolver(name="published_events", attributes={"component": "event"})
    def published_events(
        self,
        info: Info,
        organization_slug: Optional[str] = None,
        filters: Optional[List[FilterSpec]] = None,
        sort_options: Optional[List[SortSpec]] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> EventResponse:
        """Published events for public pages. Drafts are never included."""
        visible = Event.objects.filter(status=EventStatus.PUBLISHED).select_related(
            "organization", "user"
        )
        if organization_slug:
            visible = visible.filter(organization__slug=organization_slug)
        window = get_pagination_window(
            visible,
            limit=limit,
            offset=offset,
            filters=filters,
            filtering_allowed_fields=EVENTS_TABLE_FILTER_FIELDS,
            sort_options=sort_options or [SortSpec(field="start_date", direction="asc")],
            sorting_allowed_fields=EVENTS_TABLE_SORT_FIELDS,
        )
        return EventResponse(
            data=TypeEvent.from_django_list(window["data"]),
            total_items_count=window["total_items_count"],
            status_counts=[],
        )

    @strawberry.field
    @trace_resolver(name="event_by_slug", attributes={"component": "event"})
    def event_by_slug(self, info: Info, slug: str) -> Optional[TypeEvent]:
        """Published event for a public page, found by its link (``urlSlug``).

        Only the publicId at the end of the link is used, so a link with old
        title words still works. Drafts, unknown ids and links without an id
        return null.
        """
        public_id = parse_public_id(slug)
        if public_id is None:
            return None
        event = (
            Event.objects.filter(public_id=public_id, status=EventStatus.PUBLISHED)
            .select_related("organization", "user")
            .first()
        )
        if event is None:
            return None
        return TypeEvent.from_django(event)


@strawberry.type(name="Mutation")
class Mutation:
    @strawberry.mutation
    @BaseMutation.mutation(
        permission_classes=[CreateEventPermission],
        trace_name="create_event",
        trace_attributes={"component": "event"},
        track_activity={
            "verb": "created",
            "get_data": lambda result, **kwargs: {"event_id": str(result.id)},
        },
    )
    def create_event(self, info: Info, input: CreateEventInput) -> MutationResponse[TypeEvent]:
        """Create a draft owned by the caller's organization or the user."""
        event = create_event(
            user=info.context.user,
            organization=info.context.context.get("organization"),
            name=input.name or "",
            location=input.location or "",
            start_date=input.start_date,
            end_date=input.end_date,
            luma_embed=input.luma_embed,
        )
        return MutationResponse.success_response(TypeEvent.from_django(event))

    @strawberry.mutation
    @BaseMutation.mutation(
        permission_classes=[ChangeEventPermission],
        trace_name="update_event",
        trace_attributes={"component": "event"},
        track_activity={
            "verb": "updated",
            "get_data": lambda result, **kwargs: {"event_id": str(result.id)},
        },
    )
    def update_event(self, info: Info, input: UpdateEventInput) -> MutationResponse[TypeEvent]:
        """Apply a partial edit. Completeness is required only after publish."""
        event = _get_event_or_raise(input.id)
        event = apply_event_update(event, **_update_kwargs(input))
        return MutationResponse.success_response(TypeEvent.from_django(event))

    @strawberry.mutation
    @BaseMutation.mutation(
        permission_classes=[PublishEventPermission],
        trace_name="publish_event",
        trace_attributes={"component": "event"},
        track_activity={
            "verb": "published",
            "get_data": lambda result, **kwargs: {"event_id": str(result.id)},
        },
    )
    def publish_event(self, info: Info, event_id: uuid.UUID) -> MutationResponse[TypeEvent]:
        """Publish an event once name, location, dates, and a Luma embed are set."""
        event = _get_event_or_raise(event_id)
        assert_ready_to_publish(event)
        event = set_event_status(event, EventStatus.PUBLISHED)
        return MutationResponse.success_response(TypeEvent.from_django(event))

    @strawberry.mutation
    @BaseMutation.mutation(
        permission_classes=[PublishEventPermission],
        trace_name="unpublish_event",
        trace_attributes={"component": "event"},
        track_activity={
            "verb": "unpublished",
            "get_data": lambda result, **kwargs: {"event_id": str(result.id)},
        },
    )
    def unpublish_event(self, info: Info, event_id: uuid.UUID) -> MutationResponse[TypeEvent]:
        """Move an event back to draft."""
        event = _get_event_or_raise(event_id)
        event = set_event_status(event, EventStatus.DRAFT)
        return MutationResponse.success_response(TypeEvent.from_django(event))

    @strawberry.mutation
    @BaseMutation.mutation(
        permission_classes=[DeleteEventPermission],
        trace_name="delete_event",
        trace_attributes={"component": "event"},
        track_activity={
            "verb": "deleted",
            "get_data": lambda result, **kwargs: {
                "event_id": str(kwargs.get("event_id")),
                "success": result,
            },
        },
    )
    def delete_event(self, info: Info, event_id: uuid.UUID) -> MutationResponse[bool]:
        """Hard-delete an event."""
        event = _get_event_or_raise(event_id)
        event.delete()
        return MutationResponse.success_response(True)


def _update_kwargs(input: UpdateEventInput) -> dict:
    kwargs: dict = {}
    if input.name is not strawberry.UNSET:
        kwargs["name"] = input.name
    if input.location is not strawberry.UNSET:
        kwargs["location"] = input.location
    if input.start_date is not strawberry.UNSET:
        kwargs["start_date"] = input.start_date
    if input.end_date is not strawberry.UNSET:
        kwargs["end_date"] = input.end_date
    if input.luma_embed is not strawberry.UNSET:
        kwargs["luma_embed"] = input.luma_embed
    return kwargs


def _get_event_or_raise(event_id: uuid.UUID) -> Event:
    try:
        return Event.objects.get(id=event_id)
    except Event.DoesNotExist:
        raise DjangoValidationError(f"Event with id {event_id} does not exist.")
