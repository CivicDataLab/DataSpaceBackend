import strawberry
import strawberry_django
from strawberry_django import NodeInput
from strawberry_django.mutations import mutations

from api.models import Metadata
from api.types import TypeMetadata


@strawberry_django.input(Metadata, fields="__all__")
class MetadataInput:
    pass


@strawberry_django.partial(Metadata, fields="__all__")
class MetadataInputPartial(NodeInput):
    pass


@strawberry.type
class Mutation:
    create_metadata: TypeMetadata = mutations.create(MetadataInput)
    update_metadata: TypeMetadata = mutations.update(MetadataInputPartial)

    @strawberry_django.mutation(handle_django_errors=False)
    def delete_metadata(self, metadata_id: str) -> bool:
        try:
            metadata = Metadata.objects.get(id=metadata_id)
        except Metadata.DoesNotExist as e:
            raise ValueError(f"Metadata with ID {metadata_id} does not exist.")
        metadata.delete()
        return True
