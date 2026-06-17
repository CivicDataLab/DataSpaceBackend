"""Schema definitions for use cases."""

# mypy: disable-error-code=operator

import datetime
import uuid
from typing import List, Optional

import strawberry
import strawberry_django
from django.db import models
from strawberry import auto
from strawberry.file_uploads import Upload
from strawberry.types import Info
from strawberry_django.mutations import mutations
from strawberry_django.pagination import OffsetPaginationInput

from api.models import (
    SDG,
    Dataset,
    Geography,
    Metadata,
    Organization,
    Sector,
    Tag,
    UseCase,
    UseCaseMetadata,
    UseCaseOrganizationRelationship,
)
from api.schema.extensions import TrackActivity, TrackModelActivity
from api.types.type_dataset import TypeDataset
from api.types.type_organization import TypeOrganization
from api.types.type_usecase import TypeUseCase, UseCaseFilter, UseCaseOrder
from api.types.type_usecase_organization import (
    TypeUseCaseOrganizationRelationship,
    relationship_type,
)
from api.utils.enums import (
    OrganizationRelationshipType,
    UseCaseRunningStatus,
    UseCaseStatus,
)
from api.utils.graphql_telemetry import trace_resolver
from authorization.models import User
from authorization.types import TypeUser


@strawberry_django.input(UseCase, fields="__all__", exclude=["datasets", "slug"])
class UseCaseInput:
    """Input type for use case creation."""

    pass


@strawberry.input
class UCMetadataItemType:
    id: str
    value: str


@strawberry.input
class UpdateUseCaseMetadataInput:
    id: str
    metadata: List[UCMetadataItemType]
    tags: Optional[List[str]]
    sectors: List[uuid.UUID]
    sdgs: Optional[List[uuid.UUID]] = None
    geographies: Optional[List[int]] = None


use_case_running_status = strawberry.enum(UseCaseRunningStatus)  # type: ignore


@strawberry_django.partial(UseCase, fields="__all__", exclude=["datasets"])
class UseCaseInputPartial:
    """Input type for use case updates."""

    id: str
    logo: Optional[Upload] = strawberry.field(default=None)
    running_status: Optional[use_case_running_status] = UseCaseRunningStatus.INITIATED
    title: Optional[str] = None
    summary: Optional[str] = None
    platform_url: Optional[str] = None
    tags: Optional[List[str]] = None
    sectors: Optional[List[uuid.UUID]] = None
    sdgs: Optional[List[uuid.UUID]] = None
    geographies: Optional[List[int]] = None
    started_on: Optional[datetime.date] = None
    completed_on: Optional[datetime.date] = None


