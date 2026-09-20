"""GraphQL types for third-party platform imports (link-only)."""

from datetime import datetime
from typing import List, Optional

import strawberry
import strawberry_django
from strawberry import auto
from strawberry.enum import EnumType

from api.models import DatasetSource
from api.services.platform_importers import PlatformDatasetInfo
from api.types.base_type import BaseType
from api.utils.enums import ImportPlatform

import_platform_enum: EnumType = strawberry.enum(ImportPlatform)  # type: ignore


@strawberry_django.type(DatasetSource)
class TypeDatasetSource(BaseType):
    """Where an imported dataset came from."""

    id: auto
    platform: import_platform_enum  # type: ignore
    source_identifier: auto
    source_url: auto
    source_author: auto
    source_license: auto
    source_last_updated: auto
    imported_at: auto
    last_synced_at: auto


@strawberry.type
class TypePlatformDatasetPreview:
    """What an import *would* create — returned by the preview query, no side effects."""

    platform: import_platform_enum  # type: ignore
    identifier: str
    title: str
    description: str
    source_url: str
    author: str
    license: str
    mapped_license: str
    tags: List[str]
    last_updated: Optional[datetime]

    @classmethod
    def from_info(cls, info: PlatformDatasetInfo) -> "TypePlatformDatasetPreview":
        return cls(
            platform=ImportPlatform(info.platform),
            identifier=info.identifier,
            title=info.title,
            description=info.description,
            source_url=info.source_url,
            author=info.author,
            license=info.license,
            mapped_license=info.mapped_license,
            tags=list(info.tags),
            last_updated=info.last_updated,
        )
