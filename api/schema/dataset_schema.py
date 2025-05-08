import datetime
import uuid
from typing import Any, List, Optional, Union

import strawberry
import strawberry_django
from strawberry.permission import BasePermission
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
from api.utils.enums import DatasetAccessType, DatasetLicense, DatasetStatus
from api.utils.graphql_telemetry import trace_resolver
from authorization.models import DatasetPermission, OrganizationMembership, Role
from authorization.permissions import (
    DatasetPermissionGraphQL,
    HasOrganizationRoleGraphQL,
    PublishDatasetPermission,
)

DatasetAccessTypeENUM = strawberry.enum(DatasetAccessType)  # type: ignore
DatasetLicenseENUM = strawberry.enum(DatasetLicense)  # type: ignore


# Create permission classes dynamically with different operations
class ViewDatasetPermission(DatasetPermissionGraphQL):
    def __init__(self) -> None:
        super().__init__(operation="view")


class ChangeDatasetPermission(DatasetPermissionGraphQL):
    def __init__(self) -> None:
        super().__init__(operation="change")


class DeleteDatasetPermission(DatasetPermissionGraphQL):
    def __init__(self) -> None:
        super().__init__(operation="delete")


# Create organization permission class for 'add' operation
class AddOrganizationPermission(HasOrganizationRoleGraphQL):
    def __init__(self) -> None:
        super().__init__(operation="add")


from authorization.permissions import (
    CreateDatasetPermission,
    IsAuthenticated,
    UserDatasetPermission,
)


class AllowPublishedDatasets(BasePermission):
    """Permission class that allows access to published datasets for non-authenticated users."""

    message = "You need to be authenticated to access non-published datasets"

    def has_permission(self, source: Any, info: Info, **kwargs: Any) -> bool:
        request = info.context

        # For queries/mutations that don't have a source yet (e.g., getting a dataset by ID)
        if source is None:
            dataset_id = kwargs.get("dataset_id")
            if dataset_id:
                try:
                    dataset = Dataset.objects.get(id=dataset_id)
                    # Allow access to published datasets for everyone
                    if dataset.status == DatasetStatus.PUBLISHED.value:
                        return True
                except Dataset.DoesNotExist:
                    pass  # Let the resolver handle the non-existent dataset

            # For non-published datasets, require authentication
            return hasattr(request, "user") and request.user.is_authenticated

        # For queries/mutations that have a source (e.g., accessing a dataset object)
        if hasattr(source, "status"):
            # Allow access to published datasets for everyone
            if source.status == DatasetStatus.PUBLISHED.value:
                return True

        # For non-published datasets, require authentication
        return hasattr(request, "user") and request.user.is_authenticated


class ChartDataPermission(BasePermission):
    """Permission class specifically for accessing chart data.
    Allows anonymous access to published datasets and checks permissions for non-published datasets.
    """

    message = "You don't have permission to access this dataset's chart data"

    def has_permission(self, source: Any, info: Info, **kwargs: Any) -> bool:
        request = info.context
        dataset_id = kwargs.get("dataset_id")

        if not dataset_id:
            return False

        try:
            dataset = Dataset.objects.get(id=dataset_id)

            # Allow access to published datasets for everyone
            if dataset.status == DatasetStatus.PUBLISHED.value:
                return True

            # For non-published datasets, require authentication
            if not hasattr(request, "user") or not request.user.is_authenticated:
                return False

            # Superusers have access to everything
            if request.user.is_superuser:
                return True

            # Check if user is a member of the dataset's organization
            org_member = OrganizationMembership.objects.filter(
                user=request.user, organization=dataset.organization
            ).exists()

            # Check if user has specific dataset permissions
            dataset_perm = DatasetPermission.objects.filter(
                user=request.user, dataset=dataset
            ).exists()

            return org_member or dataset_perm

        except Dataset.DoesNotExist:
            return False


class UpdateDatasetPermission(BasePermission):
    """Permission class for updating dataset basic information.
    Checks if the user has permission to update the dataset.
    """

    message = "You don't have permission to update this dataset"

    def has_permission(self, source: Any, info: Info, **kwargs: Any) -> bool:
        request = info.context
        user = request.user

        # Check if user is authenticated
        if not user or not user.is_authenticated:
            return False

        # Superusers have access to everything
        if user.is_superuser:
            return True

        # Get the dataset ID from the input
        update_dataset_input = kwargs.get("update_dataset_input")
        if not update_dataset_input or not hasattr(update_dataset_input, "dataset"):
            return False

        dataset_id = update_dataset_input.dataset

        try:
            dataset = Dataset.objects.get(id=dataset_id)

            # Check if user owns the dataset
            if dataset.user and dataset.user == user:
                return True

            # If organization-owned, check organization permissions
            if dataset.organization:
                # Get the roles with names 'admin' or 'editor'
                admin_editor_roles = Role.objects.filter(
                    name__in=["admin", "editor", "owner"]
                ).values_list("id", flat=True)

                # Check if user is a member of the dataset's organization with appropriate role
                org_member = OrganizationMembership.objects.filter(
                    user=user,
                    organization=dataset.organization,
                    role__id__in=admin_editor_roles,
                ).exists()

                if org_member:
                    return True

            # Check dataset-specific permissions
            dataset_perm = DatasetPermission.objects.filter(
                user=user, dataset=dataset
            ).first()
            return dataset_perm and dataset_perm.role.can_change and dataset.status == DatasetStatus.DRAFT.value  # type: ignore

        except Dataset.DoesNotExist:
            return False


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
    access_type: Optional[DatasetAccessTypeENUM] = DatasetAccessTypeENUM.PUBLIC
    license: Optional[DatasetLicenseENUM] = (
        DatasetLicenseENUM.CC_BY_SA_4_0_ATTRIBUTION_SHARE_ALIKE
    )


