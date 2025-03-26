"""Schema definitions for organizations."""

from typing import List, Optional

import strawberry
import strawberry_django
from strawberry import auto
from strawberry.types import Info
from strawberry_django.mutations import mutations

from api.models import Organization
from api.types.type_organization import TypeOrganization


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

    organizations: list[TypeOrganization] = strawberry_django.field()

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

    @strawberry_django.mutation(handle_django_errors=True)
    def create_organization(
        self, info: Info, input: OrganizationInput
    ) -> TypeOrganization:
        """Create a new organization."""
        organization = mutations.create(OrganizationInput)(info=info, input=input)
        return TypeOrganization.from_django(organization)

    @strawberry_django.mutation(handle_django_errors=True)
    def update_organization(
        self, info: Info, input: OrganizationInputPartial
    ) -> Optional[TypeOrganization]:
        """Update an existing organization."""
        try:
            organization = mutations.update(OrganizationInputPartial, key_attr="id")(
                info=info, input=input
            )
            return TypeOrganization.from_django(organization)
        except Organization.DoesNotExist:
            raise ValueError(f"Organization with ID {input.id} does not exist.")

    @strawberry_django.mutation(handle_django_errors=False)
    def delete_organization(self, info: Info, organization_id: str) -> bool:
        """Delete an organization."""
        try:
            organization = Organization.objects.get(id=organization_id)
            organization.delete()
            return True
        except Organization.DoesNotExist:
            raise ValueError(f"Organization with ID {organization_id} does not exist.")
