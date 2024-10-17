import uuid
from typing import Optional

import strawberry
import strawberry_django

from api.utils.enums import ChartTypes, AggregateType
from api.models import ResourceChartDetails, Resource, ResourceSchema
from api.types import TypeResourceChart

ChartType = strawberry.enum(ChartTypes)
AggregateType = strawberry.enum(AggregateType)


@strawberry.type(name="Query")
class Query:
    @strawberry_django.field
    def charts_details(self, info, dataset_id: uuid.UUID) -> list[TypeResourceChart]:
        return ResourceChartDetails.objects.filter(resource__dataset_id=dataset_id)

    @strawberry_django.field
    def resource_chart(self, info, chart_details_id: uuid.UUID) -> TypeResourceChart:
        return ResourceChartDetails.objects.get(id=chart_details_id)


@strawberry_django.input(ResourceChartDetails)
class ResourceChartInput:
    chart_id: Optional[uuid.UUID]
    resource: uuid.UUID
    name: Optional[str]
    description: Optional[str]
    type: ChartType
    x_axis_label: Optional[str] = ""
    y_axis_label: Optional[str] = ""
    x_axis_Column: Optional[str]
    region_Column: Optional[str]
    value_Column: Optional[str]
    y_axis_Column: Optional[str]
    show_legend: Optional[bool] = True
    aggregate_type: AggregateType = AggregateType.NONE


def _update_chart_fields(chart: ResourceChartDetails, chart_input: ResourceChartInput, resource: Resource):
    chart.chart_type = chart_input.type
    chart.show_legend = chart_input.show_legend
    chart.aggregate_type = chart_input.aggregate_type
    chart.x_axis_label = chart_input.x_axis_label
    chart.y_axis_label = chart_input.y_axis_label
    if chart_input.name:
        chart.name = chart_input.name
    if chart_input.description:
        chart.description = chart_input.description
    if chart_input.x_axis_Column:
        field = ResourceSchema.objects.get(id=chart_input.x_axis_Column)
        chart.x_axis_column = field
    if chart_input.y_axis_Column:
        field = ResourceSchema.objects.get(id=chart_input.y_axis_Column)
        chart.y_axis_column = field
    if chart_input.region_Column:
        field = ResourceSchema.objects.get(id=chart_input.region_Column)
        chart.region_column = field
    if chart_input.value_Column:
        field = ResourceSchema.objects.get(id=chart_input.value_Column)
        chart.value_column = field
    chart.save()


@strawberry.type
class Mutation:
    @strawberry_django.mutation(handle_django_errors=True)
    def edit_resource_chart(self, chart_input: ResourceChartInput) -> TypeResourceChart:
        if not chart_input.chart_id:
            chart: ResourceChartDetails = ResourceChartDetails()
        else:
            try:
                chart = ResourceChartDetails.objects.get(id=chart_input.chart_id)
            except ResourceChartDetails.DoesNotExist as e:
                raise ValueError(f"Chart ID {chart_input.chart_id} does not exist.")
        try:
            resource = Resource.objects.get(id=chart_input.resource)
        except Resource.DoesNotExist as e:
            raise ValueError(f"Resource with ID {chart_input.resource} does not exist.")
        chart.resource = resource
        chart.save()
        _update_chart_fields(chart, chart_input, resource)
        return chart

    @strawberry_django.mutation(handle_django_errors=False)
    def delete_resource_chart(self, chart_id: uuid.UUID) -> bool:
        try:
            chart = ResourceChartDetails.objects.get(id=chart_id)
        except ResourceChartDetails.DoesNotExist as e:
            raise ValueError(f"Resource Chart with ID {chart_id} does not exist.")
        chart.delete()
        return True
