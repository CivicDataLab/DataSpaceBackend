from typing import Any, Optional

import strawberry
import strawberry_django
from strawberry import Info, auto

from api.models import Organization
from api.types.base_type import BaseType


@strawberry_django.filter(Organization)
class OrganizationFilter:
    id: auto
    slug: auto


@strawberry_django.type(
    Organization, pagination=True, fields="__all__", filters=OrganizationFilter
)
class TypeOrganization(BaseType):
    parent_id: Optional["TypeOrganization"]

    @strawberry.field
    def dataset_count(self: Any) -> int:
        return int(self.datasets.count())
