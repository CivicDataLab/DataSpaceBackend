import strawberry
import strawberry_django
from strawberry_django import NodeInput
from strawberry_django.mutations import mutations

from api.models import Category
from api.types.type_category import TypeCategory

from typing import Optional


@strawberry_django.input(Category, fields="__all__")
class CategoryInput:
    pass


@strawberry_django.partial(Category, fields="__all__")
class CategoryInputPartial:
    slug: Optional[str] = None


@strawberry.type(name="Query")
class Query:
    categories: list[TypeCategory] = strawberry_django.field()


@strawberry.type
class Mutation:
    create_category: TypeCategory = mutations.create(CategoryInput)
    update_category: TypeCategory = mutations.update(CategoryInputPartial, key_attr="id")
    delete_category: TypeCategory = mutations.delete(NodeInput)
