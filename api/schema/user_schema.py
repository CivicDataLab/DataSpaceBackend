"""Schema definitions for user-related queries and mutations."""

from typing import List, Optional

import strawberry
import strawberry_django
from strawberry.types import Info

from api.models import Dataset, Sector, UseCase
from api.types.type_dataset import TypeDataset
from api.types.type_sector import TypeSector
from api.types.type_usecase import TypeUseCase
from api.utils.enums import DatasetStatus, UseCaseStatus
from api.utils.graphql_telemetry import trace_resolver
from authorization.models import User
from authorization.types import TypeUser


@strawberry.type
class Query:
    """Queries for user-related data."""

    @strawberry_django.field
    @trace_resolver(name="get_user_by_id", attributes={"component": "user"})
    def user_by_id(self, info: Info, user_id: strawberry.ID) -> Optional[TypeUser]:
        """Get a user by ID."""
        try:
            return TypeUser.from_django(User.objects.get(id=user_id))
        except User.DoesNotExist:
            return None

    @strawberry_django.field
    @trace_resolver(
        name="get_user_published_datasets", attributes={"component": "user"}
    )
    def user_published_datasets(
        self, info: Info, user_id: strawberry.ID
    ) -> List[TypeDataset]:
        """Get published datasets for a user.

        Returns a list of datasets that have been published by the specified user.
        """
        try:
            # Get published datasets where this user is the creator
            queryset = Dataset.objects.filter(
                user_id=user_id, status=DatasetStatus.PUBLISHED.value
            )
            return TypeDataset.from_django_list(queryset)
        except Exception:
            return []

    @strawberry_django.field
    @trace_resolver(
        name="get_user_published_use_cases", attributes={"component": "user"}
    )
    def user_published_use_cases(
        self, info: Info, user_id: strawberry.ID
    ) -> List[TypeUseCase]:
        """Get published use cases for a user.

        Returns a list of use cases that have been published by the specified user.
        """
        try:
            # Get published use cases where this user is the creator
            queryset = UseCase.objects.filter(
                user_id=user_id, status=UseCaseStatus.PUBLISHED.value
            )
            return TypeUseCase.from_django_list(queryset)
        except Exception:
            return []

    @strawberry_django.field
    @trace_resolver(
        name="get_user_contributed_sectors", attributes={"component": "user"}
    )
    def user_contributed_sectors(
        self, info: Info, user_id: strawberry.ID
    ) -> List[TypeSector]:
        """Get sectors that a user has contributed to.

        Returns a list of unique sectors from all datasets and use cases published by the specified user.
        """
        try:
            # Get sectors from published datasets
            dataset_sectors = Sector.objects.filter(
                datasets__user_id=user_id,
                datasets__status=DatasetStatus.PUBLISHED.value,
            ).distinct()

            # Get sectors from published use cases
            usecase_sectors = Sector.objects.filter(
                usecases__user_id=user_id,
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
        except Exception:
            return []
