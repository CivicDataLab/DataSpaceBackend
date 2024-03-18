import strawberry_django

from api.models import Dataset


@strawberry_django.type(Dataset, fields="__all__")
class TypeDataset:
    pass
