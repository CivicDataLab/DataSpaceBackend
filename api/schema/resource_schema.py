import copy
import uuid
from enum import Enum

# mypy: disable-error-code=operator
from typing import List, Optional

import strawberry
import strawberry_django
import structlog
from django.db.models import QuerySet
from strawberry.file_uploads import Upload
from strawberry.types import Info

from api.managers.dvc_manager import DVCManager
from api.models import (
    Dataset,
    Resource,
    ResourceFileDetails,
    ResourcePreviewDetails,
    ResourceSchema,
    ResourceVersion,
)
from api.models.Resource import _increment_version
from api.schema.extensions import TrackActivity, TrackModelActivity
from api.types.type_resource import TypeResource
from api.utils.constants import FORMAT_MAPPING
from api.utils.data_indexing import index_resource_data
from api.utils.file_utils import file_validation
from api.utils.graphql_telemetry import trace_resolver

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


@strawberry.input
class CreateMajorVersionInput:
    """Input type for creating a major version of a resource."""

    resource_id: uuid.UUID = strawberry.field()
    description: str = strawberry.field(
        description="Description of the changes in this major version"
    )


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
    @trace_resolver(name="get_dataset_resources", attributes={"component": "resource"})
    def dataset_resources(
        self, info: Info, dataset_id: uuid.UUID
    ) -> List[TypeResource]:
        """Get resources for a dataset."""
        resources = Resource.objects.filter(dataset_id=dataset_id)
        return [TypeResource.from_django(resource) for resource in resources]

    @strawberry_django.field
    @trace_resolver(name="get_resource_by_id", attributes={"component": "resource"})
    def resource_by_id(self, info: Info, resource_id: uuid.UUID) -> TypeResource:
        """Get a resource by ID."""
        resource = Resource.objects.get(id=resource_id)
        return TypeResource.from_django(resource)


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


