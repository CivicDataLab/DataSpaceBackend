import copy
import typing
import uuid
from enum import Enum
from typing import Any, Dict, List, Optional, cast

import pandas as pd
import strawberry
import strawberry_django
import structlog
from django.db.models import QuerySet
from strawberry.file_uploads import Upload
from strawberry.types import Info

from api.models import (
    Dataset,
    Resource,
    ResourceFileDetails,
    ResourcePreviewDetails,
    ResourceSchema,
)
from api.types import TypeResource
from api.utils.constants import FORMAT_MAPPING
from api.utils.data_indexing import index_resource_data
from api.utils.file_utils import file_validation

logger = structlog.get_logger("dataspace.resource_schema")


@strawberry.input
class CreateFileResourceInput:
    """Input type for creating a file resource."""

    dataset: uuid.UUID = strawberry.field()
    files: List[Upload] = strawberry.field()


@strawberry.input
class CreateEmptyFileResourceInput:
    """Input type for creating an empty file resource."""

    dataset: uuid.UUID = strawberry.field()


@strawberry.input
class PreviewDetails:
    """Input type for preview details."""

    is_all_entries: bool = strawberry.field(default=True)
    start_entry: int = strawberry.field(default=0)
    end_entry: int = strawberry.field(default=10)


@strawberry.input
class UpdateFileResourceInput:
    """Input type for updating a file resource."""

    id: uuid.UUID = strawberry.field()
    file: Optional[Upload] = strawberry.field(default=None)
    name: Optional[str] = strawberry.field(default=None)
    description: Optional[str] = strawberry.field(default=None)
    preview_enabled: bool = strawberry.field(default=False)
    preview_details: Optional[PreviewDetails] = strawberry.field(default=None)


@strawberry.enum
class FieldType(Enum):
    """Enum for field types."""

    STRING = "STRING"
    NUMBER = "NUMBER"
    INTEGER = "INTEGER"
    DATE = "DATE"


@strawberry.input
class SchemaUpdate:
    """Input type for schema updates."""

    id: str = strawberry.field()
    description: str = strawberry.field()
    format: FieldType = strawberry.field()


@strawberry.input
class SchemaUpdateInput:
    """Input type for schema updates."""

    resource: uuid.UUID = strawberry.field()
    updates: List[SchemaUpdate] = strawberry.field()


@strawberry.type
class Query:
    """Queries for resources."""

    @strawberry_django.field
    def dataset_resources(
        self, info: Info, dataset_id: uuid.UUID
    ) -> List[TypeResource]:
        """Get resources for a dataset."""
        resources = Resource.objects.filter(dataset_id=dataset_id)
        return [TypeResource.from_django(resource) for resource in resources]


def _validate_file_details_and_update_format(resource: Resource) -> None:
    """Validate file details and update format."""
    file_details = getattr(resource, "resourcefiledetails", None)
    if not file_details:
        raise ValueError("Resource has no file details")

    file = file_details.file
    deep_copy_file = copy.deepcopy(file)
    mime_type = file_validation(deep_copy_file, file, FORMAT_MAPPING)
    if not mime_type:
        raise ValueError("Unsupported file format.")

    file_format = FORMAT_MAPPING.get(mime_type.lower() if mime_type else "")
    if not file_format:
        raise ValueError("Unsupported file format")

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

    file_details.format = file_format
    file_details.save()


def _create_file_resource_schema(resource: Resource) -> None:
    """Create file resource schema."""
    # Try to index CSV data if applicable
    data_table = index_resource_data(resource)

    # After indexing, check again if schema was created
    if ResourceSchema.objects.filter(resource=resource).exists():
        logger.info(f"Schema created during indexing for resource {resource.id}")
        return


def _update_file_resource_schema(
    resource: Resource, updated_schema: List[SchemaUpdate]
) -> None:
    """Update file resource schema and re-index if necessary."""
    # Check if we need to re-index after schema update
    format_changes = False

    # Update schema fields
    existing_schema: QuerySet[ResourceSchema] = ResourceSchema.objects.filter(
        resource=resource
    )

    for schema in existing_schema:  # type: ResourceSchema
        try:
            schema_change = next(
                item for item in updated_schema if item.id == str(schema.id)
            )
            # Check if format is changing, which might require re-indexing
            if schema.format != schema_change.format.value:
                format_changes = True

            # Update the schema
            schema.description = schema_change.description
            schema.format = schema_change.format.value
            schema.save()

            logger.info(
                f"Updated schema field {schema.field_name} for resource {resource.id}"
            )
        except StopIteration:
            continue

    # Re-index if format changes were made
    if format_changes:
        logger.info(f"Re-indexing resource {resource.id} due to schema format changes")
        # Re-index the resource to apply the schema changes to the database
        index_resource_data(resource)


