import typing
import uuid

import strawberry
import strawberry_django
from strawberry.file_uploads import Upload

from api.models import Resource, Dataset, ResourceFileDetails
from api.types import TypeResource


@strawberry.input
class CreateFileResourceInput:
    dataset: uuid.UUID
    files: typing.List[Upload]

@strawberry.input
class UpdateFileResourceInput:
    id: uuid.UUID
    file: typing.Optional[Upload] = None
    name: typing.Optional[str]
    description: typing.Optional[str]



@strawberry.type
class Mutation:

    @strawberry_django.mutation(handle_django_errors=False)
    def create_file_resources(self, file_resource_input: CreateFileResourceInput) -> list[TypeResource]:
        dataset_id = file_resource_input.dataset
        resources = []
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
            resources.append(resource)
        return resources

    @strawberry_django.mutation(handle_django_errors=True)
    def update_file_resource(self, file_resource_input: UpdateFileResourceInput) -> TypeResource:
        try:
            resource = Resource.objects.get(id=file_resource_input.id)
        except Resource.DoesNotExist as e:
            raise ValueError(f"Resource with ID {file_resource_input.id} does not exist.")
        if file_resource_input.name:
            resource.name = file_resource_input.name
        if file_resource_input.description:
            resource.description = file_resource_input.description
        resource.save()

        if file_resource_input.file:
            file_details = resource.resourcefiledetails_set[0]
            file_details.file = file_resource_input.file
            file_details.size = file_resource_input.file.size
            file_details.save()

        return resource
