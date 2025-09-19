import datetime
import uuid
from typing import Any, Dict, List, Optional

import strawberry
import strawberry_django
from strawberry.types import Info
from strawberry_django.mutations import mutations

from api.models import Resource, ResourceChartDetails, ResourceSchema
from api.schema.extensions import TrackModelActivity
from api.types.type_resource_chart import TypeResourceChart
from api.utils.enums import AggregateType, ChartStatus, ChartTypes

ChartTypeEnum = strawberry.enum(ChartTypes)
AggregateTypeEnum = strawberry.enum(AggregateType)


@strawberry.type(name="Query")
class Query:
    @strawberry_django.field
    def charts_details(
        self, info: Info, dataset_id: uuid.UUID
    ) -> List[TypeResourceChart]:
        charts = ResourceChartDetails.objects.filter(resource__dataset_id=dataset_id)
        return [TypeResourceChart.from_django(chart) for chart in charts]

    @strawberry_django.field
    def resource_chart(
        self, info: Info, chart_details_id: uuid.UUID
    ) -> TypeResourceChart:
        chart = ResourceChartDetails.objects.get(id=chart_details_id)
        return TypeResourceChart.from_django(chart)


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
    # Standard chart options
    x_axis_label: str = "X-Axis"
    y_axis_label: str = "Y-Axis"
    x_axis_column: Optional[str] = None
    y_axis_column: Optional[List[YAxisColumnConfig]] = None
    region_column: Optional[str] = None
    value_column: Optional[str] = None
    time_column: Optional[str] = None
    show_legend: bool = False
    aggregate_type: str = "none"
    orientation: str = "vertical"
    allow_multi_series: bool = True
    stacked: bool = False

    # Big Number Chart specific options
    title: Optional[str] = None
    subtitle: Optional[str] = None
    label: Optional[str] = None
    value_prefix: Optional[str] = None
    value_suffix: Optional[str] = None
    title_color: Optional[str] = None
    subtitle_color: Optional[str] = None
    value_color: Optional[str] = None
    label_color: Optional[str] = None
    title_font_size: Optional[int] = None
    subtitle_font_size: Optional[int] = None
    value_font_size: Optional[int] = None
    label_font_size: Optional[int] = None
    background_color: Optional[str] = None

    # Enhanced Map Chart specific options
    # Common map options
    base_map: Optional[str] = None
    series_name: Optional[str] = None
    name_field: Optional[str] = None
    width: Optional[str] = None
    height: Optional[str] = None
    roam: Optional[bool] = None
    zoom: Optional[float] = None
    center: Optional[List[float]] = None
    show_toolbox: Optional[bool] = None

    # Polygon Map Chart options
    polygon_field: Optional[str] = None

    # Point Map Chart options
    lat_field: Optional[str] = None
    lng_field: Optional[str] = None
    point_size: Optional[int] = None

    # Geospatial Map Chart options
    geospatial_field: Optional[str] = None


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
    type: Optional[ChartTypeEnum]
    options: Optional[ChartOptions] = None
    filters: Optional[List[FilterInput]] = None


def _update_value_mapping(
    value_mapping: Optional[List[ValueMapping]],
) -> Dict[str, str]:
    if not value_mapping:
        return {}
    return {
        str(mapping.key): str(mapping.value)
        for mapping in value_mapping
        if mapping.key is not None and mapping.value is not None
    }


