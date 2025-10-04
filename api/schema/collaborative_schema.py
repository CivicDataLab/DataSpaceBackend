"""Schema definitions for collaboratives."""

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
    Collaborative,
    CollaborativeMetadata,
    CollaborativeOrganizationRelationship,
    Dataset,
    Geography,
    Metadata,
    Organization,
    Sector,
    Tag,
    UseCase,
)
from api.schema.extensions import TrackActivity, TrackModelActivity
from api.types.type_collaborative import (
    CollaborativeFilter,
    CollaborativeOrder,
    TypeCollaborative,
)
from api.types.type_collaborative_organization import (
    TypeCollaborativeOrganizationRelationship,
    relationship_type,
)
from api.types.type_dataset import TypeDataset
from api.types.type_organization import TypeOrganization
from api.types.type_usecase import TypeUseCase
from api.utils.enums import CollaborativeStatus, OrganizationRelationshipType
from api.utils.graphql_telemetry import trace_resolver
from authorization.models import User
from authorization.types import TypeUser


@strawberry_django.input(Collaborative, fields="__all__", exclude=["datasets", "slug"])
class CollaborativeInput:
    """Input type for collaborative creation."""

    pass


@strawberry.input
class CollaborativeMetadataItemType:
    id: str
    value: str


@strawberry.input
class UpdateCollaborativeMetadataInput:
    id: str
    metadata: List[CollaborativeMetadataItemType]
    tags: Optional[List[str]]
    sectors: List[uuid.UUID]
    sdgs: Optional[List[uuid.UUID]]
    geographies: Optional[List[int]]


@strawberry_django.partial(Collaborative, fields="__all__", exclude=["datasets"])
class CollaborativeInputPartial:
    """Input type for collaborative updates."""

    id: str
    logo: Optional[Upload] = strawberry.field(default=None)
    cover_image: Optional[Upload] = strawberry.field(default=None)
    title: Optional[str] = None
    summary: Optional[str] = None
    platform_url: Optional[str] = None
    tags: Optional[List[str]] = None
    sectors: Optional[List[uuid.UUID]] = None
    sdgs: Optional[List[uuid.UUID]] = None
    started_on: Optional[datetime.date] = None
    completed_on: Optional[datetime.date] = None


