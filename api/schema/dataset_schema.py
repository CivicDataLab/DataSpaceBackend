# mypy: disable-error-code=union-attr
import datetime
import uuid
from typing import Any, List, Optional, Union

import strawberry
import strawberry_django
from django.core.exceptions import ValidationError as DjangoValidationError
from strawberry.permission import BasePermission
from strawberry.types import Info
from strawberry_django.pagination import OffsetPaginationInput

from api.models import (
    Dataset,
    Geography,
    Metadata,
    Organization,
    Resource,
    ResourceChartDetails,
    ResourceChartImage,
    Sector,
    UseCase,
)
from api.models.Dataset import Tag
from api.models.DatasetMetadata import DatasetMetadata
from api.schema.base_mutation import (
    BaseMutation,
    GraphQLValidationError,
    MutationResponse,
)
from api.schema.extensions import TrackActivity, TrackModelActivity
from api.types.type_dataset import DatasetFilter, DatasetOrder, TypeDataset
from api.types.type_organization import TypeOrganization
from api.types.type_resource_chart import TypeResourceChart
from api.types.type_resource_chart_image import TypeResourceChartImage
from api.utils.enums import (
    DatasetAccessType,
    DatasetLicense,
    DatasetStatus,
    UseCaseStatus,
)
from api.utils.graphql_telemetry import trace_resolver
from authorization.models import DatasetPermission, OrganizationMembership, Role, User
from authorization.permissions import (
    DatasetPermissionGraphQL,
    HasOrganizationRoleGraphQL,
    PublishDatasetPermission,
)
from authorization.types import TypeUser

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


from authorization.graphql_permissions import IsAuthenticated
from authorization.permissions import CreateDatasetPermission, UserDatasetPermission


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
                user = request.user
                if not user.is_authenticated:
                    return False
                if user.is_superuser:
                    return True
                dataset_perm = DatasetPermission.objects.filter(
                    user=user, dataset=dataset
                ).first()
                if dataset_perm:
                    return dataset_perm.role.can_view
                org_perm = OrganizationMembership.objects.filter(
                    user=user, organization=dataset.organization
                ).first()
                if org_perm:
                    return org_perm.role.can_view
                return False

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

        try:
            organization = info.context.context.get("organization")
            user = request.user
            # Superusers have access to everything
            if user.is_superuser:
                return True
            if dataset_id:
                dataset = Dataset.objects.get(id=dataset_id)
                # Allow access to published datasets for everyone
                if dataset.status == DatasetStatus.PUBLISHED.value:
                    return True
                if not user or not user.is_authenticated:
                    return False
                # Check if user owns the dataset
                if dataset.user and dataset.user == user:
                    return True
                # Check if user has specific dataset permissions
                dataset_perm = DatasetPermission.objects.filter(
                    user=user, dataset=dataset
                ).first()
                if dataset_perm:
                    return dataset_perm.role.can_view
                return False

            # For  all datasets' charts, require authentication
            if not user or not user.is_authenticated:
                return False
            # If no organization is provided, allow access to authenticated users for individual charts
            if not organization:
                return bool(user.is_authenticated)
            # Check if user is a member of the dataset's organization
            org_member = OrganizationMembership.objects.filter(
                user=user, organization=organization
            ).first()
            if org_member:
                return org_member.role.can_view
            return False

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
        if not update_dataset_input:
            update_dataset_input = kwargs.get("update_metadata_input")
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
    description: Optional[str] = None
    tags: Optional[List[str]] = None
    sectors: Optional[List[uuid.UUID]] = None
    geographies: Optional[List[int]] = None
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
    if not metadata_input:
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
def _update_dataset_tags(dataset: Dataset, tags: Optional[List[str]]) -> None:
    if tags is None:
        return
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


