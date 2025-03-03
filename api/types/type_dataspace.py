from typing import Any

import strawberry
import strawberry_django
from strawberry import auto

from api.models import DataSpace
from api.types.base_type import BaseType


@strawberry_django.filter(DataSpace)
class DataSpaceFilter:
    id: auto
    slug: auto


@strawberry_django.type(
    DataSpace, pagination=True, fields="__all__", filters=DataSpaceFilter
)
class TypeDataSpace(BaseType):

    @strawberry.field
    def dataset_count(self: Any) -> int:
        return int(self.datasets.count())