@strawberry.type(name="Query")
class Query:
    """Queries for use cases."""

    use_case: TypeUseCase = strawberry_django.field()

    @strawberry_django.field(
        filters=UseCaseFilter,
        pagination=True,
        order=UseCaseOrder,
    )
    @trace_resolver(name="get_use_cases", attributes={"component": "usecase"})
    def use_cases(
        self,
        info: Info,
        filters: Optional[UseCaseFilter] = strawberry.UNSET,
        pagination: Optional[OffsetPaginationInput] = strawberry.UNSET,
        order: Optional[UseCaseOrder] = strawberry.UNSET,
    ) -> list[TypeUseCase]:
        """Get all use cases."""
        user = info.context.user
        organization = info.context.context.get("organization")
        if organization:
            queryset = UseCase.objects.filter(organization=organization)
        elif user.is_superuser:
            queryset = UseCase.objects.all()
        elif user.is_authenticated:
            queryset = UseCase.objects.filter(user=user)
        else:
            queryset = UseCase.objects.filter(status=UseCaseStatus.PUBLISHED)

        if filters is not strawberry.UNSET:
            queryset = strawberry_django.filters.apply(filters, queryset, info)

        if order is not strawberry.UNSET:
            queryset = strawberry_django.ordering.apply(order, queryset, info)

        # Apply pagination
        if pagination is not strawberry.UNSET:
            queryset = strawberry_django.pagination.apply(pagination, queryset)

        return TypeUseCase.from_django_list(queryset)

    @strawberry_django.field
    @trace_resolver(name="get_published_use_cases", attributes={"component": "usecase"})
    def published_use_cases(
        self,
        info: Info,
        filters: Optional[UseCaseFilter] = strawberry.UNSET,
        pagination: Optional[OffsetPaginationInput] = strawberry.UNSET,
        order: Optional[UseCaseOrder] = strawberry.UNSET,
    ) -> list[TypeUseCase]:
        """Get published use cases."""
        queryset = UseCase.objects.filter(status=UseCaseStatus.PUBLISHED)

        # Apply filters first
        if filters is not strawberry.UNSET:
            queryset = strawberry_django.filters.apply(filters, queryset, info)

        # Apply ordering
        if order is not strawberry.UNSET:
            queryset = strawberry_django.ordering.apply(order, queryset, info)

        # Convert to list to avoid any slicing conflicts
        results = list(queryset)

        # Apply pagination on the list
        if pagination is not strawberry.UNSET:
            offset = getattr(pagination, "offset", 0) or 0
            limit = getattr(pagination, "limit", None)

            if limit is not None:
                results = results[offset : offset + limit]
            elif offset > 0:
                results = results[offset:]

        return TypeUseCase.from_django_list(results)

    @strawberry_django.field
    @trace_resolver(
        name="get_datasets_by_use_case", attributes={"component": "usecase"}
    )
    def dataset_by_use_case(self, info: Info, use_case_id: str) -> list[TypeDataset]:
        """Get datasets by use case."""
        queryset = Dataset.objects.filter(usecase__id=use_case_id)
        return TypeDataset.from_django_list(queryset)

    @strawberry_django.field
    @trace_resolver(
        name="get_contributors_by_use_case", attributes={"component": "usecase"}
    )
    def contributors_by_use_case(self, info: Info, use_case_id: str) -> list[TypeUser]:
        """Get contributors by use case."""
        try:
            use_case = UseCase.objects.get(id=use_case_id)
            contributors = use_case.contributors.all()
            return TypeUser.from_django_list(contributors)
        except UseCase.DoesNotExist:
            raise ValueError(f"UseCase with ID {use_case_id} does not exist.")


@trace_resolver(name="update_usecase_tags", attributes={"component": "usecase"})
def _update_usecase_tags(usecase: UseCase, tags: List[str]) -> None:
    usecase.tags.clear()
    for tag in tags:
        usecase.tags.add(
            Tag.objects.get_or_create(defaults={"value": tag}, value__iexact=tag)[0]
        )
    usecase.save()


@trace_resolver(name="update_usecase_sectors", attributes={"component": "usecase"})
def _update_usecase_sectors(usecase: UseCase, sectors: List[uuid.UUID]) -> None:
    sectors_objs = Sector.objects.filter(id__in=sectors)
    usecase.sectors.clear()
    usecase.sectors.add(*sectors_objs)
    usecase.save()


@trace_resolver(name="update_usecase_geographies", attributes={"component": "usecase"})
def _update_usecase_geographies(usecase: UseCase, geography_ids: List[int]) -> None:
    """Update geographies for a usecase."""
    usecase.geographies.clear()
    geographies = Geography.objects.filter(id__in=geography_ids)
    usecase.geographies.add(*geographies)
    usecase.save()


@trace_resolver(name="update_usecase_sdgs", attributes={"component": "usecase"})
def _update_usecase_sdgs(usecase: UseCase, sdgs: List[uuid.UUID]) -> None:
    sdgs_objs = SDG.objects.filter(id__in=sdgs)
    usecase.sdgs.clear()
    usecase.sdgs.add(*sdgs_objs)
    usecase.save()


