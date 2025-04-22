import datetime
import uuid
from typing import List, Optional, Union

import strawberry
import strawberry_django
from strawberry.types import Info
from strawberry_django.pagination import OffsetPaginationInput

from api.models import (
    Dataset,
    Metadata,
    Resource,
    ResourceChartDetails,
    ResourceChartImage,
    Sector,
)
from api.models.Dataset import Tag
from api.models.DatasetMetadata import DatasetMetadata
from api.types.type_dataset import DatasetFilter, DatasetOrder, TypeDataset
from api.types.type_resource_chart import TypeResourceChart
from api.types.type_resource_chart_image import TypeResourceChartImage
from api.utils.enums import DatasetStatus
from api.utils.graphql_telemetry import trace_resolver
from authorization.models import OrganizationMembership
from authorization.permissions import DatasetPermissionGraphQL as DatasetPermission


# Create permission classes dynamically with different operations
class ViewDatasetPermission(DatasetPermission):
    def __init__(self) -> None:
        super().__init__(operation="view")


class ChangeDatasetPermission(DatasetPermission):
    def __init__(self) -> None:
        super().__init__(operation="change")


class DeleteDatasetPermission(DatasetPermission):
    def __init__(self) -> None:
        super().__init__(operation="delete")


from authorization.permissions import HasOrganizationRoleGraphQL as HasOrganizationRole


# Create organization permission class for 'add' operation
class AddOrganizationPermission(HasOrganizationRole):
    def __init__(self) -> None:
        super().__init__(operation="add")


from authorization.permissions import IsAuthenticated


@strawberry.input
class DSMetadataItemType:
    id: str
    value: str


@strawberry.input
class UpdateMetadataInput:
    dataset: uuid.UUID
    metadata: List[DSMetadataItemType]
    description: Optional[str]
    tags: Optional[List[str]]
    sectors: List[uuid.UUID]


@strawberry.input
class UpdateDatasetInput:
    dataset: uuid.UUID
    title: Optional[str]
    description: Optional[str]
    tags: List[str]


@trace_resolver(name="add_update_dataset_metadata", attributes={"component": "dataset"})
def _add_update_dataset_metadata(
    dataset: Dataset, metadata_input: List[DSMetadataItemType]
) -> None:
    if not metadata_input or len(metadata_input) == 0:
        return
    _delete_existing_metadata(dataset)
    for metadata_input_item in metadata_input:
        try:
            metadata_field = Metadata.objects.get(id=metadata_input_item.id)
            if not metadata_field.enabled:
                _delete_existing_metadata(dataset)
                raise ValueError(
                    f"Metadata with ID {metadata_input_item.id} is not enabled."
                )
            ds_metadata = DatasetMetadata(
                dataset=dataset,
                metadata_item=metadata_field,
                value=metadata_input_item.value,
            )
            ds_metadata.save()
        except Metadata.DoesNotExist as e:
            _delete_existing_metadata(dataset)
            raise ValueError(
                f"Metadata with ID {metadata_input_item.id} does not exist."
            )


@trace_resolver(name="update_dataset_tags", attributes={"component": "dataset"})
def _update_dataset_tags(dataset: Dataset, tags: List[str]) -> None:
    dataset.tags.clear()
    for tag in tags:
        dataset.tags.add(
            Tag.objects.get_or_create(defaults={"value": tag}, value__iexact=tag)[0]
        )
    dataset.save()


@trace_resolver(name="delete_existing_metadata", attributes={"component": "dataset"})
def _delete_existing_metadata(dataset: Dataset) -> None:
    try:
        existing_metadata = DatasetMetadata.objects.filter(dataset=dataset)
        existing_metadata.delete()
    except DatasetMetadata.DoesNotExist:
        pass


@trace_resolver(name="add_update_dataset_sectors", attributes={"component": "dataset"})
def _add_update_dataset_sectors(dataset: Dataset, sectors: List[uuid.UUID]) -> None:
    sectors_objs = Sector.objects.filter(id__in=sectors)
    dataset.sectors.clear()
    dataset.sectors.add(*sectors_objs)
    dataset.save()


