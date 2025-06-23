from typing import Optional

import strawberry
import strawberry_django
from strawberry import auto

from api.models import ResourceChartImage
from api.types.base_type import BaseType
from api.types.type_dataset import TypeDataset
from api.utils.enums import ChartStatus


@strawberry_django.filter(ResourceChartImage)
class ResourceChartImageFilter:
    id: auto
    name: auto


ChartStatusEnum = strawberry.enum(ChartStatus)  # type: ignore


@strawberry_django.type(
    ResourceChartImage,
    pagination=True,
    fields="__all__",
    filters=ResourceChartImageFilter,
)
class TypeResourceChartImage(BaseType):
    modified: auto
    description: Optional[str] = ""
    dataset: Optional[TypeDataset] = None
    status: ChartStatusEnum = ChartStatusEnum.DRAFT
