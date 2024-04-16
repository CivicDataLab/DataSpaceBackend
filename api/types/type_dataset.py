from typing import List

import strawberry
import strawberry_django

from api.models import Dataset, DatasetMetadata
from api.types import TypeDatasetMetadata


@strawberry_django.type(Dataset, fields="__all__")
class TypeDataset:
    metadata: List[TypeDatasetMetadata]
    tags: List[str]
    @strawberry.field
    def metadata(self, info) -> List[TypeDatasetMetadata]:
        try:
            return DatasetMetadata.objects.filter(dataset=self.id)
        except DatasetMetadata.DoesNotExist as e:
            return []