@trace_resolver(
    name="add_update_usecase_metadata",
    attributes={"component": "usecase", "operation": "mutation"},
)
def _add_update_usecase_metadata(
    usecase: UseCase, metadata_input: List[UCMetadataItemType]
) -> None:
    if not metadata_input:
        return
    _delete_existing_metadata(usecase)
    for metadata_input_item in metadata_input:
        try:
            metadata_field = Metadata.objects.get(id=metadata_input_item.id)
            if not metadata_field.enabled:
                _delete_existing_metadata(usecase)
                raise ValueError(
                    f"Metadata with ID {metadata_input_item.id} is not enabled."
                )
            uc_metadata = UseCaseMetadata(
                usecase=usecase,
                metadata_item=metadata_field,
                value=metadata_input_item.value,
            )
            uc_metadata.save()
        except Metadata.DoesNotExist:
            _delete_existing_metadata(usecase)
            raise ValueError(
                f"Metadata with ID {metadata_input_item.id} does not exist."
            )


@trace_resolver(name="delete_existing_metadata", attributes={"component": "usecase"})
def _delete_existing_metadata(usecase: UseCase) -> None:
    try:
        existing_metadata = UseCaseMetadata.objects.filter(usecase=usecase)
        existing_metadata.delete()
    except UseCaseMetadata.DoesNotExist:
        pass


