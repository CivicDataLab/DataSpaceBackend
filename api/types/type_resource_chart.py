import json
from functools import lru_cache
from typing import Any, Dict, List, Optional, Type, TypedDict, TypeVar, Union, cast

import pandas as pd
import strawberry
import strawberry_django
from django.core.serializers.json import DjangoJSONEncoder
from pyecharts.charts.chart import Chart
from strawberry import auto
from strawberry.types import Info

from api.models import ResourceChartDetails
from api.types import TypeResource
from api.types.base_type import BaseType
from api.types.charts.chart_registry import CHART_REGISTRY
from api.types.type_file_details import TypeFileDetails
from api.types.type_resource import TypeResourceSchema

T = TypeVar("T", bound="TypeResourceChart")


@lru_cache()
def load_csv(filepath: str) -> pd.DataFrame:
    """Load CSV file into a pandas DataFrame.

    Args:
        filepath: Path to the CSV file

    Returns:
        pd.DataFrame: Loaded DataFrame
    """
    return pd.read_csv(filepath)


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


class ChartOptionsTypeDict(TypedDict):
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

    id: auto
    name: auto
    description: auto
    chart_type: auto
    resource: TypeResource
    created: auto
    modified: auto

    @strawberry.field
    def options(self) -> Optional[ChartOptionsType]:
        """Convert stored JSONField `options` into ChartOptionsType.

        Returns:
            Optional[ChartOptionsType]: Chart options if present, None otherwise
        """
        if not self.options:
            return None
        options_str = (
            self.options if isinstance(self.options, str) else json.dumps(self.options)
        )
        options_dict = json.loads(options_str)
        return ChartOptionsType.from_dict(options_dict)

    @strawberry.field
    def filters(self) -> Optional[List[FilterType]]:
        """Convert stored JSONField `filters` into List[FilterType]."""
        if not self.filters:
            return None
        filters_str = (
            self.filters if isinstance(self.filters, str) else json.dumps(self.filters)
        )
        filters_list = json.loads(filters_str)
        if not isinstance(filters_list, list):
            return None

        result: List[FilterType] = []
        for filter_dict in filters_list:
            if filter_dict is not None:
                filter_obj = FilterType.from_dict(filter_dict)
                if filter_obj is not None:
                    result.append(filter_obj)
        return result if result else None

    @strawberry.field
    def chart(self, info: Info) -> Optional[Dict[str, Any]]:
        """Get chart configuration.

        Args:
            info: Request info

        Returns:
            Optional[Dict[str, Any]]: Chart configuration if successful, None otherwise
        """
        chart_obj = chart_base(cast(ResourceChartDetails, self))
        if not chart_obj:
            return None
        return cast(Dict[str, Any], chart_obj.dump_options())

    @strawberry.field
    def chart_data(self, info: Info) -> Optional[List[Dict[str, Any]]]:
        """Get chart data for the resource.

        Args:
            info: Request info

        Returns:
            Optional[List[Dict[str, Any]]]: Chart data if successful, None otherwise
        """
        if not hasattr(self.resource, "resource_file_details"):
            return None

        file_details = self.resource.resource_file_details
        if not file_details or file_details.format.lower() != "csv":
            return None

        try:
            df = load_csv(file_details.file.path)
            return cast(List[Dict[str, Any]], df.to_dict("records"))
        except (AttributeError, FileNotFoundError):
            return None

    @strawberry.field
    def preview_data(self, info: Info) -> Optional[List[Dict[str, Any]]]:
        """Get preview data for the chart.

        Args:
            info: Request info

        Returns:
            Optional[List[Dict[str, Any]]]: Preview data if successful, None otherwise
        """
        try:
            file_details = getattr(self.resource, "resourcefiledetails", None)
            if not file_details or not getattr(self.resource, "preview_details", None):
                return None

            df = load_csv(file_details.file.path)
            if getattr(self.resource.preview_details, "is_all_entries", False):
                return cast(List[Dict[str, Any]], df.to_dict("records"))

            start = getattr(self.resource.preview_details, "start_entry", None)
            end = getattr(self.resource.preview_details, "end_entry", None)
            return cast(List[Dict[str, Any]], df.iloc[start:end].to_dict("records"))
        except (AttributeError, FileNotFoundError):
            return None
