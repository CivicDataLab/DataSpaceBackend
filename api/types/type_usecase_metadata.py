import strawberry_django

from api.models import UseCaseMetadata
from api.types.base_type import BaseType
from api.types.type_metadata import TypeMetadata


@strawberry_django.type(UseCaseMetadata, fields="__all__")
class TypeUseCaseMetadata(BaseType):
    metadata_item: TypeMetadata
