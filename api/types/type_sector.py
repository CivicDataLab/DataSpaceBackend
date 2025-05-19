from enum import Enum
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


@strawberry.enum
class DatasetCountOrdering(str, Enum):
    """Ordering options for dataset count"""

    ASC = "ASC"
    DESC = "DESC"


@strawberry_django.order(Sector)
class SectorOrder:
    name: auto

    dataset_count: Optional[DatasetCountOrdering] = strawberry.field(
        default=None, description="Order sectors by dataset count"
    )

    def order_dataset_count(
        self, queryset: Any, value: Optional[DatasetCountOrdering]
    ) -> Any:
        # Skip ordering if no value provided
        if value is None:
            return queryset

        # Determine ordering direction
        reverse_order = value == DatasetCountOrdering.DESC

        # Get all sectors with their dataset counts
        sectors_with_counts = []
        for sector in queryset:
            published_count = sector.datasets.filter(
                status=DatasetStatus.PUBLISHED
            ).count()
            sectors_with_counts.append((sector.id, published_count))

        # Sort by dataset count
        sorted_sector_ids = [
            sector_id
            for sector_id, count in sorted(
                sectors_with_counts, key=lambda x: x[1], reverse=reverse_order
            )
        ]

        # If no sectors to order, return original queryset
        if not sorted_sector_ids:
            return queryset

        # Use Case/When for preserving the sorted order
        from django.db.models import Case, IntegerField, Value, When

        # Create a list of When objects for ordering
        whens = [When(id=pk, then=Value(i)) for i, pk in enumerate(sorted_sector_ids)]

        # Apply the Case/When ordering
        return (
            queryset.filter(id__in=sorted_sector_ids)
            .annotate(_order=Case(*whens, output_field=IntegerField()))
            .order_by("_order")
        )


@strawberry_django.type(
    Sector, pagination=True, fields="__all__", filters=SectorFilter, order=SectorOrder  # type: ignore
)
class TypeSector(BaseType):
    parent_id: Optional["TypeSector"]

    @strawberry.field
    def dataset_count(self: Any) -> int:
        return int(self.datasets.filter(status=DatasetStatus.PUBLISHED).count())
