from typing import List, Optional

import strawberry
import strawberry_django
from strawberry import Info, auto, field
from strawberry.enum import EnumType

from api.activities import usecase
from api.models import (
    Organization,
    UseCase,
    UseCaseDashboard,
    UseCaseMetadata,
    UseCaseOrganizationRelationship,
)
from api.types.base_type import BaseType
from api.types.type_dataset import TypeDataset, TypeTag
from api.types.type_geo import TypeGeo
from api.types.type_organization import TypeOrganization
from api.types.type_sdg import TypeSDG
from api.types.type_sector import TypeSector
from api.types.type_usecase_dashboard import TypeUseCaseDashboard
from api.types.type_usecase_metadata import TypeUseCaseMetadata
from api.types.type_usecase_organization import TypeUseCaseOrganizationRelationship
from api.utils.enums import OrganizationRelationshipType, UseCaseStatus
from authorization.types import TypeUser

use_case_status = strawberry.enum(UseCaseStatus)  # type: ignore


@strawberry_django.filter(UseCase)
class UseCaseFilter:
    """Filter class for UseCase model."""

    id: auto
    slug: auto
    status: Optional[use_case_status]


@strawberry_django.order(UseCase)
class UseCaseOrder:
    """Order class for UseCase model."""

    title: auto
    created: auto
    modified: auto


@strawberry_django.type(
    UseCase,
    pagination=True,
    fields="__all__",
    filters=UseCaseFilter,
    order=UseCaseOrder,  # type:ignore
)
class TypeUseCase(BaseType):
    """GraphQL type for UseCase model."""

    user: TypeUser = strawberry.field(description="User who created this use case")
    organization: Optional[TypeOrganization] = strawberry.field(
        description="Organization associated with this use case"
    )
    platform_url: Optional[str] = strawberry.field(
        description="URL of the platform where this use case is published"
    )

    @strawberry.field(
        description="Check if this use case is created by an individual user."
    )
    def is_individual_usecase(self) -> bool:
        """Check if this use case is created by an individual user."""
        return self.organization is None

    @strawberry.field(description="Get datasets associated with this use case.")
    def datasets(self) -> Optional[List["TypeDataset"]]:
        """Get datasets associated with this use case."""
        try:
            # Return raw Django objects and let Strawberry handle conversion
            queryset = self.datasets.all()  # type: ignore
            if not queryset.exists():
                return []
            return TypeDataset.from_django_list(queryset)
        except Exception:
            return []

    @strawberry.field(
        description="Get the count of datasets associated with this use case."
    )
    def dataset_count(self: "TypeUseCase", info: Info) -> int:
        """Get the count of datasets associated with this use case."""
        try:
            return self.datasets.count()  # type: ignore
        except Exception:
            return 0

    @strawberry.field(description="Get publishers associated with this use case.")
    def publishers(self) -> Optional[List["TypeOrganization"]]:
        """Get publishers associated with this use case."""
        try:
            queryset = Organization.objects.filter(datasets__in=self.datasets.all()).distinct()  # type: ignore
            if not queryset.exists():
                return []
            return TypeOrganization.from_django_list(queryset)
        except Exception:
            return []

    @strawberry.field(description="Get sectors associated with this use case.")
    def sectors(self) -> Optional[List["TypeSector"]]:
        """Get sectors associated with this use case."""
        try:
            queryset = self.sectors.all()  # type: ignore
            if not queryset.exists():
                return []
            return TypeSector.from_django_list(queryset)
        except Exception:
            return []

    @strawberry.field(description="Get SDGs associated with this use case.")
    def sdgs(self) -> Optional[List["TypeSDG"]]:
        """Get SDGs associated with this use case."""
        try:
            queryset = self.sdgs.all()  # type: ignore
            if not queryset.exists():
                return []
            return TypeSDG.from_django_list(queryset)
        except Exception:
            return []

    @strawberry.field(description="Get geographies associated with this use case.")
    def geographies(self) -> Optional[List["TypeGeo"]]:
        """Get geographies associated with this use case."""
        try:
            queryset = self.geographies.all()  # type: ignore
            if not queryset.exists():
                return []
            return TypeGeo.from_django_list(queryset)
        except Exception:
            return []

    @strawberry.field(description="Get tags associated with this use case.")
    def tags(self) -> Optional[List["TypeTag"]]:
        """Get tags associated with this use case."""
        try:
            queryset = self.tags.all()  # type: ignore
            if not queryset.exists():
                return []
            return TypeTag.from_django_list(queryset)
        except Exception:
            return []

    @strawberry.field(description="Get metadata associated with this use case.")
    def metadata(self) -> Optional[List["TypeUseCaseMetadata"]]:
        """Get metadata associated with this use case."""
        try:
            queryset = UseCaseMetadata.objects.filter(usecase=self)  # type: ignore
            if not queryset.exists():
                return []
            return TypeUseCaseMetadata.from_django_list(queryset)
        except Exception:
            return []

    @strawberry.field(description="Get contributors associated with this use case.")
    def contributors(self) -> Optional[List["TypeUser"]]:
        """Get contributors associated with this use case."""
        try:
            queryset = self.contributors.all()  # type: ignore
            if not queryset.exists():
                return []
            return TypeUser.from_django_list(queryset)
        except Exception:
            return []

    @strawberry.field(
        description="Get organization relationships associated with this use case."
    )
    def organization_relationships(
        self,
    ) -> Optional[List["TypeUseCaseOrganizationRelationship"]]:
        """Get organization relationships associated with this use case."""
        try:
            queryset = UseCaseOrganizationRelationship.objects.filter(usecase=self)  # type: ignore
            if not queryset.exists():
                return []
            return TypeUseCaseOrganizationRelationship.from_django_list(queryset)
        except Exception:
            return []

    @strawberry.field(description="Get supporting organizations for this use case.")
    def supporting_organizations(self) -> Optional[List["TypeOrganization"]]:
        """Get supporting organizations for this use case."""
        try:
            relationships = UseCaseOrganizationRelationship.objects.filter(
                usecase=self,  # type: ignore
                relationship_type=OrganizationRelationshipType.SUPPORTER,
            ).select_related("organization")

            if not relationships.exists():
                return []

            organizations = [rel.organization for rel in relationships]  # type: ignore
            return TypeOrganization.from_django_list(organizations)
        except Exception:
            return []

    @strawberry.field(description="Get partner organizations for this use case.")
    def partner_organizations(self) -> Optional[List["TypeOrganization"]]:
        """Get partner organizations for this use case."""
        try:
            relationships = UseCaseOrganizationRelationship.objects.filter(
                usecase=self,  # type: ignore
                relationship_type=OrganizationRelationshipType.PARTNER,
            ).select_related("organization")

            if not relationships.exists():
                return []

            organizations = [rel.organization for rel in relationships]  # type: ignore
            return TypeOrganization.from_django_list(organizations)
        except Exception:
            return []

    @strawberry.field(
        description="Get Usecase dashboard associated with this use case."
    )
    def usecase_dashboard(self) -> Optional[List["TypeUseCaseDashboard"]]:
        """Get Usecase dashboard associated with this use case."""
        try:
            usecase_dashboards = UseCaseDashboard.objects.filter(usecase=self)  # type: ignore
            if not usecase_dashboards.exists():
                return []
            return TypeUseCaseDashboard.from_django_list(usecase_dashboards)
        except Exception:
            return []
