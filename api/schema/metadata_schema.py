"""Schema definitions for metadata."""

from typing import List, Optional

import strawberry
import strawberry_django
from strawberry.types import Info
from strawberry_django.mutations import mutations

from api.models import Metadata
from api.types.type_metadata import TypeMetadata


@strawberry_django.input(Metadata, fields="__all__")
class MetadataInput:
    """Input type for metadata creation."""

    pass


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
    def create_metadata(self, info: Info, input: MetadataInput) -> TypeMetadata:
        """Create a new metadata."""
        metadata = mutations.create(MetadataInput)(info=info, input=input)
        return TypeMetadata.from_django(metadata)

    @strawberry_django.mutation(handle_django_errors=True)
    def update_metadata(self, info: Info, input: MetadataInputPartial) -> TypeMetadata:
        """Update an existing metadata."""
        try:
            metadata = mutations.update(MetadataInputPartial)(info=info, input=input)
            return TypeMetadata.from_django(metadata)
        except Metadata.DoesNotExist:
            raise ValueError(f"Metadata with ID {input.id} does not exist.")

    @strawberry_django.mutation(handle_django_errors=False)
    def delete_metadata(self, info: Info, metadata_id: str) -> bool:
        """Delete a metadata."""
        try:
            metadata = Metadata.objects.get(id=metadata_id)
            metadata.delete()
            return True
        except Metadata.DoesNotExist:
            raise ValueError(f"Metadata with ID {metadata_id} does not exist.")
