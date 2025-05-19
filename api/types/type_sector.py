from typing import Any, List, Optional, Tuple

import strawberry
import strawberry_django
from django.db.models import Count, Q
from strawberry import auto
from strawberry.types import Info

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
        # Skip filtering if no value provided
        if value is None:
            return queryset

        # Get IDs of sectors with at least 'value' datasets
        sector_ids = []
        for sector in queryset:
            published_count = sector.datasets.filter(
                status=DatasetStatus.PUBLISHED
            ).count()
            if published_count >= value:
                sector_ids.append(sector.id)

        # Return filtered queryset
        return queryset.filter(id__in=sector_ids)

    def filter_max_dataset_count(self, queryset: Any, value: Optional[int]) -> Any:
        # Skip filtering if no value provided
        if value is None:
            return queryset

        # Get IDs of sectors with at most 'value' datasets
        sector_ids = []
        for sector in queryset:
            published_count = sector.datasets.filter(
                status=DatasetStatus.PUBLISHED
            ).count()
            if published_count <= value:
                sector_ids.append(sector.id)

        # Return filtered queryset
        return queryset.filter(id__in=sector_ids)


@strawberry_django.order(Sector)
class SectorOrder:
    name: auto

    dataset_count: Optional[strawberry_django.Ordering] = strawberry.field(
        default=None, description="Order sectors by dataset count"
    )

    @strawberry_django.order_field
    def order_dataset_count(
        self,
        queryset: Any,
        value: strawberry_django.Ordering,
        prefix: str,
    ) -> tuple[Any, list[str]]:
        # Annotate queryset with dataset count
        queryset = queryset.annotate(
            _dataset_count=Count(
                f"{prefix}datasets",
                filter=Q(datasets__status=DatasetStatus.PUBLISHED),
                distinct=True,
            )
        )

        # Determine ordering direction based on the value
        order_field = f"{prefix}_dataset_count"
        if value == strawberry_django.Ordering.DESC:
            order_field = f"-{order_field}"

        # Return the annotated queryset and ordering instructions as strings
        return queryset, [order_field]


@strawberry_django.type(
    Sector, pagination=True, fields="__all__", filters=SectorFilter, order=SectorOrder  # type: ignore
)
class TypeSector(BaseType):
    parent_id: Optional["TypeSector"]

    @strawberry.field
    def dataset_count(self: Any) -> int:
        return int(self.datasets.filter(status=DatasetStatus.PUBLISHED).count())
