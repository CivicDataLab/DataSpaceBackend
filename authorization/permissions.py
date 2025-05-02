from typing import Any, Optional, Union, cast

from django.db.models import Q
from rest_framework import permissions
from strawberry.permission import BasePermission
from strawberry.types import Info

from api.models import Organization
from authorization.models import DatasetPermission, OrganizationMembership, Role


# REST Framework Permissions
class IsOrganizationMember(permissions.BasePermission):
    """
    Permission class to check if a user is a member of the organization
    that owns the object being accessed.
    """

    def has_object_permission(self, request: Any, view: Any, obj: Any) -> bool:
        # If the user is a superuser, grant permission
        if request.user.is_superuser:
            return True

        # Get the organization from the object
        organization = self._get_organization(obj)
        if not organization:
            return False

        # Check if the user is a member of the organization
        return OrganizationMembership.objects.filter(
            user=request.user, organization=organization
        ).exists()

    def _get_organization(self, obj: Any) -> Optional[Organization]:
        """
        Get the organization from the object.
        Override this method in subclasses for specific object types.
        """
        if hasattr(obj, "organization"):
            return obj.organization  # type: ignore[attr-defined,no-any-return]
        return None


class HasOrganizationRole(permissions.BasePermission):
    """
    Permission class to check if a user has a specific role in the organization
    that owns the object being accessed.
    """

    def has_permission(self, request: Any, view: Any) -> bool:
        # For list views, check if user has access to any organization
        if request.user.is_superuser:
            return True

        # For organization-specific endpoints
        org_id = request.query_params.get("organization") or request.data.get(
            "organization"
        )
        if org_id:
            return OrganizationMembership.objects.filter(
                user=request.user, organization_id=org_id
            ).exists()  # type: ignore[no-any-return]

        # For general list views, allow if user belongs to any organization
        return OrganizationMembership.objects.filter(user=request.user).exists()

    def has_object_permission(self, request: Any, view: Any, obj: Any) -> bool:
        # If the user is a superuser, grant permission
        if request.user.is_superuser:
            return True

        # Get the organization from the object
        organization = self._get_organization(obj)
        if not organization:
            return False

        # Get the user's role in the organization
        try:
            membership = OrganizationMembership.objects.get(
                user=request.user, organization=organization
            )
            role = membership.role  # type: ignore[attr-defined]

            # Map the HTTP method to an action
            method = request.method.lower()
            action = self._get_action_from_method(method)

            # Check if the user's role allows the action
            if action == "view":
                return role.can_view  # type: ignore[attr-defined]
            elif action == "add":
                return role.can_add  # type: ignore[attr-defined]
            elif action == "change":
                return role.can_change  # type: ignore[attr-defined]
            elif action == "delete":
                return role.can_delete  # type: ignore[attr-defined]
            return False

        except OrganizationMembership.DoesNotExist:
            return False

    def _get_organization(self, obj: Any) -> Optional[Organization]:
        """
        Get the organization from the object.
        Override this method in subclasses for specific object types.
        """
        if hasattr(obj, "organization"):
            return obj.organization  # type: ignore[attr-defined,no-any-return]
        return None

    def _get_action_from_method(self, method: str) -> Optional[str]:
        """
        Map HTTP method to a permission action.
        """
        if method == "get":
            return "view"
        elif method == "post":
            return "add"
        elif method in ["put", "patch"]:
            return "change"
        elif method == "delete":
            return "delete"
        return None


# Strawberry GraphQL Permissions
class IsAuthenticated(BasePermission):
    """
    Permission class that checks if the user is authenticated.
    """

    message = "User is not authenticated"

    def has_permission(self, source: Any, info: Info, **kwargs: Any) -> bool:
        request = info.context
        return request.user.is_authenticated  # type: ignore[no-any-return]


class IsOrganizationMemberGraphQL(BasePermission):  # type: ignore[misc]
    """
    Permission class to check if a user is a member of the organization
    that owns the object being accessed.
    """

    message = "User is not a member of the organization"

    def has_permission(self, source: Any, info: Info, **kwargs: Any) -> bool:
        request = info.context

        # If the user is a superuser, grant permission
        if request.user.is_superuser:
            return True

        # For queries/mutations that don't have a source yet (e.g., creating a new object)
        if source is None:
            # Check if organization_id is provided in the arguments
            organization_id = kwargs.get("organization_id")
            if organization_id:
                return OrganizationMembership.objects.filter(
                    user=request.user, organization_id=organization_id
                ).exists()
            return True  # If no organization specified, allow and check later

        # For queries/mutations that have a source (e.g., updating an existing object)
        organization = self._get_organization(source)
        if not organization:
            return False

        return OrganizationMembership.objects.filter(
            user=request.user, organization=organization
        ).exists()

    def _get_organization(self, obj: Any) -> Optional[Organization]:
        """
        Get the organization from the object.
        Override this method in subclasses for specific object types.
        """
        if hasattr(obj, "organization"):
            return obj.organization  # type: ignore[attr-defined,no-any-return]
        return None


