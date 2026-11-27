"""Type definitions for UseCaseDashboard model."""

from typing import Optional

import strawberry
import strawberry_django
from strawberry import auto
from strawberry_django.filters import FilterLookup

from api.models import UseCaseDashboard
from api.types.base_type import BaseType
from api.utils.dashboard_links import embed_url as dashboard_embed_url


@strawberry_django.type(UseCaseDashboard)
class TypeUseCaseDashboard(BaseType):
    """Type for UseCaseDashboard model."""

    id: auto
    name: auto
    link: auto
    created: auto
    modified: auto
    usecase_id: auto

    @strawberry.field(description="The link to embed, or null when its host may not be embedded.")
    def embed_url(self) -> Optional[str]:
        return dashboard_embed_url(self.link)  # type: ignore[attr-defined]


@strawberry.input
class UseCaseDashboardFilter:
    """Filter for UseCaseDashboard queries."""

    id: Optional[FilterLookup[int]] = strawberry.UNSET
    name: Optional[FilterLookup[str]] = strawberry.UNSET
    usecase_id: Optional[FilterLookup[int]] = strawberry.UNSET


@strawberry.input
class UseCaseDashboardOrder:
    """Order for UseCaseDashboard queries."""

    name: Optional[str] = strawberry.UNSET
    created: Optional[str] = strawberry.UNSET
