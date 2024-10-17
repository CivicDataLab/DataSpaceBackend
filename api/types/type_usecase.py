from typing import Optional

import strawberry
import strawberry_django
from strawberry import auto

from api.models import UseCase
from api.types import TypeDataset


@strawberry_django.filter(UseCase)
class UseCaseFilter:
    id: auto
    slug: auto


@strawberry_django.type(UseCase, pagination=True, fields="__all__", filters=UseCaseFilter)
class TypeUseCase:
    dataset_count: int
    datasets: Optional[list[TypeDataset]]

    @strawberry.field
    def dataset_count(self: UseCase, info) -> int:
        return self.datasets.count()
