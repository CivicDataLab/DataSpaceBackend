import strawberry_django

from api.models import Metadata


@strawberry_django.type(Metadata, fields="__all__")
class TypeMetadata:
    pass
