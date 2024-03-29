import strawberry_django

from api.models import DatasetMetadata
from api.types import TypeMetadata


@strawberry_django.type(DatasetMetadata, fields="__all__")
class TypeDatasetMetadata:
    metadata_item: TypeMetadata
