from typing import Any, Dict, List, Optional

import strawberry
from strawberry.types import Info

from api.models import Dataset, Organization
from authorization.models import DatasetPermission, OrganizationMembership, Role, User
from authorization.services import AuthorizationService


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
