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
    email: auto
    organization: auto


@strawberry_django.order(ExternalContributor)
class ExternalContributorOrder:
    name: auto
    created_at: auto


@strawberry_django.type(
    ExternalContributor,
    pagination=True,
    fields=["id", "image", "has_approved"],
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
    def email(self) -> Optional[str]:
        """Email is never returned for privacy reasons."""
        return None

    @field
    def organization(self) -> Optional[str]:
        """Return organization if approved, otherwise None."""
        if self.has_approved:  # type: ignore
            return self.organization  # type: ignore
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
    def created_at(self) -> Optional[str]:
        """Return created_at if approved, otherwise None."""
        if self.has_approved:  # type: ignore
            return str(self.created_at)  # type: ignore
        return None

    @field
    def updated_at(self) -> Optional[str]:
        """Return updated_at if approved, otherwise None."""
        if self.has_approved:  # type: ignore
            return str(self.updated_at)  # type: ignore
        return None
