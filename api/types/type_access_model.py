from typing import TYPE_CHECKING, List, Optional, cast

import strawberry
from strawberry import auto
from strawberry_django import type

from api.models import AccessModel, AccessModelResource
from api.types.base_type import BaseType

if TYPE_CHECKING:
    from api.types.type_dataset import TypeDataset
    from api.types.type_organization import TypeOrganization


@type(AccessModelResource)
class TypeAccessModelResourceFields(BaseType):
    """Type for access model resource fields."""

    id: auto
    resource: auto
    access_model: "TypeAccessModel"
    created: auto
    modified: auto


@type(AccessModel)
class TypeAccessModel(BaseType):
    """Type for access model."""

    id: auto
    name: auto
    description: auto
    dataset: "TypeDataset"
    type: auto
    organization: "TypeOrganization"
    created: auto
    modified: auto

    @strawberry.field
    def model_resources(self) -> List[TypeAccessModelResourceFields]:
        """Get access model resources for this access model.

        Returns:
            List[TypeAccessModelResourceFields]: List of access model resources
        """
        try:
            queryset = AccessModelResource.objects.filter(access_model_id=self.id)
            return TypeAccessModelResourceFields.from_django_list(queryset)
        except (AttributeError, AccessModelResource.DoesNotExist):
            return []