@strawberry.type(name="Query")
class Query:
    """Queries for collaboratives."""

    collaborative: TypeCollaborative = strawberry_django.field()

    @strawberry_django.field(
        filters=CollaborativeFilter,
        pagination=True,
        order=CollaborativeOrder,
    )
    @trace_resolver(
        name="get_collaboratives", attributes={"component": "collaborative"}
    )
    def collaboratives(
        self,
        info: Info,
        filters: Optional[CollaborativeFilter] = strawberry.UNSET,
        pagination: Optional[OffsetPaginationInput] = strawberry.UNSET,
        order: Optional[CollaborativeOrder] = strawberry.UNSET,
    ) -> list[TypeCollaborative]:
        """Get all collaboratives."""
        user = info.context.user
        organization = info.context.context.get("organization")
        if organization:
            queryset = Collaborative.objects.filter(organization=organization)
        elif user.is_superuser:
            queryset = Collaborative.objects.all()
        elif user.is_authenticated:
            queryset = Collaborative.objects.filter(user=user)
        else:
            queryset = Collaborative.objects.filter(
                status=CollaborativeStatus.PUBLISHED
            )

        if filters is not strawberry.UNSET:
            queryset = strawberry_django.filters.apply(filters, queryset, info)

        if order is not strawberry.UNSET:
            queryset = strawberry_django.ordering.apply(order, queryset, info)

        # Apply pagination
        if pagination is not strawberry.UNSET:
            queryset = strawberry_django.pagination.apply(pagination, queryset)

        return TypeCollaborative.from_django_list(queryset)

    @strawberry_django.field
    @trace_resolver(
        name="get_published_collaboratives", attributes={"component": "collaborative"}
    )
    def published_collaboratives(
        self,
        info: Info,
        filters: Optional[CollaborativeFilter] = strawberry.UNSET,
        pagination: Optional[OffsetPaginationInput] = strawberry.UNSET,
        order: Optional[CollaborativeOrder] = strawberry.UNSET,
    ) -> list[TypeCollaborative]:
        """Get published collaboratives."""
        queryset = Collaborative.objects.filter(status=CollaborativeStatus.PUBLISHED)

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

        return TypeCollaborative.from_django_list(results)

    @strawberry_django.field
    @trace_resolver(
        name="get_datasets_by_collaborative", attributes={"component": "collaborative"}
    )
    def dataset_by_collaborative(
        self, info: Info, collaborative_id: str
    ) -> list[TypeDataset]:
        """Get datasets by collaborative."""
        queryset = Dataset.objects.filter(collaborative__id=collaborative_id)
        return TypeDataset.from_django_list(queryset)

    @strawberry_django.field
    @trace_resolver(
        name="get_contributors_by_collaborative",
        attributes={"component": "collaborative"},
    )
    def contributors_by_collaborative(
        self, info: Info, collaborative_id: str
    ) -> list[TypeUser]:
        """Get contributors by collaborative."""
        try:
            collaborative = Collaborative.objects.get(id=collaborative_id)
            contributors = collaborative.contributors.all()
            return TypeUser.from_django_list(contributors)
        except Collaborative.DoesNotExist:
            raise ValueError(
                f"Collaborative with ID {collaborative_id} does not exist."
            )

    @strawberry_django.field
    @trace_resolver(
        name="get_collaborative_by_slug",
        attributes={"component": "collaborative"},
    )
    def collaborative_by_slug(self, info: Info, slug: str) -> TypeCollaborative:
        try:
            collaborative = Collaborative.objects.get(slug=slug)
            return TypeCollaborative.from_django(collaborative)
        except Collaborative.DoesNotExist:
            raise ValueError(f"Collaborative with slug {slug} does not exist.")


@trace_resolver(
    name="update_collaborative_tags", attributes={"component": "collaborative"}
)
def _update_collaborative_tags(collaborative: Collaborative, tags: List[str]) -> None:
    collaborative.tags.clear()
    for tag in tags:
        collaborative.tags.add(
            Tag.objects.get_or_create(defaults={"value": tag}, value__iexact=tag)[0]
        )
    collaborative.save()


@trace_resolver(
    name="update_collaborative_sectors", attributes={"component": "collaborative"}
)
def _update_collaborative_sectors(
    collaborative: Collaborative, sectors: List[uuid.UUID]
) -> None:
    sectors_objs = Sector.objects.filter(id__in=sectors)
    collaborative.sectors.clear()
    collaborative.sectors.add(*sectors_objs)
    collaborative.save()


@trace_resolver(
    name="update_collaborative_sdgs", attributes={"component": "collaborative"}
)
def _update_collaborative_sdgs(
    collaborative: Collaborative, sdgs: List[uuid.UUID]
) -> None:
    sdgs_objs = SDG.objects.filter(id__in=sdgs)
    collaborative.sdgs.clear()
    collaborative.sdgs.add(*sdgs_objs)
    collaborative.save()


@trace_resolver(
    name="add_update_collaborative_metadata",
    attributes={"component": "collaborative", "operation": "mutation"},
)
def _add_update_collaborative_metadata(
    collaborative: Collaborative, metadata_input: List[CollaborativeMetadataItemType]
) -> None:
    if not metadata_input:
        return
    _delete_existing_metadata(collaborative)
    for metadata_input_item in metadata_input:
        try:
            metadata_field = Metadata.objects.get(id=metadata_input_item.id)
            if not metadata_field.enabled:
                _delete_existing_metadata(collaborative)
                raise ValueError(
                    f"Metadata with ID {metadata_input_item.id} is not enabled."
                )
            uc_metadata = CollaborativeMetadata(
                collaborative=collaborative,
                metadata_item=metadata_field,
                value=metadata_input_item.value,
            )
            uc_metadata.save()
        except Metadata.DoesNotExist:
            _delete_existing_metadata(collaborative)
            raise ValueError(
                f"Metadata with ID {metadata_input_item.id} does not exist."
            )