@trace_resolver(
    name="add_update_dataset_geographies", attributes={"component": "dataset"}
)
def _add_update_dataset_geographies(dataset: Dataset, geography_ids: List[int]) -> None:
    """Update geographies for a dataset."""
    dataset.geographies.clear()
    geographies = Geography.objects.filter(id__in=geography_ids)
    dataset.geographies.add(*geographies)
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
                    org_member = OrganizationMembership.objects.get(
                        user=user, organization=organization
                    )
                    if org_member.exists() and org_member.role.can_view:  # type: ignore
                        # Show only datasets from current organization
                        queryset = Dataset.objects.filter(organization=organization)
                    else:
                        # if user is not a member of the organization, return empty queryset
                        queryset = Dataset.objects.none()
                else:
                    # For non-organization authenticated users, only owned datasets
                    queryset = Dataset.objects.filter(user=user, organization=None)
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
        permission_classes=[AllowPublishedDatasets],  # type: ignore[list-item]
    )
    @trace_resolver(name="get_dataset", attributes={"component": "dataset"})
    def get_dataset(self, info: Info, dataset_id: uuid.UUID) -> Optional[TypeDataset]:
        """Get a dataset by ID."""
        try:
            dataset = Dataset.objects.get(id=dataset_id)
            return TypeDataset.from_django(dataset)
        except Dataset.DoesNotExist:
            return None

    @strawberry.field(
        permission_classes=[ChartDataPermission],  # type: ignore[list-item]
    )
    @trace_resolver(name="get_chart_data", attributes={"component": "dataset"})
    def get_chart_data(
        self, info: Info, dataset_id: Optional[uuid.UUID] = None
    ) -> List[Union[TypeResourceChartImage, TypeResourceChart]]:
        organization = info.context.context.get("organization")
        user = info.context.user
        # Check if the dataset exists
        if dataset_id:
            try:
                dataset = Dataset.objects.get(id=dataset_id)
                # Fetch ResourceChartImage for the dataset
                chart_images = list(
                    ResourceChartImage.objects.filter(dataset_id=dataset_id).order_by(
                        "modified"
                    )
                )
                resource_ids = Resource.objects.filter(
                    dataset_id=dataset_id
                ).values_list("id", flat=True)
            except Dataset.DoesNotExist:
                raise ValueError(f"Dataset with ID {dataset_id} does not exist.")
        else:
            organization = info.context.context.get("organization")
            if organization:
                chart_images = list(
                    ResourceChartImage.objects.filter(
                        dataset__organization=organization
                    ).order_by("modified")
                )
            else:
                chart_images = list(
                    ResourceChartImage.objects.filter(dataset__user=user).order_by(
                        "modified"
                    )
                )
            if organization:
                resource_ids = Resource.objects.filter(
                    dataset__organization=organization
                ).values_list("id", flat=True)
            else:
                resource_ids = Resource.objects.filter(dataset__user=user).values_list(
                    "id", flat=True
                )

        # Fetch ResourceChartDetails based on the related Resources
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

    @strawberry.field
    @trace_resolver(
        name="get_publishers",
        attributes={"component": "dataset", "operation": "query"},
    )
    def get_publishers(self, info: Info) -> List[Union[TypeOrganization, TypeUser]]:
        """Get all publishers (both individual publishers and organizations) who have published datasets."""
        # Get all published datasets
        published_datasets = Dataset.objects.filter(
            status=DatasetStatus.PUBLISHED.value
        )
        published_ds_organizations = published_datasets.values_list(
            "organization_id", flat=True
        )
        published_usecases = UseCase.objects.filter(
            status=UseCaseStatus.PUBLISHED.value
        )
        published_uc_organizations = published_usecases.values_list(
            "organization_id", flat=True
        )
        published_organizations = set(published_ds_organizations) | set(
            published_uc_organizations
        )

        # Get unique organizations that have published datasets
        org_publishers = Organization.objects.filter(
            id__in=published_organizations
        ).distinct()

        published_ds_users = published_datasets.values_list("user_id", flat=True)
        published_uc_users = published_usecases.values_list("user_id", flat=True)
        published_users = set(published_ds_users) | set(published_uc_users)

        # Get unique individual users who have published datasets without an organization
        individual_publishers = User.objects.filter(id__in=published_users).distinct()

        # Convert to GraphQL types
        org_types = [TypeOrganization.from_django(org) for org in org_publishers]
        user_types = [TypeUser.from_django(user) for user in individual_publishers]

        # Return combined list of publishers
        return org_types + user_types


