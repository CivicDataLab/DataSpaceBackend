from typing import TYPE_CHECKING, Annotated, Any, List, Optional

import strawberry
import strawberry_django
from django.db.models import Q
from strawberry import Info, auto

from api.models import Organization
from api.types.base_type import BaseType

if TYPE_CHECKING:
    from authorization.types import TypeOrganizationMembership


@strawberry_django.filter(Organization)
class OrganizationFilter:
    id: auto
    slug: auto


@strawberry_django.type(
    Organization, pagination=True, fields="__all__", filters=OrganizationFilter
)
class TypeOrganization(BaseType):
    parent_id: Optional["TypeOrganization"]

    @strawberry.field(description="Count of datasets published by this organization")
    def dataset_count(self: Any) -> int:
        return int(self.datasets.count())  # type: ignore

    @strawberry.field(description="Count of published datasets by this organization")
    def published_datasets_count(self, info: Info) -> int:
        """Get count of published datasets for this organization."""
        from api.models import Dataset
        from api.utils.enums import DatasetStatus

        try:
            # Count published datasets for this organization
            # Use the Django model directly with the ID instead of the attribute
            org_id = getattr(self, "id", None)
            if not org_id:
                return 0

            return Dataset.objects.filter(
                organization_id=org_id, status=DatasetStatus.PUBLISHED.value
            ).count()
        except Exception:
            return 0

    @strawberry.field(description="Count of published use cases by this organization")
    def published_use_cases_count(self, info: Info) -> int:
        """Get count of published use cases for this organization."""
        from api.models import UseCase
        from api.utils.enums import UseCaseStatus

        try:
            # Count published use cases for this organization
            # Get use cases through the organization relationship
            org_id = getattr(self, "id", None)
            if not org_id:
                return 0

            use_cases = UseCase.objects.filter(
                (Q(organization__id=org_id) | Q(usecaseorganizationrelationship__organization_id=org_id)),  # type: ignore
                status=UseCaseStatus.PUBLISHED.value,
            ).distinct()
            return use_cases.count()
        except Exception:
            return 0

    @strawberry.field(
        description="Count of sectors this organization has contributed to"
    )
    def contributed_sectors_count(self, info: Info) -> int:
        """Get count of sectors that this organization has contributed to."""
        from api.models import Sector
        from api.utils.enums import DatasetStatus, UseCaseStatus

        try:
            # Get sectors from published datasets
            org_id = getattr(self, "id", None)
            if not org_id:
                return 0

            dataset_sectors = (
                Sector.objects.filter(
                    datasets__organization_id=org_id,  # type: ignore
                    datasets__status=DatasetStatus.PUBLISHED.value,
                )
                .values_list("id", flat=True)
                .distinct()
            )

            # Get sectors from published use cases
            usecase_sectors = (
                Sector.objects.filter(
                    usecases__usecaseorganizationrelationship__organization_id=org_id,  # type: ignore
                    usecases__status=UseCaseStatus.PUBLISHED.value,
                )
                .values_list("id", flat=True)
                .distinct()
            )

            # Combine and deduplicate sectors
            sector_ids = set(dataset_sectors)
            sector_ids.update(usecase_sectors)

            return len(sector_ids)
        except Exception:
            return 0

    @strawberry.field(description="Count of members in this organization")
    def members_count(self, info: Info) -> int:
        """Get count of members in this organization."""
        try:
            from authorization.models import OrganizationMembership

            org_id = getattr(self, "id", None)
            if not org_id:
                return 0

            return OrganizationMembership.objects.filter(organization_id=org_id).count()  # type: ignore
        except Exception:
            return 0

    @strawberry.field(description="Members in this organization")
    def members(
        self, info: Info
    ) -> List[
        Annotated["TypeOrganizationMembership", strawberry.lazy("authorization.types")]
    ]:
        """Get members in this organization."""
        try:
            from authorization.models import OrganizationMembership
            from authorization.types import TypeOrganizationMembership

            org_id = getattr(self, "id", None)
            if not org_id:
                return []

            queryset = OrganizationMembership.objects.filter(organization_id=org_id)
            return TypeOrganizationMembership.from_django_list(queryset)
        except Exception:
            return []
