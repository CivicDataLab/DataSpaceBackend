from pyecharts import options as opts
from pyecharts.charts import Map

from api.models import ResourceChartDetails


def _get_map_chart(chart_details: ResourceChartDetails, data, values, value_col):
    geo_chart = Map(init_opts=opts.InitOpts(width="1000px", height="100")) \
        .add(
        series_name=value_col,
        data_pair=values,
        maptype=f"{chart_details.chart_type.lower().replace('', '')}",
    ) \
        .set_global_opts(title_opts=opts.TitleOpts(title=chart_details.name)) \
        .set_series_opts(label_opts=opts.LabelOpts(is_show=chart_details.show_legend))
    geo_chart.set_global_opts(
        title_opts=opts.TitleOpts(title=chart_details.name),
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
