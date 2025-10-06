from typing import List, Optional

import strawberry
import strawberry_django
from strawberry import Info, auto, field
from strawberry.enum import EnumType

from api.activities import collaborative
from api.models import (
    Collaborative,
    CollaborativeMetadata,
    CollaborativeOrganizationRelationship,
    Organization,
)
from api.types.base_type import BaseType
from api.types.type_collaborative_metadata import TypeCollaborativeMetadata
from api.types.type_collaborative_organization import (
    TypeCollaborativeOrganizationRelationship,
)
from api.types.type_dataset import TypeDataset, TypeTag
from api.types.type_geo import TypeGeo
from api.types.type_organization import TypeOrganization
from api.types.type_sdg import TypeSDG
from api.types.type_sector import TypeSector
from api.types.type_usecase import TypeUseCase
from api.utils.enums import CollaborativeStatus, OrganizationRelationshipType
from authorization.types import TypeUser

collaborative_status = strawberry.enum(CollaborativeStatus)  # type: ignore


@strawberry_django.filter(Collaborative)
class CollaborativeFilter:
    """Filter class for Collaborative model."""

    id: auto
    slug: auto
    status: Optional[collaborative_status]


@strawberry_django.order(Collaborative)
class CollaborativeOrder:
    """Order class for Collaborative model."""

    title: auto
    created: auto
    modified: auto


