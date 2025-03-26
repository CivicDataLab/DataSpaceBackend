import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any, List, Optional, cast

import strawberry
import strawberry_django
from strawberry.enum import EnumType
from strawberry.types import Info

from api.models import Dataset, DatasetMetadata, Resource, Tag
from api.types.base_type import BaseType
from api.types.type_dataset_metadata import TypeDatasetMetadata
from api.types.type_organization import TypeOrganization
from api.types.type_resource import TypeResource
from api.types.type_sector import TypeSector
from api.utils.enums import DatasetStatus

dataset_status: EnumType = strawberry.enum(DatasetStatus)  # type: ignore


@strawberry_django.filter(Dataset)
class DatasetFilter:
    """Filter for dataset."""

    id: Optional[uuid.UUID]
    status: Optional[dataset_status]


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
    title: str
    description: Optional[str]
    slug: str
    status: dataset_status
    organization: "TypeOrganization"
    created: datetime
    modified: datetime
    tags: List["TypeTag"]

    @strawberry.field
    def sectors(self, info: Info) -> List["TypeSector"]:
        """Get sectors for this dataset.

        Args:
            info: Request info

        Returns:
            List[TypeSector]: List of sectors
        """
        try:
            django_instance = cast(Dataset, self)
            queryset = django_instance.sectors.all()
            return TypeSector.from_django_list(queryset)
        except (AttributeError, Dataset.DoesNotExist):
            return []

    @strawberry.field
    def metadata(self) -> List["TypeDatasetMetadata"]:
        """Get metadata for this dataset."""
        try:
            queryset = DatasetMetadata.objects.filter(dataset_id=self.id)
            return TypeDatasetMetadata.from_django_list(queryset)
        except (AttributeError, DatasetMetadata.DoesNotExist):
            return []

    @strawberry.field
    def resources(self) -> List["TypeResource"]:
        """Get resources for this dataset."""
        try:
            queryset = Resource.objects.filter(dataset_id=self.id)
            return TypeResource.from_django_list(queryset)
        except (AttributeError, Resource.DoesNotExist):
            return []

    @strawberry.field
    def formats(self: Any) -> List[str]:
        """Get formats for this dataset."""
        try:
            # Get all format values and filter out None values
            formats = Resource.objects.filter(dataset_id=self.id).values_list(
                "resourcefiledetails__format", flat=True
            )
            # Filter out None values and return as list
            return [fmt for fmt in formats if fmt is not None]
        except (AttributeError, Resource.DoesNotExist):
            return []


@strawberry_django.type(Tag, fields="__all__")
class TypeTag(BaseType):
    """Type for tag."""

    id: strawberry.auto
    value: strawberry.auto