@strawberry.type
class Mutation:
    """Mutations for use cases."""

    create_use_case: TypeUseCase = mutations.create(UseCaseInput)
    # update_use_case: TypeUseCase = mutations.update(UseCaseInputPartial, key_attr="id")

    @strawberry_django.mutation(
        handle_django_errors=True,
        extensions=[
            TrackModelActivity(
                verb="created",
                get_data=lambda result, **kwargs: {
                    "usecase_id": str(result.id),
                    "usecase_title": result.title,
                    "organization_id": (
                        str(result.organization.id) if result.organization else None
                    ),
                },
            )
        ],
    )
    @trace_resolver(
        name="add_use_case",
        attributes={"component": "usecase", "operation": "mutation"},
    )
    def add_use_case(self, info: Info) -> TypeUseCase:
        """Add a new use case."""
        user = info.context.user
        organization = info.context.context.get("organization")
        if organization:
            use_case = UseCase.objects.create(
                title=f"New use_case {datetime.datetime.now().strftime('%d %b %Y - %H:%M:%S')}",
                summary="",
                organization=organization,
                status=UseCaseStatus.DRAFT,
                user=user,
            )
        else:
            use_case = UseCase.objects.create(
                title=f"New use_case {datetime.datetime.now().strftime('%d %b %Y - %H:%M:%S')}",
                summary="",
                user=user,
                status=UseCaseStatus.DRAFT,
            )

        return TypeUseCase.from_django(use_case)

    @strawberry_django.mutation(
        handle_django_errors=True,
        extensions=[
            TrackModelActivity(
                verb="updated",
                get_data=lambda result, update_metadata_input, **kwargs: {
                    "usecase_id": update_metadata_input.id,
                    "usecase_title": result.title,
                    "updated_fields": {
                        "metadata": True if update_metadata_input.metadata else False,
                        "tags": (
                            update_metadata_input.tags
                            if update_metadata_input.tags is not None
                            else None
                        ),
                        "sectors": (
                            [
                                str(sector_id)
                                for sector_id in update_metadata_input.sectors
                            ]
                            if update_metadata_input.sectors
                            else []
                        ),
                    },
                },
            )
        ],
    )
    @trace_resolver(
        name="add_update_usecase_metadata",
        attributes={"component": "usecase", "operation": "mutation"},
    )
    def add_update_usecase_metadata(
        self, update_metadata_input: UpdateUseCaseMetadataInput
    ) -> TypeUseCase:
        usecase_id = update_metadata_input.id
        metadata_input = update_metadata_input.metadata
        try:
            usecase = UseCase.objects.get(id=usecase_id)
        except UseCase.DoesNotExist:
            raise ValueError(f"UseCase with ID {usecase_id} does not exist.")

        if usecase.status != UseCaseStatus.DRAFT:
            raise ValueError(f"UseCase with ID {usecase_id} is not in draft status.")

        if update_metadata_input.tags is not None:
            _update_usecase_tags(usecase, update_metadata_input.tags)
        _add_update_usecase_metadata(usecase, metadata_input)
        _update_usecase_sectors(usecase, update_metadata_input.sectors)
        if update_metadata_input.sdgs is not None:
            _update_usecase_sdgs(usecase, update_metadata_input.sdgs)
        if update_metadata_input.geographies is not None:
            _update_usecase_geographies(usecase, update_metadata_input.geographies)
        return TypeUseCase.from_django(usecase)

    @strawberry_django.mutation(handle_django_errors=False)
    @trace_resolver(
        name="update_use_case",
        attributes={"component": "usecase", "operation": "mutation"},
    )
    def update_use_case(self, info: Info, data: UseCaseInputPartial) -> TypeUseCase:
        usecase_id = data.id
        try:
            usecase = UseCase.objects.get(id=usecase_id)
        except UseCase.DoesNotExist:
            raise ValueError(f"UseCase with ID {usecase_id} does not exist.")

        if usecase.status != UseCaseStatus.DRAFT:
            raise ValueError(f"UseCase with ID {usecase_id} is not in draft status.")

        if data.title is not None:
            if data.title.strip() == "":
                raise ValueError("Title cannot be empty.")
            usecase.title = data.title.strip()
        if data.summary is not None:
            usecase.summary = data.summary.strip()
        if data.platform_url is not None:
            usecase.platform_url = data.platform_url.strip()
        if data.started_on is not None:
            usecase.started_on = data.started_on
        if data.completed_on is not None and data.completed_on is not strawberry.UNSET:
            usecase.completed_on = data.completed_on
        if (
            data.running_status is not None
            and data.running_status is not strawberry.UNSET
        ):
            usecase.running_status = data.running_status
        if data.logo is not None and data.logo is not strawberry.UNSET:
            usecase.logo = data.logo
        usecase.save()
        return TypeUseCase.from_django(usecase)

    @strawberry_django.mutation(
        handle_django_errors=False,
        extensions=[
            TrackActivity(
                verb="deleted",
                get_data=lambda info, use_case_id, **kwargs: {
                    "usecase_id": use_case_id
                },
            )
        ],
    )
    @trace_resolver(
        name="delete_use_case",
        attributes={"component": "usecase", "operation": "mutation"},
    )
    def delete_use_case(self, info: Info, use_case_id: str) -> bool:
        """Delete a use case."""
        try:
            use_case = UseCase.objects.get(id=use_case_id)
        except UseCase.DoesNotExist:
            raise ValueError(f"UseCase with ID {use_case_id} does not exist.")
        use_case.delete()
        return True

    @strawberry_django.mutation(handle_django_errors=True)
    def add_dataset_to_use_case(
        self, info: Info, use_case_id: str, dataset_id: uuid.UUID
    ) -> TypeUseCase:
        """Add a dataset to a use case."""
        try:
            dataset = Dataset.objects.get(id=dataset_id)
        except Dataset.DoesNotExist:
            raise ValueError(f"Dataset with ID {dataset_id} does not exist.")

        try:
            use_case = UseCase.objects.get(id=use_case_id)
        except UseCase.DoesNotExist:
            raise ValueError(f"UseCase with ID {use_case_id} does not exist.")

        if use_case.status != UseCaseStatus.DRAFT:
            raise ValueError(f"UseCase with ID {use_case_id} is not in draft status.")

        use_case.datasets.add(dataset)
        use_case.save()
        return TypeUseCase.from_django(use_case)

    @strawberry_django.mutation(handle_django_errors=True)
    def remove_dataset_from_use_case(
        self, info: Info, use_case_id: str, dataset_id: uuid.UUID
    ) -> TypeUseCase:
        """Remove a dataset from a use case."""
        try:
            dataset = Dataset.objects.get(id=dataset_id)
        except Dataset.DoesNotExist:
            raise ValueError(f"Dataset with ID {dataset_id} does not exist.")
        try:
            use_case = UseCase.objects.get(id=use_case_id)
        except UseCase.DoesNotExist:
            raise ValueError(f"UseCase with ID {use_case_id} does not exist.")

        if use_case.status != UseCaseStatus.DRAFT:
            raise ValueError(f"UseCase with ID {use_case_id} is not in draft status.")
        use_case.datasets.remove(dataset)
        use_case.save()
        return TypeUseCase.from_django(use_case)

    @strawberry_django.mutation(handle_django_errors=True)
    @trace_resolver(
        name="update_usecase_datasets",
        attributes={"component": "usecase", "operation": "mutation"},
    )
    def update_usecase_datasets(
        self, info: Info, use_case_id: str, dataset_ids: List[uuid.UUID]
    ) -> TypeUseCase:
        """Update the datasets of a use case."""
        try:
            datasets = Dataset.objects.filter(id__in=dataset_ids)
            use_case = UseCase.objects.get(id=use_case_id)
        except UseCase.DoesNotExist:
            raise ValueError(f"Use Case with ID {use_case_id} doesn't exist")

        if use_case.status != UseCaseStatus.DRAFT:
            raise ValueError(f"UseCase with ID {use_case_id} is not in draft status.")

        use_case.datasets.set(datasets)
        use_case.save()
        return TypeUseCase.from_django(use_case)

    @strawberry_django.mutation(
        handle_django_errors=True,
        extensions=[
            TrackModelActivity(
                verb="published",
                get_data=lambda result, use_case_id, **kwargs: {
                    "usecase_id": use_case_id,
                    "usecase_title": result.title,
                },
            )
        ],
    )
    @trace_resolver(
        name="publish_use_case",
        attributes={"component": "usecase", "operation": "mutation"},
    )
    def publish_use_case(self, info: Info, use_case_id: str) -> TypeUseCase:
        """Publish a use case."""
        try:
            use_case = UseCase.objects.get(id=use_case_id)
        except UseCase.DoesNotExist:
            raise ValueError(f"Use Case with ID {use_case_id} doesn't exist")

        use_case.status = UseCaseStatus.PUBLISHED.value
        use_case.save()
        return TypeUseCase.from_django(use_case)

    @strawberry_django.mutation(
        handle_django_errors=True,
        extensions=[
            TrackModelActivity(
                verb="unpublished",
                get_data=lambda result, use_case_id, **kwargs: {
                    "usecase_id": use_case_id,
                    "usecase_title": result.title,
                },
            )
        ],
    )
    @trace_resolver(
        name="unpublish_use_case",
        attributes={"component": "usecase", "operation": "mutation"},
    )
    def unpublish_use_case(self, info: Info, use_case_id: str) -> TypeUseCase:
        """Un-publish a use case."""
        try:
            use_case = UseCase.objects.get(id=use_case_id)
        except UseCase.DoesNotExist:
            raise ValueError(f"Use Case with ID {use_case_id} doesn't exist")

        use_case.status = UseCaseStatus.DRAFT.value
        use_case.save()
        return TypeUseCase.from_django(use_case)

    # Add a contributor to a use case.
    @strawberry_django.mutation(handle_django_errors=True)
    @trace_resolver(
        name="add_contributor_to_use_case",
        attributes={"component": "usecase", "operation": "mutation"},
    )
    def add_contributor_to_use_case(
        self, info: Info, use_case_id: str, user_id: strawberry.ID
    ) -> TypeUseCase:
        """Add a contributor to a use case."""
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            raise ValueError(f"User with ID {user_id} does not exist.")

        try:
            use_case = UseCase.objects.get(id=use_case_id)
        except UseCase.DoesNotExist:
            raise ValueError(f"UseCase with ID {use_case_id} does not exist.")

        if use_case.status != UseCaseStatus.DRAFT:
            raise ValueError(f"UseCase with ID {use_case_id} is not in draft status.")

        use_case.contributors.add(user)
        use_case.save()
        return TypeUseCase.from_django(use_case)

    # Remove a contributor from a use case.
    @strawberry_django.mutation(handle_django_errors=True)
    @trace_resolver(
        name="remove_contributor_from_use_case",
        attributes={"component": "usecase", "operation": "mutation"},
    )
    def remove_contributor_from_use_case(
        self, info: Info, use_case_id: str, user_id: strawberry.ID
    ) -> TypeUseCase:
        """Remove a contributor from a use case."""
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            raise ValueError(f"User with ID {user_id} does not exist.")

        try:
            use_case = UseCase.objects.get(id=use_case_id)
        except UseCase.DoesNotExist:
            raise ValueError(f"UseCase with ID {use_case_id} does not exist.")

        if use_case.status != UseCaseStatus.DRAFT:
            raise ValueError(f"UseCase with ID {use_case_id} is not in draft status.")

        use_case.contributors.remove(user)
        use_case.save()
        return TypeUseCase.from_django(use_case)

    # Update the contributors of a use case.
    @strawberry_django.mutation(
        handle_django_errors=True,
        extensions=[
            TrackModelActivity(
                verb="updated",
                get_data=lambda result, use_case_id, user_ids, **kwargs: {
                    "usecase_id": use_case_id,
                    "usecase_title": result.title,
                    "updated_fields": {
                        "contributors": [str(user_id) for user_id in user_ids]
                    },
                },
            )
        ],
    )
    @trace_resolver(
        name="update_usecase_contributors",
        attributes={"component": "usecase", "operation": "mutation"},
    )
    def update_usecase_contributors(
        self, info: Info, use_case_id: str, user_ids: List[strawberry.ID]
    ) -> TypeUseCase:
        """Update the contributors of a use case."""
        try:
            users = User.objects.filter(id__in=user_ids)
            use_case = UseCase.objects.get(id=use_case_id)
        except UseCase.DoesNotExist:
            raise ValueError(f"Use Case with ID {use_case_id} doesn't exist")

        if use_case.status != UseCaseStatus.DRAFT:
            raise ValueError(f"UseCase with ID {use_case_id} is not in draft status.")

        use_case.contributors.set(users)
        use_case.save()
        return TypeUseCase.from_django(use_case)

    # Add an organization as a supporter to a use case.
    @strawberry_django.mutation(handle_django_errors=True)
    @trace_resolver(
        name="add_supporting_organization_to_use_case",
        attributes={"component": "usecase", "operation": "mutation"},
    )
    def add_supporting_organization_to_use_case(
        self, info: Info, use_case_id: str, organization_id: strawberry.ID
    ) -> TypeUseCaseOrganizationRelationship:
        """Add an organization as a supporter to a use case."""
        try:
            organization = Organization.objects.get(id=organization_id)
        except Organization.DoesNotExist:
            raise ValueError(f"Organization with ID {organization_id} does not exist.")

        try:
            use_case = UseCase.objects.get(id=use_case_id)
        except UseCase.DoesNotExist:
            raise ValueError(f"UseCase with ID {use_case_id} does not exist.")

        if use_case.status != UseCaseStatus.DRAFT:
            raise ValueError(f"UseCase with ID {use_case_id} is not in draft status.")

        # Create or get the relationship
        relationship, created = UseCaseOrganizationRelationship.objects.get_or_create(
            usecase=use_case,
            organization=organization,
            relationship_type=OrganizationRelationshipType.SUPPORTER,
        )

        return TypeUseCaseOrganizationRelationship.from_django(relationship)

    # Remove an organization as a supporter from a use case.
    @strawberry_django.mutation(handle_django_errors=True)
    @trace_resolver(
        name="remove_supporting_organization_from_use_case",
        attributes={"component": "usecase", "operation": "mutation"},
    )
    def remove_supporting_organization_from_use_case(
        self, info: Info, use_case_id: str, organization_id: strawberry.ID
    ) -> TypeUseCaseOrganizationRelationship:
        """Remove an organization as a supporter from a use case."""
        try:
            relationship = UseCaseOrganizationRelationship.objects.get(
                usecase_id=use_case_id,
                organization_id=organization_id,
                relationship_type=OrganizationRelationshipType.SUPPORTER,
            )
            relationship.delete()
            return TypeUseCaseOrganizationRelationship.from_django(relationship)
        except UseCaseOrganizationRelationship.DoesNotExist:
            raise ValueError(
                f"Organization with ID {organization_id} is not a supporter of use case with ID {use_case_id}"
            )

    # Add an organization as a partner to a use case.
    @strawberry_django.mutation(handle_django_errors=True)
    @trace_resolver(
        name="add_partner_organization_to_use_case",
        attributes={"component": "usecase", "operation": "mutation"},
    )
    def add_partner_organization_to_use_case(
        self, info: Info, use_case_id: str, organization_id: strawberry.ID
    ) -> TypeUseCaseOrganizationRelationship:
        """Add an organization as a partner to a use case."""
        try:
            organization = Organization.objects.get(id=organization_id)
        except Organization.DoesNotExist:
            raise ValueError(f"Organization with ID {organization_id} does not exist.")

        try:
            use_case = UseCase.objects.get(id=use_case_id)
        except UseCase.DoesNotExist:
            raise ValueError(f"UseCase with ID {use_case_id} does not exist.")

        if use_case.status != UseCaseStatus.DRAFT:
            raise ValueError(f"UseCase with ID {use_case_id} is not in draft status.")

        # Create or get the relationship
        relationship, created = UseCaseOrganizationRelationship.objects.get_or_create(
            usecase=use_case,
            organization=organization,
            relationship_type=OrganizationRelationshipType.PARTNER,
        )

        return TypeUseCaseOrganizationRelationship.from_django(relationship)

    # Remove an organization as a partner from a use case.
    @strawberry_django.mutation(handle_django_errors=True)
    @trace_resolver(
        name="remove_partner_organization_from_use_case",
        attributes={"component": "usecase", "operation": "mutation"},
    )
    def remove_partner_organization_from_use_case(
        self, info: Info, use_case_id: str, organization_id: strawberry.ID
    ) -> TypeUseCaseOrganizationRelationship:
        """Remove an organization as a partner from a use case."""
        try:
            relationship = UseCaseOrganizationRelationship.objects.get(
                usecase_id=use_case_id,
                organization_id=organization_id,
                relationship_type=OrganizationRelationshipType.PARTNER,
            )
            relationship.delete()
            return TypeUseCaseOrganizationRelationship.from_django(relationship)
        except UseCaseOrganizationRelationship.DoesNotExist:
            raise ValueError(
                f"Organization with ID {organization_id} is not a partner of use case with ID {use_case_id}"
            )

    # Update organization relationships for a use case.
    @strawberry_django.mutation(
        handle_django_errors=True,
        extensions=[
            TrackModelActivity(
                verb="updated",
                get_data=lambda result, use_case_id, supporter_organization_ids, partner_organization_ids, **kwargs: {
                    "usecase_id": use_case_id,
                    "usecase_title": result.title,
                    "updated_fields": {
                        "supporter_organizations": [
                            str(org_id) for org_id in supporter_organization_ids
                        ],
                        "partner_organizations": [
                            str(org_id) for org_id in partner_organization_ids
                        ],
                    },
                },
            )
        ],
    )
    @trace_resolver(
        name="update_usecase_organization_relationships",
        attributes={"component": "usecase", "operation": "mutation"},
    )
    def update_usecase_organization_relationships(
        self,
        info: Info,
        use_case_id: str,
        supporter_organization_ids: List[strawberry.ID],
        partner_organization_ids: List[strawberry.ID],
    ) -> TypeUseCase:
        """Update organization relationships for a use case."""
        try:
            use_case = UseCase.objects.get(id=use_case_id)
        except UseCase.DoesNotExist:
            raise ValueError(f"UseCase with ID {use_case_id} does not exist.")

        if use_case.status != UseCaseStatus.DRAFT:
            raise ValueError(f"UseCase with ID {use_case_id} is not in draft status.")

        # Clear existing relationships
        UseCaseOrganizationRelationship.objects.filter(usecase=use_case).delete()

        # Add supporter organizations
        supporter_orgs = Organization.objects.filter(id__in=supporter_organization_ids)
        for org in supporter_orgs:
            UseCaseOrganizationRelationship.objects.create(
                usecase=use_case,
                organization=org,
                relationship_type=OrganizationRelationshipType.SUPPORTER,
            )

        # Add partner organizations
        partner_orgs = Organization.objects.filter(id__in=partner_organization_ids)
        for org in partner_orgs:
            UseCaseOrganizationRelationship.objects.create(
                usecase=use_case,
                organization=org,
                relationship_type=OrganizationRelationshipType.PARTNER,
            )

        return TypeUseCase.from_django(use_case)