@strawberry.type
class Mutation:
    @strawberry.mutation
    @BaseMutation.mutation(
        permission_classes=[IsAuthenticated, CreateDatasetPermission],
        trace_name="add_dataset",
        trace_attributes={"component": "dataset"},
        track_activity={
            "verb": "created",
            "get_data": lambda result, **kwargs: {
                "dataset_id": str(result.id),
                "dataset_title": result.title,
                "organization": (
                    str(result.organization.id) if result.organization else None
                ),
            },
        },
    )
    def add_dataset(self, info: Info) -> MutationResponse[TypeDataset]:
        # Get organization from context
        organization = info.context.context.get("organization")
        dataspace = info.context.context.get("dataspace")
        user = info.context.user

        dataset = Dataset.objects.create(
            organization=organization,
            dataspace=dataspace,
            title=f"New dataset {datetime.datetime.now().strftime('%d %b %Y - %H:%M:%S')}",
            description="",
            user=user,
            access_type=DatasetAccessType.PUBLIC,
            license=DatasetLicense.CC_BY_4_0_ATTRIBUTION,
        )
        DatasetPermission.objects.create(
            user=user, dataset=dataset, role=Role.objects.get(name="owner")
        )

        return MutationResponse.success_response(TypeDataset.from_django(dataset))

    @strawberry.mutation
    @BaseMutation.mutation(
        permission_classes=[UpdateDatasetPermission],
        track_activity={
            "verb": "updated",
            "get_data": lambda result, update_metadata_input=None, **kwargs: {
                "dataset_id": str(result.id),
                "dataset_title": result.title,
                "organization": (
                    str(result.organization.id) if result.organization else None
                ),
                "updated_fields": {
                    "metadata": True,
                    "description": bool(
                        update_metadata_input and update_metadata_input.description
                    ),
                },
            },
        },
        trace_name="add_update_dataset_metadata",
        trace_attributes={"component": "dataset"},
    )
    def add_update_dataset_metadata(
        self, info: Info, update_metadata_input: UpdateMetadataInput
    ) -> MutationResponse[TypeDataset]:
        dataset_id = update_metadata_input.dataset
        metadata_input = update_metadata_input.metadata
        try:
            dataset = Dataset.objects.get(id=dataset_id)
        except Dataset.DoesNotExist as e:
            raise DjangoValidationError(f"Dataset with ID {dataset_id} does not exist.")
        if dataset.status != DatasetStatus.DRAFT.value:
            raise DjangoValidationError(
                f"Dataset with ID {dataset_id} is not in draft status."
            )

        if update_metadata_input.description:
            dataset.description = update_metadata_input.description
        if update_metadata_input.access_type:
            dataset.access_type = update_metadata_input.access_type
        if update_metadata_input.license:
            dataset.license = update_metadata_input.license
        dataset.save()
        if update_metadata_input.tags is not None:
            _update_dataset_tags(dataset, update_metadata_input.tags)
        _add_update_dataset_metadata(dataset, metadata_input)
        if update_metadata_input.sectors is not None:
            _add_update_dataset_sectors(dataset, update_metadata_input.sectors)
        if update_metadata_input.geographies is not None:
            _add_update_dataset_geographies(dataset, update_metadata_input.geographies)
        return MutationResponse.success_response(TypeDataset.from_django(dataset))

    @strawberry_django.mutation(
        handle_django_errors=True,
        permission_classes=[UpdateDatasetPermission],  # type: ignore[list-item]
        extensions=[
            TrackModelActivity(
                verb="updated",
                get_data=lambda result, **kwargs: {
                    "dataset_id": str(result.id),
                    "dataset_title": result.title,
                    "organization": (
                        str(result.organization.id) if result.organization else None
                    ),
                    "updated_fields": {
                        "title": kwargs.get("update_dataset_input").title is not None,
                        "description": kwargs.get("update_dataset_input").description
                        is not None,
                        "access_type": kwargs.get("update_dataset_input").access_type
                        is not None,
                        "license": kwargs.get("update_dataset_input").license
                        is not None,
                        "tags": kwargs.get("update_dataset_input").tags is not None,
                    },
                },
            )
        ],
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
        if dataset.status != DatasetStatus.DRAFT.value:
            raise ValueError(f"Dataset with ID {dataset_id} is not in draft status.")
        if update_dataset_input.title:
            if update_dataset_input.title.strip() == "":
                raise ValueError("Title cannot be empty.")
            dataset.title = update_dataset_input.title.strip()
        if update_dataset_input.description:
            dataset.description = update_dataset_input.description.strip()
        if update_dataset_input.access_type:
            dataset.access_type = update_dataset_input.access_type
        if update_dataset_input.license:
            dataset.license = update_dataset_input.license
        dataset.save()
        _update_dataset_tags(dataset, update_dataset_input.tags)
        return TypeDataset.from_django(dataset)

    @strawberry_django.mutation(
        handle_django_errors=True,
        permission_classes=[PublishDatasetPermission],  # type: ignore[list-item]
        extensions=[
            TrackModelActivity(
                verb="published",
                get_data=lambda result, **kwargs: {
                    "dataset_id": str(result.id),
                    "dataset_title": result.title,
                    "organization": (
                        str(result.organization.id) if result.organization else None
                    ),
                },
            )
        ],
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
        extensions=[
            TrackModelActivity(
                verb="updated",
                get_data=lambda result, **kwargs: {
                    "dataset_id": str(result.id),
                    "dataset_title": result.title,
                    "organization": (
                        str(result.organization.id) if result.organization else None
                    ),
                    "updated_fields": {"status": "DRAFT", "action": "unpublished"},
                },
            )
        ],
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
        dataset.status = DatasetStatus.DRAFT.value
        dataset.save()
        return TypeDataset.from_django(dataset)

    @strawberry_django.mutation(
        handle_django_errors=False,
        permission_classes=[IsAuthenticated, DeleteDatasetPermission],  # type: ignore[list-item]
        extensions=[
            TrackActivity(
                verb="deleted dataset",
                get_data=lambda result, **kwargs: {
                    "dataset_id": str(kwargs.get("dataset_id")),
                    "success": result,
                },
            )
        ],
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
