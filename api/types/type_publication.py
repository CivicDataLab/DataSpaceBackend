import uuid
from datetime import date, datetime
from typing import List, Optional, cast

import strawberry
import strawberry_django
from strawberry.enum import EnumType
from strawberry.types import Info

from api.models import Publication, PublicationBlock, ResourceType
from api.types.base_type import BaseType
from api.types.type_geo import TypeGeo
from api.types.type_organization import TypeOrganization
from api.types.type_sector import TypeSector
from api.utils.enums import DatasetLicense, PublicationBlockType, PublicationStatus
from authorization.types import TypeUser

# Fields are enumerated on every type below — never ``fields="__all__"`` — so a
# future column is never silently published.
publication_status: EnumType = strawberry.enum(PublicationStatus)  # type: ignore
publication_block_type: EnumType = strawberry.enum(PublicationBlockType)  # type: ignore
publication_license: EnumType = strawberry.enum(DatasetLicense)  # type: ignore


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
        """Ordered content blocks of this resource."""
        try:
            instance = cast(Publication, self)
            return TypePublicationBlock.from_django_list(instance.blocks.all().order_by("position"))
        except (AttributeError, Publication.DoesNotExist):
            return []

    @strawberry.field
    def is_individual_publication(self) -> bool:
        """True when owned by an individual rather than an organization."""
        return self.organization is None
