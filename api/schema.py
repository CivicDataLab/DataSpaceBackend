import strawberry
import strawberry_django
from strawberry.extensions import MaskErrors
from strawberry.extensions.tracing import OpenTelemetryExtension
from strawberry_django.optimizer import DjangoOptimizerExtension

from api.types.type_geo import TypeGeo


@strawberry.type
class Query:
    geography: list[TypeGeo] = strawberry_django.field()


schema = strawberry.Schema(
    query=Query,
    # mutation=Mutation,
    extensions=[
        DjangoOptimizerExtension,
        MaskErrors,
        OpenTelemetryExtension
    ],
)
