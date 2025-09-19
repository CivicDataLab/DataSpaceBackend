"""Schema definitions for organization-related data queries."""

from typing import List, Optional

import strawberry
import strawberry_django
import structlog
from django.db.models import Q
from strawberry.types import Info

from api.models import Dataset, Organization, Sector, UseCase
from api.types.type_dataset import TypeDataset
from api.types.type_organization import TypeOrganization
from api.types.type_sector import TypeSector
from api.types.type_usecase import TypeUseCase
from api.utils.enums import DatasetStatus, UseCaseStatus
from api.utils.graphql_telemetry import trace_resolver
from authorization.models import OrganizationMembership, User
from authorization.permissions import IsAuthenticated, IsOrganizationMemberGraphQL
from authorization.types import TypeUser

logger = structlog.get_logger(__name__)


@strawberry.type
class Query:
    """Queries for organization-related data."""

    @strawberry_django.field
    @trace_resolver(
        name="get_organization_published_datasets",
        attributes={"component": "organization"},
    )
    def organization_published_datasets(
        self, info: Info, organization_id: strawberry.ID
    ) -> List[TypeDataset]:
        """Get published datasets for an organization.

        Returns a list of datasets that have been published by the specified organization.
        """
        try:
            # Get published datasets for this organization
            queryset = Dataset.objects.filter(
                organization_id=organization_id, status=DatasetStatus.PUBLISHED.value
            )
            return TypeDataset.from_django_list(queryset)
        except Dataset.DoesNotExist:
            logger.warning(f"No datasets found for organization {organization_id}")
            return []
        except Exception as e:
            logger.error(
                f"Error fetching datasets for organization {organization_id}: {str(e)}"
            )
            return []

    @strawberry_django.field
    @trace_resolver(
        name="get_organization_published_use_cases",
        attributes={"component": "organization"},
    )
    def organization_published_use_cases(
        self, info: Info, organization_id: strawberry.ID
    ) -> List[TypeUseCase]:
        """Get published use cases for an organization.

        Returns a list of use cases that have been published by the specified organization.
        """
        try:
            # Get published use cases for this organization
            queryset = UseCase.objects.filter(
                (
                    Q(organization__id=organization_id)
                    | Q(
                        usecaseorganizationrelationship__organization_id=organization_id
                    )
                ),
                status=UseCaseStatus.PUBLISHED.value,
            ).distinct()
            return TypeUseCase.from_django_list(queryset)
        except UseCase.DoesNotExist:
            logger.warning(f"No use cases found for organization {organization_id}")
            return []
        except Exception as e:
            logger.error(
                f"Error fetching use cases for organization {organization_id}: {str(e)}"
            )
            return []

    @strawberry_django.field
    @trace_resolver(
        name="get_organization_contributed_sectors",
        attributes={"component": "organization"},
    )
    def organization_contributed_sectors(
        self, info: Info, organization_id: strawberry.ID
    ) -> List[TypeSector]:
        """Get sectors that an organization has contributed to.

        Returns a list of unique sectors from all datasets and use cases published by the specified organization.
        """
        try:
            # Get sectors from published datasets
            dataset_sectors = Sector.objects.filter(
                datasets__organization_id=organization_id,
                datasets__status=DatasetStatus.PUBLISHED.value,
            ).distinct()

            # Get sectors from published use cases
            usecase_sectors = Sector.objects.filter(
                usecases__usecaseorganizationrelationship__organization_id=organization_id,
                usecases__status=UseCaseStatus.PUBLISHED.value,
            ).distinct()

            # Combine and deduplicate sectors
            sector_ids = set(dataset_sectors.values_list("id", flat=True))
            sector_ids.update(usecase_sectors.values_list("id", flat=True))

            if not sector_ids:
                return []

            # Get all sectors by their IDs
            queryset = Sector.objects.filter(id__in=sector_ids)
            return TypeSector.from_django_list(queryset)
        except Sector.DoesNotExist:
            logger.warning(f"No sectors found for organization {organization_id}")
            return []
        except Exception as e:
            logger.error(
                f"Error fetching sectors for organization {organization_id}: {str(e)}"
            )
            return []

    @strawberry_django.field
    @trace_resolver(
        name="get_organization_members", attributes={"component": "organization"}
    )
    def organization_members(
        self, info: Info, organization_id: strawberry.ID
    ) -> List[TypeUser]:
        """Get members of an organization.

        Returns a list of users who are members of the specified organization.
        """
        try:
            user_ids = OrganizationMembership.objects.filter(
                organization_id=organization_id
            ).values_list("user_id", flat=True)
            users = User.objects.filter(id__in=user_ids)
            return TypeUser.from_django_list(users)
        except OrganizationMembership.DoesNotExist:
            logger.warning(f"No members found for organization {organization_id}")
            return []
        except Exception as e:
            logger.error(
                f"Error fetching members for organization {organization_id}: {str(e)}"
            )
            return []
