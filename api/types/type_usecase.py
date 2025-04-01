from typing import TYPE_CHECKING, Any, List, Optional

import strawberry
import strawberry_django
from strawberry import Info, auto
from strawberry.enum import EnumType

from api.models import UseCase
from api.types.base_type import BaseType
from api.utils.enums import UseCaseStatus

if TYPE_CHECKING:
    from api.types import TypeDataset

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

    datasets: Optional[List["TypeDataset"]]

    @strawberry.field
    def dataset_count(self: "TypeUseCase", info: Info) -> int:
        """Get the count of datasets associated with this use case."""
        if not self.datasets:
            return 0
        return len(self.datasets)
