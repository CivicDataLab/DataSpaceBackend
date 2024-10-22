import json
from typing import Optional, Tuple, List

import pandas as pd
import strawberry
import strawberry_django
from pyecharts import options as opts
from pyecharts.charts import Line, Bar, Geo, Map, Page
from pyecharts.charts.basic_charts.geo import GeoChartBase
from pyecharts.charts.chart import Chart
from pyecharts.commons.utils import JsCode
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


def chart_base(chart_details: ResourceChartDetails) -> None | Chart:
    if chart_details.resource.resourcefiledetails.format.lower() != "csv":
        return None
    # Load the data
    data = pd.read_csv(chart_details.resource.resourcefiledetails.file.path)
    # Determine the chart class dynamically based on chart_type
    chart_class = CHART_TYPE_MAP.get(chart_details.chart_type)
    if not chart_class:
        return None  # If chart type is not supported

    if chart_details.chart_type == "ASSAM_DISTRICT":
        district_col = chart_details.region_column.field_name
        value_col = chart_details.value_column.field_name
        data[district_col] = data[district_col].str.upper()
        district_values = data[[district_col, value_col]].values.tolist()
        geo_chart = Map(init_opts=opts.InitOpts(width="1000px", height="100")) \
            .add(
            series_name="District Data",
            data_pair=district_values,
            maptype="assam_district",
        ) \
            .set_global_opts(title_opts=opts.TitleOpts(title="Assam Districts")) \
            .set_series_opts(label_opts=opts.LabelOpts(is_show=chart_details.show_legend))
        print(data[value_col].max(), data[value_col].min())
        geo_chart.set_global_opts(
            title_opts=opts.TitleOpts(title="Assam District Data"),
            visualmap_opts=opts.VisualMapOpts(
                max_=int(data[value_col].max()),
                min_=int(data[value_col].min()),
                # range_color=["#313695", "#4575b4", "#74add1", "#abd9e9", "#e0f3f8",
                #              "#ffffbf", "#fee090", "#fdae61", "#f46d43", "#d73027",
                #              "#a50026", ],
                range_text=["High", "Low"],
                range_size=[10],
                is_calculable=True,
                orient="vertical",
                pos_left="right",
                pos_top="bottom",
            )
        )
        return geo_chart
    elif chart_details.chart_type == "ASSAM_RC":
        geojson_file = "api/types/map_base/assam_revenue_circles.geojson"
        rc_col = chart_details.region_column.field_name
        value_col = chart_details.value_column.field_name
        with open(geojson_file, 'r') as f:
            geojson = json.load(f)
        rc_values = data[[rc_col, value_col]].values.tolist()
        geo_chart = Geo()
        geo_chart.add_coordinate_json(geojson)
        geo_chart.add(
            series_name="RC Data",
            data_pair=rc_values,
            type_=GeoType.HEATMAP)  # You can also use SCATTER or EFFECT_SCATTER
        return geo_chart
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
