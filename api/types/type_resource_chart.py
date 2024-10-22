import json
from functools import lru_cache
from typing import Optional

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


@strawberry_django.type(ResourceChartDetails, fields="__all__")
class TypeResourceChart:
    resource: TypeResource
    chart: JSON
    x_axis_column: Optional[TypeResourceSchema]
    y_axis_column: Optional[TypeResourceSchema]
    region_column: Optional[TypeResourceSchema]
    value_column: Optional[TypeResourceSchema]

    @strawberry.field
    def chart(self: ResourceChartDetails, info) -> JSON:
        base_chart = chart_base(self)
        if base_chart:
            options = base_chart.dump_options_with_quotes()
            return json.loads(options)
        else:
            return {}
