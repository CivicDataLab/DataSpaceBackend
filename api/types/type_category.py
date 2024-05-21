from typing import Optional

import strawberry_django
from strawberry import auto

from api.models import Category


@strawberry_django.type(Category, pagination=True)
class TypeCategory:
    name: auto
    description: auto
    parent_id: Optional["TypeCategory"]