@strawberry.input
class UpdateDatasetInput:
    dataset: uuid.UUID
    title: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[List[str]] = None
    access_type: Optional[DatasetAccessTypeENUM] = DatasetAccessTypeENUM.PUBLIC
    license: Optional[DatasetLicenseENUM] = (
        DatasetLicenseENUM.CC_BY_SA_4_0_ATTRIBUTION_SHARE_ALIKE
    )


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
        organization = info.context.context.get("organization")
        user = info.context.user

        if organization:
            queryset = Dataset.objects.filter(organization=organization)
        else:
            # If user is authenticated
            if user.is_authenticated:
                # If user is superuser, show all datasets
                if user.is_superuser:
                    queryset = Dataset.objects.all()
                elif organization:
                    # Check id user has access to organization
                    org_member = OrganizationMembership.objects.filter(
                        user=user, organization=organization
                    ).exists()
                    if org_member and org_member.role.can_view:  # type: ignore
                        # Show only datasets from current organization
                        queryset = Dataset.objects.filter(organization=organization)
                    else:
                        # if user is not a member of the organization, return empty queryset
                        queryset = Dataset.objects.none()
                else:
                    # For non-organization authenticated users, only owned datasets
                    queryset = Dataset.objects.filter(user=user)
            else:
                # For non-authenticated users, return empty queryset
                queryset = Dataset.objects.none()

        if filters is not strawberry.UNSET:
            queryset = strawberry_django.filters.apply(filters, queryset, info)

        if order is not strawberry.UNSET:
            queryset = strawberry_django.ordering.apply(order, queryset, info)

        if pagination is not strawberry.UNSET:
            queryset = strawberry_django.pagination.apply(pagination, queryset)

        return TypeDataset.from_django_list(queryset)

    @strawberry.field(
        permission_classes=[ChartDataPermission],  # type: ignore[list-item]
    )
    @trace_resolver(name="get_chart_data", attributes={"component": "dataset"})
    def get_chart_data(
        self, info: Info, dataset_id: uuid.UUID
    ) -> List[Union[TypeResourceChartImage, TypeResourceChart]]:
        # Check if the dataset exists
        try:
            dataset = Dataset.objects.get(id=dataset_id)
        except Dataset.DoesNotExist:
            raise ValueError(f"Dataset with ID {dataset_id} does not exist.")

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
        permission_classes=[IsAuthenticated, CreateDatasetPermission],  # type: ignore[list-item]
    )
    @trace_resolver(
        name="add_dataset", attributes={"component": "dataset", "operation": "mutation"}
    )
    def add_dataset(self, info: Info) -> TypeDataset:
        # Get organization from context
        organization = info.context.context.get("organization")
        dataspace = info.context.context.get("dataspace")
        user = info.context.context.get("user")
        dataset = Dataset.objects.create(
            organization=organization,
            dataspace=dataspace,
            title=f"New dataset {datetime.datetime.now().strftime('%d %b %Y - %H:%M')}",
            description="",
            access_type=DatasetAccessType.PUBLIC,
            license=DatasetLicense.CC_BY_4_0_ATTRIBUTION,
        )
        if not organization:
            dataset.user = user
            dataset.save()
        DatasetPermission.objects.create(
            user=user, dataset=dataset, role=Role.objects.get(name="owner")
        )
        return TypeDataset.from_django(dataset)

    @strawberry_django.mutation(
        handle_django_errors=True,
        permission_classes=[UpdateDatasetPermission],  # type: ignore[list-item]
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
        permission_classes=[UpdateDatasetPermission],  # type: ignore[list-item]
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
        except Dataset.DoesNotExist as e:
            raise ValueError(f"Dataset with ID {dataset_id} does not exist.")

        if update_dataset_input.title:
            dataset.title = update_dataset_input.title
        if update_dataset_input.description:
            dataset.description = update_dataset_input.description
        if update_dataset_input.access_type:
            dataset.access_type = update_dataset_input.access_type
        if update_dataset_input.license:
            dataset.license = update_dataset_input.license
        _update_dataset_tags(dataset, update_dataset_input.tags or [])
        dataset.save()
        return TypeDataset.from_django(dataset)

    @strawberry_django.mutation(
        handle_django_errors=True,
        permission_classes=[PublishDatasetPermission],  # type: ignore[list-item]
    )
    @trace_resolver(
        name="publish_dataset",
        attributes={"component": "dataset", "operation": "mutation"},
    )
    def publish_dataset(self, info: Info, dataset_id: uuid.UUID) -> TypeDataset:
        try:
            dataset = Dataset.objects.get(id=dataset_id)
        except Dataset.DoesNotExist as e:
            raise ValueError(f"Dataset with ID {dataset_id} does not exist.")

        # TODO: validate dataset
        dataset.status = DatasetStatus.PUBLISHED.value
        dataset.save()
        return TypeDataset.from_django(dataset)

    @strawberry_django.mutation(
        handle_django_errors=True,
        permission_classes=[PublishDatasetPermission],  # type: ignore[list-item]
    )
    @trace_resolver(
        name="un_publish_dataset",
        attributes={"component": "dataset", "operation": "mutation"},
    )
    def un_publish_dataset(self, info: Info, dataset_id: uuid.UUID) -> TypeDataset:
        try:
            dataset = Dataset.objects.get(id=dataset_id)
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
            dataset.delete()
            return True
        except Dataset.DoesNotExist as e:
            raise ValueError(f"Dataset with ID {dataset_id} does not exist.")
