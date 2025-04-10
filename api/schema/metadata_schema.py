"""Schema definitions for metadata."""

from typing import Dict, List, Optional

import strawberry
import strawberry_django
from strawberry.enum import EnumType
from strawberry.types import Info

from api.models import Metadata
from api.types.type_metadata import TypeMetadata
from api.utils.enums import (
    MetadataDataTypes,
    MetadataModels,
    MetadataStandards,
    MetadataTypes,
)

metadata_data_type: EnumType = strawberry.enum(MetadataDataTypes)
metadata_standard: EnumType = strawberry.enum(MetadataStandards)
metadata_type: EnumType = strawberry.enum(MetadataTypes)
metadata_model: EnumType = strawberry.enum(MetadataModels)


@strawberry.input
class MetadataInput:
    """Input type for metadata creation."""

    label: str
    data_standard: metadata_standard
    urn: Optional[str] = None
    data_type: metadata_data_type
    options: Optional[List[str]] = None
    validator: Optional[List[str]] = None
    validator_options: Optional[Dict[str, str]] = None
    type: Optional[metadata_type] = MetadataTypes.OPTIONAL
    model: Optional[metadata_model] = MetadataModels.DATASET
    enabled: Optional[bool] = True
    filterable: Optional[bool] = False


@strawberry_django.partial(Metadata, fields="__all__")
class MetadataInputPartial:
    """Input type for metadata updates."""

    id: str


@strawberry.type(name="Query")
class Query:
    """Queries for metadata."""

    @strawberry_django.field(pagination=True)
    def metadata_list(
        self,
        info: Info,
        first: Optional[int] = None,
        after: Optional[str] = None,
    ) -> List[TypeMetadata]:
        """Get paginated metadata list."""
        metadata_list = Metadata.objects.all()
        if first is not None:
            metadata_list = metadata_list[:first]
        if after is not None:
            metadata_list = metadata_list.filter(id__gt=after)
        return [TypeMetadata.from_django(meta) for meta in metadata_list]


@strawberry.type
class Mutation:
    """Mutations for metadata."""

    @strawberry_django.mutation(handle_django_errors=True)
    def create_metadata(self, input: MetadataInput) -> TypeMetadata:
        """Create a new metadata."""
        metadata = Metadata.objects.create(**input.__dict__)
        return TypeMetadata.from_django(metadata)

    @strawberry_django.mutation(handle_django_errors=True)
    def update_metadata(self, input: MetadataInputPartial) -> TypeMetadata:
        """Update an existing metadata."""
        try:
            metadata = Metadata.objects.get(id=input.id)
            for key, value in input.__dict__.items():
                if key == "id":
                    continue
                setattr(metadata, key, value)
            metadata.save()
            return TypeMetadata.from_django(metadata)
        except Metadata.DoesNotExist:
            raise ValueError(f"Metadata with ID {input.id} does not exist.")

    @strawberry_django.mutation(handle_django_errors=False)
    def delete_metadata(self, metadata_id: str) -> bool:
        """Delete a metadata."""
        try:
            Metadata.objects.get(id=metadata_id).delete()
            return True
        except Metadata.DoesNotExist:
            raise ValueError(f"Metadata with ID {metadata_id} does not exist.")
