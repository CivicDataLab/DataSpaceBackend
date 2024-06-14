import strawberry
import strawberry_django
from strawberry import auto
from strawberry_django import NodeInput
from strawberry_django.mutations import mutations

from api.models import Organization
from api.types.type_organization import TypeOrganization

from typing import Optional


@strawberry_django.input(Organization, fields="__all__")
class OrganizationInput:
    pass


@strawberry_django.partial(Organization, fields="__all__")
class OrganizationInputPartial:
    slug: auto


@strawberry.type(name="Query")
class Query:
    organizations: list[TypeOrganization] = strawberry_django.field()


@strawberry.type
class Mutation:
    create_organization: TypeOrganization = mutations.create(OrganizationInput)
    update_organization: TypeOrganization = mutations.update(OrganizationInputPartial, key_attr="id")
    delete_organization: TypeOrganization = mutations.delete(NodeInput)
