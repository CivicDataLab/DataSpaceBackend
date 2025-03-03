import strawberry_django

from api.models import DatasetMetadata
from api.types import TypeMetadata
from api.types.base_type import BaseType


@strawberry_django.type(DatasetMetadata, fields="__all__")
class TypeDatasetMetadata(BaseType):
    metadata_item: TypeMetadata
