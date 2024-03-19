import strawberry
import strawberry_django
# from strawberry.extensions import MaskErrors
from strawberry.extensions.tracing import OpenTelemetryExtension
from strawberry.tools import merge_types
from strawberry_django.optimizer import DjangoOptimizerExtension

import api.dataset_schema
from api.types import TypeGeo


@strawberry.type
class Query:
    geography: list[TypeGeo] = strawberry_django.field()


Mutation = merge_types(
    "Mutation",
    (
        api.dataset_schema.Mutation,
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
