import strawberry_django

from api.models import ResourceMetadata
from api.types import TypeMetadata


@strawberry_django.type(ResourceMetadata, fields="__all__")
class TypeResourceMetadata:
    metadata_item: TypeMetadata
