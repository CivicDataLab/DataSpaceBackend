import strawberry_django
from strawberry import auto

from api.models import ResourceChartImage


@strawberry_django.filter(ResourceChartImage)
class ResourceChartImageFilter:
    id: auto
    name: auto


@strawberry_django.type(ResourceChartImage, pagination=True, fields="__all__", filters=ResourceChartImageFilter)
class TypeResourceChartImage:
    pass
