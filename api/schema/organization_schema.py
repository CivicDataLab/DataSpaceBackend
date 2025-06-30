"""Schema definitions for organizations."""

import logging
from typing import List, Optional

import strawberry
import strawberry_django
from strawberry.permission import BasePermission
from strawberry.types import Info

from api.models import Organization
from api.schema.extensions import TrackActivity, TrackModelActivity
from api.types.type_organization import TypeOrganization
from api.utils.graphql_utils import is_superuser
from authorization.models import OrganizationMembership, Role
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


@strawberry.type(name="Query")
class Query:
    """Queries for organizations."""

    @strawberry_django.field(permission_classes=[IsAuthenticated])
    def organizations(
        self, info: Info, slug: Optional[str] = None, id: Optional[str] = None
    ) -> List[TypeOrganization]:
        """Get all organizations the user has access to."""
        user = info.context.user
        if not user or getattr(user, "is_anonymous", True):
            logging.warning("Anonymous user or no user found in context")
            return []

        # If superuser, return all organizations
        if is_superuser(info):
            queryset = Organization.objects.all()
        else:
            # Get organizations the user is a member of
            user_orgs = OrganizationMembership.objects.filter(user=user).values_list(  # type: ignore[misc]
                "organization_id", flat=True
            )
            queryset = Organization.objects.filter(id__in=user_orgs)

        # Apply manual filtering based on parameters
        if slug is not None:
            queryset = queryset.filter(slug=slug)

        if id is not None:
            queryset = queryset.filter(id=id)

        return [TypeOrganization.from_django(org) for org in queryset]

    @strawberry_django.field(permission_classes=[IsAuthenticated])
    def all_organizations(self, info: Info) -> List[TypeOrganization]:
        """Get all organizations."""
        user = info.context.user
        if not user or getattr(user, "is_anonymous", True):
            logging.warning("Anonymous user or no user found in context")
            return []
        return [TypeOrganization.from_django(org) for org in Organization.objects.all()]

    @strawberry_django.field
    def organization(self, info: Info, id: str) -> Optional[TypeOrganization]:
        """Get organization by ID."""
        try:
            organization = Organization.objects.get(id=id)
            return TypeOrganization.from_django(organization)
        except Organization.DoesNotExist:
            raise ValueError(f"Organization with ID {id} does not exist.")


@strawberry.type
class Mutation:
    """Mutations for organizations."""

    @strawberry_django.mutation(
        handle_django_errors=True,
        permission_classes=[IsAuthenticated],
        extensions=[
            TrackModelActivity(
                verb="created",
                get_data=lambda result, **kwargs: {
                    "organization_name": result.name,
                    "organization_id": str(result.id),
                    "organization_type": result.organization_types,
                },
            )
        ],
    )
    def create_organization(
        self, info: Info, input: OrganizationInput
    ) -> TypeOrganization:
        """Create a new organization."""
        # Create the organization
        input_dict = {k: v for k, v in vars(input).items() if not k.startswith("_")}

        # Filter out any special Strawberry values like UNSET
        filtered_dict = {}
        for key, value in input_dict.items():
            if (
                key in ["id", "created", "modified", "parent", "slug"]
                or value is strawberry.UNSET
            ):
                continue
            if key == "organization_types":
                # Extract the value from the enum if it's an enum object
                if hasattr(value, "value"):
                    filtered_dict[key] = value.value
                else:
                    filtered_dict[key] = str(value)
            else:
                filtered_dict[key] = value

        # Create the organization using the filtered input dictionary
        organization = Organization.objects.create(**filtered_dict)  # type: ignore[arg-type]

        # Add the current user as an admin of the organization
        OrganizationMembership.objects.create(
            user=info.context.user, organization=organization, role=Role.objects.get(name="admin")  # type: ignore[misc]
        )

        return TypeOrganization.from_django(organization)

    @strawberry_django.mutation(
        handle_django_errors=True,
        permission_classes=[IsAuthenticated, ChangeOrganizationPermission],  # type: ignore[list-item]
        extensions=[
            TrackModelActivity(
                verb="updated",
                get_data=lambda result, **kwargs: {
                    "organization_name": result.name,
                    "organization_id": str(result.id),
                    "updated_fields": {
                        k: v
                        for k, v in vars(kwargs.get("input")).items()
                        if not k.startswith("_")
                        and v is not strawberry.UNSET
                        and k not in ["created", "modified", "id"]
                    },
                },
            )
        ],
    )
    def update_organization(
        self, info: Info, input: OrganizationInputPartial
    ) -> Optional[TypeOrganization]:
        """Update an existing organization."""
        try:
            # Get the organization to update
            organization = Organization.objects.get(id=input.id)

            # Get all fields from the input as a dictionary, excluding private attributes
            input_dict = {k: v for k, v in vars(input).items() if not k.startswith("_")}

            # Filter out any special Strawberry values like UNSET
            filtered_dict = {}
            for key, value in input_dict.items():
                if value is strawberry.UNSET or key in ["created", "modified", "id"]:
                    continue
                # Handle organization_types specially
                if key == "organization_types":
                    # Extract the value from the enum if it's an enum object
                    if hasattr(value, "value"):
                        filtered_dict[key] = value.value
                    else:
                        filtered_dict[key] = str(value)
                else:
                    filtered_dict[key] = value

            for key, value in filtered_dict.items():
                # Get parent organization
                if key == "parent" and value is not None:
                    try:
                        parent_org = Organization.objects.get(id=value)
                        setattr(organization, key, parent_org)
                    except Organization.DoesNotExist:
                        continue
                else:
                    setattr(organization, key, value)

            # Save the updated organization
            organization.save()
            return TypeOrganization.from_django(organization)
        except Organization.DoesNotExist:
            raise ValueError(f"Organization with ID {input.id} does not exist.")

    @strawberry_django.mutation(
        handle_django_errors=False,
        permission_classes=[IsAuthenticated, DeleteOrganizationPermission],  # type: ignore[list-item]
        extensions=[
            TrackActivity(
                verb="deleted",
                get_data=lambda info, organization_id, **kwargs: {
                    "organization_id": organization_id,
                },
            )
        ],
    )
    def delete_organization(self, info: Info, organization_id: str) -> bool:
        """Delete an organization."""
        try:
            organization = Organization.objects.get(id=organization_id)

            # Check if user has permission to delete this organization
            user = info.context.user
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
