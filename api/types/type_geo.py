from typing import Optional

import strawberry
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

    @strawberry.field(description="Parent geography")
    def parent_id(self) -> Optional["TypeGeo"]:
        """Get parent geography."""
        if self.parent_id:  # type: ignore
            return TypeGeo.from_django(self.parent_id)  # type: ignore
        return None
