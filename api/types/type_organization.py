from typing import Optional

import strawberry
import strawberry_django
from strawberry import auto

from api.models import Organization


@strawberry_django.filter(Organization)
class OrganizationFilter:
    id: auto
    slug: auto


@strawberry_django.type(Organization, pagination=True, fields="__all__", filters=OrganizationFilter)
class TypeOrganization:
    parent_id: Optional["TypeOrganization"]
    dataset_count: int

    @strawberry.field
    def dataset_count(self: Organization, info) -> int:
        return self.dataset_set.count()
