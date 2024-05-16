import strawberry_django

from api.models import AccessModelResource
from api.types import TypeResource
from api.types.type_resource import TypeResourceSchema


@strawberry_django.type(AccessModelResource, fields="__all__")
class TypeAccessModelResource:
    resource: TypeResource
    fields: list[TypeResourceSchema]
