import strawberry
import strawberry_django
from asgiref.sync import sync_to_async

from api import types, models


@strawberry.type
class Mutation:
    # @strawberry_django.input_mutation()
    @strawberry.mutation
    async def add_dataset(self) -> types.TypeDataset:
        dataset = models.Dataset()
        sync_to_async(dataset.save)()
        return dataset
