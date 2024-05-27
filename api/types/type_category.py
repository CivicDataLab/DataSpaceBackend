import uuid
from typing import Optional

import strawberry
import strawberry_django
from strawberry import auto

from api.models import Category


@strawberry_django.filter(Category)
class CategoryFilter:
    id: auto
    slug: auto


@strawberry_django.type(Category, pagination=True, fields="__all__", filters=CategoryFilter)
class TypeCategory:
    parent_id: Optional["TypeCategory"]
    dataset_count: int

    @strawberry.field
    def dataset_count(self:Category, info) -> int:
        return self.dataset_set.count()
