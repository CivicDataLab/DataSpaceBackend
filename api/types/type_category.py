import uuid
from typing import Optional

import strawberry_django

from api.models import Category


@strawberry_django.filter(Category)
class CategoryFilter:
    id: uuid.UUID


@strawberry_django.type(Category, pagination=True, fields="__all__", filters=CategoryFilter)
class TypeCategory:
    parent_id: Optional["TypeCategory"]
    dataset_count: int

    def dataset_count(self:Category, info):
        return self.dataset_set.count()
