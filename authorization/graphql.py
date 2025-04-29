from typing import Any, Dict, List, Optional, cast

import strawberry
import strawberry_django
import structlog
from strawberry.file_uploads import Upload
from strawberry.permission import BasePermission
from strawberry.types import Info

from api.models import Dataset, Organization
from api.utils.graphql_telemetry import trace_resolver
from authorization.keycloak import keycloak_manager
from authorization.models import DatasetPermission, OrganizationMembership, Role, User
from authorization.permissions import IsAuthenticated
from authorization.services import AuthorizationService
from authorization.types import TypeOrganizationMembership, TypeUser

logger = structlog.getLogger(__name__)


@strawberry.type
class RoleType:
    id: strawberry.ID
    name: str
    description: Optional[str]
    can_view: bool
    can_add: bool
    can_change: bool
    can_delete: bool


@strawberry.type
class OrganizationPermissionType:
    organization_id: strawberry.ID
    organization_name: str
    role_name: str
    can_view: bool
    can_add: bool
    can_change: bool
    can_delete: bool


@strawberry.type
class DatasetPermissionType:
    dataset_id: strawberry.ID
    dataset_title: str
    role_name: str
    can_view: bool
    can_add: bool
    can_change: bool
    can_delete: bool


@strawberry.type
class UserPermissionsType:
    organizations: List[OrganizationPermissionType]
    datasets: List[DatasetPermissionType]


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
        organization_id = kwargs.get("organization_id")
        if not organization_id:
            return False

        try:
            # Check if the user is an admin of the organization
            membership = OrganizationMembership.objects.get(
                user=info.context.user, organization_id=organization_id
            )
            return membership.role.name == "admin"
        except OrganizationMembership.DoesNotExist:
            return False


@strawberry.input
class UpdateUserInput:
    """Input for updating user details."""

    first_name: Optional[str] = None
    last_name: Optional[str] = None
    bio: Optional[str] = None
    profile_picture: Optional[Upload] = None
    email: Optional[str] = None


@strawberry.input
class AddUserToOrganizationInput:
    """Input for adding a user to an organization."""

    user_id: strawberry.ID
    organization_id: strawberry.ID
    role_id: strawberry.ID


@strawberry.type
class Query:
    @strawberry.field
    def user_permissions(self, info: Info) -> UserPermissionsType:
        """
        Get all permissions for the current user.
        """
        user = info.context.user

        # Get organization permissions
        org_memberships = OrganizationMembership.objects.filter(
            user=user
        ).select_related("organization", "role")
        organization_permissions = [
            OrganizationPermissionType(
                organization_id=str(membership.organization.id),  # type: ignore[attr-defined,arg-type]
                organization_name=membership.organization.name,  # type: ignore[attr-defined]
                role_name=membership.role.name,  # type: ignore[attr-defined]
                can_view=membership.role.can_view,  # type: ignore[attr-defined]
                can_add=membership.role.can_add,  # type: ignore[attr-defined]
                can_change=membership.role.can_change,  # type: ignore[attr-defined]
                can_delete=membership.role.can_delete,  # type: ignore[attr-defined]
            )
            for membership in org_memberships
        ]

        # Get dataset permissions
        dataset_perms = DatasetPermission.objects.filter(user=user).select_related(
            "dataset", "role"
        )
        dataset_permissions = [
            DatasetPermissionType(
                dataset_id=str(perm.dataset.id),  # type: ignore[attr-defined,arg-type]
                dataset_title=perm.dataset.title,  # type: ignore[attr-defined]
                role_name=perm.role.name,  # type: ignore[attr-defined]
                can_view=perm.role.can_view,  # type: ignore[attr-defined]
                can_add=perm.role.can_add,  # type: ignore[attr-defined]
                can_change=perm.role.can_change,  # type: ignore[attr-defined]
                can_delete=perm.role.can_delete,  # type: ignore[attr-defined]
            )
            for perm in dataset_perms
        ]

        return UserPermissionsType(
            organizations=organization_permissions, datasets=dataset_permissions
        )

    @strawberry.field
    def roles(self, info: Info) -> List[RoleType]:
        """
        Get all available roles in the system.
        """
        roles = Role.objects.all()
        return [
            RoleType(
                id=str(role.id),  # type: ignore[attr-defined,arg-type]
                name=role.name,  # type: ignore[attr-defined]
                description=role.description,  # type: ignore[attr-defined]
                can_view=role.can_view,  # type: ignore[attr-defined]
                can_add=role.can_add,  # type: ignore[attr-defined]
                can_change=role.can_change,  # type: ignore[attr-defined]
                can_delete=role.can_delete,  # type: ignore[attr-defined]
            )
            for role in roles
        ]

    @strawberry_django.field(
        permission_classes=[AllowPublicUserInfo],
    )
    @trace_resolver(name="users", attributes={"component": "user"})
    def users(self, info: Info, limit: int = 10, offset: int = 0) -> List[TypeUser]:
        """Get a list of users with basic information."""
        queryset = User.objects.all().order_by("username")[offset : offset + limit]
        return TypeUser.from_django_list(queryset)

    @strawberry_django.field(
        permission_classes=[AllowPublicUserInfo],
    )
    @trace_resolver(name="user", attributes={"component": "user"})
    def user(
        self,
        info: Info,
        id: Optional[strawberry.ID] = None,
        username: Optional[str] = None,
    ) -> Optional[TypeUser]:
        """Get a user by ID or username."""
        if id:
            try:
                user = User.objects.get(id=id)
                return TypeUser.from_django(user)
            except User.DoesNotExist:
                return None
        elif username:
            try:
                user = User.objects.get(username=username)
                return TypeUser.from_django(user)
            except User.DoesNotExist:
                return None
        return None

    @strawberry_django.field(
        permission_classes=[IsAuthenticated],
    )
    @trace_resolver(name="me", attributes={"component": "user"})
    def me(self, info: Info) -> TypeUser:
        """Get the current authenticated user."""
        return TypeUser.from_django(info.context.user)


