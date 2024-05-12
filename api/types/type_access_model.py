import strawberry
import strawberry_django

from api.models import AccessModel, AccessModelResource
from api.types.type_access_model_resource import TypeAccessModelResource


@strawberry_django.type(AccessModel, fields="__all__")
class TypeAccessModel:
    model_resources: list[TypeAccessModelResource]

    @strawberry.field
    def model_resources(self, info) -> list[TypeAccessModelResource]:
        try:
            return AccessModelResource.objects.filter(access_model=self.id)
        except AccessModelResource.DoesNotExist as e:
            return []
