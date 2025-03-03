import uuid
from typing import Any, Optional

import strawberry
import strawberry_django
from strawberry import auto

from api.models import Category
from api.types.base_type import BaseType


@strawberry_django.filter(Category)
class CategoryFilter:
    id: auto
    slug: auto


@strawberry_django.type(
    Category, pagination=True, fields="__all__", filters=CategoryFilter
)
class TypeCategory(BaseType):
    parent_id: Optional["TypeCategory"]

    @strawberry.field
    def dataset_count(self: Any) -> int:
        return int(self.datasets.count())
