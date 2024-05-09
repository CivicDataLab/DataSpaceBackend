from typing import List

import strawberry
import strawberry_django

from api.models import DatasetMetadata, ResourceMetadata, Resource
from api.types import TypeResourceMetadata


@strawberry_django.type(Resource, fields="__all__")
class TypeResource:
    metadata: List[TypeResourceMetadata]

    @strawberry.field
    def metadata(self, info) -> List[TypeResourceMetadata]:
        try:
            return ResourceMetadata.objects.filter(resource=self.id)
        except DatasetMetadata.DoesNotExist as e:
            return []
