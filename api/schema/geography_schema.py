"""Schema definitions for geographies."""

import strawberry
import strawberry_django

from api.models import Geography
from api.types.type_geo import TypeGeo


@strawberry.type(name="Query")
class Query:
    """Queries for geographies."""

    geographies: list[TypeGeo] = strawberry_django.field()
    geography: TypeGeo = strawberry_django.field()
