import uuid
from typing import List, Optional

import strawberry
import strawberry_django
from strawberry import auto
from strawberry.types import Info
from strawberry_django.mutations import mutations

from api.models import Category
from api.types.type_category import TypeCategory


@strawberry_django.input(Category, fields="__all__")
class CategoryInput:
    pass


@strawberry_django.partial(Category, fields="__all__")
class CategoryInputPartial:
    id: uuid.UUID
    slug: auto


@strawberry.type(name="Query")
class Query:
    categories: list[TypeCategory] = strawberry_django.field()

    @strawberry_django.field
    def category(self, info: Info, id: uuid.UUID) -> Optional[TypeCategory]:
        """Get category by ID."""
        try:
            category = Category.objects.get(id=id)
            return TypeCategory.from_django(category)
        except Category.DoesNotExist:
            raise ValueError(f"Category with ID {id} does not exist.")


@strawberry.type
class Mutation:
    @strawberry_django.mutation(handle_django_errors=True)
    def create_category(self, info: Info, input: CategoryInput) -> TypeCategory:
        """Create a new category."""
        category = mutations.create(CategoryInput)(info=info, input=input)
        return TypeCategory.from_django(category)

    @strawberry_django.mutation(handle_django_errors=True)
    def update_category(
        self, info: Info, input: CategoryInputPartial
    ) -> Optional[TypeCategory]:
        """Update an existing category."""
        try:
            category = mutations.update(CategoryInputPartial, key_attr="id")(
                info=info, input=input
            )
            return TypeCategory.from_django(category)
        except Category.DoesNotExist:
            raise ValueError(f"Category with ID {input.id} does not exist.")

    @strawberry_django.mutation(handle_django_errors=False)
    def delete_category(self, info: Info, category_id: uuid.UUID) -> bool:
        """Delete a category."""
        try:
            category = Category.objects.get(id=category_id)
            category.delete()
            return True
        except Category.DoesNotExist:
            raise ValueError(f"Category with ID {category_id} does not exist.")
