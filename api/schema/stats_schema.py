from typing import Optional

import strawberry
import strawberry_django
from django.db.models import Count, Q
from strawberry.types import Info

from api.models.Dataset import Dataset
from api.models.Organization import Organization
from api.models.UseCase import UseCase
from api.utils.enums import DatasetStatus, UseCaseStatus
from api.utils.graphql_telemetry import trace_resolver
from authorization.models import User


@strawberry.type
class StatsType:
    """Type for platform statistics"""

    total_users: int
    total_published_datasets: int
    total_publishers: int
    total_published_usecases: int
    total_organizations: int
    total_individuals: int


@strawberry.type
class Query:
    @strawberry_django.field
    @trace_resolver(name="stats", attributes={"component": "stats"})
    def stats(self, info: Info) -> StatsType:
        """Get platform statistics"""
        # Count total users
        total_users = User.objects.count()

        # Count published datasets
        total_published_datasets = Dataset.objects.filter(
            status=DatasetStatus.PUBLISHED
        ).count()

        # Count publishers (organizations and individuals who have published datasets)
        # First, get organizations that have published datasets
        org_publishers = (
            Organization.objects.filter(datasets__status=DatasetStatus.PUBLISHED)
            .distinct()
            .count()
        )

        # Then, get individual users who have published datasets
        individual_publishers = (
            User.objects.filter(
                datasets__status=DatasetStatus.PUBLISHED,
                datasets__organization__isnull=True,
            )
            .distinct()
            .count()
        )

        # Total publishers is the sum of organizations and individual publishers
        total_publishers = org_publishers + individual_publishers

        # Count published usecases
        total_published_usecases = UseCase.objects.filter(
            status=UseCaseStatus.PUBLISHED
        ).count()

        return StatsType(
            total_users=total_users,
            total_published_datasets=total_published_datasets,
            total_publishers=total_publishers,
            total_organizations=org_publishers,
            total_individuals=individual_publishers,
            total_published_usecases=total_published_usecases,
        )
