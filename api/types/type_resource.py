import uuid
from typing import Any, List, Optional, TypeVar

import pandas as pd
import strawberry
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
from api.utils.file_utils import load_csv

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
    preview_details: TypePreviewDetails

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

            df = load_csv(file_details.file.path)
            # Convert object columns to string to ensure type safety
            object_columns = df.select_dtypes(include=["object"]).columns
            df[object_columns] = df[object_columns].astype(str)

            def convert_value(val: Any) -> Any:
                """Convert value to appropriate type for GraphQL."""
                if pd.isna(val):
                    return None
                if isinstance(val, (int, float, bool)):
                    return val
                if isinstance(val, (dict, list)):
                    return str(val)
                return str(val)

            if getattr(self.preview_details, "is_all_entries", False):
                records = [
                    [convert_value(val) for val in row] for row in df.values.tolist()
                ]
            else:
                start = getattr(self.preview_details, "start_entry", None)
                end = getattr(self.preview_details, "end_entry", None)
                records = [
                    [convert_value(val) for val in row]
                    for row in df.iloc[start:end].values.tolist()
                ]

            return PreviewData(columns=list(df.columns), rows=records)
        except (AttributeError, FileNotFoundError):
            return None
