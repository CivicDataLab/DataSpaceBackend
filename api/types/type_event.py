import uuid
from datetime import date, datetime
from typing import List, Optional

import strawberry
import strawberry_django
from strawberry.enum import EnumType

from api.models import Event
from api.types.base_type import BaseType
from api.types.type_organization import TypeOrganization
from api.utils.enums import EventStatus
from api.utils.qs_utils import StatusCount
from authorization.types import TypeUser

event_status: EnumType = strawberry.enum(EventStatus)  # type: ignore


def _text(value: object) -> Optional[str]:
    return value if isinstance(value, str) and value else None


@strawberry.type
class TypeLumaEmbed:
    """Presentation attributes taken from a Luma iframe. ``src`` is always a Luma embed URL."""

    src: str
    width: Optional[str]
    height: Optional[str]
    style: Optional[str]
    title: Optional[str]
    allow: Optional[str]
    allowfullscreen: bool
    frameborder: Optional[str]
    referrerpolicy: Optional[str]
    loading: Optional[str]


@strawberry_django.filter(Event)
class EventFilter:
    id: Optional[uuid.UUID]
    status: Optional[event_status]


@strawberry_django.order(Event)
class EventOrder:
    name: strawberry.auto
    created: strawberry.auto
    modified: strawberry.auto
    start_date: strawberry.auto


@strawberry_django.type(Event, filters=EventFilter, pagination=True, order=EventOrder)  # type: ignore
class TypeEvent(BaseType):
    """A Luma event in the dashboard provider flow."""

    id: uuid.UUID
    name: str
    slug: str
    location: str
    start_date: Optional[date]
    end_date: Optional[date]
    status: event_status
    created: datetime
    modified: datetime
    organization: Optional["TypeOrganization"]
    user: Optional["TypeUser"]

    @strawberry.field
    def luma_embed(self) -> Optional["TypeLumaEmbed"]:
        """Whitelisted iframe attributes. Empty when the event has no embed yet."""
        raw = self.luma_embed if isinstance(getattr(self, "luma_embed", None), dict) else {}
        src = raw.get("src")
        if not isinstance(src, str) or not src:
            return None
        return TypeLumaEmbed(
            src=src,
            width=_text(raw.get("width")),
            height=_text(raw.get("height")),
            style=_text(raw.get("style")),
            title=_text(raw.get("title")),
            allow=_text(raw.get("allow")),
            allowfullscreen=bool(raw.get("allowfullscreen")),
            frameborder=_text(raw.get("frameborder")),
            referrerpolicy=_text(raw.get("referrerpolicy")),
            loading=_text(raw.get("loading")),
        )

    @strawberry.field
    def is_individual_event(self) -> bool:
        """True when owned by an individual rather than an organization."""
        return self.organization is None


@strawberry.type
class EventResponse:
    """One page of ``eventsTable``: rows, the filtered total, and tab counts."""

    data: List[TypeEvent]
    total_items_count: int
    status_counts: List[StatusCount] = strawberry.field(
        default_factory=list,
        description="Counts per status with the same filters applied, except any status filter.",
    )