@strawberry.type
class Query:
    @strawberry_django.field(
        filters=DatasetFilter,
        pagination=True,
        order=DatasetOrder,
        permission_classes=[IsAuthenticated],
    )
    @trace_resolver(name="datasets", attributes={"component": "dataset"})
    def datasets(
        self,
        info: Info,
        filters: Optional[DatasetFilter] = strawberry.UNSET,
        pagination: Optional[OffsetPaginationInput] = strawberry.UNSET,
        order: Optional[DatasetOrder] = strawberry.UNSET,
    ) -> List[TypeDataset]:
        """Get all datasets."""
        organization = info.context.request.context.get("organization")
        dataspace = info.context.request.context.get("dataspace")
        user = info.context.request.user

        # Base queryset filtering by organization or dataspace
        if dataspace:
            queryset = Dataset.objects.filter(dataspace=dataspace)
        elif organization:
            queryset = Dataset.objects.filter(organization=organization)
        else:
            # If user is superuser, show all datasets
            if user.is_superuser:
                queryset = Dataset.objects.all()
            else:
                # Show only datasets from organizations the user belongs to
                user_orgs = OrganizationMembership.objects.filter(
                    user=user
                ).values_list("organization_id", flat=True)
                queryset = Dataset.objects.filter(organization_id__in=user_orgs)

        if filters is not strawberry.UNSET:
            queryset = strawberry_django.filters.apply(filters, queryset, info)

        if order is not strawberry.UNSET:
            queryset = strawberry_django.ordering.apply(order, queryset, info)

        if pagination is not strawberry.UNSET:
            queryset = strawberry_django.pagination.apply(pagination, queryset)

        return TypeDataset.from_django_list(queryset)

    @strawberry.field(
        permission_classes=[IsAuthenticated, ViewDatasetPermission],  # type: ignore[list-item]
    )
    @trace_resolver(name="get_chart_data", attributes={"component": "dataset"})
    def get_chart_data(
        self, dataset_id: uuid.UUID
    ) -> List[Union[TypeResourceChartImage, TypeResourceChart]]:
        # Fetch ResourceChartImage for the dataset
        chart_images = list(
            ResourceChartImage.objects.filter(dataset_id=dataset_id).order_by(
                "modified"
            )
        )

        # Fetch ResourceChartDetails based on the related Resource in the same dataset
        resource_ids = Resource.objects.filter(dataset_id=dataset_id).values_list(
            "id", flat=True
        )
        chart_details = list(
            ResourceChartDetails.objects.filter(resource_id__in=resource_ids).order_by(
                "modified"
            )
        )

        # Convert to Strawberry types after getting lists
        chart_images_typed = TypeResourceChartImage.from_django_list(chart_images)
        chart_details_typed = TypeResourceChart.from_django_list(chart_details)

        # Combine both chart_images and chart_details into a single list
        combined_list: List[Union[TypeResourceChart, TypeResourceChartImage]] = (
            chart_images_typed + chart_details_typed
        )

        # Sort the combined list by the 'modified' field in descending order
        sorted_list = sorted(combined_list, key=lambda x: x.modified, reverse=True)

        return sorted_list


