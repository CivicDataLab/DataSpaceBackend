import strawberry_django

from api.models import DatasetMetadata
from api.types.base_type import BaseType
from api.types.type_metadata import TypeMetadata


@strawberry_django.type(DatasetMetadata, fields="__all__")
class TypeDatasetMetadata(BaseType):
    metadata_item: TypeMetadata
