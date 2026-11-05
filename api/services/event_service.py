"""
event_service
──────────────
Domain helpers for the Event CRUD flow. GraphQL resolvers stay thin and call
these with plain values.
"""

import datetime
from typing import Any, List, Optional

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import QuerySet

from api.models import Event
from api.utils.enums import EventStatus
from api.utils.luma import canonical_luma_src, validate_luma_embed

_UNSET: Any = object()


def create_event(
    *,
    user: Any,
    organization: Any,
    name: str = "",
    location: str = "",
    start_date: Any = None,
    end_date: Any = None,
    luma_embed: Optional[str] = None,
) -> Event:
    """Create a draft. A blank name is replaced with a generated one.

    An organization on the request owns the row; otherwise the user does.
    A sent embed must already be a Luma embed URL. Dates, when both are sent,
    must run forward.
    """
    errors: dict[str, List[str]] = {}
    embed = _normalize_embed(luma_embed, errors)
    _check_date_order(start_date, end_date, errors)
    if errors:
        raise DjangoValidationError(errors)

    return Event.objects.create(
        name=(name or "").strip() or _default_name(),
        location=(location or "").strip(),
        start_date=start_date,
        end_date=end_date,
        luma_embed=embed or {},
        organization=organization,
        user=user,
        status=EventStatus.DRAFT,
    )


def apply_event_update(
    event: Event,
    *,
    name: Any = _UNSET,
    location: Any = _UNSET,
    start_date: Any = _UNSET,
    end_date: Any = _UNSET,
    luma_embed: Any = _UNSET,
) -> Event:
    """Apply a partial update. Omitted fields are left untouched.

    A draft may be saved incomplete. A row that is already published cannot be
    saved back into an incomplete state.
    """
    errors: dict[str, List[str]] = {}
    new_name = event.name if name is _UNSET else (name or "").strip()
    new_location = event.location if location is _UNSET else (location or "").strip()
    new_start = event.start_date if start_date is _UNSET else start_date
    new_end = event.end_date if end_date is _UNSET else end_date

    new_embed = event.luma_embed or {}
    if luma_embed is not _UNSET:
        if luma_embed:
            parsed = _normalize_embed(luma_embed, errors)
            if parsed is not None:
                new_embed = parsed
        else:
            new_embed = {}

    _check_date_order(new_start, new_end, errors)
    if errors:
        raise DjangoValidationError(errors)

    if event.status == EventStatus.PUBLISHED:
        _require_complete(
            name=new_name,
            location=new_location,
            start_date=new_start,
            end_date=new_end,
            luma_embed=new_embed,
        )

    with transaction.atomic():
        event.name = new_name
        event.location = new_location
        event.start_date = new_start
        event.end_date = new_end
        event.luma_embed = new_embed
        event.save()
    return event


def assert_ready_to_publish(event: Event) -> None:
    """Reject a publish when the draft is still missing a required field."""
    _require_complete(
        name=event.name,
        location=event.location,
        start_date=event.start_date,
        end_date=event.end_date,
        luma_embed=event.luma_embed or {},
    )


def set_event_status(event: Event, status: EventStatus) -> Event:
    """Flip an event's publish status and save it."""
    event.status = status
    event.save()
    return event


def get_scoped_events(*, user: Any, organization: Any) -> "QuerySet[Event, Event]":
    """Return the events a caller may list.

    Organization context → that org's events; an authenticated individual →
    their own; anonymous → published only. Ordered newest-first.
    """
    if organization:
        queryset = Event.objects.filter(organization=organization)
    elif getattr(user, "is_superuser", False):
        queryset = Event.objects.all()
    elif getattr(user, "is_authenticated", False):
        queryset = Event.objects.filter(user=user, organization__isnull=True)
    else:
        queryset = Event.objects.filter(status=EventStatus.PUBLISHED)

    return queryset.select_related("organization", "user").order_by("-modified")


def _require_complete(
    *,
    name: Optional[str],
    location: Optional[str],
    start_date: Any,
    end_date: Any,
    luma_embed: Any,
) -> None:
    errors: dict[str, List[str]] = {}
    if not name or not name.strip():
        errors["name"] = ["Name is required."]
    if not location or not location.strip():
        errors["location"] = ["Location is required."]
    if start_date is None:
        errors["start_date"] = ["Start date is required."]
    if end_date is None:
        errors["end_date"] = ["End date is required."]
    _check_date_order(start_date, end_date, errors)
    src = luma_embed.get("src") if isinstance(luma_embed, dict) else ""
    if not src or not canonical_luma_src(str(src)):
        errors["luma_embed"] = ["A Luma embed is required."]
    if errors:
        raise DjangoValidationError(errors)


def _normalize_embed(value: Optional[str], errors: dict[str, List[str]]) -> Optional[dict]:
    if value is None or not str(value).strip():
        return None
    try:
        return validate_luma_embed(value)
    except DjangoValidationError as exc:
        errors["luma_embed"] = [str(message) for message in exc.messages]
        return None


def _check_date_order(start_date: Any, end_date: Any, errors: dict[str, List[str]]) -> None:
    if start_date and end_date and end_date < start_date:
        errors["end_date"] = ["End date must be on or after the start date."]


def _default_name() -> str:
    return f"New event {datetime.datetime.now().strftime('%d %b %Y - %H:%M:%S')}"
