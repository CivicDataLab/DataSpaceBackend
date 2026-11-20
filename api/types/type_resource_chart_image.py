# mypy: disable-error-code="valid-type"

from typing import Any, Optional

import strawberry
import strawberry_django
from django.db.models import QuerySet
from strawberry import auto
from strawberry.types import Info

from api.models import ResourceChartImage
from api.types.base_type import BaseType
from api.types.type_dataset import TypeDataset
from api.utils.dataset_access import viewable_datasets_q
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

    @classmethod
    def get_queryset(cls, queryset: QuerySet, info: Info, **kwargs: Any) -> QuerySet:
        """Only images of datasets the caller may see."""
        return queryset.filter(viewable_datasets_q(info.context.user, prefix="dataset__"))
