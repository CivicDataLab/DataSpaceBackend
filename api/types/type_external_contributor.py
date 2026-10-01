from typing import Optional

import strawberry
import strawberry_django
from strawberry import auto, field

from api.models import ExternalContributor
from api.types.base_type import BaseType


@strawberry_django.filter(ExternalContributor)
class ExternalContributorFilter:
    id: auto
    name: auto


@strawberry_django.order(ExternalContributor)
class ExternalContributorOrder:
    name: auto
    created_at: auto


@strawberry_django.type(
    ExternalContributor,
    pagination=True,
    fields=["id", "has_approved"],
    filters=ExternalContributorFilter,
    order=ExternalContributorOrder,
)
class TypeExternalContributor(BaseType):
    """GraphQL type for ExternalContributor with privacy controls."""

    @field
    def name(self) -> str:
        """Return name if approved, otherwise return 'Anonymous'."""
        if self.has_approved:  # type: ignore
            return self.name  # type: ignore
        return "Anonymous"

    @field
    def image(self) -> Optional[str]:
        """Return image if approved, otherwise None."""
        if self.has_approved:  # type: ignore
            return self.image  # type: ignore
        return None

    @field
    def designation(self) -> Optional[str]:
        """Return designation if approved, otherwise None."""
        if self.has_approved:  # type: ignore
            return self.designation  # type: ignore
        return None

    @field
    def bio(self) -> Optional[str]:
        """Return bio if approved, otherwise None."""
        if self.has_approved:  # type: ignore
            return self.bio  # type: ignore
        return None

    @field
    def created_at(self) -> str:
        """Always return created_at for all users (approved or not)."""
        return str(self.created_at)  # type: ignore

    @field
    def updated_at(self) -> str:
        """Always return updated_at for all users (approved or not)."""
        return str(self.updated_at)  # type: ignore
