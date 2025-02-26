import json
from functools import lru_cache
from typing import Optional, List

import pandas as pd
import strawberry
import strawberry_django
from pyecharts.charts.chart import Chart
from strawberry.scalars import JSON

from api.models import ResourceChartDetails, ResourceSchema
from api.types import TypeResource
from api.types.charts.chart_registry import CHART_REGISTRY
from api.types.type_resource import TypeResourceSchema
from api.utils.django_utils import convert_to_graphql_type


@lru_cache()
def load_csv(filepath: str) -> pd.DataFrame:
    return pd.read_csv(filepath)


def chart_base(chart_details: ResourceChartDetails) -> None | Chart:
    if chart_details.resource.resourcefiledetails.format.lower() != "csv":
        return None

    data = load_csv(chart_details.resource.resourcefiledetails.file.path)

    chart_class = CHART_REGISTRY.get(chart_details.chart_type)
    if not chart_class:
        return None

    chart_instance = chart_class(chart_details, data)
    return chart_instance.create_chart()

@strawberry.type
class FilterType:
    column: str
    operator: str
    value: str

@strawberry.type
class ValueMappingType:
    key: str
    value: str

@strawberry.type
class YAxisColumnConfigType:
    field: Optional[TypeResourceSchema]
    label: Optional[str]
    color: Optional[str]
    value_mapping: Optional[List[ValueMappingType]]

@strawberry.type
class ChartOptionsType:
    x_axis_label: Optional[str]
    y_axis_label: Optional[str]
    x_axis_column: Optional[TypeResourceSchema]
    y_axis_column: Optional[list[YAxisColumnConfigType]]
    region_column: Optional[TypeResourceSchema]
    value_column: Optional[TypeResourceSchema]
    time_column: Optional[TypeResourceSchema]
    show_legend: Optional[bool]
    aggregate_type: Optional[str]

def ensure_type(value, target_type, element_type=None):
    """Ensure value is converted to the correct Strawberry type."""
    if value is None:
        return None

    if isinstance(value, dict):
        # Special case: If converting YAxisColumnConfigType, ensure `field` is also converted
        if target_type is YAxisColumnConfigType:
            return YAxisColumnConfigType(
                field=ensure_type(value.get("field"), TypeResourceSchema),  # Convert field properly
                label=value.get("label"),
                color=value.get("color"),
                value_mapping=[
                    ValueMappingType(key=vm["key"], value=vm["value"]) for vm in value.get("value_mapping", [])
                ] if value.get("value_mapping") else []
            )

        return target_type(**value)  # Convert dictionary to target type

    if element_type is not None:
        # Convert list elements properly
        if element_type:
            return [ensure_type(item, element_type) for item in value]
        return value

    if isinstance(value, ResourceSchema) and target_type == TypeResourceSchema:
        return convert_to_graphql_type(value, target_type)  # Convert Django model to Strawberry type

    return None  # Handle unexpected cases gracefully
@strawberry_django.type(ResourceChartDetails, fields="__all__")
class TypeResourceChart:
    resource: TypeResource
    chart_type: str
    options: Optional[ChartOptionsType]
    filters: Optional[List[FilterType]]
    
    

    @strawberry.field
    def options(self) -> Optional[ChartOptionsType]:
        """Convert stored JSONField `options` into ChartOptionsType, handling already deserialized objects"""
        if not self.options:  # Handle None case
            return None

        

        # Ensure y_axis_column is always treated as a list
        y_axis_column_data = self.options.get("y_axis_column")
        if isinstance(y_axis_column_data, dict):  # If a single object, wrap it in a list
            y_axis_column_data = [y_axis_column_data]
        # Convert only if needed
        options_data = {
            "x_axis_label": self.options.get("x_axis_label"),
            "y_axis_label": self.options.get("y_axis_label"),
            "x_axis_column": ensure_type(self.options.get("x_axis_column"), TypeResourceSchema),
            "y_axis_column": ensure_type(y_axis_column_data, list, YAxisColumnConfigType),
            "region_column": ensure_type(self.options.get("region_column"), TypeResourceSchema),
            "value_column": ensure_type(self.options.get("value_column"), TypeResourceSchema),
            "time_column": ensure_type(self.options.get("time_column"), TypeResourceSchema),
            "show_legend": self.options.get("show_legend", False),  # Default to False
            "aggregate_type": self.options.get("aggregate_type"),
        }

        return ChartOptionsType(**options_data)  # Convert dictionary to object

    @strawberry.field
    def filters(self) -> Optional[List[FilterType]]:
        """Convert stored JSONField `filters` into List[FilterType]"""
        if not self.filters:  # Handle None or empty cases
            return []
            
        # Ensure each filter is properly formatted
        formatted_filters = []
        for filter_data in self.filters:
            if isinstance(filter_data, dict):
                filter_dict = {
                    "column": ensure_type(filter_data.get("column"), TypeResourceSchema),
                    "operator": filter_data.get("operator", ""),
                    "value": filter_data.get("value", "")
                }
                formatted_filters.append(FilterType(**filter_dict))
            elif isinstance(filter_data, FilterType):
                formatted_filters.append(filter_data)
                
        return formatted_filters

    @strawberry.field
    def chart(self: ResourceChartDetails, info) -> JSON:
            base_chart = chart_base(self)
            if base_chart:
                options = base_chart.dump_options_with_quotes()
                return json.loads(options)
            else:
                return {}
