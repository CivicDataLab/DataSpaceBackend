from typing import Optional

import strawberry
import strawberry_django
from strawberry import auto

from api.models import UseCase
from api.types import TypeDataset
from api.utils.enums import UseCaseStatus

use_case_status = strawberry.enum(UseCaseStatus)


@strawberry_django.filter(UseCase)
class UseCaseFilter:
    id: auto
    slug: auto
    status: Optional[use_case_status]


@strawberry_django.order(UseCase)
class UseCaseOrder:
    title: strawberry.auto
    created: strawberry.auto
    modified: strawberry.auto


@strawberry_django.type(UseCase, pagination=True, fields="__all__", filters=UseCaseFilter, order=UseCaseOrder)
class TypeUseCase:
    dataset_count: int
    datasets: Optional[list[TypeDataset]]

    @strawberry.field
    def dataset_count(self: UseCase, info) -> int:
        return self.datasets.count()
