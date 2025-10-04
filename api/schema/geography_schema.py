"""Schema definitions for geographies."""

from typing import List

import strawberry
import strawberry_django
from strawberry.types import Info

from api.models import Geography
from api.types.type_geo import TypeGeo


@strawberry.type(name="Query")
class Query:
    """Queries for geographies."""

    @strawberry_django.field
    def geographies(self, info: Info) -> List[TypeGeo]:
        """Get all geographies."""
        geographies = Geography.objects.all()
        return TypeGeo.from_django_list(geographies)

    @strawberry_django.field
    def geography(self, info: Info, id: int) -> TypeGeo:
        """Get a single geography by ID."""
        geography = Geography.objects.get(id=id)
        return TypeGeo.from_django(geography)
