import logging
from typing import Any, Dict, List, Optional, Union

from django.db import transaction

from api.models import Dataset, Organization
from authorization.models import DatasetPermission, OrganizationMembership, Role, User

logger = logging.getLogger(__name__)


class AuthorizationService:
    """
    Service class for handling authorization-related operations.
    This centralizes all authorization logic in one place.
    """

    @staticmethod
    def get_user_organizations(user_id: int) -> List[Dict[str, Any]]:
        """
        Get all organizations a user belongs to with their roles.

        Args:
            user_id: The ID of the user

        Returns:
            List of dictionaries containing organization info and user's role
        """
        # Use explicit type annotation for the queryset result
        memberships = OrganizationMembership.objects.filter(user_id=user_id).select_related(
            "organization", "role"
        )  # type: ignore[attr-defined]

        logger.info(
            f"Getting organizations for user_id={user_id}, found {memberships.count()} memberships"
        )

        return [
            {
                "id": membership.organization.id,  # type: ignore[attr-defined]
                "name": membership.organization.name,  # type: ignore[attr-defined]
                "role": membership.role.name,  # type: ignore[attr-defined]
                "permissions": {
                    "can_view": membership.role.can_view,  # type: ignore[attr-defined]
                    "can_add": membership.role.can_add,  # type: ignore[attr-defined]
                    "can_change": membership.role.can_change,  # type: ignore[attr-defined]
                    "can_delete": membership.role.can_delete,  # type: ignore[attr-defined]
                },
            }
            for membership in memberships
        ]

    @staticmethod
    def get_user_datasets(user_id: int) -> List[Dict[str, Any]]:
        """
        Get all datasets a user has specific permissions for.

        Args:
            user_id: The ID of the user

        Returns:
            List of dictionaries containing dataset info and user's role
        """
        # Use explicit type annotation for the queryset result
        dataset_permissions = DatasetPermission.objects.filter(user_id=user_id).select_related(
            "dataset", "role"
        )  # type: ignore[attr-defined]
        return [
            {
                "id": perm.dataset.id,  # type: ignore[attr-defined]
                "title": perm.dataset.title,  # type: ignore[attr-defined]
                "role": perm.role.name,  # type: ignore[attr-defined]
                "permissions": {
                    "can_view": perm.role.can_view,  # type: ignore[attr-defined]
                    "can_add": perm.role.can_add,  # type: ignore[attr-defined]
                    "can_change": perm.role.can_change,  # type: ignore[attr-defined]
                    "can_delete": perm.role.can_delete,  # type: ignore[attr-defined]
                },
            }
            for perm in dataset_permissions
        ]

    @staticmethod
    def check_organization_permission(user_id: int, organization_id: int, operation: str) -> bool:
        """
        Check if a user has permission to perform an operation on an organization.

        Args:
            user_id: The ID of the user
            organization_id: The ID of the organization
            operation: The operation to check (view, add, change, delete)

        Returns:
            Boolean indicating if the user has permission
        """
        try:
            # Check if the user is a superuser
            user = User.objects.get(id=user_id)
            if user.is_superuser:
                return True

            # Check organization membership and role
            membership = OrganizationMembership.objects.get(
                user_id=user_id, organization_id=organization_id
            )

            # Check if the role has the required permission
            if operation == "view":
                return membership.role.can_view
            elif operation == "add":
                return membership.role.can_add
            elif operation == "change":
                return membership.role.can_change
            elif operation == "delete":
                return membership.role.can_delete
            return False

        except (User.DoesNotExist, OrganizationMembership.DoesNotExist):
            return False

    @staticmethod
    def check_dataset_permission(user_id: int, dataset_id: Union[int, str], operation: str) -> bool:
        """
        Check if a user has permission to perform an operation on a dataset.
        Checks both organization-level and dataset-specific permissions.

        Args:
            user_id: The ID of the user
            dataset_id: The ID of the dataset
            operation: The operation to check (view, add, change, delete)

        Returns:
            Boolean indicating if the user has permission
        """
        try:
            # Check if the user is a superuser
            user = User.objects.get(id=user_id)
            if user.is_superuser:
                return True

            # First check dataset-specific permissions
            try:
                dataset_perm = DatasetPermission.objects.get(
                    user_id=user_id, dataset_id=dataset_id  # type: ignore[arg-type,misc]
                )

                # Check if the role has the required permission
                if operation == "view":
                    return dataset_perm.role.can_view
                elif operation == "add":
                    return dataset_perm.role.can_add
                elif operation == "change":
                    return dataset_perm.role.can_change
                elif operation == "delete":
                    return dataset_perm.role.can_delete
                return False

            except DatasetPermission.DoesNotExist:
                # If no dataset-specific permission, check organization-level
                dataset = Dataset.objects.get(id=dataset_id)  # type: ignore[misc]
                return AuthorizationService.check_organization_permission(
                    user_id=user_id,
                    organization_id=dataset.organization_id,  # type: ignore[arg-type]
                    operation=operation,
                )

        except (User.DoesNotExist, Dataset.DoesNotExist):
            return False

    @staticmethod
    @transaction.atomic
    def assign_user_to_organization(
        user_id: Union[int, str],
        organization: Organization,
        role_id: Union[int, str],
    ) -> bool:
        """
        Assign a user to an organization with a specific role.

        Args:
            user_id: The ID of the user
            organization: The organization to assign the user to
            role_id: The ID of the role to assign

        Returns:
            Boolean indicating success
        """
        try:
            user = User.objects.get(id=user_id)  # type: ignore[arg-type,misc]
            role = Role.objects.get(id=role_id)

            # Create or update the membership
            OrganizationMembership.objects.update_or_create(
                user=user, organization=organization, defaults={"role": role}
            )

            return True
        except (User.DoesNotExist, Role.DoesNotExist) as e:
            logger.error(f"Error assigning user to organization: {e}")
            return False

    @staticmethod
    @transaction.atomic
    def assign_user_to_dataset(
        user_id: Union[int, str], dataset_id: Union[int, str], role_id: Union[int, str]
    ) -> bool:
        """
        Assign a user to a dataset with a specific role.

        Args:
            user_id: The ID of the user
            dataset_id: The ID of the dataset
            role_id: The ID of the role to assign

        Returns:
            Boolean indicating success
        """
        try:
            user = User.objects.get(id=user_id)  # type: ignore[arg-type,misc]
            dataset = Dataset.objects.get(id=dataset_id)  # type: ignore[arg-type,misc]
            role = Role.objects.get(id=role_id)

            # Create or update the dataset permission
            DatasetPermission.objects.update_or_create(
                user=user, dataset=dataset, defaults={"role": role}
            )

            return True
        except (User.DoesNotExist, Dataset.DoesNotExist, Role.DoesNotExist) as e:
            logger.error(f"Error assigning user to dataset: {e}")
            return False


# Keycloak integration has been moved to keycloak.py
