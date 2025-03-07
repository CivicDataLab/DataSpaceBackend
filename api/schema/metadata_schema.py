import uuid
from typing import List, Optional

import strawberry
import strawberry_django
from strawberry.types import Info
from strawberry_django.mutations import mutations

from api.models import Metadata
from api.types import TypeMetadata


@strawberry_django.input(Metadata, fields="__all__")
class MetadataInput:
    pass


@strawberry_django.partial(Metadata, fields="__all__")
class MetadataInputPartial:
    id: uuid.UUID


@strawberry.type(name="Query")
class Query:
    @strawberry_django.field(pagination=True)
    def metadata_list(
        self,
        info: Info,
        first: Optional[int] = None,
        after: Optional[strawberry.ID] = None,
    ) -> List[TypeMetadata]:
        """Get all metadata."""
        metadata_list = Metadata.objects.all()
        if first is not None:
            metadata_list = metadata_list[:first]
        if after is not None:
            after_id = uuid.UUID(after)
            metadata_list = metadata_list.filter(id__gt=after_id)
        return [TypeMetadata.from_django(meta) for meta in metadata_list]


@strawberry.type
class Mutation:
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
