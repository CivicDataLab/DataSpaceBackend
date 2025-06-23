from enum import Enum
from typing import Any, List, Optional, Tuple, cast

import strawberry
import strawberry_django
from django.db.models import Count, Q
from strawberry import auto
from strawberry.types import Info

from api.models import Sector
from api.types.base_type import BaseType
from api.utils.enums import DatasetStatus


@strawberry.enum
class OrderDirection(Enum):
    ASC = "ASC"
    DESC = "DESC"


@strawberry_django.filter(Sector)
class SectorFilter:
    id: auto
    slug: auto
    name: auto

    @strawberry_django.filter_field
    def search(self, value: Optional[str], prefix: str) -> Q:  # type: ignore
        # Skip filtering if no value provided
        if not value or not value.strip():
            return Q()

        # Search in name and description fields
        search_term = value.strip()
        return Q(**{f"{prefix}name__icontains": search_term}) | Q(
            **{f"{prefix}description__icontains": search_term}
        )

    @strawberry_django.filter_field
    def min_dataset_count(self, queryset: Any, value: Optional[int], prefix: str) -> tuple[Any, Q]:  # type: ignore
        # Skip filtering if no value provided
        if value is None:
            return queryset, Q()

        # Annotate queryset with dataset count
        queryset = queryset.annotate(
            _dataset_count=Count(
                "datasets",
                filter=Q(datasets__status=DatasetStatus.PUBLISHED),
                distinct=True,
            )
        )

        # Return queryset with filter
        return queryset, Q(**{f"{prefix}_dataset_count__gte": value})

    @strawberry_django.filter_field
    def max_dataset_count(self, queryset: Any, value: Optional[int], prefix: str) -> tuple[Any, Q]:  # type: ignore
        # Skip filtering if no value provided
        if value is None:
            return queryset, Q()

        # Annotate queryset with dataset count
        queryset = queryset.annotate(
            _dataset_count=Count(
                "datasets",
                filter=Q(datasets__status=DatasetStatus.PUBLISHED),
                distinct=True,
            )
        )

        # Return queryset with filter
        return queryset, Q(**{f"{prefix}_dataset_count__lte": value})


@strawberry_django.order(Sector)
class SectorOrder:
    name: auto

    @strawberry_django.order_field
    def dataset_count(self, queryset: Any, value: Optional[OrderDirection], prefix: str) -> tuple[Any, list[str]]:  # type: ignore
        # Skip ordering if no value provided
        if value is None:
            return queryset, []

        # Annotate queryset with dataset count - use prefix for proper relationship traversal
        queryset = queryset.annotate(
            _dataset_count=Count(
                f"{prefix}datasets",
                filter=Q(**{f"{prefix}datasets__status": DatasetStatus.PUBLISHED}),
                distinct=True,
            )
        )

        # Determine ordering direction based on enum value
        order_field = "_dataset_count"
        if value == OrderDirection.DESC:
            order_field = f"-{order_field}"

        # Return the annotated queryset and ordering instructions
        return queryset, [order_field]


@strawberry_django.type(
    Sector, pagination=True, fields="__all__", filters=SectorFilter, order=SectorOrder  # type: ignore
)
class TypeSector(BaseType):
    parent_id: Optional["TypeSector"]

    @strawberry.field
    def dataset_count(self: Any) -> int:
        return int(self.datasets.filter(status=DatasetStatus.PUBLISHED).count())
