import strawberry_django

from api.models import AccessModel, AccessModelResource


@strawberry_django.type(AccessModelResource, fields="__all__")
class TypeAccessModelResource:
    pass


@strawberry_django.type(AccessModel, fields="__all__")
class TypeAccessModel:
    pass
