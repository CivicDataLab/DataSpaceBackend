import copy
import typing
import uuid
from enum import Enum

import pandas as pd
import strawberry
import strawberry_django
from strawberry.file_uploads import Upload

from api.utils.constants import FORMAT_MAPPING
from api.utils.file_utils import file_validation
from api.models import Resource, Dataset, ResourceFileDetails, ResourcePreviewDetails
from api.models.ResourceSchema import ResourceSchema
from api.types import TypeResource


@strawberry.input
class CreateFileResourceInput:
    dataset: uuid.UUID
    files: typing.List[Upload]


@strawberry.input
class CreateEmptyFileResourceInput:
    dataset: uuid.UUID


@strawberry.input
class PreviewDetails:
    is_all_entries: typing.Optional[bool] = True
    start_entry: typing.Optional[int] = 0
    end_entry: typing.Optional[int] = 10


@strawberry.input
class UpdateFileResourceInput:
    id: uuid.UUID
    file: typing.Optional[Upload] = None
    name: typing.Optional[str] = None
    description: typing.Optional[str] = None
    preview_enabled: typing.Optional[bool] = False
    preview_details: typing.Optional[PreviewDetails] = None


# TODO extract strawberry enum from django text choices
@strawberry.enum
class FieldType(Enum):
    STRING = "STRING"
    NUMBER = "NUMBER"
    INTEGER = "INTEGER"
    DATE = "DATE"


@strawberry.input
class SchemaUpdate:
    id: str
    description: str
    format: FieldType


@strawberry.input
class SchemaUpdateInput:
    resource: uuid.UUID
    updates: list[SchemaUpdate]


@strawberry.type(name="Query")
class Query:
    @strawberry_django.field
    def dataset_resources(self, info, dataset_id: uuid.UUID) -> list[TypeResource]:
        return Resource.objects.filter(dataset_id=dataset_id)


def _validate_file_details_and_update_format(resource: Resource):
    file = resource.resourcefiledetails.file
    deep_copy_file = copy.deepcopy(resource.resourcefiledetails.file)
    mime_type = file_validation(deep_copy_file, file, FORMAT_MAPPING)
    if not mime_type:
        raise ValueError("Unsupported file format.")
    file_format = FORMAT_MAPPING.get(mime_type.lower())
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
        schema_item = ResourceSchema(field_name=each["name"], format=str(each["type"]).upper(), description="")
        schema_item.resource = resource
        schema_item.save()


def _update_file_resource_schema(resource: Resource, updated_schema: list[SchemaUpdate]):
    existing_schema = ResourceSchema.objects.filter(resource=resource)
    for schema in existing_schema:
        try:
            schema_change = next(item for item in updated_schema if item.id == str(schema.id))
            schema.description = schema_change.description
            schema.format = schema_change.format.value
            schema.save()
        except KeyError:
            pass


def _update_resource_preview_details(file_resource_input, resource):
    if resource.preview_details:
        resource.preview_details.delete()
    preview_details = ResourcePreviewDetails(is_all_entries=file_resource_input.preview_details.is_all_entries,
                                             start_entry=file_resource_input.preview_details.start_entry,
                                             end_entry=file_resource_input.preview_details.end_entry)
    preview_details.save()
    resource.preview_details = preview_details
    resource.save()


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
    def create_file_resource(self, file_resource_input: CreateEmptyFileResourceInput) -> TypeResource:
        dataset_id = file_resource_input.dataset
        try:
            dataset = Dataset.objects.get(id=dataset_id)
        except Dataset.DoesNotExist as e:
            raise ValueError(f"Dataset with ID {dataset_id} does not exist.")
        resource = Resource()
        resource.dataset = dataset
        resource.save()
        return resource

    @strawberry_django.mutation(handle_django_errors=True)
    def update_file_resource(self, file_resource_input: UpdateFileResourceInput) -> TypeResource:
        try:
            resource = Resource.objects.get(id=file_resource_input.id)
        except Resource.DoesNotExist as e:
            raise ValueError(f"Resource with ID {file_resource_input.id} does not exist.")
        if file_resource_input.name:
            resource.name = file_resource_input.name
        if not file_resource_input.description is None:
            resource.description = file_resource_input.description
        resource.save()

        if file_resource_input.file:
            file_details = resource.resourcefiledetails
            file_details.file = file_resource_input.file
            file_details.size = file_resource_input.file.size
            file_details.save()

        resource.preview_enabled = file_resource_input.preview_enabled
        resource.save()
        if file_resource_input.preview_details:
            _update_resource_preview_details(file_resource_input, resource)

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

    @strawberry_django.mutation(handle_django_errors=True)
    def update_schema(self, input: SchemaUpdateInput) -> TypeResource:
        try:
            resource = Resource.objects.get(id=input.resource)
        except Resource.DoesNotExist as e:
            raise ValueError(f"Resource with ID {input.resource} does not exist.")
        _update_file_resource_schema(resource, input.updates)
        return resource
