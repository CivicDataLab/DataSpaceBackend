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

    @strawberry_django.filter_field
    def search(self, queryset: Any, value: Optional[str]) -> Any:
        # Skip filtering if no search term provided
        if value is None or value.strip() == "":
            return queryset

        # Search in name and description fields
        search_term = value.strip()
        return queryset.filter(
            Q(name__icontains=search_term) | Q(description__icontains=search_term)
        )

    @strawberry_django.filter_field
    def min_dataset_count(self, queryset: Any, value: Optional[int]) -> Any:
        # Skip filtering if no value provided
        if value is None:
            return queryset

        # Annotate queryset with dataset count
        queryset = queryset.annotate(
            _dataset_count=Count(
                "datasets",
                filter=Q(datasets__status=DatasetStatus.PUBLISHED),
                distinct=True,
            )
        )

        # Filter by minimum count
        return queryset.filter(_dataset_count__gte=value)

    @strawberry_django.filter_field
    def max_dataset_count(self, queryset: Any, value: Optional[int]) -> Any:
        # Skip filtering if no value provided
        if value is None:
            return queryset

        # Annotate queryset with dataset count
        queryset = queryset.annotate(
            _dataset_count=Count(
                "datasets",
                filter=Q(datasets__status=DatasetStatus.PUBLISHED),
                distinct=True,
            )
        )

        # Filter by maximum count
        return queryset.filter(_dataset_count__lte=value)


@strawberry_django.order(Sector)
class SectorOrder:
    name: auto

    @strawberry_django.order_field
    def dataset_count(self, queryset: Any, value: Optional[str], prefix: str) -> tuple[Any, list[str]]:  # type: ignore
        # Skip ordering if no value provided
        if value is None:
            return queryset, []

        # Annotate queryset with dataset count
        queryset = queryset.annotate(
            _dataset_count=Count(
                f"{prefix}datasets",
                filter=Q(datasets__status=DatasetStatus.PUBLISHED),
                distinct=True,
            )
        )

        # Determine ordering direction and field
        order_field = "_dataset_count"
        if value.startswith("-"):
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
