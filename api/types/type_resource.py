from typing import List, Optional, TypeVar

import strawberry
from django.db.models import QuerySet
from strawberry import auto
from strawberry_django import type

from api.models import (
    AccessModel,
    AccessModelResource,
    Resource,
    ResourceFileDetails,
    ResourceMetadata,
    ResourceSchema,
)
from api.types import TypeResourceMetadata
from api.types.base_type import BaseType
from api.types.type_access_model import TypeAccessModel, TypeAccessModelResourceFields
from api.types.type_file_details import TypeFileDetails

T = TypeVar("T", bound="TypeResource")


@type(ResourceSchema, fields="__all__")
class TypeResourceSchema(BaseType):
    """Type for resource schema."""

    id: auto
    resource: auto
    column_name: auto
    column_type: auto
    description: auto
    created: auto
    modified: auto


@type(Resource)
class TypeResource(BaseType):
    """Type for resource."""

    id: auto
    dataset: auto
    created: auto
    modified: auto
    type: auto
    name: auto
    description: auto
    preview_enabled: auto
    preview_details: auto

    @strawberry.field
    def model_resources(self) -> List[TypeAccessModelResourceFields]:
        """Get access model resources for this resource.

        Returns:
            List[TypeAccessModelResourceFields]: List of access model resources
        """
        try:
            queryset = AccessModelResource.objects.filter(resource_id=self.id)
            return TypeAccessModelResourceFields.from_django_list(queryset)
        except (AttributeError, AccessModelResource.DoesNotExist):
            return []

    @strawberry.field
    def metadata(self) -> List[TypeResourceMetadata]:
        """Get metadata for this resource
        Returns:
            List[TypeResourceMetadata]: List of resource metadata
        """
        try:
            queryset: QuerySet = ResourceMetadata.objects.filter(resource_id=self.id)
            return TypeResourceMetadata.from_django_list(queryset)
        except (AttributeError, ResourceMetadata.DoesNotExist):
            return []

    @strawberry.field
    def access_models(self) -> List[TypeAccessModel]:
        """Get access models for this resource.

        Returns:
            List[TypeAccessModel]: List of access models
        """
        try:
            model_resources = AccessModelResource.objects.filter(resource_id=self.id)
            queryset: QuerySet[AccessModel] = AccessModel.objects.filter(
                id__in=[mr.access_model.id for mr in model_resources]  # type: ignore
            )
            return TypeAccessModel.from_django_list(queryset)
        except (AttributeError, AccessModel.DoesNotExist):
            return []

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
