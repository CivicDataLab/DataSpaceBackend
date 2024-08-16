import json
from random import randrange

import strawberry
import strawberry_django
from pyecharts import options as opts
from pyecharts.charts import Line
from pyecharts.charts.chart import RectChart
from strawberry.scalars import JSON

from api.models import ResourceChartDetails
from api.types import TypeResource


def chart_base() -> RectChart:
    chart = (
        Line()
        .add_xaxis(["python", "node", "java", "c#", "scala", "Rust"])
        .add_yaxis("like", [randrange(0, 100) for _ in range(6)])
        .add_yaxis("dislike", [randrange(0, 100) for _ in range(6)])
        .set_global_opts(title_opts=opts.TitleOpts(title="Chart", subtitle="Subtitle"))
    )
    return chart


@strawberry_django.type(ResourceChartDetails, fields="__all__")
class TypeResourceChart:
    resource: TypeResource
    chart: JSON

    @strawberry.field
    def chart(self, info) -> JSON:
        return json.loads(chart_base().dump_options_with_quotes())
