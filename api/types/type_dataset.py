import uuid
from typing import List

import strawberry
import strawberry_django

from api.models import Dataset, DatasetMetadata, Resource
from api.types import TypeDatasetMetadata, TypeResource


@strawberry_django.filter(Dataset)
class DatasetFilter:
    id: uuid.UUID


@strawberry_django.type(Dataset, fields="__all__", filters=DatasetFilter)
class TypeDataset:
    metadata: List[TypeDatasetMetadata]
    resources: List["TypeResource"]
    tags: List[str]

    @strawberry.field
    def metadata(self, info) -> List[TypeDatasetMetadata]:
        try:
            return DatasetMetadata.objects.filter(dataset=self.id)
        except DatasetMetadata.DoesNotExist as e:
            return []
    @strawberry.field
    def resources(self, info) -> List[TypeResource]:
        try:
            return Resource.objects.filter(dataset=self.id)
        except Resource.DoesNotExist as e:
            return []
