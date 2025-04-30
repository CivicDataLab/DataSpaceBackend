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
        """Update user details (synced with Keycloak)."""
        user = info.context.user

        # Update Django user fields
        if input.first_name is not None:
            user.first_name = input.first_name
        if input.last_name is not None:
            user.last_name = input.last_name
        if input.bio is not None:
            user.bio = input.bio
        if input.email is not None and input.email != user.email:
            # Email changes should be synced with Keycloak
            # This is a placeholder for the actual implementation
            user.email = input.email

        # Handle profile picture upload
        if input.profile_picture is not None:
            # Save the uploaded file
            user.profile_picture = input.profile_picture

        user.save()

        # Log the update for debugging
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
                # Cast the organization_id to avoid mypy errors
                organization_id = cast(int, dataset.organization_id)

                # Check if the user has admin rights on the organization
                try:
                    membership = OrganizationMembership.objects.get(
                        user=current_user, organization_id=organization_id
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