def _update_chart_fields(
    chart: ResourceChartDetails, chart_input: ResourceChartInput, resource: Resource
) -> None:
    if chart_input.type:
        chart.chart_type = chart_input.type

    # Build options dictionary
    options: Dict[str, Any] = {}
    if chart_input.options:
        for field_name, value in vars(chart_input.options).items():
            if value is not None:
                if field_name in [
                    "x_axis_column",
                    "region_column",
                    "value_column",
                    "time_column",
                    "name_field",
                    "polygon_field",
                    "lat_field",
                    "lng_field",
                    "geospatial_field",
                ]:
                    if value:  # Only process if value is not empty
                        field = ResourceSchema.objects.get(id=value)
                        options[field_name] = field
                elif field_name == "y_axis_column":
                    if value:  # Only process if list is not empty
                        options[field_name] = [
                            {
                                "field": ResourceSchema.objects.get(
                                    id=column.field_name
                                ),
                                "label": column.label,
                                "color": column.color,
                                "value_mapping": _update_value_mapping(
                                    column.value_mapping
                                ),
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
        filters = []
        for filter_input in chart_input.filters:
            if filter_input.column:
                filter_dict = {
                    "column": ResourceSchema.objects.get(id=filter_input.column),
                    "operator": filter_input.operator,
                    "value": filter_input.value,
                }
                filters.append(filter_dict)
        chart.filters = filters
    chart.save()


@strawberry.type
class Mutation:
    @strawberry_django.mutation(handle_django_errors=True)
    def add_resource_chart(self, info: Info, resource: uuid.UUID) -> TypeResourceChart:
        try:
            resource_obj = Resource.objects.get(id=resource)
        except Resource.DoesNotExist as e:
            raise ValueError(f"Resource with ID {resource} does not exist.")

        now = datetime.datetime.now()
        chart = ResourceChartDetails.objects.create(
            name=f"New chart {now.strftime('%d %b %Y - %H:%M:%S')}",
            resource=resource_obj,
        )
        return TypeResourceChart.from_django(chart)

    @strawberry_django.mutation(
        handle_django_errors=True,
        extensions=[
            # Use TrackModelActivity to automatically track the activity
            # The extension will use the returned chart as the action object
            # and the resource as the target
            TrackModelActivity(
                verb="created chart",
                target_attr="resource",
                get_data=lambda result, **kwargs: {
                    "chart_name": result.name,
                    "chart_type": result.chart_type,
                    "resource_id": str(result.resource.id),
                    "resource_name": result.resource.name,
                },
            )
        ],
    )
    def create_resource_chart(
        self, info: Info, chart_input: ResourceChartInput
    ) -> TypeResourceChart:
        try:
            resource_obj = Resource.objects.get(id=chart_input.resource)
        except Resource.DoesNotExist as e:
            raise ValueError(f"Resource with ID {chart_input.resource} does not exist.")

        chart = ResourceChartDetails.objects.create(
            name=chart_input.name
            or f"New chart {datetime.datetime.now().strftime('%d %b %Y - %H:%M:%S')}",
            resource=resource_obj,
            description=chart_input.description or "",
            chart_type=chart_input.type or ChartTypeEnum.BAR,
            options=chart_input.options or {},
            filters=chart_input.filters or [],
        )

        _update_chart_fields(chart, chart_input, resource_obj)
        return TypeResourceChart.from_django(chart)

    @strawberry_django.mutation(
        handle_django_errors=True,
        extensions=[
            # Track updates to charts
            TrackModelActivity(
                verb="updated chart",
                target_attr="resource",
                get_data=lambda result, **kwargs: {
                    "chart_id": str(result.id),
                    "chart_name": result.name,
                    "chart_type": result.chart_type,
                    "resource_id": str(result.resource.id),
                    "resource_name": result.resource.name,
                },
            )
        ],
    )
    def edit_resource_chart(
        self, info: Info, chart_input: ResourceChartInput
    ) -> TypeResourceChart:
        if not chart_input.chart_id:
            chart = ResourceChartDetails()
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
        return TypeResourceChart.from_django(chart)

    @strawberry_django.mutation(handle_django_errors=False)
    def delete_resource_chart(self, info: Info, chart_id: uuid.UUID) -> bool:
        try:
            chart = ResourceChartDetails.objects.get(id=chart_id)
            chart.delete()
            return True
        except ResourceChartDetails.DoesNotExist as e:
            raise ValueError(f"Resource Chart with ID {chart_id} does not exist.")

    @strawberry_django.mutation(handle_django_errors=False)
    def publish_resource_chart(self, info: Info, chart_id: uuid.UUID) -> bool:
        try:
            chart = ResourceChartDetails.objects.get(id=chart_id)
            chart.status = ChartStatus.PUBLISHED
            chart.save()
            return True
        except ResourceChartDetails.DoesNotExist as e:
            raise ValueError(f"Resource Chart with ID {chart_id} does not exist.")

    @strawberry_django.mutation(handle_django_errors=False)
    def unpublish_resource_chart(self, info: Info, chart_id: uuid.UUID) -> bool:
        try:
            chart = ResourceChartDetails.objects.get(id=chart_id)
            chart.status = ChartStatus.DRAFT
            chart.save()
            return True
        except ResourceChartDetails.DoesNotExist as e:
            raise ValueError(f"Resource Chart with ID {chart_id} does not exist.")
