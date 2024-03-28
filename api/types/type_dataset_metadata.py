import strawberry_django

from api.models import DatasetMetadata


@strawberry_django.type(DatasetMetadata, fields="__all__")
class TypeDatasetMetadata:
    pass
