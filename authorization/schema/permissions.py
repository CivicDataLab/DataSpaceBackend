"""Permission classes for GraphQL schema in authorization module."""

from typing import Any

import structlog
from strawberry.permission import BasePermission
from strawberry.types import Info

from authorization.models import OrganizationMembership

logger = structlog.getLogger(__name__)


class AllowPublicUserInfo(BasePermission):
    """Permission class that allows access to basic user information for everyone."""

    message = "Access to detailed user information requires authentication"

    def has_permission(self, source: Any, info: Info, **kwargs: Any) -> bool:
        # Allow access to basic user information for everyone
        return True


class HasOrganizationAdminRole(BasePermission):
    """Permission class that checks if the user has admin role in the organization."""

    message = "You need to be an admin of the organization to perform this action"

    def has_permission(self, source: Any, info: Info, **kwargs: Any) -> bool:
        # Only authenticated users can proceed
        if not info.context.user.is_authenticated:
            return False

        # Superusers can do anything
        if info.context.user.is_superuser:
            return True

        # For adding user to organization, check if the user is an admin
        organization = info.context.context.get("organization")
        if not organization:
            return False

        try:
            # Check if the user is an admin of the organization
            membership = OrganizationMembership.objects.get(
                user=info.context.user, organization=organization
            )
            return membership.role.name == "admin"
        except OrganizationMembership.DoesNotExist:
            return False
