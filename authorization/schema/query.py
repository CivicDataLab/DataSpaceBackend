"""Query definitions for authorization GraphQL schema."""

from typing import Dict, List, Optional, cast

import strawberry
import strawberry_django
import structlog
from django.db import models
from strawberry.types import Info

from api.utils.graphql_telemetry import trace_resolver
from authorization.models import DatasetPermission, OrganizationMembership, Role, User
from authorization.permissions import IsAuthenticated
from authorization.schema.types import (
    DatasetPermissionType,
    OrganizationPermissionType,
    RoleType,
    UserPermissionsType,
)
from authorization.types import TypeUser

logger = structlog.getLogger(__name__)


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
        organization_permissions = []

        for membership in org_memberships:
            # Type ignore is needed because mypy doesn't understand Django's select_related
            org = membership.organization  # type: ignore
            role = membership.role  # type: ignore
            organization_permissions.append(
                OrganizationPermissionType(
                    organization_id=strawberry.ID(str(org.id)),
                    organization_name=org.name,
                    role_name=role.name,
                    can_view=role.can_view,
                    can_add=role.can_add,
                    can_change=role.can_change,
                    can_delete=role.can_delete,
                )
            )

        # Get dataset permissions
        dataset_permissions = DatasetPermission.objects.filter(
            user=user
        ).select_related("dataset", "role")
        dataset_permission_types = []

        for permission in dataset_permissions:
            # Type ignore is needed because mypy doesn't understand Django's select_related
            dataset = permission.dataset  # type: ignore
            role = permission.role  # type: ignore
            dataset_permission_types.append(
                DatasetPermissionType(
                    dataset_id=strawberry.ID(str(dataset.id)),
                    dataset_title=dataset.title,
                    role_name=role.name,
                    can_view=role.can_view,
                    can_add=role.can_add,
                    can_change=role.can_change,
                    can_delete=role.can_delete,
                )
            )

        return UserPermissionsType(
            organizations=organization_permissions, datasets=dataset_permission_types
        )

    @strawberry.field
    def roles(self, info: Info) -> List[RoleType]:
        """
        Get all available roles in the system.
        """
        roles = Role.objects.all()
        result = []

        for role in roles:
            # Add type ignores for mypy since it doesn't understand Django model attributes
            # This aligns with the preference for runtime execution over strict type checking
            role_id = cast(int, role.id)  # type: ignore
            result.append(
                RoleType(
                    id=strawberry.ID(str(role_id)),
                    name=role.name,  # type: ignore
                    description=role.description,  # type: ignore
                    can_view=role.can_view,  # type: ignore
                    can_add=role.can_add,  # type: ignore
                    can_change=role.can_change,  # type: ignore
                    can_delete=role.can_delete,  # type: ignore
                )
            )
        return result

    @strawberry.field
    def user_by_organization(self, info: Info) -> List[TypeUser]:
        """Get a list of users with basic information."""
        organization = info.context.context.get("organization")
        if not organization:
            return []

        # Get users belonging to this organization
        users = User.objects.filter(
            organizationmembership__organization=organization
        ).distinct()

        # Get all memberships for these users in the current organization
        memberships = OrganizationMembership.objects.filter(
            user__in=users, organization=organization
        )

        # Create a mapping of user_id to memberships
        user_memberships: Dict[str, List[OrganizationMembership]] = {}

        for membership in memberships:
            user_id = str(membership.user_id)  # type: ignore
            if user_id not in user_memberships:
                user_memberships[user_id] = []
            user_memberships[user_id].append(membership)

        # Attach the filtered memberships to each user
        for user in users:
            # Cast to satisfy mypy
            user_id = str(user.id)  # type: ignore
            # Use setattr to avoid attribute error
            setattr(user, "current_org_memberships", user_memberships.get(user_id, []))

        return TypeUser.from_django_list(users)

    @strawberry.field
    def users(self, info: Info, limit: int = 10, offset: int = 0) -> List[TypeUser]:
        """Get a list of users with basic information."""
        users = User.objects.all()[offset : offset + limit]
        return TypeUser.from_django_list(users)

    @strawberry.field
    def user(
        self,
        info: Info,
        id: Optional[strawberry.ID] = None,
        username: Optional[str] = None,
    ) -> Optional[TypeUser]:
        """Get a user by ID or username."""
        if id is not None:
            try:
                user = User.objects.get(id=id)
                return TypeUser.from_django(user)
            except User.DoesNotExist:
                return None
        elif username is not None:
            try:
                user = User.objects.get(username=username)
                return TypeUser.from_django(user)
            except User.DoesNotExist:
                return None
        return None

    @strawberry.field(permission_classes=[IsAuthenticated])
    def me(self, info: Info) -> TypeUser:
        """Get the current authenticated user."""
        return TypeUser.from_django(info.context.user)

    @strawberry_django.field
    @trace_resolver(name="search_users", attributes={"component": "user"})
    def search_users(
        self, info: Info, search_term: str, limit: Optional[int] = 10
    ) -> List[TypeUser]:
        """Search for users by username, first name, last name, or email."""
        if not search_term or len(search_term.strip()) < 2:
            return []

        search_term = search_term.strip()
        queryset = User.objects.filter(
            models.Q(username__icontains=search_term)
            | models.Q(first_name__icontains=search_term)
            | models.Q(last_name__icontains=search_term)
            | models.Q(email__icontains=search_term)
        ).distinct()[:limit]

        return TypeUser.from_django_list(queryset)
