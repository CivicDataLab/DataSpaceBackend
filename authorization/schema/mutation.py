"""Mutation definitions for authorization GraphQL schema."""

from typing import Any, cast

import strawberry
import strawberry_django
import structlog
from strawberry.types import Info

from api.models import Dataset, Organization
from api.utils.graphql_telemetry import trace_resolver
from authorization.models import OrganizationMembership, Role, User
from authorization.permissions import IsAuthenticated
from authorization.schema.inputs import (
    AddUserToOrganizationInput,
    AssignDatasetPermissionInput,
    AssignOrganizationRoleInput,
    UpdateUserInput,
)
from authorization.schema.permissions import HasOrganizationAdminRole
from authorization.schema.types import SuccessResponse
from authorization.services import AuthorizationService
from authorization.types import TypeOrganizationMembership, TypeUser

logger = structlog.getLogger(__name__)


@strawberry.type
class Mutation:
    @strawberry.mutation(permission_classes=[IsAuthenticated])
    @trace_resolver(
        name="update_user", attributes={"component": "user", "operation": "mutation"}
    )
    def update_user(self, info: Info, input: UpdateUserInput) -> TypeUser:
        """Update user details and sync with Keycloak."""
        from authorization.keycloak import keycloak_manager

        user = info.context.user

        # Track if we need to sync with Keycloak
        needs_keycloak_sync = False

        # Update Django user fields
        if input.first_name is not None and input.first_name != user.first_name:
            user.first_name = input.first_name
            needs_keycloak_sync = True

        if input.last_name is not None and input.last_name != user.last_name:
            user.last_name = input.last_name
            needs_keycloak_sync = True

        if input.bio is not None:
            user.bio = input.bio

        if input.email is not None and input.email != user.email:
            user.email = input.email
            needs_keycloak_sync = True

        # Handle profile picture upload
        if input.profile_picture is not None:
            user.profile_picture = input.profile_picture

        # Save the user to the database
        user.save()

        # Sync with Keycloak if needed
        if needs_keycloak_sync and user.keycloak_id:
            logger.info(
                "Syncing user details with Keycloak",
                user_id=str(user.id),
                keycloak_id=user.keycloak_id,
            )

            # Call the Keycloak manager to update the user
            sync_success = keycloak_manager.update_user_in_keycloak(user)

            if not sync_success:
                logger.warning(
                    "Failed to sync user details with Keycloak",
                    user_id=str(user.id),
                    keycloak_id=user.keycloak_id,
                )

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
            organization = info.context.context.get("organization")
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
        except Role.DoesNotExist:
            raise ValueError(f"Role with ID {input.role_id} does not exist.")

    @strawberry.mutation
    def assign_organization_role(
        self, info: Info, input: AssignOrganizationRoleInput
    ) -> SuccessResponse:
        """
        Assign a role to a user for an organization.
        """
        # Check if the current user has permission to assign roles
        current_user = info.context.user
        organization = info.context.context.get("organization")
        if not current_user.is_superuser:
            try:
                membership = OrganizationMembership.objects.get(
                    user=current_user, organization=organization
                )
                if not membership.role.can_change:
                    return SuccessResponse(
                        success=False,
                        message="You don't have permission to assign roles in this organization",
                    )
            except OrganizationMembership.DoesNotExist:
                return SuccessResponse(
                    success=False, message="You are not a member of this organization"
                )

        # Assign the role
        result = AuthorizationService.assign_user_to_organization(
            user_id=input.user_id,
            organization=organization,
            role_name=input.role_name,
        )

        if result:
            return SuccessResponse(success=True, message="Role assigned successfully")
        else:
            return SuccessResponse(success=False, message="Failed to assign role")

    @strawberry.mutation
    def assign_dataset_permission(
        self, info: Info, input: AssignDatasetPermissionInput
    ) -> SuccessResponse:
        """
        Assign a permission to a user for a dataset.
        """

        # Check if the current user has permission to assign dataset permissions
        current_user = info.context.user
        if not current_user.is_superuser:
            # Get the dataset's organization
            try:
                dataset = Dataset.objects.get(id=input.dataset_id)
                # Cast the organization_id to avoid mypy errors
                organization_id = cast(int, dataset.organization_id)

                # Check if the user has admin rights on the organization
                try:
                    membership = OrganizationMembership.objects.get(
                        user=current_user, organization_id=organization_id
                    )
                    if not membership.role.can_change:
                        return SuccessResponse(
                            success=False,
                            message="You don't have permission to assign permissions for this dataset",
                        )
                except OrganizationMembership.DoesNotExist:
                    return SuccessResponse(
                        success=False,
                        message="You are not a member of the organization that owns this dataset",
                    )
            except Dataset.DoesNotExist:
                return SuccessResponse(success=False, message="Dataset not found")

        # Assign the permission
        result = AuthorizationService.assign_user_to_dataset(
            user_id=input.user_id,
            dataset_id=input.dataset_id,
            role_name=input.role_name,
        )

        if result:
            return SuccessResponse(
                success=True, message="Permission assigned successfully"
            )
        else:
            return SuccessResponse(success=False, message="Failed to assign permission")
