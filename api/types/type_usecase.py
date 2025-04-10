from typing import TYPE_CHECKING, List, Optional

import strawberry
import strawberry_django
from strawberry import Info, auto
from strawberry.enum import EnumType

from api.models import Organization, UseCase
from api.types.base_type import BaseType
from api.types.type_dataset import TypeDataset
from api.types.type_organization import TypeOrganization
from api.utils.enums import UseCaseStatus

use_case_status: EnumType = strawberry.enum(UseCaseStatus)


@strawberry_django.filter(UseCase)
class UseCaseFilter:
    """Filter class for UseCase model."""

    id: auto
    slug: auto
    status: Optional[use_case_status]


@strawberry_django.order(UseCase)
class UseCaseOrder:
    """Order class for UseCase model."""

    title: auto
    created: auto
    modified: auto


@strawberry_django.type(
    UseCase,
    pagination=True,
    fields="__all__",
    filters=UseCaseFilter,
    order=UseCaseOrder,  # type:ignore
)
class TypeUseCase(BaseType):
    """GraphQL type for UseCase model."""

    @strawberry.field
    def datasets(self) -> Optional[List["TypeDataset"]]:
        """Get datasets associated with this use case."""
        try:
            # Return raw Django objects and let Strawberry handle conversion
            queryset = self.datasets.all()  # type: ignore
            if not queryset.exists():
                return []
            return TypeDataset.from_django_list(queryset)
        except Exception:
            return []

    @strawberry.field
    def dataset_count(self: "TypeUseCase", info: Info) -> int:
        """Get the count of datasets associated with this use case."""
        try:
            return self.datasets.count()  # type: ignore
        except Exception:
            return 0

    @strawberry.field
    def publishers(self) -> Optional[List["TypeOrganization"]]:
        """Get publishers associated with this use case."""
        try:
            queryset = Organization.objects.filter(datasets__in=self.datasets.all()).distinct()  # type: ignore
            if not queryset.exists():
                return []
            return TypeOrganization.from_django_list(queryset)
        except Exception:
            return []
