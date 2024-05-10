import strawberry_django

from api.models import AccessModel, AccessModelResource


@strawberry_django.type(AccessModelResource, fields="__all__")
class TypeAccessModelResource:
    pass


@strawberry_django.type(AccessModel, fields="__all__")
class TypeAccessModel:
    resources: list[TypeAccessModelResource]

    def resources(self, info) -> list[TypeAccessModelResource]:
        try:
            return AccessModelResource.objects.filter(access_model=self.id)
        except AccessModelResource.DoesNotExist as e:
            return []