class HasOrganizationRoleGraphQL(BasePermission):  # type: ignore[misc]
    """
    Permission class to check if a user has a specific role in the organization
    that owns the object being accessed.
    """

    message = "User does not have the required role in the organization"

    def __init__(self, operation: str = "view"):
        self.operation = operation

    def has_permission(self, source: Any, info: Info, **kwargs: Any) -> bool:
        request = info.context

        # If the user is a superuser, grant permission
        if request.user.is_superuser:
            return True

        # For queries/mutations that don't have a source yet (e.g., creating a new object)
        if source is None:
            # Check if organization_id is provided in the arguments
            organization_id = kwargs.get("organization_id")
            # Also check if organization is in the context
            organization = (
                info.context.context.get("organization")
                if hasattr(info.context, "context")
                else None
            )

            if organization_id:
                try:
                    membership = OrganizationMembership.objects.get(
                        user=request.user, organization_id=organization_id
                    )
                    role = membership.role
                    return self._check_role_permission(role)  # type: ignore[no-any-return]
                except OrganizationMembership.DoesNotExist:
                    return False
            elif organization:
                try:
                    membership = OrganizationMembership.objects.get(
                        user=request.user, organization=organization
                    )
                    role = membership.role
                    return self._check_role_permission(role)  # type: ignore[no-any-return]
                except OrganizationMembership.DoesNotExist:
                    return False

            # If we're creating something that doesn't need organization permission yet,
            # we'll check later when the specific object is accessed
            return request.user.is_authenticated  # type: ignore[no-any-return]

        # For queries/mutations that have a source (e.g., updating an existing object)
        organization = self._get_organization(source)
        if not organization:
            return False

        try:
            membership = OrganizationMembership.objects.get(
                user=request.user, organization=organization
            )
            role = membership.role
            return self._check_role_permission(role)
        except OrganizationMembership.DoesNotExist:
            return False

    def _get_organization(self, obj: Any) -> Optional[Organization]:
        """
        Get the organization from the object.
        Override this method in subclasses for specific object types.
        """
        if hasattr(obj, "organization"):
            return obj.organization  # type: ignore[attr-defined,no-any-return]
        return None

    def _check_role_permission(self, role: Role) -> bool:
        """
        Check if the role has the required permission for the operation.
        """
        if self.operation == "view":
            return role.can_view
        elif self.operation == "add":
            return role.can_add
        elif self.operation == "change":
            return role.can_change
        elif self.operation == "delete":
            return role.can_delete
        return False


# Specialized permission classes for specific models
class DatasetPermissionGraphQL(HasOrganizationRoleGraphQL):  # type: ignore[misc]
    """
    Permission class specifically for Dataset objects.
    Also checks for dataset-specific permissions.
    """

    def has_permission(self, source: Any, info: Info, **kwargs: Any) -> bool:
        # First check organization-level permissions
        if super().has_permission(source, info, **kwargs):
            return True

        # If not allowed at organization level, check dataset-specific permissions
        request = info.context

        # Check if user is authenticated before proceeding with permission checks
        if not hasattr(request, "user") or not request.user.is_authenticated:
            return False

        # For queries/mutations that don't have a source yet
        if source is None:
            dataset_id = kwargs.get("dataset_id")
            if not dataset_id:
                return False

            try:
                dataset_perm = DatasetPermission.objects.get(
                    user=request.user, dataset_id=dataset_id
                )
                role = dataset_perm.role
                return self._check_role_permission(role)
            except DatasetPermission.DoesNotExist:
                return False

        # For queries/mutations that have a source
        if hasattr(source, "id"):
            try:
                dataset_perm = DatasetPermission.objects.get(
                    user=request.user, dataset=source
                )
                role = dataset_perm.role
                return self._check_role_permission(role)
            except DatasetPermission.DoesNotExist:
                return False

        return False


class ResourcePermissionGraphQL(HasOrganizationRoleGraphQL):  # type: ignore[misc]
    """
    Permission class specifically for Resource objects.
    """

    def _get_organization(self, obj: Any) -> Optional[Organization]:
        return obj.dataset.organization if hasattr(obj, "dataset") else None  # type: ignore[attr-defined,no-any-return]
