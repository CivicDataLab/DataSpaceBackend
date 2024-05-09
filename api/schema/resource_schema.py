import typing
import uuid

import strawberry
import strawberry_django
from strawberry.file_uploads import Upload

from api.models import Resource, Dataset, ResourceFileDetails


@strawberry.input
class CreateFileResourceInput:
    dataset: uuid.UUID
    files: typing.List[Upload]


@strawberry.type
class Mutation:

    @strawberry_django.mutation(handle_django_errors=False)
    def create_file_resources(self, file_resource_input: CreateFileResourceInput) -> bool:
        dataset_id = file_resource_input.dataset
        # resources = []
        try:
            dataset = Dataset.objects.get(id=dataset_id)
        except Dataset.DoesNotExist as e:
            raise ValueError(f"Dataset with ID {dataset_id} does not exist.")
        for file in file_resource_input.files:
            resource = Resource()
            resource.name = file.name
            resource.dataset = dataset
            resource.save()
            file_details = ResourceFileDetails()
            file_details.file = file
            file_details.size = file.size
            file_details.resource = resource
            file_details.save()
            # resources.append(resource)
        return True
