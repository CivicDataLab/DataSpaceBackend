from typing import Optional

import strawberry
import strawberry_django
from strawberry import auto

from api.models import SDG
from api.types.base_type import BaseType


@strawberry_django.filter(SDG)
class SDGFilter:
    """Filter class for SDG model."""

    id: auto
    code: auto
    name: auto


@strawberry_django.order(SDG)
class SDGOrder:
    """Order class for SDG model."""

    number: auto
    code: auto
    name: auto


@strawberry_django.type(
    SDG,
    pagination=True,
    fields="__all__",
    filters=SDGFilter,
    order=SDGOrder,  # type: ignore
)
class TypeSDG(BaseType):
    """GraphQL type for SDG model."""

    pass
