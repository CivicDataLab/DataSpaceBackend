"""Schema definitions for usecase dashboards."""

from typing import List, Optional

import strawberry
import strawberry_django
from strawberry.types import Info
from strawberry_django.pagination import OffsetPaginationInput

from api.models import UseCase, UseCaseDashboard
from api.schema.base_mutation import BaseMutation, MutationResponse
from api.types.type_usecase_dashboard import (
    TypeUseCaseDashboard,
    UseCaseDashboardFilter,
    UseCaseDashboardOrder,
)
from api.utils.graphql_telemetry import trace_resolver
from authorization.permissions import IsAuthenticated


@strawberry.input
class UseCaseDashboardInput:
    """Input type for usecase dashboard creation."""

    name: str
    link: str


@strawberry.input
class AddUseCaseDashboardsInput:
    """Input for adding multiple dashboards to a usecase."""

    usecase_id: int
    dashboards: List[UseCaseDashboardInput]


@strawberry.type
class UseCaseDashboardMutationResponse:
    """Response type for usecase dashboard mutations."""

    dashboards: Optional[List[TypeUseCaseDashboard]] = None
    success: bool = False
    message: str = ""


@strawberry.type
class Mutation:
    """UseCaseDashboard mutations."""

    @strawberry.mutation
    @BaseMutation.mutation(
        permission_classes=[IsAuthenticated],
        trace_name="add_usecase_dashboards",
        trace_attributes={"component": "usecase_dashboard"},
        track_activity={
            "verb": "created",
            "get_data": lambda result, **kwargs: {
                "usecase_id": str(kwargs.get("input").usecase_id),
                "dashboard_count": len(result),
            },
        },
    )
    def add_usecase_dashboards(
        self, info: Info, input: AddUseCaseDashboardsInput
    ) -> MutationResponse[List[TypeUseCaseDashboard]]:
        """Add multiple dashboards to a usecase."""
        try:
            # Check if usecase exists
            usecase = UseCase.objects.get(id=input.usecase_id)

            # Create dashboards
            created_dashboards = []
            for dashboard_input in input.dashboards:
                dashboard = UseCaseDashboard.objects.create(
                    name=dashboard_input.name,
                    link=dashboard_input.link,
                    usecase=usecase,
                )
                created_dashboards.append(dashboard)

            return MutationResponse.success_response(
                TypeUseCaseDashboard.from_django_list(created_dashboards)
            )
        except UseCase.DoesNotExist:
            raise Exception(f"Usecase with ID {input.usecase_id} does not exist")
        except Exception as e:
            raise Exception(f"Failed to add dashboards: {str(e)}")

    @strawberry.mutation
    @BaseMutation.mutation(
        permission_classes=[IsAuthenticated],
        trace_name="add_usecase_dashboard",
        trace_attributes={"component": "usecase_dashboard"},
        track_activity={
            "verb": "created",
            "get_data": lambda result, **kwargs: {
                "usecase_id": str(kwargs.get("usecase_id")),
                "dashboard_id": str(kwargs.get("id")),
            },
        },
    )
    def add_usecase_dashboard(
        self,
        info: Info,
        usecase_id: int,
        name: Optional[str] = "",
        link: Optional[str] = "",
    ) -> MutationResponse[TypeUseCaseDashboard]:
        """Add a usecase dashboard."""
        try:
            # Check if usecase exists
            usecase = UseCase.objects.get(id=usecase_id)

            # Create dashboard
            dashboard = UseCaseDashboard.objects.create(
                name=name or "",
                link=link or "",
                usecase=usecase,
            )

            return MutationResponse.success_response(
                TypeUseCaseDashboard.from_django(dashboard)
            )
        except UseCase.DoesNotExist:
            raise Exception(f"Usecase with ID {usecase_id} does not exist")
        except Exception as e:
            raise Exception(f"Failed to add dashboard: {str(e)}")

    @strawberry.mutation
    @BaseMutation.mutation(
        permission_classes=[IsAuthenticated],
        trace_name="update_usecase_dashboard",
        trace_attributes={"component": "usecase_dashboard"},
        track_activity={
            "verb": "updated",
            "get_data": lambda result, **kwargs: {
                "dashboard_id": str(kwargs.get("id")),
            },
        },
    )
    def update_usecase_dashboard(
        self, info: Info, id: str, name: Optional[str] = "", link: Optional[str] = ""
    ) -> MutationResponse[TypeUseCaseDashboard]:
        """Update a usecase dashboard."""
        try:
            dashboard = UseCaseDashboard.objects.get(id=id)
            dashboard.name = name or dashboard.name
            dashboard.link = link or dashboard.link
            dashboard.save()
            return MutationResponse.success_response(
                TypeUseCaseDashboard.from_django(dashboard)
            )
        except UseCaseDashboard.DoesNotExist:
            raise Exception(f"Dashboard with ID {id} does not exist")
        except Exception as e:
            raise Exception(f"Failed to update dashboard: {str(e)}")

    @strawberry.mutation
    @BaseMutation.mutation(
        permission_classes=[IsAuthenticated],
        trace_name="delete_usecase_dashboard",
        trace_attributes={"component": "usecase_dashboard"},
        track_activity={
            "verb": "deleted",
            "get_data": lambda result, **kwargs: {
                "dashboard_id": str(kwargs.get("id")),
            },
        },
    )
    def delete_usecase_dashboard(self, info: Info, id: int) -> MutationResponse[bool]:
        """Delete a usecase dashboard."""
        try:
            dashboard = UseCaseDashboard.objects.get(id=id)
            dashboard.delete()
            return MutationResponse.success_response(True)
        except UseCaseDashboard.DoesNotExist:
            raise Exception(f"Dashboard with ID {id} does not exist")
        except Exception as e:
            raise Exception(f"Failed to delete dashboard: {str(e)}")


