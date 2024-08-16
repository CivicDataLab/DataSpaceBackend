import strawberry_django

from api.models import ResourceChartDetails
from api.types import TypeResource


@strawberry_django.type(ResourceChartDetails, fields="__all__")
class TypeResourceChart:
    resource: TypeResource
