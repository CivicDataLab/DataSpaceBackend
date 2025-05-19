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

    def order_dataset_count(self, queryset: Any, value: Optional[str]) -> Any:
        # Skip ordering if no value provided
        if value is None:
            return queryset

        # Use annotation to add dataset_count field to queryset
        queryset = queryset.annotate(
            dataset_count=Count(
                "datasets", filter=Q(datasets__status=DatasetStatus.PUBLISHED)
            )
        )

        # Determine ordering direction
        order_field = "dataset_count"
        if value.startswith("-"):
            order_field = f"-{order_field}"

        # Return ordered queryset
        return queryset.order_by(order_field)


@strawberry_django.type(
    Sector, pagination=True, fields="__all__", filters=SectorFilter, order=SectorOrder  # type: ignore
)
class TypeSector(BaseType):
    parent_id: Optional["TypeSector"]

    @strawberry.field
    def dataset_count(self: Any) -> int:
        return int(self.datasets.filter(status=DatasetStatus.PUBLISHED).count())
