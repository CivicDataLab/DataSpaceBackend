import uuid
from typing import Any, List, Optional, TypeVar

import pandas as pd
import strawberry
import structlog
from django.db.models import QuerySet
from strawberry import auto
from strawberry.scalars import JSON
from strawberry_django import type

from api.models import (
    Resource,
    ResourceFileDetails,
    ResourceMetadata,
    ResourcePreviewDetails,
    ResourceSchema,
)
from api.types.base_type import BaseType
from api.types.type_file_details import TypeFileDetails
from api.types.type_resource_metadata import TypeResourceMetadata
from api.utils.data_indexing import get_preview_data, get_row_count
from api.utils.file_utils import load_csv

logger = structlog.get_logger(__name__)

T = TypeVar("T", bound="TypeResource")


@type(ResourceSchema, fields="__all__")
class TypeResourceSchema(BaseType):
    """Type for resource schema."""

    id: auto
    resource: auto
    field_name: auto
    format: auto
    description: auto
    created: auto
    modified: auto


@type(ResourcePreviewDetails, fields="__all__")
class TypePreviewDetails(BaseType):
    """Type for preview details."""

    pass


@strawberry.type
class PreviewData:
    """Type for preview data."""

    columns: List[str]
    rows: List[List[JSON]]


@type(Resource)
class TypeResource(BaseType):
    """Type for resource."""

    id: uuid.UUID
    dataset: auto
    created: auto
    modified: auto
    type: auto
    name: auto
    description: auto
    preview_enabled: auto
    preview_details: Optional[TypePreviewDetails]
    download_count: auto

    # @strawberry.field
    # def model_resources(self) -> List[TypeAccessModelResourceFields]:
    #     """Get access model resources for this resource.

    #     Returns:
    #         List[TypeAccessModelResourceFields]: List of access model resources
    #     """
    #     try:
    #         queryset = AccessModelResource.objects.filter(resource_id=self.id)
    #         return TypeAccessModelResourceFields.from_django_list(queryset)
    #     except (AttributeError, AccessModelResource.DoesNotExist):
    #         return []

    @strawberry.field
    def metadata(self) -> List[TypeResourceMetadata]:
        """Get metadata for this resource
        Returns:
            List[TypeResourceMetadata]: List of resource metadata
        """
        try:
            queryset: QuerySet = ResourceMetadata.objects.filter(resource__id=self.id)
            return TypeResourceMetadata.from_django_list(queryset)
        except (AttributeError, ResourceMetadata.DoesNotExist):
            return []

    # @strawberry.field
    # def access_models(self) -> List[TypeAccessModel]:
    #     """Get access models for this resource.

    #     Returns:
    #         List[TypeAccessModel]: List of access models
    #     """
    #     try:
    #         model_resources = AccessModelResource.objects.filter(resource_id=self.id)
    #         queryset: QuerySet[AccessModel] = AccessModel.objects.filter(
    #             id__in=[mr.access_model.id for mr in model_resources]  # type: ignore
    #         )
    #         return TypeAccessModel.from_django_list(queryset)
    #     except (AttributeError, AccessModel.DoesNotExist):
    #         return []

    @strawberry.field
    def file_details(self) -> Optional[TypeFileDetails]:
        """Get file details for this resource.

        Returns:
            Optional[TypeFileDetails]: File details if they exist, None otherwise
        """
        try:
            details = getattr(self, "resourcefiledetails", None)
            if details is None:
                return None
            return TypeFileDetails.from_django(details)
        except (AttributeError, ResourceFileDetails.DoesNotExist):
            return None

    @strawberry.field
    def schema(self) -> List[TypeResourceSchema]:
        """Get schema for this resource.

        Returns:
            List[TypeResourceSchema]: List of resource schema
        """
        try:
            queryset = getattr(self, "resourceschema_set", None)
            if queryset is None:
                return []
            return TypeResourceSchema.from_django_list(queryset.all())
        except (AttributeError, ResourceSchema.DoesNotExist):
            return []

    @strawberry.field
    def preview_data(self) -> Optional[PreviewData]:
        """Get preview data for the resource.

        Returns:
            Optional[PreviewData]: Preview data with columns and rows if successful, None otherwise
        """
        try:
            file_details = getattr(self, "resourcefiledetails", None)
            if not file_details or not getattr(self, "preview_details", None):
                return None
            preview_details = getattr(self, "preview_details", None)
            if (
                not getattr(self, "preview_enabled", False)
                or not file_details.format.lower() == "csv"
            ):
                return None
            return get_preview_data(self)  # type: ignore
        except (AttributeError, FileNotFoundError) as e:
            logger.error(f"Error loading preview data: {str(e)}")
            return None

    @strawberry.field
    def no_of_entries(self) -> int:
        """Get the number of entries in the resource."""
        try:
            file_details = getattr(self, "resourcefiledetails", None)
            if not file_details:
                return 0
            return get_row_count(self)  # type: ignore
        except (AttributeError, FileNotFoundError) as e:
            logger.error(f"Error getting number of entries: {str(e)}")
            return 0
