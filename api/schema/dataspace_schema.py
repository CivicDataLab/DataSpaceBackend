import strawberry
import strawberry_django
from strawberry import auto
from strawberry_django import NodeInput
from strawberry_django.mutations import mutations

from api.models import DataSpace
from api.types.type_dataspace import TypeDataSpace


@strawberry_django.input(DataSpace, fields="__all__")
class DataSpaceInput:
    pass


@strawberry_django.partial(DataSpace, fields="__all__")
class DataSpaceInputPartial:
    slug: auto


@strawberry.type(name="Query")
class Query:
    dataspaces: list[TypeDataSpace] = strawberry_django.field()


@strawberry.type
class Mutation:
    create_dataspace: TypeDataSpace = mutations.create(DataSpaceInput)
    update_dataspace: TypeDataSpace = mutations.update(DataSpaceInputPartial, key_attr="id")
    delete_dataspace: TypeDataSpace = mutations.delete(NodeInput)
