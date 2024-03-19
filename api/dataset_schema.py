import strawberry
from asgiref.sync import sync_to_async

from api import types, models
from api.models import Dataset


@strawberry.type
class Mutation:
    # @strawberry_django.input_mutation()
    @strawberry.mutation
    def add_dataset(self) -> types.TypeDataset:
        dataset: Dataset = models.Dataset()
        # sync_to_async(dataset.save)()
        dataset.save()
        return dataset
