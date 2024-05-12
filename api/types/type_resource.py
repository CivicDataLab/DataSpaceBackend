import uuid
from typing import List

import strawberry
import strawberry_django

from api.models import DatasetMetadata, ResourceMetadata, Resource, AccessModel, AccessModelResource
from api.types import TypeResourceMetadata
# from api.types.type_access_model import TypeAccessModel
# from api.types.type_access_model_resource import TypeAccessModelResource


@strawberry_django.type(AccessModelResource)
class TypeAccessModelResourceFields:
    fields: list[uuid.UUID]

    @strawberry.field
    def fields(self, info):
        return []


@strawberry_django.type(AccessModel, fields="__all__")
class TypeResourceAccessModel:
    model_resources: list[TypeAccessModelResourceFields]

    @strawberry.field
    def model_resources(self, info) -> list[TypeAccessModelResourceFields]:
        try:
            return AccessModelResource.objects.filter(access_model=self.id)
        except AccessModelResource.DoesNotExist as e:
            return []


@strawberry_django.type(Resource, fields="__all__")
class TypeResource:
    metadata: List[TypeResourceMetadata]
    access_models: List[TypeResourceAccessModel]

    @strawberry.field
    def metadata(self, info) -> List[TypeResourceMetadata]:
        try:
            return ResourceMetadata.objects.filter(resource=self.id)
        except DatasetMetadata.DoesNotExist as e:
            return []

    @strawberry.field
    def access_models(self, info) -> List[TypeResourceAccessModel]:
        access_model_resources = AccessModelResource.objects.filter(resource=self.id).all()
        access_models = AccessModel.objects.filter(id__in=[x.access_model.id for x in access_model_resources]).all()
        return access_models
