from typing import TYPE_CHECKING, Optional

import strawberry
import strawberry_django
from strawberry import auto

from api.models import ResourceMetadata
from api.types import TypeMetadata
from api.types.base_type import BaseType

if TYPE_CHECKING:
    from api.types.type_resource import TypeResource


@strawberry_django.type(ResourceMetadata, fields="__all__")
class TypeResourceMetadata(BaseType):
    """Type for resource metadata."""

    id: auto
    resource: "TypeResource"
    metadata_item: TypeMetadata
    value: auto
    created: auto
    modified: auto
