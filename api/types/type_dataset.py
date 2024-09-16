import uuid
from typing import List

import strawberry
import strawberry_django

from api.models import Dataset, DatasetMetadata, Resource, AccessModel, Tag
from api.types import TypeDatasetMetadata, TypeResource
from api.types.type_access_model import TypeAccessModel
from api.types.type_category import TypeCategory


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
    categories: List[TypeCategory]
    formats: List[str]

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

    @strawberry.field
    def formats(self: Dataset, info) -> List[str]:
        return self.formats_indexing
