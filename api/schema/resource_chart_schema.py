import strawberry
import strawberry_django
from strawberry_django import NodeInput
from strawberry_django.mutations import mutations

from api.models import ResourceChartDetails
from api.types import TypeResourceChart


@strawberry_django.input(ResourceChartDetails, fields="__all__")
class ResourceChartInput:
    pass


@strawberry_django.partial(ResourceChartDetails, fields="__all__")
class ResourceChartInputPartial(NodeInput):
    pass


@strawberry.type
class Mutation:
    create_resource_chart: TypeResourceChart = mutations.create(ResourceChartInput)
    update_resource_chart: TypeResourceChart = mutations.update(ResourceChartInputPartial)
    delete_resource_chart: TypeResourceChart = mutations.delete(NodeInput)
