"""Schema definitions for organizations."""

from typing import List, Optional

import strawberry
import strawberry_django
from strawberry import auto
from strawberry.types import Info
from strawberry_django.mutations import mutations

from api.models import Organization
from api.types.type_organization import TypeOrganization
from authorization.models import OrganizationMembership
from authorization.permissions import HasOrganizationRoleGraphQL as HasOrganizationRole


# Create permission classes dynamically with different operations
class ViewOrganizationPermission(HasOrganizationRole):
    def __init__(self) -> None:
        super().__init__(operation="view")


class ChangeOrganizationPermission(HasOrganizationRole):
    def __init__(self) -> None:
        super().__init__(operation="change")


class DeleteOrganizationPermission(HasOrganizationRole):
    def __init__(self) -> None:
        super().__init__(operation="delete")


from authorization.permissions import IsAuthenticated
from authorization.permissions import (
    IsOrganizationMemberGraphQL as IsOrganizationMember,
)


@strawberry_django.input(Organization, fields="__all__")
class OrganizationInput:
    """Input type for organization creation."""

    pass


@strawberry_django.partial(Organization, fields="__all__")
class OrganizationInputPartial:
    """Input type for organization updates."""

    id: str
    slug: auto


@strawberry.type(name="Query")
class Query:
    """Queries for organizations."""

    @strawberry_django.field(permission_classes=[IsAuthenticated])
    def organizations(self, info: Info) -> list[TypeOrganization]:
        """Get all organizations the user has access to."""
        user = info.context.request.user

        # If superuser, return all organizations
        if user.is_superuser:
            organizations = Organization.objects.all()
        else:
            # Get organizations the user is a member of
            user_orgs = OrganizationMembership.objects.filter(user=user).values_list(
                "organization_id", flat=True
            )
            organizations = Organization.objects.filter(id__in=user_orgs)

        return [TypeOrganization.from_django(org) for org in organizations]

    @strawberry_django.field(
        permission_classes=[IsAuthenticated, IsOrganizationMember]  # type: ignore[list-item]
    )
    def organization(self, info: Info, id: str) -> Optional[TypeOrganization]:
        """Get organization by ID."""
        try:
            organization = Organization.objects.get(id=id)

            # Check if user has permission to view this organization
            user = info.context.request.user
            if (
                not user.is_superuser
                and not OrganizationMembership.objects.filter(
                    user=user, organization=organization
                ).exists()
            ):
                raise ValueError("You don't have permission to view this organization")

            return TypeOrganization.from_django(organization)
        except Organization.DoesNotExist:
            raise ValueError(f"Organization with ID {id} does not exist.")


@strawberry.type
class Mutation:
    """Mutations for organizations."""

    @strawberry_django.mutation(
        handle_django_errors=True, permission_classes=[IsAuthenticated]
    )
    def create_organization(
        self, info: Info, input: OrganizationInput
    ) -> TypeOrganization:
        """Create a new organization."""
        # Create the organization
        organization = mutations.create(OrganizationInput)(info=info, input=input)

        # Add the current user as an admin of the organization
        OrganizationMembership.objects.create(
            user=info.context.request.user, organization=organization, role="admin"  # type: ignore[misc]
        )

        return TypeOrganization.from_django(organization)

    @strawberry_django.mutation(
        handle_django_errors=True,
        permission_classes=[IsAuthenticated, ChangeOrganizationPermission],  # type: ignore[list-item]
    )
    def update_organization(
        self, info: Info, input: OrganizationInputPartial
    ) -> Optional[TypeOrganization]:
        """Update an existing organization."""
        try:
            # Check if user has permission to update this organization
            organization = Organization.objects.get(id=input.id)
            user = info.context.request.user

            if not user.is_superuser:
                try:
                    user_org = OrganizationMembership.objects.get(
                        user=user, organization=organization
                    )
                    if user_org.role not in ["admin", "editor"]:
                        raise ValueError(
                            "You don't have permission to update this organization"
                        )
                except OrganizationMembership.DoesNotExist:
                    raise ValueError(
                        "You don't have permission to update this organization"
                    )

            # Update the organization
            organization = mutations.update(OrganizationInputPartial, key_attr="id")(
                info=info, input=input
            )
            return TypeOrganization.from_django(organization)
        except Organization.DoesNotExist:
            raise ValueError(f"Organization with ID {input.id} does not exist.")

    @strawberry_django.mutation(
        handle_django_errors=False,
        permission_classes=[IsAuthenticated, DeleteOrganizationPermission],  # type: ignore[list-item]
    )
    def delete_organization(self, info: Info, organization_id: str) -> bool:
        """Delete an organization."""
        try:
            organization = Organization.objects.get(id=organization_id)

            # Check if user has permission to delete this organization
            user = info.context.request.user
            if not user.is_superuser:
                try:
                    user_org = OrganizationMembership.objects.get(
                        user=user, organization=organization
                    )
                    if user_org.role != "admin":
                        raise ValueError(
                            "You don't have permission to delete this organization"
                        )
                except OrganizationMembership.DoesNotExist:
                    raise ValueError(
                        "You don't have permission to delete this organization"
                    )

            organization.delete()
            return True
        except Organization.DoesNotExist:
            raise ValueError(f"Organization with ID {organization_id} does not exist.")
