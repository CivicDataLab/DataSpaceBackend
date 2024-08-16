import json
from random import randrange
import pandas as pd
import strawberry
import strawberry_django
from pyecharts import options as opts
from pyecharts.charts import Line, Bar
from pyecharts.charts.chart import RectChart
from strawberry.scalars import JSON

from api.models import ResourceChartDetails
from api.types import TypeResource


def chart_base(chart_details: ResourceChartDetails) -> RectChart:
    data = pd.read_csv(chart_details.resource.resourcefiledetails.file.path)
    metrics = data.groupby(chart_details.x_axis_column.field_name).agg(
        {chart_details.y_axis_column.field_name: chart_details.aggregate_type}).reset_index()
    metrics.columns = [chart_details.x_axis_column.field_name, chart_details.y_axis_column.field_name]
    chart = (
        Bar()
        .add_xaxis(metrics[chart_details.x_axis_column.field_name].tolist())
        .add_yaxis(chart_details.y_axis_label, metrics[chart_details.x_axis_column.field_name].tolist())
        # .add_yaxis("dislike", [randrange(0, 100) for _ in range(6)])
        .set_global_opts(title_opts=opts.TitleOpts(title=chart_details.name, subtitle=chart_details.description))
    )
    return chart


@strawberry_django.type(ResourceChartDetails, fields="__all__")
class TypeResourceChart:
    resource: TypeResource
    chart: JSON

    @strawberry.field
    def chart(self, info) -> JSON:
        return json.loads(chart_base(self).dump_options_with_quotes())