@strawberry.type
class Query:
    """UseCaseDashboard queries."""

    @strawberry_django.field(
        filters=UseCaseDashboardFilter,
        pagination=True,
        order=UseCaseDashboardOrder,
    )
    @trace_resolver(
        name="get_usecase_dashboards_all", attributes={"component": "usecase_dashboard"}
    )
    def usecase_dashboards_all(
        self,
        info: Info,
        filters: UseCaseDashboardFilter = strawberry.UNSET,
        pagination: OffsetPaginationInput = strawberry.UNSET,
        order: UseCaseDashboardOrder = strawberry.UNSET,
    ) -> list[TypeUseCaseDashboard]:
        """Get all usecase dashboards."""
        queryset = UseCaseDashboard.objects.all()

        if filters is not strawberry.UNSET:
            queryset = strawberry_django.filters.apply(filters, queryset, info)

        if order is not strawberry.UNSET:
            queryset = strawberry_django.ordering.apply(order, queryset, info)

        dashboard_instances = list(queryset)

        if pagination is not strawberry.UNSET:
            offset = pagination.offset if pagination.offset is not None else 0
            limit = pagination.limit

            if limit is not None:
                dashboard_instances = dashboard_instances[offset : offset + limit]
            else:
                dashboard_instances = dashboard_instances[offset:]

        return [
            TypeUseCaseDashboard.from_django(instance)
            for instance in dashboard_instances
        ]

    @strawberry_django.field
    @trace_resolver(
        name="get_usecase_dashboards", attributes={"component": "usecase_dashboard"}
    )
    def usecase_dashboards(
        self, info: Info, usecase_id: int
    ) -> list[TypeUseCaseDashboard]:
        """Get dashboards for a specific usecase."""
        try:
            # Check if usecase exists
            usecase = UseCase.objects.get(id=usecase_id)

            # Get dashboards for the usecase
            dashboards = UseCaseDashboard.objects.filter(usecase=usecase)

            return [
                TypeUseCaseDashboard.from_django(dashboard) for dashboard in dashboards
            ]
        except UseCase.DoesNotExist:
            raise Exception(f"Usecase with ID {usecase_id} does not exist")
        except Exception as e:
            raise Exception(f"Failed to get usecase dashboards: {str(e)}")
