from typing import List, Optional

import strawberry
import strawberry_django
from django.http import HttpRequest
from strawberry.tools import merge_types
from strawberry.types import Info
from strawberry_django.optimizer import DjangoOptimizerExtension

import api.schema.access_model_schema
import api.schema.aimodel_schema
import api.schema.collaborative_schema
import api.schema.dataset_schema
import api.schema.dataspace_schema
import api.schema.geography_schema
import api.schema.metadata_schema
import api.schema.organization_data_schema
import api.schema.organization_schema
import api.schema.resource_chart_schema
import api.schema.resource_schema
import api.schema.resoure_chart_image_schema
import api.schema.sdg_schema
import api.schema.sector_schema
import api.schema.stats_schema
import api.schema.tags_schema
import api.schema.usecase_dashboard_schema
import api.schema.usecase_schema
import api.schema.user_schema
from api.models import Resource, Tag
from api.types.type_dataset import TypeTag
from api.types.type_metadata import TypeMetadata
from api.types.type_resource import TypeResource
from api.utils.graphql_error_extension import ErrorFormatterExtension
from api.utils.graphql_telemetry import TelemetryExtension, trace_resolver
from authorization.graphql import Mutation as AuthMutation
from authorization.graphql import Query as AuthQuery


@strawberry.type
class DefaultQuery:

    metadata: list[TypeMetadata] = strawberry_django.field()

    @strawberry_django.field
    @trace_resolver(name="resources", attributes={"component": "default"})
    def resources(self, info: Info) -> List[TypeResource]:
        resources = Resource.objects.all()
        return [TypeResource.from_django(resource) for resource in resources]

    @strawberry_django.field
    @trace_resolver(name="tags", attributes={"component": "default"})
    def tags(self, info: Info) -> List[TypeTag]:
        tags = Tag.objects.all()
        return [TypeTag.from_django(tag) for tag in tags]


Query = merge_types(
    "Query",
    (
        DefaultQuery,
        api.schema.usecase_dashboard_schema.Query,
        api.schema.dataset_schema.Query,
        api.schema.resource_schema.Query,
        api.schema.access_model_schema.Query,
        api.schema.aimodel_schema.Query,
        api.schema.sdg_schema.Query,
        api.schema.sector_schema.Query,
        api.schema.geography_schema.Query,
        api.schema.resource_chart_schema.Query,
        api.schema.stats_schema.Query,
        api.schema.usecase_schema.Query,
        api.schema.organization_schema.Query,
        api.schema.organization_data_schema.Query,
        api.schema.dataspace_schema.Query,
        api.schema.resoure_chart_image_schema.Query,
        api.schema.user_schema.Query,
        api.schema.collaborative_schema.Query,
        AuthQuery,
    ),
)

Mutation = merge_types(
    "Mutation",
    (
        api.schema.usecase_dashboard_schema.Mutation,
        api.schema.dataset_schema.Mutation,
        api.schema.resource_schema.Mutation,
        api.schema.access_model_schema.Mutation,
        api.schema.aimodel_schema.Mutation,
        api.schema.sdg_schema.Mutation,
        api.schema.sector_schema.Mutation,
        api.schema.resource_chart_schema.Mutation,
        api.schema.usecase_schema.Mutation,
        api.schema.organization_schema.Mutation,
        api.schema.metadata_schema.Mutation,
        api.schema.dataspace_schema.Mutation,
        api.schema.resoure_chart_image_schema.Mutation,
        api.schema.tags_schema.Mutation,
        api.schema.collaborative_schema.Mutation,
        AuthMutation,
    ),
)


# Custom context class to include authentication information
class CustomContext:
    def __init__(self, request: Optional[HttpRequest] = None) -> None:
        self.request = request


# Context getter function for Strawberry
def get_context(request: Optional[HttpRequest] = None, response=None) -> CustomContext:  # type: ignore
    # Ignore the response parameter as we don't need it, but Strawberry tries to pass it
    return CustomContext(request=request)


schema = strawberry.Schema(
    query=Query,
    mutation=Mutation,
    extensions=[
        DjangoOptimizerExtension,
        TelemetryExtension,
        ErrorFormatterExtension,
    ],
)
