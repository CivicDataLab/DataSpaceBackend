import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Type, TypedDict, TypeVar, Union, cast

import strawberry
import strawberry_django
from pyecharts.charts.chart import Chart
from strawberry.scalars import JSON
from strawberry.types import Info

from api.models import ResourceChartDetails
from api.types.base_type import BaseType
from api.types.charts.chart_registry import CHART_REGISTRY
from api.types.type_resource import TypeResource, TypeResourceSchema
from api.utils.file_utils import load_csv

T = TypeVar("T", bound="TypeResourceChart")


def chart_base(chart_details: ResourceChartDetails) -> Optional[Chart]:
    """Create a chart instance based on the chart details.

    Args:
        chart_details: Chart details for creating the chart

    Returns:
        Optional[Chart]: Chart instance if successful, None otherwise
    """
    try:
        file_details = getattr(chart_details.resource, "resourcefiledetails", None)
        if not file_details or file_details.format.lower() != "csv":
            return None

        data = load_csv(file_details.file.path)
    except (AttributeError, FileNotFoundError):
        return None

    chart_class = CHART_REGISTRY.get(chart_details.chart_type)
    if not chart_class:
        return None

    chart_instance = chart_class(chart_details, data)
    return chart_instance.create_chart()


@strawberry.type
class ChartConfig:
    """Type for chart configuration."""

    options: JSON
    width: str
    height: str
    renderer: str


@strawberry.type
class FilterType(BaseType):
    """Type for filter."""

    column: Optional[TypeResourceSchema]
    operator: str
    value: str


@strawberry.type
class ValueMappingType(BaseType):
    """Type for value mapping."""

    key: str
    value: str


@strawberry.type
class YAxisColumnConfigType(BaseType):
    """Type for Y-axis column configuration."""

    field: Optional[TypeResourceSchema]
    label: Optional[str]
    color: Optional[str]
    value_mapping: Optional[List[ValueMappingType]]


@strawberry.type
class ChartOptionsType(BaseType):
    """Type for chart options."""

    x_axis_label: Optional[str]
    y_axis_label: Optional[str]
    x_axis_column: Optional[TypeResourceSchema]
    y_axis_column: Optional[List[YAxisColumnConfigType]]
    region_column: Optional[TypeResourceSchema]
    value_column: Optional[TypeResourceSchema]
    time_column: Optional[TypeResourceSchema]
    show_legend: Optional[bool]
    aggregate_type: Optional[str]


class ChartOptionsTypeDict(TypedDict, total=False):
    """Type for chart options dictionary."""

    x_axis_column: str
    y_axis_column: Union[Dict[str, Any], List[Dict[str, Any]]]
    time_column: Optional[Dict[str, Any]]
    filters: Optional[List[Dict[str, Any]]]
    aggregation: Optional[Dict[str, Any]]


def ensure_type(
    value: Any,
    target_type: Type[BaseType],
    element_type: Optional[Type[BaseType]] = None,
) -> Any:
    """Ensure value is converted to the correct Strawberry type.

    Args:
        value: Value to convert
        target_type: Target type to convert to
        element_type: Element type for lists

    Returns:
        Converted value
    """
    if value is None:
        return None

    if isinstance(value, dict):
        return target_type.from_dict(value)

    if isinstance(value, list) and element_type:
        return [ensure_type(item, element_type) for item in value]

    return value


@strawberry_django.type(ResourceChartDetails)
class TypeResourceChart(BaseType):
    """Type for resource chart."""

    id: uuid.UUID
    name: str
    chart_type: str
    created: datetime
    modified: datetime
    description: Optional[str] = ""

    @strawberry.field
    def resource(self: Any) -> Optional[TypeResource]:
        """Get resource for this chart."""
        return TypeResource.from_django(self.resource)

    @strawberry.field
    def chart_options(self) -> Optional[ChartOptionsType]:
        """Convert stored JSONField `options` into ChartOptionsType."""
        try:
            options_dict = getattr(self, "options", {}) or {}
            if not options_dict:
                return None

            return ChartOptionsType(
                x_axis_label=options_dict.get("x_axis_label"),
                y_axis_label=options_dict.get("y_axis_label"),
                x_axis_column=(
                    ensure_type(options_dict.get("x_axis_column"), TypeResourceSchema)
                    if options_dict.get("x_axis_column")
                    else None
                ),
                y_axis_column=(
                    [
                        YAxisColumnConfigType(
                            field=ensure_type(col.get("field"), TypeResourceSchema),
                            label=col.get("label"),
                            color=col.get("color"),
                            value_mapping=(
                                [
                                    ValueMappingType(key=vm["key"], value=vm["value"])
                                    for vm in col.get("value_mapping", [])
                                ]
                                if col.get("value_mapping")
                                else None
                            ),
                        )
                        for col in options_dict.get("y_axis_column", [])
                    ]
                    if options_dict.get("y_axis_column")
                    else None
                ),
                region_column=(
                    ensure_type(options_dict.get("region_column"), TypeResourceSchema)
                    if options_dict.get("region_column")
                    else None
                ),
                value_column=(
                    ensure_type(options_dict.get("value_column"), TypeResourceSchema)
                    if options_dict.get("value_column")
                    else None
                ),
                time_column=(
                    ensure_type(options_dict.get("time_column"), TypeResourceSchema)
                    if options_dict.get("time_column")
                    else None
                ),
                show_legend=options_dict.get("show_legend"),
                aggregate_type=options_dict.get("aggregate_type"),
            )
        except (AttributeError, KeyError):
            return None

    @strawberry.field
    def chart_filters(self) -> List[FilterType]:
        """Convert stored JSONField `filters` into List[FilterType]."""
        try:
            filters_list = getattr(self, "filters", []) or []
            return [
                FilterType(
                    column=(
                        ensure_type(f["column"], TypeResourceSchema)
                        if f.get("column")
                        else None
                    ),
                    operator=f["operator"],
                    value=f["value"],
                )
                for f in filters_list
            ]
        except (AttributeError, KeyError):
            return []

    @strawberry.field
    def chart(self, info: Info) -> Optional[ChartConfig]:
        """Get chart configuration."""
        chart_instance = chart_base(cast(ResourceChartDetails, self))
        if not chart_instance:
            return None

        # Convert chart to JSON-serializable format
        chart_options = (
            chart_instance.dump_options_with_quotes() if chart_instance else None
        )
        if not chart_options:
            return None

        return ChartConfig(
            options=json.loads(chart_options),
            width=chart_instance.width,
            height=chart_instance.height,
            renderer=chart_instance.renderer,
        )
