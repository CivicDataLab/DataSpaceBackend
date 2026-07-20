"""Schema definitions for publications (UI "Resource").

Docs: ./publication_architecture.md

This is a flow file: each resolver reads as a short sequence of named helper
calls. The metadata validation, row writes, scoping and pagination bounds all
live in ``api/services/publication_service.py``; permission/role logic lives in
``authorization/permissions.py``. Nothing here reaches into the ORM or business
rules directly.
"""

import datetime
import uuid
from typing import List, Optional

import strawberry
import strawberry_django
from django.core.exceptions import ValidationError as DjangoValidationError
from strawberry.file_uploads import Upload
from strawberry.types import Info

from api.models import Publication, PublicationBlock, ResourceType
from api.schema.base_mutation import BaseMutation, MutationResponse
from api.services.publication_blocks import (
    add_file_block,
    add_youtube_block,
    remove_block,
    reorder_blocks,
    replace_block_file,
)
from api.services.publication_service import (
    apply_publication_update,
    create_publication,
    get_scoped_publications,
    resolve_pagination,
    set_publication_status,
    validate_publication_metadata,
)
from api.types.type_publication import (
    PublicationFilter,
    PublicationOrder,
    TypePublication,
    TypePublicationBlock,
    TypeResourceType,
    publication_license,
)
from api.utils.enums import PublicationStatus
from api.utils.graphql_telemetry import trace_resolver
from authorization.permissions import (
    AllowPublishedPublications,
    ChangePublicationPermission,
    CreatePublicationPermission,
    DeletePublicationPermission,
    PublishPublicationPermission,
)


@strawberry.input
class CreatePublicationInput:
    """Metadata for a new resource. All fields validated at the boundary."""

    title: str
    description: str
    authors: List[str]
    publication_date: datetime.date
    license: publication_license
    resource_type_id: uuid.UUID
    sector_ids: List[uuid.UUID]
    geography_ids: List[int]
    external_source_link: Optional[str] = None


@strawberry.input
class UpdatePublicationInput:
    """Partial edit to a resource — only the fields provided are touched."""

    id: uuid.UUID
    title: Optional[str] = None
    description: Optional[str] = None
    authors: Optional[List[str]] = None
    publication_date: Optional[datetime.date] = None
    license: Optional[publication_license] = None
    resource_type_id: Optional[uuid.UUID] = None
    sector_ids: Optional[List[uuid.UUID]] = None
    geography_ids: Optional[List[int]] = None
    external_source_link: Optional[str] = None


@strawberry.type(name="Query")
class Query:
    """Queries for publications."""

    @strawberry.field
    @trace_resolver(name="get_resource_types", attributes={"component": "publication"})
    def resource_types(self, info: Info) -> List[TypeResourceType]:
        """List the active Resource Types for a create/edit form's dropdown."""
        return TypeResourceType.from_django_list(
            ResourceType.objects.filter(is_active=True).order_by("name")
        )

    @strawberry.field(
        permission_classes=[AllowPublishedPublications],  # type: ignore[list-item]
    )
    @trace_resolver(name="get_publication", attributes={"component": "publication"})
    def get_publication(self, info: Info, publication_id: uuid.UUID) -> Optional[TypePublication]:
        """Get a single resource by id (drafts gated to owner/org by the permission)."""
        try:
            return TypePublication.from_django(Publication.objects.get(id=publication_id))
        except Publication.DoesNotExist:
            return None

    @strawberry.field
    @trace_resolver(name="get_publications", attributes={"component": "publication"})
    def publications(
        self,
        info: Info,
        filters: Optional[PublicationFilter] = strawberry.UNSET,
        pagination: Optional[strawberry_django.pagination.OffsetPaginationInput] = strawberry.UNSET,
        order: Optional[PublicationOrder] = strawberry.UNSET,
        include_public: Optional[bool] = False,
    ) -> List[TypePublication]:
        """List resources, scoped to the caller and paginated with server limits."""
        user = info.context.user
        organization = info.context.context.get("organization")

        # Scope to org / owner / anonymous and optionally union in the public set.
        queryset = get_scoped_publications(
            user=user, organization=organization, include_public=bool(include_public)
        )

        # Apply client filters and ordering, then enforce a bounded page window.
        if filters is not strawberry.UNSET:
            queryset = strawberry_django.filters.apply(filters, queryset, info)
        if order is not strawberry.UNSET:
            queryset = strawberry_django.ordering.apply(order, queryset, info)

        offset, limit = resolve_pagination(
            getattr(pagination, "offset", None) if pagination is not strawberry.UNSET else None,
            getattr(pagination, "limit", None) if pagination is not strawberry.UNSET else None,
        )
        return TypePublication.from_django_list(queryset[offset : offset + limit])


