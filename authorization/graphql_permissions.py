from typing import Any, List, Optional, cast

import strawberry
from strawberry.permission import BasePermission
from strawberry.types import Info

from authorization.models import DatasetPermission, OrganizationMembership, User
from authorization.services import AuthorizationService


class AllowAny(BasePermission):
    """
    Permission class that allows any access.
    This is the default permission class for GraphQL queries.
    """

    message = ""  # No message needed since permission is always granted

    def has_permission(self, source: Any, info: Info, **kwargs: Any) -> bool:
        return True


class IsAuthenticated(BasePermission):
    """
    Permission class that checks if the user is authenticated.
    """

    message = "User is not authenticated"

    def has_permission(self, source: Any, info: Info, **kwargs: Any) -> bool:
        request = info.context.request
        return request.user.is_authenticated  # type: ignore[no-any-return]


class IsOrganizationMember(BasePermission):
    """
    Permission class that checks if the user is a member of the organization.
    """

    message = "User is not a member of the organization"

    def __init__(self, organization_id_arg: str = "organization_id"):
        self.organization_id_arg = organization_id_arg

    def has_permission(self, source: Any, info: Info, **kwargs: Any) -> bool:
        request = info.context.request

        # If the user is a superuser, grant permission
        if request.user.is_superuser:
            return True

        # Get the organization ID from the arguments
        organization_id = kwargs.get(self.organization_id_arg)
        if not organization_id:
            return False

        # Check if the user is a member of the organization
        auth_service = AuthorizationService()
        # Use the check_organization_permission method instead
        return auth_service.check_organization_permission(
            request.user.id, organization_id, "view"
        )


class HasOrganizationRole(BasePermission):
    """
    Permission class that checks if the user has the required role in the organization.
    """

    message = "User does not have the required role in the organization"

    def __init__(
        self, operation: str = "view", organization_id_arg: str = "organization_id"
    ):
        # Convert operation to a list of role names for backward compatibility
        self.operation = operation
        self.organization_id_arg = organization_id_arg

    def has_permission(self, source: Any, info: Info, **kwargs: Any) -> bool:
        request = info.context.request

        # If the user is a superuser, grant permission
        if request.user.is_superuser:
            return True

        # Get the organization ID from the arguments
        organization_id = kwargs.get(self.organization_id_arg)
        if not organization_id:
            return False

        # Check if the user has the required permission in the organization
        return AuthorizationService.check_organization_permission(
            request.user.id, organization_id, self.operation
        )  # type: ignore[no-any-return]

        return False


class HasDatasetPermission(BasePermission):
    """
    Permission class that checks if the user has the required permission for the dataset.
    """

    message = "User does not have the required permission for the dataset"

    def __init__(self, operation: str = "view", dataset_id_arg: str = "dataset_id"):
        self.operation = operation
        self.dataset_id_arg = dataset_id_arg

    def has_permission(self, source: Any, info: Info, **kwargs: Any) -> bool:
        request = info.context.request

        # If the user is a superuser, grant permission
        if request.user.is_superuser:
            return True

        # Get the dataset ID from the arguments
        dataset_id = kwargs.get(self.dataset_id_arg)
        if not dataset_id:
            return False

        # Check if the user has the required permission for the dataset
        return AuthorizationService.check_dataset_permission(
            request.user.id, dataset_id, self.operation
        )  # type: ignore[no-any-return]
