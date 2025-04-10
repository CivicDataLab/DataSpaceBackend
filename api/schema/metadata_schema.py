"""Schema definitions for metadata."""

from typing import List, Optional

import strawberry
import strawberry_django
from strawberry.types import Info

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

    create_metadata: TypeMetadata = strawberry_django.mutations.create(MetadataInput)
    update_metadata: TypeMetadata = strawberry_django.mutations.update(
        MetadataInputPartial
    )
    delete_metadata: bool = strawberry_django.mutations.delete(MetadataInputPartial)