@trace_resolver(
    name="delete_existing_metadata", attributes={"component": "collaborative"}
)
def _delete_existing_metadata(collaborative: Collaborative) -> None:
    try:
        existing_metadata = CollaborativeMetadata.objects.filter(
            collaborative=collaborative
        )
        existing_metadata.delete()
    except CollaborativeMetadata.DoesNotExist:
        pass


@strawberry.type
class Mutation:
    """Mutations for collaboratives."""

    create_collaborative: TypeCollaborative = mutations.create(CollaborativeInput)

    @strawberry_django.mutation(
        handle_django_errors=True,
        extensions=[
            TrackModelActivity(
                verb="created",
                get_data=lambda result, **kwargs: {
                    "collaborative_id": str(result.id),
                    "collaborative_title": result.title,
                    "organization_id": (
                        str(result.organization.id) if result.organization else None
                    ),
                },
            )
        ],
    )
    @trace_resolver(
        name="add_collaborative",
        attributes={"component": "collaborative", "operation": "mutation"},
    )
    def add_collaborative(self, info: Info) -> TypeCollaborative:
        """Add a new collaborative."""
        user = info.context.user
        organization = info.context.context.get("organization")
        if organization:
            collaborative = Collaborative.objects.create(
                title=f"New collaborative {datetime.datetime.now().strftime('%d %b %Y - %H:%M:%S')}",
                summary="",
                organization=organization,
                status=CollaborativeStatus.DRAFT,
                user=user,
            )
        else:
            collaborative = Collaborative.objects.create(
                title=f"New collaborative {datetime.datetime.now().strftime('%d %b %Y - %H:%M:%S')}",
                summary="",
                user=user,
                status=CollaborativeStatus.DRAFT,
            )

        return TypeCollaborative.from_django(collaborative)

    @strawberry_django.mutation(
        handle_django_errors=True,
        extensions=[
            TrackModelActivity(
                verb="updated",
                get_data=lambda result, update_metadata_input, **kwargs: {
                    "collaborative_id": update_metadata_input.id,
                    "collaborative_title": result.title,
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
        name="add_update_collaborative_metadata",
        attributes={"component": "collaborative", "operation": "mutation"},
    )
    def add_update_collaborative_metadata(
        self, update_metadata_input: UpdateCollaborativeMetadataInput
    ) -> TypeCollaborative:
        collaborative_id = update_metadata_input.id
        metadata_input = update_metadata_input.metadata
        try:
            collaborative = Collaborative.objects.get(id=collaborative_id)
        except Collaborative.DoesNotExist:
            raise ValueError(
                f"Collaborative with ID {collaborative_id} does not exist."
            )

        if collaborative.status != CollaborativeStatus.DRAFT:
            raise ValueError(
                f"Collaborative with ID {collaborative_id} is not in draft status."
            )

        if update_metadata_input.tags is not None:
            _update_collaborative_tags(collaborative, update_metadata_input.tags)
        _add_update_collaborative_metadata(collaborative, metadata_input)
        _update_collaborative_sectors(collaborative, update_metadata_input.sectors)
        if update_metadata_input.sdgs is not None:
            _update_collaborative_sdgs(collaborative, update_metadata_input.sdgs)
        if update_metadata_input.geographies is not None:
            _update_collaborative_geographies(
                collaborative, update_metadata_input.geographies
            )
        return TypeCollaborative.from_django(collaborative)

    @strawberry_django.mutation(handle_django_errors=False)
    @trace_resolver(
        name="update_collaborative",
        attributes={"component": "collaborative", "operation": "mutation"},
    )
    def update_collaborative(
        self, info: Info, data: CollaborativeInputPartial
    ) -> TypeCollaborative:
        collaborative_id = data.id
        try:
            collaborative = Collaborative.objects.get(id=collaborative_id)
        except Collaborative.DoesNotExist:
            raise ValueError(
                f"Collaborative with ID {collaborative_id} does not exist."
            )

        if collaborative.status != CollaborativeStatus.DRAFT:
            raise ValueError(
                f"Collaborative with ID {collaborative_id} is not in draft status."
            )

        if data.title is not None:
            if data.title.strip() == "":
                raise ValueError("Title cannot be empty.")
            collaborative.title = data.title.strip()
        if data.summary is not None:
            collaborative.summary = data.summary.strip()
        if data.platform_url is not None:
            collaborative.platform_url = data.platform_url.strip()
        if data.started_on is not None:
            collaborative.started_on = data.started_on
        if data.completed_on is not None and data.completed_on is not strawberry.UNSET:
            collaborative.completed_on = data.completed_on
        if data.logo is not None and data.logo is not strawberry.UNSET:
            collaborative.logo = data.logo
        if data.cover_image is not None and data.cover_image is not strawberry.UNSET:
            collaborative.cover_image = data.cover_image
        collaborative.save()
        return TypeCollaborative.from_django(collaborative)

    @strawberry_django.mutation(
        handle_django_errors=False,
        extensions=[
            TrackActivity(
                verb="deleted",
                get_data=lambda info, collaborative_id, **kwargs: {
                    "collaborative_id": collaborative_id
                },
            )
        ],
    )
    @trace_resolver(
        name="delete_collaborative",
        attributes={"component": "collaborative", "operation": "mutation"},
    )
    def delete_collaborative(self, info: Info, collaborative_id: str) -> bool:
        """Delete a collaborative."""
        try:
            collaborative = Collaborative.objects.get(id=collaborative_id)
        except Collaborative.DoesNotExist:
            raise ValueError(
                f"Collaborative with ID {collaborative_id} does not exist."
            )
        collaborative.delete()
        return True

    @strawberry_django.mutation(handle_django_errors=True)
    def add_dataset_to_collaborative(
        self, info: Info, collaborative_id: str, dataset_id: uuid.UUID
    ) -> TypeCollaborative:
        """Add a dataset to a collaborative."""
        try:
            dataset = Dataset.objects.get(id=dataset_id)
        except Dataset.DoesNotExist:
            raise ValueError(f"Dataset with ID {dataset_id} does not exist.")

        try:
            collaborative = Collaborative.objects.get(id=collaborative_id)
        except Collaborative.DoesNotExist:
            raise ValueError(
                f"Collaborative with ID {collaborative_id} does not exist."
            )

        if collaborative.status != CollaborativeStatus.DRAFT:
            raise ValueError(
                f"Collaborative with ID {collaborative_id} is not in draft status."
            )

        collaborative.datasets.add(dataset)
        collaborative.save()
        return TypeCollaborative.from_django(collaborative)

    @strawberry_django.mutation(handle_django_errors=True)
    def add_usecase_to_collaborative(
        self, info: Info, collaborative_id: str, usecase_id: str
    ) -> TypeCollaborative:
        """Add a usecase to a collaborative."""
        try:
            usecase = UseCase.objects.get(id=usecase_id)
        except UseCase.DoesNotExist:
            raise ValueError(f"UseCase with ID {usecase_id} does not exist.")

        try:
            collaborative = Collaborative.objects.get(id=collaborative_id)
        except Collaborative.DoesNotExist:
            raise ValueError(
                f"Collaborative with ID {collaborative_id} does not exist."
            )

        if collaborative.status != CollaborativeStatus.DRAFT:
            raise ValueError(
                f"Collaborative with ID {collaborative_id} is not in draft status."
            )

        collaborative.use_cases.add(usecase)
        collaborative.save()
        return TypeCollaborative.from_django(collaborative)

    @strawberry_django.mutation(handle_django_errors=True)
    def remove_dataset_from_collaborative(
        self, info: Info, collaborative_id: str, dataset_id: uuid.UUID
    ) -> TypeCollaborative:
        """Remove a dataset from a collaborative."""
        try:
            dataset = Dataset.objects.get(id=dataset_id)
        except Dataset.DoesNotExist:
            raise ValueError(f"Dataset with ID {dataset_id} does not exist.")
        try:
            collaborative = Collaborative.objects.get(id=collaborative_id)
        except Collaborative.DoesNotExist:
            raise ValueError(
                f"Collaborative with ID {collaborative_id} does not exist."
            )

        if collaborative.status != CollaborativeStatus.DRAFT:
            raise ValueError(
                f"Collaborative with ID {collaborative_id} is not in draft status."
            )
        collaborative.datasets.remove(dataset)
        collaborative.save()
        return TypeCollaborative.from_django(collaborative)

    @strawberry_django.mutation(handle_django_errors=True)
    def remove_usecase_from_collaborative(
        self, info: Info, collaborative_id: str, usecase_id: str
    ) -> TypeCollaborative:
        """Remove a usecase from a collaborative."""
        try:
            usecase = UseCase.objects.get(id=usecase_id)
        except UseCase.DoesNotExist:
            raise ValueError(f"UseCase with ID {usecase_id} does not exist.")
        try:
            collaborative = Collaborative.objects.get(id=collaborative_id)
        except Collaborative.DoesNotExist:
            raise ValueError(
                f"Collaborative with ID {collaborative_id} does not exist."
            )

        if collaborative.status != CollaborativeStatus.DRAFT:
            raise ValueError(
                f"Collaborative with ID {collaborative_id} is not in draft status."
            )
        collaborative.use_cases.remove(usecase)
        collaborative.save()
        return TypeCollaborative.from_django(collaborative)

    @strawberry_django.mutation(handle_django_errors=True)
    @trace_resolver(
        name="update_collaborative_datasets",
        attributes={"component": "collaborative", "operation": "mutation"},
    )
    def update_collaborative_datasets(
        self, info: Info, collaborative_id: str, dataset_ids: List[uuid.UUID]
    ) -> TypeCollaborative:
        """Update the datasets of a collaborative."""
        try:
            datasets = Dataset.objects.filter(id__in=dataset_ids)
            collaborative = Collaborative.objects.get(id=collaborative_id)
        except Collaborative.DoesNotExist:
            raise ValueError(f"Collaborative with ID {collaborative_id} doesn't exist")

        if collaborative.status != CollaborativeStatus.DRAFT:
            raise ValueError(
                f"Collaborative with ID {collaborative_id} is not in draft status."
            )

        collaborative.datasets.set(datasets)
        collaborative.save()
        return TypeCollaborative.from_django(collaborative)

    @strawberry_django.mutation(handle_django_errors=True)
    @trace_resolver(
        name="update_collaborative_use_cases",
        attributes={"component": "collaborative", "operation": "mutation"},
    )
    def update_collaborative_use_cases(
        self, info: Info, collaborative_id: str, use_case_ids: List[str]
    ) -> TypeCollaborative:
        """Update the use cases of a collaborative."""
        try:
            use_cases = UseCase.objects.filter(id__in=use_case_ids)
            collaborative = Collaborative.objects.get(id=collaborative_id)
        except Collaborative.DoesNotExist:
            raise ValueError(f"Collaborative with ID {collaborative_id} doesn't exist")

        if collaborative.status != CollaborativeStatus.DRAFT:
            raise ValueError(
                f"Collaborative with ID {collaborative_id} is not in draft status."
            )

        collaborative.use_cases.set(use_cases)
        collaborative.save()
        return TypeCollaborative.from_django(collaborative)

    @strawberry_django.mutation(
        handle_django_errors=True,
        extensions=[
            TrackModelActivity(
                verb="published",
                get_data=lambda result, collaborative_id, **kwargs: {
                    "collaborative_id": collaborative_id,
                    "collaborative_title": result.title,
                },
            )
        ],
    )
    @trace_resolver(
        name="publish_collaborative",
        attributes={"component": "collaborative", "operation": "mutation"},
    )
    def publish_collaborative(
        self, info: Info, collaborative_id: str
    ) -> TypeCollaborative:
        """Publish a collaborative."""
        try:
            collaborative = Collaborative.objects.get(id=collaborative_id)
        except Collaborative.DoesNotExist:
            raise ValueError(f"Collaborative with ID {collaborative_id} doesn't exist")

        collaborative.status = CollaborativeStatus.PUBLISHED.value
        collaborative.save()
        return TypeCollaborative.from_django(collaborative)

    @strawberry_django.mutation(
        handle_django_errors=True,
        extensions=[
            TrackModelActivity(
                verb="unpublished",
                get_data=lambda result, collaborative_id, **kwargs: {
                    "collaborative_id": collaborative_id,
                    "collaborative_title": result.title,
                },
            )
        ],
    )
    @trace_resolver(
        name="unpublish_collaborative",
        attributes={"component": "collaborative", "operation": "mutation"},
    )
    def unpublish_collaborative(
        self, info: Info, collaborative_id: str
    ) -> TypeCollaborative:
        """Un-publish a collaborative."""
        try:
            collaborative = Collaborative.objects.get(id=collaborative_id)
        except Collaborative.DoesNotExist:
            raise ValueError(f"Collaborative with ID {collaborative_id} doesn't exist")

        collaborative.status = CollaborativeStatus.DRAFT.value
        collaborative.save()
        return TypeCollaborative.from_django(collaborative)

    # Add a contributor to a collaborative.
    @strawberry_django.mutation(handle_django_errors=True)
    @trace_resolver(
        name="add_contributor_to_collaborative",
        attributes={"component": "collaborative", "operation": "mutation"},
    )
    def add_contributor_to_collaborative(
        self, info: Info, collaborative_id: str, user_id: strawberry.ID
    ) -> TypeCollaborative:
        """Add a contributor to a collaborative."""
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            raise ValueError(f"User with ID {user_id} does not exist.")

        try:
            collaborative = Collaborative.objects.get(id=collaborative_id)
        except Collaborative.DoesNotExist:
            raise ValueError(
                f"Collaborative with ID {collaborative_id} does not exist."
            )

        if collaborative.status != CollaborativeStatus.DRAFT:
            raise ValueError(
                f"Collaborative with ID {collaborative_id} is not in draft status."
            )

        collaborative.contributors.add(user)
        collaborative.save()
        return TypeCollaborative.from_django(collaborative)

    # Remove a contributor from a collaborative.
    @strawberry_django.mutation(handle_django_errors=True)
    @trace_resolver(
        name="remove_contributor_from_collaborative",
        attributes={"component": "collaborative", "operation": "mutation"},
    )
    def remove_contributor_from_collaborative(
        self, info: Info, collaborative_id: str, user_id: strawberry.ID
    ) -> TypeCollaborative:
        """Remove a contributor from a collaborative."""
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            raise ValueError(f"User with ID {user_id} does not exist.")

        try:
            collaborative = Collaborative.objects.get(id=collaborative_id)
        except Collaborative.DoesNotExist:
            raise ValueError(
                f"Collaborative with ID {collaborative_id} does not exist."
            )

        if collaborative.status != CollaborativeStatus.DRAFT:
            raise ValueError(
                f"Collaborative with ID {collaborative_id} is not in draft status."
            )

        collaborative.contributors.remove(user)
        collaborative.save()
        return TypeCollaborative.from_django(collaborative)

    # Update the contributors of a collaborative.
    @strawberry_django.mutation(
        handle_django_errors=True,
        extensions=[
            TrackModelActivity(
                verb="updated",
                get_data=lambda result, collaborative_id, user_ids, **kwargs: {
                    "collaborative_id": collaborative_id,
                    "collaborative_title": result.title,
                    "updated_fields": {
                        "contributors": [str(user_id) for user_id in user_ids]
                    },
                },
            )
        ],
    )
    @trace_resolver(
        name="update_collaborative_contributors",
        attributes={"component": "collaborative", "operation": "mutation"},
    )
    def update_collaborative_contributors(
        self, info: Info, collaborative_id: str, user_ids: List[strawberry.ID]
    ) -> TypeCollaborative:
        """Update the contributors of a collaborative."""
        try:
            users = User.objects.filter(id__in=user_ids)
            collaborative = Collaborative.objects.get(id=collaborative_id)
        except Collaborative.DoesNotExist:
            raise ValueError(f"Collaborative with ID {collaborative_id} doesn't exist")

        if collaborative.status != CollaborativeStatus.DRAFT:
            raise ValueError(
                f"Collaborative with ID {collaborative_id} is not in draft status."
            )

        collaborative.contributors.set(users)
        collaborative.save()
        return TypeCollaborative.from_django(collaborative)

    # Add an organization as a supporter to a collaborative.
    @strawberry_django.mutation(handle_django_errors=True)
    @trace_resolver(
        name="add_supporting_organization_to_collaborative",
        attributes={"component": "collaborative", "operation": "mutation"},
    )
    def add_supporting_organization_to_collaborative(
        self, info: Info, collaborative_id: str, organization_id: strawberry.ID
    ) -> TypeCollaborativeOrganizationRelationship:
        """Add an organization as a supporter to a collaborative."""
        try:
            organization = Organization.objects.get(id=organization_id)
        except Organization.DoesNotExist:
            raise ValueError(f"Organization with ID {organization_id} does not exist.")

        try:
            collaborative = Collaborative.objects.get(id=collaborative_id)
        except Collaborative.DoesNotExist:
            raise ValueError(
                f"Collaborative with ID {collaborative_id} does not exist."
            )

        if collaborative.status != CollaborativeStatus.DRAFT:
            raise ValueError(
                f"Collaborative with ID {collaborative_id} is not in draft status."
            )

        # Create or get the relationship
        relationship, created = (
            CollaborativeOrganizationRelationship.objects.get_or_create(
                collaborative=collaborative,
                organization=organization,
                relationship_type=OrganizationRelationshipType.SUPPORTER,
            )
        )

        return TypeCollaborativeOrganizationRelationship.from_django(relationship)

    # Remove an organization as a supporter from a collaborative.
    @strawberry_django.mutation(handle_django_errors=True)
    @trace_resolver(
        name="remove_supporting_organization_from_collaborative",
        attributes={"component": "collaborative", "operation": "mutation"},
    )
    def remove_supporting_organization_from_collaborative(
        self, info: Info, collaborative_id: str, organization_id: strawberry.ID
    ) -> TypeCollaborativeOrganizationRelationship:
        """Remove an organization as a supporter from a collaborative."""
        try:
            relationship = CollaborativeOrganizationRelationship.objects.get(
                collaborative_id=collaborative_id,
                organization_id=organization_id,
                relationship_type=OrganizationRelationshipType.SUPPORTER,
            )
            relationship.delete()
            return TypeCollaborativeOrganizationRelationship.from_django(relationship)
        except CollaborativeOrganizationRelationship.DoesNotExist:
            raise ValueError(
                f"Organization with ID {organization_id} is not a supporter of collaborative with ID {collaborative_id}"
            )

    # Add an organization as a partner to a collaborative.
    @strawberry_django.mutation(handle_django_errors=True)
    @trace_resolver(
        name="add_partner_organization_to_collaborative",
        attributes={"component": "collaborative", "operation": "mutation"},
    )
    def add_partner_organization_to_collaborative(
        self, info: Info, collaborative_id: str, organization_id: strawberry.ID
    ) -> TypeCollaborativeOrganizationRelationship:
        """Add an organization as a partner to a collaborative."""
        try:
            organization = Organization.objects.get(id=organization_id)
        except Organization.DoesNotExist:
            raise ValueError(f"Organization with ID {organization_id} does not exist.")

        try:
            collaborative = Collaborative.objects.get(id=collaborative_id)
        except Collaborative.DoesNotExist:
            raise ValueError(
                f"Collaborative with ID {collaborative_id} does not exist."
            )

        if collaborative.status != CollaborativeStatus.DRAFT:
            raise ValueError(
                f"Collaborative with ID {collaborative_id} is not in draft status."
            )

        # Create or get the relationship
        relationship, created = (
            CollaborativeOrganizationRelationship.objects.get_or_create(
                collaborative=collaborative,
                organization=organization,
                relationship_type=OrganizationRelationshipType.PARTNER,
            )
        )

        return TypeCollaborativeOrganizationRelationship.from_django(relationship)

    # Remove an organization as a partner from a collaborative.
    @strawberry_django.mutation(handle_django_errors=True)
    @trace_resolver(
        name="remove_partner_organization_from_collaborative",
        attributes={"component": "collaborative", "operation": "mutation"},
    )
    def remove_partner_organization_from_collaborative(
        self, info: Info, collaborative_id: str, organization_id: strawberry.ID
    ) -> TypeCollaborativeOrganizationRelationship:
        """Remove an organization as a partner from a collaborative."""
        try:
            relationship = CollaborativeOrganizationRelationship.objects.get(
                collaborative_id=collaborative_id,
                organization_id=organization_id,
                relationship_type=OrganizationRelationshipType.PARTNER,
            )
            relationship.delete()
            return TypeCollaborativeOrganizationRelationship.from_django(relationship)
        except CollaborativeOrganizationRelationship.DoesNotExist:
            raise ValueError(
                f"Organization with ID {organization_id} is not a partner of collaborative with ID {collaborative_id}"
            )

    # Update organization relationships for a collaborative.
    @strawberry_django.mutation(
        handle_django_errors=True,
        extensions=[
            TrackModelActivity(
                verb="updated",
                get_data=lambda result, collaborative_id, supporter_organization_ids, partner_organization_ids, **kwargs: {
                    "collaborative_id": collaborative_id,
                    "collaborative_title": result.title,
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
        name="update_collaborative_organization_relationships",
        attributes={"component": "collaborative", "operation": "mutation"},
    )
    def update_collaborative_organization_relationships(
        self,
        info: Info,
        collaborative_id: str,
        supporter_organization_ids: List[strawberry.ID],
        partner_organization_ids: List[strawberry.ID],
    ) -> TypeCollaborative:
        """Update organization relationships for a collaborative."""
        try:
            collaborative = Collaborative.objects.get(id=collaborative_id)
        except Collaborative.DoesNotExist:
            raise ValueError(
                f"Collaborative with ID {collaborative_id} does not exist."
            )

        if collaborative.status != CollaborativeStatus.DRAFT:
            raise ValueError(
                f"Collaborative with ID {collaborative_id} is not in draft status."
            )

        # Clear existing relationships
        CollaborativeOrganizationRelationship.objects.filter(
            collaborative=collaborative
        ).delete()

        # Add supporter organizations
        supporter_orgs = Organization.objects.filter(id__in=supporter_organization_ids)
        for org in supporter_orgs:
            CollaborativeOrganizationRelationship.objects.create(
                collaborative=collaborative,
                organization=org,
                relationship_type=OrganizationRelationshipType.SUPPORTER,
            )

        # Add partner organizations
        partner_orgs = Organization.objects.filter(id__in=partner_organization_ids)
        for org in partner_orgs:
            CollaborativeOrganizationRelationship.objects.create(
                collaborative=collaborative,
                organization=org,
                relationship_type=OrganizationRelationshipType.PARTNER,
            )

        return TypeCollaborative.from_django(collaborative)


def _update_collaborative_geographies(
    collaborative: Collaborative, geography_ids: List[int]
) -> None:
    """Update geographies for a collaborative."""
    collaborative.geographies.clear()
    geographies = Geography.objects.filter(id__in=geography_ids)
    collaborative.geographies.add(*geographies)