def _update_resource_preview_details(
    file_resource_input: UpdateFileResourceInput, resource: Resource
) -> None:
    """Update resource preview details."""
    preview_details = getattr(resource, "preview_details", None)
    if preview_details:
        preview_details.delete()

    if file_resource_input.preview_details:
        preview_details = ResourcePreviewDetails.objects.create(
            is_all_entries=file_resource_input.preview_details.is_all_entries,
            start_entry=file_resource_input.preview_details.start_entry,
            end_entry=file_resource_input.preview_details.end_entry,
        )
        resource.preview_details = preview_details
        resource.save()


@strawberry.type
class Mutation:
    """Mutations for resources."""

    @strawberry_django.mutation(handle_django_errors=False)
    def create_file_resources(
        self, info: Info, file_resource_input: CreateFileResourceInput
    ) -> List[TypeResource]:
        """Create file resources."""
        dataset_id = file_resource_input.dataset
        resources = []
        try:
            dataset = Dataset.objects.get(id=dataset_id)
        except Dataset.DoesNotExist as e:
            raise ValueError(f"Dataset with ID {dataset_id} does not exist.")

        for file in file_resource_input.files:
            resource = Resource.objects.create(name=file.name, dataset=dataset)
            ResourceFileDetails.objects.create(
                file=file, size=file.size, resource=resource
            )
            _validate_file_details_and_update_format(resource)
            resources.append(TypeResource.from_django(resource))
        return resources

    @strawberry_django.mutation(handle_django_errors=True)
    def create_file_resource(
        self, info: Info, file_resource_input: CreateEmptyFileResourceInput
    ) -> TypeResource:
        """Create a file resource."""
        dataset_id = file_resource_input.dataset
        try:
            dataset = Dataset.objects.get(id=dataset_id)
        except Dataset.DoesNotExist as e:
            raise ValueError(f"Dataset with ID {dataset_id} does not exist.")

        resource = Resource.objects.create(dataset=dataset)
        return TypeResource.from_django(resource)

    @strawberry_django.mutation(handle_django_errors=True)
    def update_file_resource(
        self, info: Info, file_resource_input: UpdateFileResourceInput
    ) -> TypeResource:
        """Update a file resource."""
        try:
            resource = Resource.objects.get(id=file_resource_input.id)
        except Resource.DoesNotExist as e:
            raise ValueError(
                f"Resource with ID {file_resource_input.id} does not exist."
            )

        if file_resource_input.name:
            resource.name = file_resource_input.name
        if file_resource_input.description is not None:
            resource.description = file_resource_input.description
        resource.save()

        if file_resource_input.file:
            file_details = getattr(resource, "resourcefiledetails", None)
            if file_details:
                file_details.file = file_resource_input.file
                file_details.size = file_resource_input.file.size
                file_details.save()
            else:
                ResourceFileDetails.objects.create(
                    file=file_resource_input.file,
                    size=file_resource_input.file.size,
                    resource=resource,
                )

        if file_resource_input.preview_details:
            _update_resource_preview_details(file_resource_input, resource)

        return TypeResource.from_django(resource)

    @strawberry_django.mutation(handle_django_errors=True)
    def update_file_resource_schema(
        self, info: Info, schema_update_input: SchemaUpdateInput
    ) -> TypeResource:
        """Update file resource schema."""
        try:
            resource = Resource.objects.get(id=schema_update_input.resource)
        except Resource.DoesNotExist as e:
            raise ValueError(
                f"Resource with ID {schema_update_input.resource} does not exist."
            )

        _update_file_resource_schema(resource, schema_update_input.updates)
        return TypeResource.from_django(resource)

    @strawberry_django.mutation(handle_django_errors=True)
    def reset_file_resource_schema(
        self, info: Info, resource_id: uuid.UUID
    ) -> TypeResource:
        """Reset file resource schema."""
        try:
            resource = Resource.objects.get(id=resource_id)
        except Resource.DoesNotExist as e:
            raise ValueError(f"Resource with ID {resource_id} does not exist.")
        # TODO: validate file vs api type for schema
        _create_file_resource_schema(resource)
        resource.save()
        return TypeResource.from_django(resource)

    @strawberry_django.mutation(handle_django_errors=False)
    def delete_file_resource(self, info: Info, resource_id: uuid.UUID) -> bool:
        """Delete a file resource."""
        try:
            resource = Resource.objects.get(id=resource_id)
            resource.delete()
            return True
        except Resource.DoesNotExist as e:
            raise ValueError(f"Resource with ID {resource_id} does not exist.")
