from typing import Any

import strawberry
import strawberry_django
from strawberry import auto

from api.models import Catalog
from api.types.base_type import BaseType


@strawberry_django.filter(Catalog)
class CatalogFilter:
    id: auto
    slug: auto


@strawberry_django.type(
    Catalog, pagination=True, fields="__all__", filters=CatalogFilter
)
class TypeCatalog(BaseType):

    @strawberry.field
    def dataset_count(self: Any) -> int:
        return int(self.datasets.count())
