import uuid
from typing import List

import strawberry
import strawberry_django

from api.models import Dataset, DatasetMetadata, Resource, AccessModel, Tag
from api.types import TypeDatasetMetadata, TypeResource
from api.types.type_access_model import TypeAccessModel


@strawberry_django.filter(Dataset)
class DatasetFilter:
    id: uuid.UUID


@strawberry_django.type(Tag, fields="__all__")
class TypeTag:
    pass


@strawberry_django.type(Dataset, fields="__all__", filters=DatasetFilter, pagination=True)
class TypeDataset:
    metadata: List[TypeDatasetMetadata]
    resources: List["TypeResource"]
    access_models: List["TypeAccessModel"]
    tags: List[TypeTag]

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

    @strawberry.field
    def access_models(self, info) -> List[TypeAccessModel]:
        try:
            return AccessModel.objects.filter(dataset=self.id)
        except AccessModel.DoesNotExist as e:
            return []
