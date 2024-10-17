import strawberry
import strawberry_django
# from strawberry.extensions import MaskErrors
from strawberry.tools import merge_types
from strawberry_django.optimizer import DjangoOptimizerExtension

import api.schema.dataset_schema
import api.schema.metadata_schema
import api.schema.resource_schema
import api.schema.access_model_schema
import api.schema.category_schema
import api.schema.organization_schema
import api.schema.dataspace_schema
import api.schema.resource_chart_schema
import api.schema.usecase_schema
from api.types import TypeDataset, TypeMetadata, TypeResource
from api.types.type_dataset import TypeTag
from api.types.type_dataspace import TypeDataSpace
from api.types.type_organization import TypeOrganization
from api.types.type_usecase import TypeUseCase


@strawberry.type
class DefaultQuery:
    datasets: list[TypeDataset] = strawberry_django.field()
    organisations: list[TypeOrganization] = strawberry_django.field()
    usecases: list[TypeUseCase] = strawberry_django.field()
    dataspaces: list[TypeDataSpace] = strawberry_django.field()
    metadata: list[TypeMetadata] = strawberry_django.field()
    resource: list[TypeResource] = strawberry_django.field()
    tags: list[TypeTag] = strawberry_django.field()


Query = merge_types(
    "Query",
    (
        DefaultQuery,
        api.schema.resource_schema.Query,
        api.schema.access_model_schema.Query,
        api.schema.category_schema.Query,
        api.schema.resource_chart_schema.Query
    ),
)

Mutation = merge_types(
    "Mutation",
    (
        api.schema.dataset_schema.Mutation,
        api.schema.metadata_schema.Mutation,
        api.schema.resource_schema.Mutation,
        api.schema.access_model_schema.Mutation,
        api.schema.category_schema.Mutation,
        api.schema.organization_schema.Mutation,
        api.schema.dataspace_schema.Mutation,
        api.schema.resource_chart_schema.Mutation,
        api.schema.usecase_schema.Mutation,
    ),
)
schema = strawberry.Schema(
    query=Query,
    mutation=Mutation,
    extensions=[
        DjangoOptimizerExtension,
        # MaskErrors,
        # OpenTelemetryExtension
    ],
)
