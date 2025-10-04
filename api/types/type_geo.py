from typing import Optional

import strawberry_django
from strawberry import auto

from api.models import Geography
from api.types.base_type import BaseType


@strawberry_django.type(Geography)
class TypeGeo(BaseType):
    id: auto
    name: auto
    code: auto
    type: auto
    parent_id: Optional["TypeGeo"]
