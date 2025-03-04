import uuid
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

import strawberry
from strawberry import auto
from strawberry.types import Info
from strawberry_django import type

from api.models import AccessModel, AccessModelResource
from api.types.base_type import BaseType
from api.types.type_organization import TypeOrganization
from api.types.type_resource import TypeResource


@type(AccessModelResource)
class TypeAccessModelResourceFields(BaseType):
    """Type for access model resource fields."""

    id: strawberry.ID
    resource: "TypeResource"
    access_model: "TypeAccessModel"
    fields: List[str]
    created: datetime
    modified: datetime


@type(AccessModel)
class TypeAccessModel(BaseType):
    """Type for access model."""

    id: uuid.UUID
    name: str
    description: Optional[str]
    type: str
    organization: "TypeOrganization"
    created: datetime
    modified: datetime

    @strawberry.field
    def resource_fields(self, info: Info) -> List[TypeAccessModelResourceFields]:
        """Get resources for this access model."""
        try:
            queryset = AccessModelResource.objects.filter(access_model_id=self.id)
            return TypeAccessModelResourceFields.from_django_list(queryset)
        except (AttributeError, AccessModelResource.DoesNotExist):
            return []