@strawberry.type(name="Mutation")
class Mutation:
    """Mutations for publications."""

    @strawberry.mutation
    @BaseMutation.mutation(
        permission_classes=[CreatePublicationPermission],
        trace_name="create_publication",
        trace_attributes={"component": "publication"},
        track_activity={
            "verb": "created",
            "get_data": lambda result, **kwargs: {"publication_id": str(result.id)},
        },
    )
    def create_publication(
        self, info: Info, input: CreatePublicationInput
    ) -> MutationResponse[TypePublication]:
        """Create a DRAFT resource owned by the caller's org or the user."""
        user = info.context.user
        organization = info.context.context.get("organization")

        # Reject missing/invalid metadata before any row is written.
        resource_type = validate_publication_metadata(
            title=input.title,
            description=input.description,
            authors=input.authors,
            publication_date=input.publication_date,
            license_value=input.license.value if input.license else None,
            resource_type_id=input.resource_type_id,
            sector_ids=input.sector_ids,
            geography_ids=input.geography_ids,
            external_source_link=input.external_source_link,
        )

        # Create the draft and wire its sector/geography tags.
        publication = create_publication(
            user=user,
            organization=organization,
            title=input.title,
            description=input.description,
            authors=input.authors,
            publication_date=input.publication_date,
            license_value=input.license.value,
            resource_type=resource_type,
            sector_ids=input.sector_ids,
            geography_ids=input.geography_ids,
            external_source_link=input.external_source_link,
        )
        return MutationResponse.success_response(TypePublication.from_django(publication))

    @strawberry.mutation
    @BaseMutation.mutation(
        permission_classes=[ChangePublicationPermission],
        trace_name="update_publication",
        trace_attributes={"component": "publication"},
        track_activity={
            "verb": "updated",
            "get_data": lambda result, **kwargs: {"publication_id": str(result.id)},
        },
    )
    def update_publication(
        self, info: Info, input: UpdatePublicationInput
    ) -> MutationResponse[TypePublication]:
        """Apply a partial metadata edit to an existing resource."""
        # Load the target, or surface a clean not-found.
        publication = _get_publication_or_raise(input.id)

        # Update only the provided fields, validating each.
        publication = apply_publication_update(
            publication,
            title=input.title,
            description=input.description,
            authors=input.authors,
            publication_date=input.publication_date,
            license_value=input.license.value if input.license else None,
            resource_type_id=input.resource_type_id,
            sector_ids=input.sector_ids,
            geography_ids=input.geography_ids,
            external_source_link=input.external_source_link,
        )
        return MutationResponse.success_response(TypePublication.from_django(publication))

    @strawberry.mutation
    @BaseMutation.mutation(
        permission_classes=[PublishPublicationPermission],
        trace_name="publish_publication",
        trace_attributes={"component": "publication"},
        track_activity={
            "verb": "published",
            "get_data": lambda result, **kwargs: {"publication_id": str(result.id)},
        },
    )
    def publish_publication(
        self, info: Info, publication_id: uuid.UUID
    ) -> MutationResponse[TypePublication]:
        """Flip a resource to PUBLISHED (self-serve, no moderation)."""
        publication = _get_publication_or_raise(publication_id)

        # Mark it published — the index signal picks up the visibility change.
        publication = set_publication_status(publication, PublicationStatus.PUBLISHED)
        return MutationResponse.success_response(TypePublication.from_django(publication))

    @strawberry.mutation
    @BaseMutation.mutation(
        permission_classes=[PublishPublicationPermission],
        trace_name="unpublish_publication",
        trace_attributes={"component": "publication"},
        track_activity={
            "verb": "unpublished",
            "get_data": lambda result, **kwargs: {"publication_id": str(result.id)},
        },
    )
    def unpublish_publication(
        self, info: Info, publication_id: uuid.UUID
    ) -> MutationResponse[TypePublication]:
        """Flip a resource back to DRAFT — hidden from public reads, links untouched."""
        publication = _get_publication_or_raise(publication_id)

        # Back to draft; the render-time filters do the hiding, no links change.
        publication = set_publication_status(publication, PublicationStatus.DRAFT)
        return MutationResponse.success_response(TypePublication.from_django(publication))

    @strawberry.mutation
    @BaseMutation.mutation(
        permission_classes=[DeletePublicationPermission],
        trace_name="delete_publication",
        trace_attributes={"component": "publication"},
        track_activity={
            "verb": "deleted",
            "get_data": lambda result, **kwargs: {
                "publication_id": str(kwargs.get("publication_id")),
                "success": result,
            },
        },
    )
    def delete_publication(self, info: Info, publication_id: uuid.UUID) -> MutationResponse[bool]:
        """Hard-delete a resource — cascades its blocks, clears its links."""
        publication = _get_publication_or_raise(publication_id)

        # FK cascade drops blocks; M2M join rows auto-clear on delete.
        publication.delete()
        return MutationResponse.success_response(True)

    @strawberry.mutation
    @BaseMutation.mutation(
        permission_classes=[ChangePublicationPermission],
        trace_name="add_publication_file_block",
        trace_attributes={"component": "publication"},
    )
    def add_publication_file_block(
        self, info: Info, publication_id: uuid.UUID, file: Upload
    ) -> MutationResponse[TypePublicationBlock]:
        """Append an uploaded file as the next content block (validated server-side)."""
        publication = _get_publication_or_raise(publication_id)

        # Validate + store the file as the last block.
        block = add_file_block(publication, file)
        return MutationResponse.success_response(TypePublicationBlock.from_django(block))

    @strawberry.mutation
    @BaseMutation.mutation(
        permission_classes=[ChangePublicationPermission],
        trace_name="add_publication_youtube_block",
        trace_attributes={"component": "publication"},
    )
    def add_publication_youtube_block(
        self, info: Info, publication_id: uuid.UUID, youtube_url: str
    ) -> MutationResponse[TypePublicationBlock]:
        """Append a YouTube link as the next content block (validated server-side)."""
        publication = _get_publication_or_raise(publication_id)

        # Validate the url + extract its video id, then store the block.
        block = add_youtube_block(publication, youtube_url)
        return MutationResponse.success_response(TypePublicationBlock.from_django(block))

    @strawberry.mutation
    @BaseMutation.mutation(
        permission_classes=[ChangePublicationPermission],
        trace_name="replace_publication_block_file",
        trace_attributes={"component": "publication"},
    )
    def replace_publication_block_file(
        self, info: Info, block_id: uuid.UUID, file: Upload
    ) -> MutationResponse[TypePublicationBlock]:
        """Swap a file block's file, deleting the old one from disk."""
        block = _get_block_or_raise(block_id)

        # Replace in place — same block id, old file removed.
        block = replace_block_file(block, file)
        return MutationResponse.success_response(TypePublicationBlock.from_django(block))

    @strawberry.mutation
    @BaseMutation.mutation(
        permission_classes=[ChangePublicationPermission],
        trace_name="remove_publication_block",
        trace_attributes={"component": "publication"},
    )
    def remove_publication_block(self, info: Info, block_id: uuid.UUID) -> MutationResponse[bool]:
        """Remove a content block and renumber the rest contiguously."""
        block = _get_block_or_raise(block_id)

        # Delete + renumber siblings; the signal removes the file from disk.
        remove_block(block)
        return MutationResponse.success_response(True)

    @strawberry.mutation
    @BaseMutation.mutation(
        permission_classes=[ChangePublicationPermission],
        trace_name="reorder_publication_blocks",
        trace_attributes={"component": "publication"},
    )
    def reorder_publication_blocks(
        self, info: Info, publication_id: uuid.UUID, block_ids: List[uuid.UUID]
    ) -> MutationResponse[TypePublication]:
        """Set the content blocks' order to the given block-id sequence."""
        publication = _get_publication_or_raise(publication_id)

        # Reassign positions to match the requested order.
        reorder_blocks(publication, block_ids)
        publication.refresh_from_db()
        return MutationResponse.success_response(TypePublication.from_django(publication))


def _get_publication_or_raise(publication_id: uuid.UUID) -> Publication:
    """Load a publication by id or raise a clean validation error."""
    try:
        return Publication.objects.get(id=publication_id)
    except Publication.DoesNotExist:
        raise DjangoValidationError(f"Resource with id {publication_id} does not exist.")


def _get_block_or_raise(block_id: uuid.UUID) -> PublicationBlock:
    """Load a content block by id or raise a clean validation error."""
    try:
        return PublicationBlock.objects.get(id=block_id)
    except PublicationBlock.DoesNotExist:
        raise DjangoValidationError(f"Content block {block_id} does not exist.")
