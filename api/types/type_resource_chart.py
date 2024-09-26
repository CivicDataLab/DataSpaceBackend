import json
from typing import Optional

import pandas as pd
import strawberry
import strawberry_django
from pyecharts import options as opts
from pyecharts.charts import Line, Bar, Geo
from pyecharts.charts.chart import RectChart
from pyecharts.globals import GeoType
from strawberry.scalars import JSON

from api.models import ResourceChartDetails
from api.types import TypeResource
from api.types.type_resource import TypeResourceSchema

# Define a mapping for chart types
CHART_TYPE_MAP = {
    "BAR_VERTICAL": Bar,
    "BAR_HORIZONTAL": Bar,
    "LINE": Line,
    "ASSAM_DISTRICT": Geo,
    "ASSAM_RC": Geo
    # Add more chart types here
}


def chart_base(chart_details: ResourceChartDetails) -> Optional[RectChart]:
    # Load the data
    data = pd.read_csv(chart_details.resource.resourcefiledetails.file.path)
    # Determine the chart class dynamically based on chart_type
    chart_class = CHART_TYPE_MAP.get(chart_details.chart_type)
    if not chart_class:
        return None  # If chart type is not supported

    if chart_details.chart_type == "ASSAM_DISTRICT":
        geojson_file = "api/geojson/assam_districts.json"
        district_col = chart_details.region_column.field_name
        value_col = chart_details.value_column.field_name
        with open(geojson_file, 'r') as f:
            geojson = json.load(f)
        # Register the map with a custom name "ASSAM"
        from pyecharts.datasets import register_map

        register_map("ASSAM_DISTRICT", geojson)  # Register custom map
        district_values = data[[district_col, value_col]].values.tolist()
        geo = (
            Geo()
            .add_schema(maptype="ASSAM_DISTRICT")
            .add(
                series_name="District Data",
                data_pair=district_values,
                type_=GeoType.HEATMAP  # You can also use SCATTER or EFFECT_SCATTER
            )
            .set_series_opts(label_opts=opts.LabelOpts(is_show=False))  # Hide labels
            .set_global_opts(
                title_opts=opts.TitleOpts(title="Assam District Data"),
                visualmap_opts=opts.VisualMapOpts(max_=data[value_col].max())  # Visual scale
            )
        )
        return geo
    # Ensure that x_axis_column and y_axis_column exist
    if not chart_details.x_axis_column or not chart_details.y_axis_column:
        return None

    # Perform aggregation based on chart details
    metrics = data.groupby(chart_details.x_axis_column.field_name).agg(
        {chart_details.y_axis_column.field_name: chart_details.aggregate_type.lower()}
    ).reset_index()

    # Rename the columns based on x-axis and y-axis
    metrics.columns = [chart_details.x_axis_column.field_name, chart_details.y_axis_column.field_name]

    chart = chart_class()

    # Add x and y axis data (no swapping)
    chart.add_xaxis(metrics[chart_details.x_axis_column.field_name].tolist())
    chart.add_yaxis(chart_details.y_axis_label, metrics[chart_details.y_axis_column.field_name].tolist())

    # Configure horizontal or vertical layout based on chart_type
    if chart_details.chart_type == "BAR_HORIZONTAL":
        chart.reversal_axis()  # Correctly renders bars horizontally
        chart.set_series_opts(label_opts=opts.LabelOpts(position="right"))  # Labels on right for horizontal bars
        chart.set_global_opts(
            legend_opts=opts.LegendOpts(is_show=chart_details.show_legend),
            xaxis_opts=opts.AxisOpts(type_="value", name=chart_details.y_axis_label),  # Value on x-axis for horizontal
            yaxis_opts=opts.AxisOpts(type_="category", name=chart_details.x_axis_label)
            # Category on y-axis for horizontal
        )

    else:  # For BAR_VERTICAL and other chart types
        chart.set_global_opts(
            legend_opts=opts.LegendOpts(is_show=chart_details.show_legend),
            xaxis_opts=opts.AxisOpts(type_="category", name=chart_details.x_axis_label),  # Category on x-axis
            yaxis_opts=opts.AxisOpts(type_="value", name=chart_details.y_axis_label)  # Value on y-axis
        )

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
