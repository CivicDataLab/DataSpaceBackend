from typing import Any, Callable, List, Optional, cast

import strawberry
import strawberry_django
from strawberry import auto, lazy
from strawberry.types import Info

from api.types.base_type import BaseType
from api.types.type_organization import TypeOrganization
from api.types.type_sector import TypeSector  # type: ignore
from authorization.models import OrganizationMembership, Role, User


@strawberry_django.type(Role, fields="__all__")
class TypeRole(BaseType):
    """Type for user role."""

    id: auto
    name: auto
    description: auto


@strawberry_django.type(OrganizationMembership)
class TypeOrganizationMembership(BaseType):
    """Type for organization membership."""

    organization: TypeOrganization
    role: TypeRole
    created_at: auto
    updated_at: auto


@strawberry_django.filter(User)
class UserFilter:
    """Filter for user."""

    id: Optional[strawberry.ID]
    username: Optional[str]
    email: Optional[str]


@strawberry_django.order(User)
class UserOrder:
    """Order for user."""

    username: auto
    first_name: auto
    last_name: auto
    date_joined: auto


@strawberry_django.type(
    User,
    fields=[
        "id",
        "username",
        "email",
        "first_name",
        "last_name",
        "bio",
        "profile_picture",
        "date_joined",
        "last_login",
        "github_profile",
        "linkedin_profile",
        "twitter_profile",
        "location",
    ],
    filters=UserFilter,
    pagination=True,
    order=UserOrder,  # type: ignore
)
class TypeUser(BaseType):
    """Type for user."""

    @strawberry.field
    def organization_memberships(self) -> List[TypeOrganizationMembership]:
        """Get organization memberships for this user.

        If current_org_memberships is prefetched (from user_by_organization query),
        returns only those memberships. Otherwise, returns all memberships.
        """
        try:
            # Check if we have prefetched current_org_memberships
            if hasattr(self, "current_org_memberships"):
                return TypeOrganizationMembership.from_django_list(
                    self.current_org_memberships
                )

            # Otherwise, fall back to fetching all memberships
            user_id = str(getattr(self, "id", None))
            queryset = OrganizationMembership.objects.filter(user_id=user_id)
            return TypeOrganizationMembership.from_django_list(queryset)
        except Exception:
            return []

    @strawberry.field
    def full_name(self) -> str:
        """Get full name of the user."""
        first_name = getattr(self, "first_name", "")
        last_name = getattr(self, "last_name", "")
        if first_name and last_name:
            return f"{first_name} {last_name}"
        elif first_name:
            return first_name
        elif last_name:
            return last_name
        else:
            return getattr(self, "username", "")
