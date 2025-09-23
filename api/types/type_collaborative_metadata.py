import strawberry_django

from api.models import CollaborativeMetadata
from api.types.base_type import BaseType
from api.types.type_metadata import TypeMetadata


@strawberry_django.type(CollaborativeMetadata, fields="__all__")
class TypeCollaborativeMetadata(BaseType):
    metadata_item: TypeMetadata
