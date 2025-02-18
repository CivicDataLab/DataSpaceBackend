import json
from functools import lru_cache
from typing import Optional, List

import pandas as pd
import strawberry
import strawberry_django
from pyecharts.charts.chart import Chart
from strawberry.scalars import JSON

from api.models import ResourceChartDetails
from api.types import TypeResource
from api.types.charts.chart_registry import CHART_REGISTRY
from api.types.type_resource import TypeResourceSchema


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
    field_name: Optional[TypeResourceSchema]
    label: Optional[str]
    color: Optional[str]
    value_mapping: Optional[List[ValueMappingType]]

@strawberry.type
class ChartOptionsType:
    x_axis_label: Optional[str]
    y_axis_label: Optional[str]
    x_axis_column: Optional[TypeResourceSchema]
    y_axis_column: Optional[YAxisColumnConfigType]
    region_column: Optional[TypeResourceSchema]
    value_column: Optional[TypeResourceSchema]
    time_column: Optional[TypeResourceSchema]
    show_legend: Optional[bool]
    aggregate_type: Optional[str]

@strawberry_django.type(ResourceChartDetails, fields="__all__")
class TypeResourceChart:
    resource: TypeResource
    chart_type: str
    options: Optional[ChartOptionsType]
    filters: Optional[List[FilterType]]

    @strawberry.field
    def options(self) -> Optional[ChartOptionsType]:
        """Convert stored JSONField `options` into ChartOptionsType"""
        if not self.options:  # Handle None case
            return None
        return ChartOptionsType(**self.options)

    @strawberry.field
    def filters(self) -> Optional[List[FilterType]]:
        """Convert stored JSONField `filters` into List[FilterType]"""
        if not self.filters:  # Handle None or empty cases
            return []
        return [FilterType(**f) for f in self.filters]

    @strawberry.field
    def chart(self: ResourceChartDetails, info) -> JSON:
            base_chart = chart_base(self)
            if base_chart:
                options = base_chart.dump_options_with_quotes()
                return json.loads(options)
            else:
                return {}
