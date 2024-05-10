import strawberry_django

from api.models import AccessModel, AccessModelResource
from api.types import TypeResource


@strawberry_django.type(AccessModelResource, fields="__all__")
class TypeAccessModelResource:
    resource: TypeResource


@strawberry_django.type(AccessModel, fields="__all__")
class TypeAccessModel:
    model_resources: list[TypeAccessModelResource]

    def model_resources(self, info) -> list[TypeAccessModelResource]:
        try:
            return AccessModelResource.objects.filter(access_model=self.id)
        except AccessModelResource.DoesNotExist as e:
            return []
