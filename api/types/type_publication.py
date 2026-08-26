import uuid
from datetime import date, datetime
from typing import List, Optional, cast

import strawberry
import strawberry_django
from strawberry.enum import EnumType
from strawberry.types import Info

from api.models import (
    Collaborative,
    Publication,
    PublicationBlock,
    ResourceType,
    UseCase,
)
from api.types.base_type import BaseType
from api.types.type_geo import TypeGeo
from api.types.type_organization import TypeOrganization
from api.types.type_sector import TypeSector
from api.utils.enums import (
    CollaborativeStatus,
    DatasetLicense,
    PublicationBlockType,
    PublicationStatus,
    UseCaseStatus,
)
from authorization.types import TypeUser


def _caller_can_see_links(info: Info, publication: Publication) -> bool:
    """Whether the caller may see where a resource is linked (owner / org / superuser).

    The 'linked to N' flag is the owner's view; outsiders (including anonymous
    visitors to a public resource) must not learn which projects reference it.
    """
    user = getattr(info.context, "user", None)
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if user.is_superuser:
        return True
    if publication.user and publication.user == user:
        return True
    if publication.organization:
        from authorization.models import OrganizationMembership

        return OrganizationMembership.objects.filter(
            user=user, organization=publication.organization
        ).exists()
    return False


# Fields are enumerated on every type below — never ``fields="__all__"`` — so a
# future column is never silently published.
publication_status: EnumType = strawberry.enum(PublicationStatus)  # type: ignore
publication_block_type: EnumType = strawberry.enum(PublicationBlockType)  # type: ignore
publication_license: EnumType = strawberry.enum(DatasetLicense)  # type: ignore


@strawberry.type
class TypeLinkedReference:
    """A lightweight pointer to a Use Case / Collaborative a resource is linked into.

    Kept minimal (id / title / slug) so ``TypePublication`` can name where it's
    linked without importing the heavier Use Case / Collaborative types.
    """

    id: str
    title: str
    slug: str


@strawberry_django.type(ResourceType)
class TypeResourceType(BaseType):
    """Type for the admin-managed Resource Type lookup."""

    id: uuid.UUID
    name: str
    slug: Optional[str]
    is_active: bool


@strawberry_django.type(PublicationBlock)
class TypePublicationBlock(BaseType):
    """Type for one content block (a file XOR a YouTube embed)."""

    id: uuid.UUID
    position: int
    block_type: publication_block_type
    file_name: str
    file_format: str
    file_size: Optional[int]
    youtube_url: Optional[str]
    youtube_video_id: str


@strawberry_django.filter(Publication)
class PublicationFilter:
    """Filter for publications."""

    id: Optional[uuid.UUID]
    status: Optional[publication_status]
    resource_type: Optional[uuid.UUID]


@strawberry_django.order(Publication)
class PublicationOrder:
    """Order for publications."""

    title: strawberry.auto
    created: strawberry.auto
    modified: strawberry.auto


@strawberry_django.type(
    Publication,
    filters=PublicationFilter,
    pagination=True,
    order=PublicationOrder,  # type: ignore
)
class TypePublication(BaseType):
    """Type for a Publication (UI 'Resource')."""

    id: uuid.UUID
    title: str
    description: Optional[str]
    slug: str
    status: publication_status
    authors: List[str]
    publication_date: Optional[date]
    license: publication_license
    external_source_link: Optional[str]
    download_count: int
    created: datetime
    modified: datetime
    organization: Optional["TypeOrganization"]
    user: Optional["TypeUser"]
    resource_type: Optional["TypeResourceType"]

    @strawberry.field
    def sectors(self, info: Info) -> List["TypeSector"]:
        """Sectors tagged on this resource."""
        try:
            instance = cast(Publication, self)
            return TypeSector.from_django_list(instance.sectors.all())
        except (AttributeError, Publication.DoesNotExist):
            return []

    @strawberry.field
    def geographies(self, info: Info) -> List["TypeGeo"]:
        """Geographies tagged on this resource."""
        try:
            instance = cast(Publication, self)
            return TypeGeo.from_django_list(instance.geographies.all())
        except (AttributeError, Publication.DoesNotExist):
            return []

    @strawberry.field
    def blocks(self, info: Info) -> List["TypePublicationBlock"]:
        """Ordered content blocks of this resource.

        ``PublicationBlock`` orders by ``position`` in its Meta, so ``.all()`` is
        already position-ordered and reuses the listing's prefetch cache — an
        explicit ``.order_by`` here would re-query and reintroduce an N+1.
        """
        try:
            instance = cast(Publication, self)
            return TypePublicationBlock.from_django_list(instance.blocks.all())
        except (AttributeError, Publication.DoesNotExist):
            return []

    @strawberry.field
    def is_individual_publication(self) -> bool:
        """True when owned by an individual rather than an organization."""
        return self.organization is None

    @strawberry.field
    def linked_usecases(self, info: Info) -> List["TypeLinkedReference"]:
        """Use Cases this resource is linked into — the owner's 'linked to N' flag.

        Only the owner / org members may see this, and only published projects
        are named, so a private draft (possibly in another org that linked this
        public resource) never leaks its title through here.
        """
        try:
            instance = cast(Publication, self)
            if not _caller_can_see_links(info, instance):
                return []
            usecases: List[UseCase] = list(
                UseCase.objects.filter(publications=instance, status=UseCaseStatus.PUBLISHED)
            )
            return [
                TypeLinkedReference(id=str(uc.id), title=uc.title or "", slug=uc.slug or "")
                for uc in usecases
            ]
        except (AttributeError, Publication.DoesNotExist):
            return []

    @strawberry.field
    def linked_collaboratives(self, info: Info) -> List["TypeLinkedReference"]:
        """Collaboratives this resource is linked into — the owner's 'linked to N' flag."""
        try:
            instance = cast(Publication, self)
            if not _caller_can_see_links(info, instance):
                return []
            collabs: List[Collaborative] = list(
                Collaborative.objects.filter(
                    publications=instance, status=CollaborativeStatus.PUBLISHED
                )
            )
            return [
                TypeLinkedReference(
                    id=str(collab.id), title=collab.title or "", slug=collab.slug or ""
                )
                for collab in collabs
            ]
        except (AttributeError, Publication.DoesNotExist):
            return []

    @strawberry.field
    def linked_count(self, info: Info) -> int:
        """Published Use Cases + Collaboratives this resource is linked into (owner only)."""
        try:
            instance = cast(Publication, self)
            if not _caller_can_see_links(info, instance):
                return 0
            usecases = UseCase.objects.filter(
                publications=instance, status=UseCaseStatus.PUBLISHED
            ).count()
            collabs = Collaborative.objects.filter(
                publications=instance, status=CollaborativeStatus.PUBLISHED
            ).count()
            return usecases + collabs
        except (AttributeError, Publication.DoesNotExist):
            return 0