@strawberry_django.type(
    Collaborative,
    pagination=True,
    fields="__all__",
    filters=CollaborativeFilter,
    order=CollaborativeOrder,  # type:ignore
)
class TypeCollaborative(BaseType):
    """GraphQL type for Collaborative model."""

    user: TypeUser = strawberry.field(description="User who created this collaborative")
    organization: Optional[TypeOrganization] = strawberry.field(
        description="Organization associated with this collaborative"
    )
    platform_url: Optional[str] = strawberry.field(
        description="URL of the platform where this collaborative is published"
    )

    @strawberry.field(
        description="Check if this collaborative is created by an individual user."
    )
    def is_individual_collaborative(self) -> bool:
        """Check if this collaborative is created by an individual user."""
        return self.organization is None

    @strawberry.field(description="Get geographies associated with this collaborative.")
    def geographies(self) -> Optional[List[TypeGeo]]:
        """Get geographies associated with this collaborative."""
        try:
            queryset = self.geographies.all().order_by("name")  # type: ignore
            if not queryset.exists():
                return []
            return TypeGeo.from_django_list(queryset)
        except Exception:
            return []

    @strawberry.field(description="Get datasets associated with this collaborative.")
    def datasets(self) -> Optional[List["TypeDataset"]]:
        """Get datasets associated with this collaborative."""
        try:
            # Return raw Django objects and let Strawberry handle conversion
            queryset = self.datasets.all().order_by("-modified")  # type: ignore
            if not queryset.exists():
                return []
            return TypeDataset.from_django_list(queryset)
        except Exception:
            return []

    @strawberry.field(description="Get use cases associated with this collaborative.")
    def use_cases(self) -> Optional[List["TypeUseCase"]]:
        """Get use cases associated with this collaborative."""
        try:
            queryset = self.use_cases.all().order_by("-modified")  # type: ignore
            if not queryset.exists():
                return []
            return TypeUseCase.from_django_list(queryset)
        except Exception:
            return []

    @strawberry.field(
        description="Get the count of datasets associated with this collaborative."
    )
    def dataset_count(self: "TypeCollaborative", info: Info) -> int:
        """Get the count of datasets associated with this collaborative."""
        try:
            return self.datasets.count()  # type: ignore
        except Exception:
            return 0

    @strawberry.field(
        description="Get the count of use cases associated with this collaborative."
    )
    def use_case_count(self: "TypeCollaborative", info: Info) -> int:
        """Get the count of use cases associated with this collaborative."""
        try:
            return self.use_cases.count()  # type: ignore
        except Exception:
            return 0

    @strawberry.field(description="Get publishers associated with this collaborative.")
    def publishers(self) -> Optional[List["TypeOrganization"]]:
        """Get publishers associated with this collaborative."""
        try:
            queryset = Organization.objects.filter(datasets__in=self.datasets.all()).distinct()  # type: ignore
            if not queryset.exists():
                return []
            return TypeOrganization.from_django_list(queryset)
        except Exception:
            return []

    @strawberry.field(description="Get sectors associated with this collaborative.")
    def sectors(self) -> Optional[List["TypeSector"]]:
        """Get sectors associated with this collaborative."""
        try:
            queryset = self.sectors.all().order_by("name")  # type: ignore
            if not queryset.exists():
                return []
            return TypeSector.from_django_list(queryset)
        except Exception:
            return []

    @strawberry.field(description="Get SDGs associated with this collaborative.")
    def sdgs(self) -> Optional[List["TypeSDG"]]:
        """Get SDGs associated with this collaborative."""
        try:
            queryset = self.sdgs.all()  # type: ignore
            if not queryset.exists():
                return []
            return TypeSDG.from_django_list(queryset)
        except Exception:
            return []

    @strawberry.field(description="Get tags associated with this collaborative.")
    def tags(self) -> Optional[List["TypeTag"]]:
        """Get tags associated with this collaborative."""
        try:
            queryset = self.tags.all()  # type: ignore
            if not queryset.exists():
                return []
            return TypeTag.from_django_list(queryset)
        except Exception:
            return []

    @strawberry.field(description="Get metadata associated with this collaborative.")
    def metadata(self) -> Optional[List["TypeCollaborativeMetadata"]]:
        """Get metadata associated with this collaborative."""
        try:
            queryset = CollaborativeMetadata.objects.filter(collaborative=self)  # type: ignore
            if not queryset.exists():
                return []
            return TypeCollaborativeMetadata.from_django_list(queryset)
        except Exception:
            return []

    @strawberry.field(
        description="Get contributors associated with this collaborative."
    )
    def contributors(self) -> Optional[List["TypeUser"]]:
        """Get contributors associated with this collaborative."""
        try:
            queryset = self.contributors.all().order_by("first_name")  # type: ignore
            if not queryset.exists():
                return []
            return TypeUser.from_django_list(queryset)
        except Exception:
            return []

    @strawberry.field(
        description="Get organization relationships associated with this collaborative."
    )
    def organization_relationships(
        self,
    ) -> Optional[List["TypeCollaborativeOrganizationRelationship"]]:
        """Get organization relationships associated with this collaborative."""
        try:
            queryset = CollaborativeOrganizationRelationship.objects.filter(collaborative=self)  # type: ignore
            if not queryset.exists():
                return []
            return TypeCollaborativeOrganizationRelationship.from_django_list(queryset)
        except Exception:
            return []

    @strawberry.field(
        description="Get supporting organizations for this collaborative."
    )
    def supporting_organizations(self) -> Optional[List["TypeOrganization"]]:
        """Get supporting organizations for this collaborative."""
        try:
            relationships = (
                CollaborativeOrganizationRelationship.objects.filter(
                    collaborative=self,  # type: ignore
                    relationship_type=OrganizationRelationshipType.SUPPORTER,
                )
                .select_related("organization")
                .order_by("organization__name")
            )

            if not relationships.exists():
                return []

            organizations = [rel.organization for rel in relationships]  # type: ignore
            return TypeOrganization.from_django_list(organizations)
        except Exception:
            return []

    @strawberry.field(description="Get partner organizations for this collaborative.")
    def partner_organizations(self) -> Optional[List["TypeOrganization"]]:
        """Get partner organizations for this collaborative."""
        try:
            relationships = (
                CollaborativeOrganizationRelationship.objects.filter(
                    collaborative=self,  # type: ignore
                    relationship_type=OrganizationRelationshipType.PARTNER,
                )
                .select_related("organization")
                .order_by("organization__name")
            )

            if not relationships.exists():
                return []

            organizations = [rel.organization for rel in relationships]  # type: ignore
            return TypeOrganization.from_django_list(organizations)
        except Exception:
            return []
