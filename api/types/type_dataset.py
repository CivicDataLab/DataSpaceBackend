import uuid
from typing import TYPE_CHECKING, Any, List, Optional, cast

import strawberry
import strawberry_django
from strawberry.enum import EnumType
from strawberry.types import Info

from api.models import AccessModel, Dataset, DatasetMetadata, Resource, Tag
from api.types import TypeDatasetMetadata, TypeResource
from api.types.base_type import BaseType
from api.types.type_access_model import TypeAccessModel
from api.types.type_category import TypeCategory
from api.utils.enums import DatasetStatus

dataset_status: EnumType = strawberry.enum(DatasetStatus)  # type: ignore


@strawberry_django.filter(Dataset)
class DatasetFilter:
    """Filter for dataset."""

    id: Optional[uuid.UUID]
    status: Optional[dataset_status]


@strawberry_django.type(Tag, fields="__all__")
class TypeTag(BaseType):
    """Type for tag."""

    id: strawberry.auto
    name: strawberry.auto
    description: strawberry.auto
    created: strawberry.auto
    modified: strawberry.auto


@strawberry_django.order(Dataset)
class DatasetOrder:
    """Order for dataset."""

    title: strawberry.auto
    created: strawberry.auto
    modified: strawberry.auto


@strawberry_django.type(
    Dataset,
    fields="__all__",
    filters=DatasetFilter,
    pagination=True,
    order=DatasetOrder,  # type: ignore
)
class TypeDataset(BaseType):
    """Type for dataset."""

    id: uuid.UUID
    tags: List[TypeTag]
    categories: List[TypeCategory]

    @strawberry.field
    def metadata(self, info: Info) -> List[TypeDatasetMetadata]:
        """Get metadata for this dataset.

        Args:
            info: Request info

        Returns:
            List[TypeDatasetMetadata]: List of dataset metadata
        """
        try:
            queryset = DatasetMetadata.objects.filter(dataset_id=self.id)
            return TypeDatasetMetadata.from_django_list(queryset)
        except (AttributeError, DatasetMetadata.DoesNotExist):
            return []

    @strawberry.field
    def resources(self, info: Info) -> List[TypeResource]:
        """Get resources for this dataset.

        Args:
            info: Request info

        Returns:
            List[TypeResource]: List of resources
        """
        try:
            queryset = Resource.objects.filter(dataset_id=self.id)
            return TypeResource.from_django_list(queryset)
        except (AttributeError, Resource.DoesNotExist):
            return []

    @strawberry.field
    def access_models(self, info: Info) -> List[TypeAccessModel]:
        """Get access models for this dataset.

        Args:
            info: Request info

        Returns:
            List[TypeAccessModel]: List of access models
        """
        try:
            queryset = AccessModel.objects.filter(dataset_id=self.id)
            return TypeAccessModel.from_django_list(queryset)
        except (AttributeError, AccessModel.DoesNotExist):
            return []

    @strawberry.field
    def formats(self: Any) -> List[str]:
        """Get formats for this dataset.

        Returns:
            List[str]: List of formats
        """
        try:
            formats = set()
            for resource in self.resources.all():
                if (
                    hasattr(resource, "resource_file_details")
                    and resource.resource_file_details
                ):
                    format_str = str(resource.resource_file_details.format or "")
                    if format_str:
                        formats.add(format_str.lower())
            return sorted(list(formats))
        except Exception:
            return []
