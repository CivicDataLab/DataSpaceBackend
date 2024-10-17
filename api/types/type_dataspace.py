import strawberry
import strawberry_django
from strawberry import auto

from api.models import DataSpace


@strawberry_django.filter(DataSpace)
class DataSpaceFilter:
    id: auto
    slug: auto


@strawberry_django.type(DataSpace, pagination=True, fields="__all__", filters=DataSpaceFilter)
class TypeDataSpace:
    dataset_count: int

    @strawberry.field
    def dataset_count(self: DataSpace, info) -> int:
        return self.dataset_set.count()
