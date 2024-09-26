import json
from random import randrange
from typing import Optional

import pandas as pd
import strawberry
import strawberry_django
from pyecharts import options as opts
from pyecharts.charts import Line, Bar
from pyecharts.charts.chart import RectChart
from strawberry.scalars import JSON

from api.models import ResourceChartDetails
from api.types import TypeResource
from api.types.type_resource import TypeResourceSchema

# Define a mapping for chart types
CHART_TYPE_MAP = {
    "BAR_VERTICAL": Bar,
    "BAR_HORIZONTAL": Bar,
    "LINE": Line,
    # Add more chart types here
}


def chart_base(chart_details: ResourceChartDetails) -> Optional[RectChart]:
    # Ensure that x_axis_column and y_axis_column exist
    if not chart_details.x_axis_column or not chart_details.y_axis_column:
        return None

    # Load the data
    data = pd.read_csv(chart_details.resource.resourcefiledetails.file.path)

    # Perform aggregation based on chart details
    metrics = data.groupby(chart_details.x_axis_column.field_name).agg(
        {chart_details.y_axis_column.field_name: chart_details.aggregate_type.lower()}
    ).reset_index()

    # Rename the columns based on x-axis and y-axis
    metrics.columns = [chart_details.x_axis_column.field_name, chart_details.y_axis_column.field_name]

    # Determine the chart class dynamically based on chart_type
    chart_class = CHART_TYPE_MAP.get(chart_details.chart_type)
    if not chart_class:
        return None  # If chart type is not supported

    chart = chart_class()

    # Add x and y axis data
    chart.add_xaxis(metrics[chart_details.x_axis_column.field_name].tolist())
    chart.add_yaxis(chart_details.y_axis_label, metrics[chart_details.y_axis_column.field_name].tolist())
    if chart_details.chart_type == "BAR_HORIZONTAL":
        chart.reversal_axis()
        chart.set_series_opts(label_opts=opts.LabelOpts(position="right"))  # Adjust label for horizontal bars
        chart.set_global_opts(xaxis_opts=opts.AxisOpts(type_="category", name=chart_details.y_axis_label),
                              yaxis_opts=opts.AxisOpts(type_="value", name=chart_details.x_axis_label))

    # Global options like title, description, legend, etc.
    chart.set_global_opts(
        # title_opts=opts.TitleOpts(title=chart_details.name, subtitle=chart_details.description),
        legend_opts=opts.LegendOpts(is_show=chart_details.show_legend),
        xaxis_opts=opts.AxisOpts(name=chart_details.x_axis_label),
        yaxis_opts=opts.AxisOpts(name=chart_details.y_axis_label),
    )

    # Set horizontal/vertical layout based on chart type


    return chart

@strawberry_django.type(ResourceChartDetails, fields="__all__")
class TypeResourceChart:
    resource: TypeResource
    chart: JSON
    x_axis_column: Optional[TypeResourceSchema]
    y_axis_column: Optional[TypeResourceSchema]

    @strawberry.field
    def chart(self: ResourceChartDetails, info) -> JSON:
        base_chart = chart_base(self)
        if base_chart:
            return json.loads(base_chart.dump_options_with_quotes())
        else:
            return {}
