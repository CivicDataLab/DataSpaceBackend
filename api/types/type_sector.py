from typing import Any, Optional

import strawberry
import strawberry_django
from django.db.models import Count, Q
from strawberry import auto

from api.models import Sector
from api.types.base_type import BaseType
from api.utils.enums import DatasetStatus


@strawberry_django.filter(Sector)
class SectorFilter:
    id: auto
    slug: auto
    name: auto

    # Filter by minimum dataset count
    min_dataset_count: Optional[int] = strawberry.field(
        default=None,
        description="Filter sectors with at least this many published datasets",
    )

    # Filter by maximum dataset count
    max_dataset_count: Optional[int] = strawberry.field(
        default=None,
        description="Filter sectors with at most this many published datasets",
    )

    def filter_min_dataset_count(self, queryset: Any, value: Optional[int]) -> Any:
        if value is None:
            return queryset
        return queryset.annotate(
            dataset_count=Count(
                "datasets", filter=Q(datasets__status=DatasetStatus.PUBLISHED)
            )
        ).filter(dataset_count__gte=value)

    def filter_max_dataset_count(self, queryset: Any, value: Optional[int]) -> Any:
        if value is None:
            return queryset
        return queryset.annotate(
            dataset_count=Count(
                "datasets", filter=Q(datasets__status=DatasetStatus.PUBLISHED)
            )
        ).filter(dataset_count__lte=value)


@strawberry_django.order(Sector)
class SectorOrder:
    name: auto

    dataset_count: Optional[strawberry.auto] = strawberry.field(
        default=None, description="Order sectors by dataset count"
    )

    def order_dataset_count(self, queryset: Any, value: Optional[str]) -> Any:
        if value is None:
            return queryset
        # Annotate queryset with dataset count
        queryset = queryset.annotate(
            dataset_count=Count(
                "datasets", filter=Q(datasets__status=DatasetStatus.PUBLISHED)
            )
        )
        # Order by dataset count
        return queryset.order_by(f"{value}dataset_count")


@strawberry_django.type(
    Sector, pagination=True, fields="__all__", filters=SectorFilter, order=SectorOrder  # type: ignore
)
class TypeSector(BaseType):
    parent_id: Optional["TypeSector"]

    @strawberry.field
    def dataset_count(self: Any) -> int:
        return int(self.datasets.filter(status=DatasetStatus.PUBLISHED).count())
