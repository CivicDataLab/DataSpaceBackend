import copy
import typing
import uuid

import strawberry
import strawberry_django
from strawberry.file_uploads import Upload

from api.constants import FORMAT_MAPPING
from api.file_utils import file_validation
from api.models import Resource, Dataset, ResourceFileDetails
from api.models.ResourceSchema import ResourceSchema
from api.types import TypeResource
import pandas as pd


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


@strawberry.type(name="Query")
class Query:
    @strawberry_django.field
    def dataset_resources(self, info, dataset_id: uuid.UUID) -> list[TypeResource]:
        return Resource.objects.filter(dataset_id=dataset_id)


def _validate_file_details_and_update_format(resource: Resource):
    file = resource.resourcefiledetails.file
    deep_copy_file = copy.deepcopy(resource.resourcefiledetails.file)
    mime_type = file_validation(deep_copy_file, file, FORMAT_MAPPING)
    file_format = FORMAT_MAPPING.get(mime_type.lower())
    file_obj = copy.deepcopy(file)
    supported_format = [file_format]
    if file_format.lower() == "csv":
        data = pd.read_csv(file.path, keep_default_na=False, encoding="utf8")
        cols = data.columns
        for vals in cols:
            if vals == " " or vals == "Unnamed: 1":
                supported_format = []
                break
            elif not vals.isalnum():
                supported_format.pop()
                break
    if file_format:
        resource.resourcefiledetails.format = file_format
    resource.resourcefiledetails.save()


def _create_file_resource_schema(resource: Resource):
    existing_schema = ResourceSchema.objects.filter(resource=resource)
    if existing_schema.exists():
        existing_schema.delete()
    df = pd.read_csv(resource.resourcefiledetails.file)
    schema_list = pd.io.json.build_table_schema(df, version=False)
    schema_list = schema_list.get("fields", [])
    for each in schema_list[1:]:
        schema_item = ResourceSchema(field_name=each["name"], format=each["type"], description="")
        schema_item.resource = resource
        schema_item.save()


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
            _validate_file_details_and_update_format(resource)
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

    @strawberry_django.mutation(handle_django_errors=False)
    def delete_file_resource(self, resource_id: uuid.UUID) -> bool:
        try:
            resource = Resource.objects.get(id=resource_id)
        except Resource.DoesNotExist as e:
            raise ValueError(f"Resource with ID {resource_id} does not exist.")
        if resource.resourcefiledetails:
            resource.resourcefiledetails.delete()
        resource.delete()
        return True

    @strawberry_django.mutation(handle_django_errors=True)
    def reset_file_resource_schema(self, resource_id: uuid.UUID) -> TypeResource:
        try:
            resource = Resource.objects.get(id=resource_id)
        except Resource.DoesNotExist as e:
            raise ValueError(f"Resource with ID {resource_id} does not exist.")
        # TODO: validate file vs api type for schema
        _create_file_resource_schema(resource)
        resource.save()
        return resource
