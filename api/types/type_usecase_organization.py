"""GraphQL type for UseCase-Organization relationship."""

from typing import Optional

import strawberry
import strawberry_django
from strawberry import auto

from api.models import UseCaseOrganizationRelationship
from api.types.base_type import BaseType
from api.types.type_organization import TypeOrganization
from api.utils.enums import OrganizationRelationshipType

# Create an enum for the relationship type
relationship_type = strawberry.enum(OrganizationRelationshipType)  # type: ignore


@strawberry_django.type(UseCaseOrganizationRelationship)
class TypeUseCaseOrganizationRelationship(BaseType):
    """GraphQL type for UseCase-Organization relationship."""

    organization: TypeOrganization
    relationship_type: relationship_type
    created_at: auto
    updated_at: auto
