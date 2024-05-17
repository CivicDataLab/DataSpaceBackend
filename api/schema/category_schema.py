import strawberry
import strawberry_django
from strawberry_django import NodeInput
from strawberry_django.mutations import mutations

from api.models import Category
from api.types.type_category import TypeCategory


@strawberry_django.input(Category, fields="__all__")
class CategoryInput:
    pass


@strawberry_django.partial(Category, fields="__all__")
class CategoryInputPartial(NodeInput):
    pass


@strawberry_django.type
class Query:
    categories: list[TypeCategory] = strawberry_django.field()


@strawberry.type
class Mutation:
    create_category: TypeCategory = mutations.create(CategoryInput)
    update_category: TypeCategory = mutations.update(CategoryInputPartial)
    delete_category: TypeCategory = mutations.delete(NodeInput)
