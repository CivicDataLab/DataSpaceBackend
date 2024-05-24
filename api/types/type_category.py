from typing import Optional

import strawberry_django
from strawberry import auto

from api.models import Category


@strawberry_django.type(Category, pagination=True, fields="__all__")
class TypeCategory:
    parent_id: Optional["TypeCategory"]
