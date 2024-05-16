from typing import List, Optional

import strawberry
import strawberry_django

from api.models import DatasetMetadata, ResourceMetadata, Resource, AccessModel, AccessModelResource, \
    ResourceFileDetails, ResourceSchema
from api.types import TypeResourceMetadata


@strawberry_django.type(ResourceSchema, fields="__all__")
class TypeResourceSchema:
    pass


@strawberry_django.type(AccessModelResource)
class TypeAccessModelResourceFields:
    fields: list[TypeResourceSchema]


@strawberry_django.type(ResourceFileDetails, fields="__all__")
class TypeFileDetails:
    pass


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
    file_details: Optional[TypeFileDetails]
    schema: Optional[List[TypeResourceSchema]]

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

    @strawberry.field
    def file_details(self, info) -> Optional[TypeFileDetails]:
        # try:
        return self.resourcefiledetails
        # except ResourceFileDetails.DoesNotExist as e:
        #     return None

    @strawberry.field
    def schema(self: Resource, info) -> Optional[List[TypeResourceSchema]]:
        return [a for a in self.resourceschema_set.all()]