@strawberry.input
class AssignOrganizationRoleInput:
    user_id: strawberry.ID
    organization_id: strawberry.ID
    role_name: str


@strawberry.input
class AssignDatasetPermissionInput:
    user_id: strawberry.ID
    dataset_id: strawberry.ID
    role_name: str


@strawberry.type
class Mutation:
    @strawberry_django.mutation(
        permission_classes=[IsAuthenticated],
    )
    @trace_resolver(
        name="update_user",
        attributes={"component": "user", "operation": "mutation"},
    )
    def update_user(self, info: Info, input: UpdateUserInput) -> TypeUser:
        """Update user details (synced with Keycloak)."""
        # Get the user to update - either the current user or a specific user by ID
        user = info.context.user

        # Update local user fields
        if input.first_name is not None:
            user.first_name = input.first_name
        if input.last_name is not None:
            user.last_name = input.last_name
        if input.bio is not None:
            user.bio = input.bio
        if input.email is not None:
            user.email = input.email
        if input.profile_picture is not None:
            user.profile_picture = input.profile_picture  # type: ignore[attr-defined]

        user.save()

        # Sync with Keycloak - this would need to be implemented
        # For now, we'll just log that we would sync with Keycloak

        logger.info(
            "Would sync user details with Keycloak",
            user_id=str(user.id),
            keycloak_id=user.keycloak_id,
        )

        # TODO: Implement actual Keycloak sync

        return TypeUser.from_django(user)

    @strawberry_django.mutation(
        permission_classes=[IsAuthenticated, HasOrganizationAdminRole],
    )
    @trace_resolver(
        name="add_user_to_organization",
        attributes={"component": "user", "operation": "mutation"},
    )
    def add_user_to_organization(
        self, info: Info, input: AddUserToOrganizationInput
    ) -> TypeOrganizationMembership:
        """Add a user to an organization with a specific role."""
        try:
            user = User.objects.get(id=input.user_id)
            organization = Organization.objects.get(id=input.organization_id)
            role = Role.objects.get(id=input.role_id)

            # Check if the membership already exists
            membership, created = OrganizationMembership.objects.get_or_create(
                user=user, organization=organization, defaults={"role": role}
            )

            # If the membership exists but the role is different, update it
            if not created and membership.role != role:
                membership.role = role
                membership.save()

            return TypeOrganizationMembership.from_django(membership)
        except User.DoesNotExist:
            raise ValueError(f"User with ID {input.user_id} does not exist.")
        except Organization.DoesNotExist:
            raise ValueError(
                f"Organization with ID {input.organization_id} does not exist."
            )
        except Role.DoesNotExist:
            raise ValueError(f"Role with ID {input.role_id} does not exist.")

    @strawberry.mutation
    def assign_organization_role(
        self, info: Info, input: AssignOrganizationRoleInput
    ) -> bool:
        """
        Assign a role to a user for an organization.
        """
        # Check if the current user has permission to assign roles
        current_user = info.context.user
        if not current_user.is_superuser:
            org_id = input.organization_id
            try:
                membership = OrganizationMembership.objects.get(
                    user=current_user, organization_id=org_id
                )
                if not membership.role.can_change:
                    return False
            except OrganizationMembership.DoesNotExist:
                return False

        # Assign the role
        return AuthorizationService.assign_user_to_organization(
            user_id=input.user_id,
            organization_id=input.organization_id,
            role_name=input.role_name,
        )

    @strawberry.mutation
    def assign_dataset_permission(
        self, info: Info, input: AssignDatasetPermissionInput
    ) -> bool:
        """
        Assign a permission to a user for a dataset.
        """
        # Check if the current user has permission to assign dataset permissions
        current_user = info.context.user
        if not current_user.is_superuser:
            # Get the dataset's organization
            try:
                dataset = Dataset.objects.get(id=input.dataset_id)
                organization_id = dataset.organization_id  # type: ignore[attr-defined,misc]

                # Check if the user has admin rights on the organization
                try:
                    membership = OrganizationMembership.objects.get(
                        user=current_user, organization_id=organization_id  # type: ignore[misc]
                    )
                    if not membership.role.can_change:
                        return False
                except OrganizationMembership.DoesNotExist:
                    return False
            except Dataset.DoesNotExist:
                return False

        # Assign the permission
        return AuthorizationService.assign_user_to_dataset(
            user_id=input.user_id,
            dataset_id=input.dataset_id,
            role_name=input.role_name,
        )
