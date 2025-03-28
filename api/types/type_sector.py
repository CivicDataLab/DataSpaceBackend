from typing import Any, List, Optional, Tuple, cast

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

    @strawberry_django.filter_field
    def filter_min_dataset_count(
        self, info: Info, queryset: Any, value: int, prefix: str
    ) -> Tuple[Any, Q]:
        # Annotate the queryset with dataset count
        queryset = queryset.annotate(
            dataset_count=Count(
                f"{prefix}datasets", filter=Q(datasets__status=DatasetStatus.PUBLISHED)
            )
        )

        # Return the queryset and filter condition
        return queryset, Q(dataset_count__gte=value)

    @strawberry_django.filter_field
    def filter_max_dataset_count(
        self, info: Info, queryset: Any, value: int, prefix: str
    ) -> Tuple[Any, Q]:
        # Annotate the queryset with dataset count
        queryset = queryset.annotate(
            dataset_count=Count(
                f"{prefix}datasets", filter=Q(datasets__status=DatasetStatus.PUBLISHED)
            )
        )

        # Return the queryset and filter condition
        return queryset, Q(dataset_count__lte=value)


@strawberry_django.order(Sector)
class SectorOrder:
    name: auto

    dataset_count: Optional[strawberry_django.Ordering] = strawberry.field(
        default=None, description="Order sectors by dataset count"
    )

    @strawberry_django.order_field
    def order_dataset_count(
        self,
        info: Info,
        queryset: Any,
        value: Any,
        prefix: str,
    ) -> Tuple[Any, List[str]]:
        # Annotate queryset with dataset count
        queryset = queryset.annotate(
            dataset_count=Count(
                f"{prefix}datasets", filter=Q(datasets__status=DatasetStatus.PUBLISHED)
            )
        )

        # Get the ordering string
        order_direction = "-" if str(value).startswith("DESC") else ""
        ordering = f"{order_direction}dataset_count"

        # Return the queryset and ordering fields
        return queryset, [ordering]


@strawberry_django.type(
    Sector, pagination=True, fields="__all__", filters=SectorFilter, order=SectorOrder  # type: ignore
)
class TypeSector(BaseType):
    parent_id: Optional["TypeSector"]

    @strawberry.field
    def dataset_count(self: Any) -> int:
        return int(self.datasets.filter(status=DatasetStatus.PUBLISHED).count())
