import json
import timeit
from typing import Optional

import strawberry
import strawberry_django
from django.core.serializers import serialize
from django.db.models import F, Max, Q
from strawberry.scalars import JSON
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
    ],
)