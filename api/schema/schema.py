import strawberry
import strawberry_django
# from strawberry.extensions import MaskErrors
from strawberry.tools import merge_types
from strawberry_django.optimizer import DjangoOptimizerExtension

import api.schema.dataset_schema
import api.schema.metadata_schema
import api.schema.resource_schema
from api.types import TypeDataset, TypeMetadata, TypeResource


@strawberry.type
class Query:
    dataset: list[TypeDataset] = strawberry_django.field()
    metadata: list[TypeMetadata] = strawberry_django.field()
    resource: list[TypeResource] = strawberry_django.field()


Mutation = merge_types(
    "Mutation",
    (
        api.schema.dataset_schema.Mutation,
        api.schema.metadata_schema.Mutation,
        api.schema.resource_schema.Mutation,
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
