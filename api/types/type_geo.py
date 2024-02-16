import datetime
from typing import Optional

import strawberry
import strawberry_django
from strawberry import auto

from api.models import Geography

@strawberry_django.type(Geography)
class TypeGeo:
    name: auto
    code: auto
    type: auto
    parent_id: Optional["TypeGeo"]