def _reset_file_resource_schema(resource: Resource) -> None:
    ResourceSchema.objects.filter(resource=resource).delete()
    data_table = index_resource_data(resource)


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

    if file_resource_input.preview_details:
        # If preview_details already exists, update it
        if preview_details:
            preview_details.is_all_entries = (
                file_resource_input.preview_details.is_all_entries
            )
            preview_details.start_entry = (
                file_resource_input.preview_details.start_entry
            )
            preview_details.end_entry = file_resource_input.preview_details.end_entry
            preview_details.save()
        # Otherwise, create a new one
        else:
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

    @strawberry_django.mutation(
        handle_django_errors=False,
        extensions=[
            TrackModelActivity(
                verb="created",
                get_data=lambda result, file_resource_input, **kwargs: {
                    "resource_id": str(result[0].id) if result else "",
                    "resource_name": result[0].name if result else "",
                    "dataset_id": str(file_resource_input.dataset),
                    "file_count": len(file_resource_input.files),
                },
            )
        ],
    )
    @trace_resolver(name="create_file_resources", attributes={"component": "resource"})
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
            _create_file_resource_schema(resource)
            resources.append(TypeResource.from_django(resource))
        return resources

    @strawberry_django.mutation(
        handle_django_errors=True,
        extensions=[
            TrackModelActivity(
                verb="created",
                get_data=lambda result, file_resource_input, **kwargs: {
                    "resource_id": str(result.id),
                    "dataset_id": str(file_resource_input.dataset),
                    "empty_resource": True,
                },
            )
        ],
    )
    @trace_resolver(name="create_file_resource", attributes={"component": "resource"})
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

    @strawberry_django.mutation(
        handle_django_errors=True,
        extensions=[
            TrackModelActivity(
                verb="updated",
                get_data=lambda result, file_resource_input, **kwargs: {
                    "resource_id": str(result.id),
                    "resource_name": result.name,
                    "updated_fields": {
                        "name": (
                            file_resource_input.name
                            if file_resource_input.name
                            else None
                        ),
                        "description": (
                            file_resource_input.description
                            if file_resource_input.description is not None
                            else None
                        ),
                        "preview_enabled": file_resource_input.preview_enabled,
                        "file_updated": file_resource_input.file is not None,
                        "preview_details_updated": file_resource_input.preview_details
                        is not None,
                    },
                },
            )
        ],
    )
    @trace_resolver(name="update_file_resource", attributes={"component": "resource"})
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
        resource.preview_enabled = file_resource_input.preview_enabled
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
            _validate_file_details_and_update_format(resource)
            _create_file_resource_schema(resource)

        if file_resource_input.preview_details:
            _update_resource_preview_details(file_resource_input, resource)

        return TypeResource.from_django(resource)

    @strawberry_django.mutation(handle_django_errors=True)
    @trace_resolver(
        name="update_file_resource_schema", attributes={"component": "resource"}
    )
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
    @trace_resolver(
        name="reset_file_resource_schema", attributes={"component": "resource"}
    )
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

    @strawberry_django.mutation(
        handle_django_errors=False,
        extensions=[
            TrackActivity(
                verb="deleted",
                get_data=lambda info, resource_id, **kwargs: {
                    "resource_id": str(resource_id),
                },
            )
        ],
    )
    @trace_resolver(name="delete_file_resource", attributes={"component": "resource"})
    def delete_file_resource(self, info: Info, resource_id: uuid.UUID) -> bool:
        """Delete a file resource."""
        try:
            resource = Resource.objects.get(id=resource_id)
            resource.delete()
            return True
        except Resource.DoesNotExist as e:
            raise ValueError(f"Resource with ID {resource_id} does not exist.")

    @strawberry_django.mutation(
        handle_django_errors=True,
        extensions=[
            TrackModelActivity(
                verb="versioned",
                get_data=lambda result, input, **kwargs: {
                    "resource_id": str(result.id),
                    "resource_name": result.name,
                    "version": result.version,
                    "description": input.description,
                },
            )
        ],
    )
    @trace_resolver(name="create_major_version", attributes={"component": "resource"})
    def create_major_version(
        self, info: Info, input: CreateMajorVersionInput
    ) -> TypeResource:
        """Create a major version for a resource.

        This should be used when significant changes are made to the resource data structure,
        such as schema changes, column additions/removals, or other breaking changes.
        """
        import os

        from django.conf import settings

        try:
            # Get the resource
            resource = Resource.objects.get(id=input.resource_id)
        except Resource.DoesNotExist:
            raise ValueError(f"Resource with ID {input.resource_id} does not exist")

        # Get the latest version
        last_version = resource.versions.order_by("-created_at").first()

        if not last_version:
            logger.warning(
                f"No previous version found for resource {resource.name}, creating initial version"
            )
            new_version = "v1.0.0"
        else:
            # Increment major version
            new_version = _increment_version(
                last_version.version_number, increment_type="major"
            )

        # Initialize DVC manager
        dvc = DVCManager(settings.DVC_REPO_PATH)

        # Get the resource file path
        file_path = resource.resourcefiledetails.file.path

        # Determine if file is large and should use chunking
        file_size = (
            resource.resourcefiledetails.file.size
            if hasattr(resource.resourcefiledetails.file, "size")
            else os.path.getsize(file_path)
        )
        use_chunked = file_size > 100 * 1024 * 1024  # 100MB threshold

        # Track with DVC
        dvc_file = dvc.track_resource(file_path, chunked=use_chunked)
        message = f"Major version update for resource: {resource.name} to version {new_version}"
        dvc.commit_version(dvc_file, message)
        dvc.tag_version(f"{resource.name}-{new_version}")

        # Create version record
        ResourceVersion.objects.create(
            resource=resource,
            version_number=new_version,
            change_description=input.description,
        )

        # Update resource version field
        resource.version = new_version
        resource.save(update_fields=["version"])

        logger.info(f"Created major version {new_version} for resource {resource.name}")
        return TypeResource.from_django(resource)