@strawberry.type
class Mutation:
    @strawberry_django.mutation(
        handle_django_errors=True,
        permission_classes=[IsAuthenticated, AddOrganizationPermission],  # type: ignore[list-item]
    )
    @trace_resolver(
        name="add_dataset", attributes={"component": "dataset", "operation": "mutation"}
    )
    def add_dataset(self, info: Info) -> TypeDataset:
        # Get organization from context
        organization = info.context.request.context.get("organization")
        dataspace = info.context.request.context.get("dataspace")
        user = info.context.request.user

        # Check if user has permission to create a dataset for this organization
        if organization and not user.is_superuser:
            try:
                user_org = OrganizationMembership.objects.get(
                    user=user, organization=organization
                )
                if user_org.role not in ["admin", "editor"]:
                    raise ValueError(
                        "You don't have permission to create datasets for this organization"
                    )
            except OrganizationMembership.DoesNotExist:
                raise ValueError(
                    "You don't have permission to create datasets for this organization"
                )

        dataset = Dataset.objects.create(
            organization=organization,
            dataspace=dataspace,
            title=f"New dataset {datetime.datetime.now().strftime('%d %b %Y - %H:%M')}",
        )
        return TypeDataset.from_django(dataset)

    @strawberry_django.mutation(
        handle_django_errors=True,
        permission_classes=[IsAuthenticated, ChangeDatasetPermission],  # type: ignore[list-item]
    )
    @trace_resolver(
        name="add_update_dataset_metadata",
        attributes={"component": "dataset", "operation": "mutation"},
    )
    def add_update_dataset_metadata(
        self, info: Info, update_metadata_input: UpdateMetadataInput
    ) -> TypeDataset:
        dataset_id = update_metadata_input.dataset
        metadata_input = update_metadata_input.metadata
        try:
            dataset = Dataset.objects.get(id=dataset_id)

            # Check if user has permission to update this dataset
            user = info.context.request.user
            if not user.is_superuser:
                try:
                    user_org = OrganizationMembership.objects.get(
                        user=user, organization=dataset.organization
                    )
                    if user_org.role not in ["admin", "editor"]:
                        raise ValueError(
                            "You don't have permission to update this dataset"
                        )
                except OrganizationMembership.DoesNotExist:
                    raise ValueError("You don't have permission to update this dataset")

        except Dataset.DoesNotExist as e:
            raise ValueError(f"Dataset with ID {dataset_id} does not exist.")

        if update_metadata_input.description:
            dataset.description = update_metadata_input.description
            dataset.save()
        if update_metadata_input.tags is not None:
            _update_dataset_tags(dataset, update_metadata_input.tags)
        _add_update_dataset_metadata(dataset, metadata_input)
        _add_update_dataset_sectors(dataset, update_metadata_input.sectors)
        return TypeDataset.from_django(dataset)

    @strawberry_django.mutation(
        handle_django_errors=True,
        permission_classes=[IsAuthenticated, ChangeDatasetPermission],  # type: ignore[list-item]
    )
    @trace_resolver(
        name="update_dataset",
        attributes={"component": "dataset", "operation": "mutation"},
    )
    def update_dataset(
        self, info: Info, update_dataset_input: UpdateDatasetInput
    ) -> TypeDataset:
        dataset_id = update_dataset_input.dataset
        try:
            dataset = Dataset.objects.get(id=dataset_id)

            # Check if user has permission to update this dataset
            user = info.context.request.user
            if not user.is_superuser:
                try:
                    user_org = OrganizationMembership.objects.get(
                        user=user, organization=dataset.organization
                    )
                    if user_org.role not in ["admin", "editor"]:
                        raise ValueError(
                            "You don't have permission to update this dataset"
                        )
                except OrganizationMembership.DoesNotExist:
                    raise ValueError("You don't have permission to update this dataset")

        except Dataset.DoesNotExist as e:
            raise ValueError(f"Dataset with ID {dataset_id} does not exist.")

        if update_dataset_input.title:
            dataset.title = update_dataset_input.title
        if update_dataset_input.description:
            dataset.description = update_dataset_input.description
        _update_dataset_tags(dataset, update_dataset_input.tags)
        return TypeDataset.from_django(dataset)

    @strawberry_django.mutation(
        handle_django_errors=True,
        permission_classes=[IsAuthenticated, ChangeDatasetPermission],  # type: ignore[list-item]
    )
    @trace_resolver(
        name="publish_dataset",
        attributes={"component": "dataset", "operation": "mutation"},
    )
    def publish_dataset(self, info: Info, dataset_id: uuid.UUID) -> TypeDataset:
        try:
            dataset = Dataset.objects.get(id=dataset_id)

            # Check if user has permission to publish this dataset
            user = info.context.request.user
            if not user.is_superuser:
                try:
                    user_org = OrganizationMembership.objects.get(
                        user=user, organization=dataset.organization
                    )
                    if user_org.role not in ["admin", "editor"]:
                        raise ValueError(
                            "You don't have permission to publish this dataset"
                        )
                except OrganizationMembership.DoesNotExist:
                    raise ValueError(
                        "You don't have permission to publish this dataset"
                    )

        except Dataset.DoesNotExist as e:
            raise ValueError(f"Dataset with ID {dataset_id} does not exist.")

        # TODO: validate dataset
        dataset.status = DatasetStatus.PUBLISHED.value
        dataset.save()
        return TypeDataset.from_django(dataset)

    @strawberry_django.mutation(
        handle_django_errors=True,
        permission_classes=[IsAuthenticated, ChangeDatasetPermission],  # type: ignore[list-item]
    )
    @trace_resolver(
        name="un_publish_dataset",
        attributes={"component": "dataset", "operation": "mutation"},
    )
    def un_publish_dataset(self, info: Info, dataset_id: uuid.UUID) -> TypeDataset:
        try:
            dataset = Dataset.objects.get(id=dataset_id)

            # Check if user has permission to unpublish this dataset
            user = info.context.request.user
            if not user.is_superuser:
                try:
                    user_org = OrganizationMembership.objects.get(
                        user=user, organization=dataset.organization
                    )
                    if user_org.role not in ["admin", "editor"]:
                        raise ValueError(
                            "You don't have permission to unpublish this dataset"
                        )
                except OrganizationMembership.DoesNotExist:
                    raise ValueError(
                        "You don't have permission to unpublish this dataset"
                    )

        except Dataset.DoesNotExist as e:
            raise ValueError(f"Dataset with ID {dataset_id} does not exist.")

        # TODO: validate dataset
        dataset.status = DatasetStatus.DRAFT
        dataset.save()
        return TypeDataset.from_django(dataset)

    @strawberry_django.mutation(
        handle_django_errors=False,
        permission_classes=[IsAuthenticated, DeleteDatasetPermission],  # type: ignore[list-item]
    )
    @trace_resolver(
        name="delete_dataset",
        attributes={"component": "dataset", "operation": "mutation"},
    )
    def delete_dataset(self, info: Info, dataset_id: uuid.UUID) -> bool:
        try:
            dataset = Dataset.objects.get(id=dataset_id)

            # Check if user has permission to delete this dataset
            user = info.context.request.user
            if not user.is_superuser:
                try:
                    user_org = OrganizationMembership.objects.get(
                        user=user, organization=dataset.organization
                    )
                    if user_org.role != "admin":
                        raise ValueError(
                            "You don't have permission to delete this dataset"
                        )
                except OrganizationMembership.DoesNotExist:
                    raise ValueError("You don't have permission to delete this dataset")

            dataset.delete()
            return True
        except Dataset.DoesNotExist as e:
            raise ValueError(f"Dataset with ID {dataset_id} does not exist.")
