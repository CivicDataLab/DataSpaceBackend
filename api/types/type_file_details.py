from typing import Optional

import strawberry
from strawberry import auto
from strawberry_django import type

from api.models import ResourceFileDetails
from api.types.base_type import BaseType


@type(ResourceFileDetails)
class TypeFileDetails(BaseType):
    id: auto
    resource: auto
    file: auto
    size: auto
    format: auto
    created: auto
    modified: auto
