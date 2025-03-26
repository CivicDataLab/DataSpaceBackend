from typing import TYPE_CHECKING, Optional

import strawberry
import strawberry_django
from strawberry import auto

from api.models import ResourceMetadata
from api.types.base_type import BaseType
from api.types.type_metadata import TypeMetadata


@strawberry_django.type(ResourceMetadata, fields="__all__")
class TypeResourceMetadata(BaseType):
    """Type for resource metadata."""

    id: auto
    metadata_item: TypeMetadata
    value: auto
    created: auto
    modified: auto
