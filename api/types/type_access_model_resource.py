import strawberry_django

from api.models import AccessModelResource
from api.types import TypeResource


@strawberry_django.type(AccessModelResource, fields="__all__")
class TypeAccessModelResource:
    resource: TypeResource
