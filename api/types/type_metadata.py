import strawberry_django

from api.models import Metadata


@strawberry_django.filter(Metadata)
class MetadataFilter:
    model: str
    enabled: bool


@strawberry_django.type(Metadata, fields="__all__", filters=MetadataFilter)
class TypeMetadata:
    pass
