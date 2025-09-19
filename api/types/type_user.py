from typing import TYPE_CHECKING, Annotated, List, Optional

import strawberry
import strawberry_django
from strawberry import auto

from api.types.base_type import BaseType
from authorization.models import OrganizationMembership, Role, User

if TYPE_CHECKING:
    from authorization.types import TypeOrganizationMembership


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
    ],
    filters=UserFilter,
    pagination=True,
    order=True,  # Changed from UserOrder to True
)
class TypeUser(BaseType):
    """Type for user."""

    @strawberry.field
    def organization_memberships(
        self,
    ) -> List[
        Annotated["TypeOrganizationMembership", strawberry.lazy("authorization.types")]
    ]:
        """Get organization memberships for this user."""
        try:
            from authorization.types import TypeOrganizationMembership

            user_id = str(getattr(self, "id", ""))
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
