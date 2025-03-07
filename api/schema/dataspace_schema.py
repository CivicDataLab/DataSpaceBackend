from typing import List, Optional

import strawberry
import strawberry_django
from strawberry import auto
from strawberry.types import Info
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
    dataspace: TypeDataSpace = strawberry_django.field()


@strawberry.type
class Mutation:
    @strawberry_django.mutation
    def create_dataspace(self, info: Info, input: DataSpaceInput) -> TypeDataSpace:
        dataspace = mutations.create(DataSpaceInput)(info=info, input=input)
        return TypeDataSpace.from_django(dataspace)

    @strawberry_django.mutation
    def update_dataspace(
        self, info: Info, input: DataSpaceInputPartial
    ) -> TypeDataSpace:
        dataspace = mutations.update(DataSpaceInputPartial, key_attr="id")(
            info=info, input=input
        )
        return TypeDataSpace.from_django(dataspace)

    @strawberry_django.mutation
    def delete_dataspace(
        self, info: Info, input: DataSpaceInputPartial
    ) -> TypeDataSpace:
        dataspace = mutations.delete(DataSpaceInputPartial, key_attr="id")(
            info=info, input=input
        )
        return TypeDataSpace.from_django(dataspace)
