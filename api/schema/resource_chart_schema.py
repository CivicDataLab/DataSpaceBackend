import datetime
import uuid
from typing import Optional, List, Dict, Any
from dataclasses import field

import strawberry
import strawberry_django
from strawberry.scalars import JSON

from api.models import ResourceChartDetails, Resource, ResourceSchema
from api.types import TypeResourceChart
from api.utils.enums import ChartTypes, AggregateType

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


@strawberry.input
class FilterInput:
    column: str
    operator: str
    value: str


@strawberry.input
class ValueMapping:
    key: str
    value: str

@strawberry.input
class ValueMappingInput:
    key: str
    value: str

@strawberry.input
class YAxisColumnConfig:
    field_name: str
    label: Optional[str] = None
    color: Optional[str] = None
    value_mapping: Optional[List[ValueMapping]] = None


@strawberry.input
class ChartOptions:
    x_axis_label: Optional[str] = "X-Axis"
    y_axis_label: Optional[str] = "Y-Axis"
    x_axis_column: Optional[str] = None
    y_axis_column: Optional[List[YAxisColumnConfig]] = field(default_factory=list)
    region_column: Optional[str] = None
    value_column: Optional[str] = None
    time_column: Optional[str] = None
    show_legend: bool = False
    aggregate_type: Optional[str] = "none"


@strawberry.input
class YAxisColumnInput:
    field_name: str
    label: Optional[str] = None
    color: Optional[str] = None
    value_mapping: Optional[List[ValueMappingInput]] = None


@strawberry.input
class ChartRequestInput:
    resource_id: str
    chart_type: str
    x_axis_column: str
    y_axis_columns: List[YAxisColumnInput]
    time_column: str
    time_groups: Optional[List[str]] = None
    x_axis_label: Optional[str] = None
    y_axis_label: Optional[str] = None


@strawberry_django.input(ResourceChartDetails)
class ResourceChartInput:
    chart_id: Optional[uuid.UUID]
    resource: uuid.UUID
    name: Optional[str]
    description: Optional[str]
    type: Optional[ChartType]
    filters: Optional[List[FilterInput]] = []
    options: Optional[ChartOptions] = field(default_factory=ChartOptions)


def _update_chart_fields(chart: ResourceChartDetails, chart_input: ResourceChartInput, resource: Resource):
    chart.chart_type = chart_input.type
    
    # Build options dictionary
    options = {}
    for field_name, value in vars(chart_input.options).items():
        if value is not None:
            if field_name in ['x_axis_column', 'region_column', 'value_column', 'time_column']:
                if value:  # Only process if value is not empty
                    field = ResourceSchema.objects.get(id=value)
                    options[field_name] = field
            elif field_name == 'y_axis_column':
                if value:# Only process if list is not empty
                    options[field_name] = [
                        {
                            'field': ResourceSchema.objects.get(id=column.field_name),
                            'label': column.label,
                            'color': column.color,
                            'value_mapping': [ValueMapping(key=k, value=v) for k, v in column.value_mapping] if column.value_mapping else []
                        }
                        for column in value
                    ]
            else:
                options[field_name] = value

    if chart_input.name:
        chart.name = chart_input.name
    if chart_input.description:
        chart.description = chart_input.description

    # Update options and filters
    chart.options = options
    if chart_input.filters:
        chart.filters = [vars(f) for f in chart_input.filters]
    chart.save()


@strawberry.type
class Mutation:
    @strawberry_django.mutation(handle_django_errors=True)
    def add_resource_chart(self, info, resource: uuid.UUID) -> TypeResourceChart:
        resource_chart: ResourceChartDetails = ResourceChartDetails()
        now = datetime.datetime.now()
        resource_chart.name = f"New chart {now.strftime('%d %b %Y - %H:%M')}"
        try:
            resource = Resource.objects.get(id=resource)
        except Resource.DoesNotExist as e:
            raise ValueError(f"Resource with ID {resource} does not exist.")
        resource_chart.resource = resource
        resource_chart.save()
        return resource_chart

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
