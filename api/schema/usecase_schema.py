import strawberry
import strawberry_django
from strawberry import auto
from strawberry_django import NodeInput
from strawberry_django.mutations import mutations

from api.models import UseCase
from api.types.type_usecase import TypeUseCase


@strawberry_django.input(UseCase, fields="__all__", exclude=["datasets"])
class UseCaseInput:
    pass


@strawberry_django.partial(UseCase, fields="__all__", exclude=["datasets"])
class UseCaseInputPartial:
    slug: auto


@strawberry.type(name="Query")
class Query:
    use_cases: list[TypeUseCase] = strawberry_django.field()


@strawberry.type
class Mutation:
    create_use_case: TypeUseCase = mutations.create(UseCaseInput)
    update_use_case: TypeUseCase = mutations.update(UseCaseInputPartial, key_attr="id")
    delete_use_case: TypeUseCase = mutations.delete(NodeInput)

