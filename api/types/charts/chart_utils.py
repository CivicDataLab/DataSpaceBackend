from pyecharts import options as opts
from pyecharts.charts import Map

from api.models import ResourceChartDetails


def _get_map_chart(chart_details: ResourceChartDetails, data, values):
    value_col = chart_details.options.get("value_column").field_name
    map_chart = Map(init_opts=opts.InitOpts(width="1000px", height="100")) \
        .add(
        series_name=value_col,
        data_pair=values,
        maptype=f"{chart_details.chart_type.lower().replace('', '')}",
    )
    # map_chart.set_global_opts(title_opts=opts.TitleOpts(title=chart_details.name)) \
    map_chart.set_series_opts(label_opts=opts.LabelOpts(is_show=chart_details.options.get("show_legend", True)))
    map_chart.set_global_opts(
        # title_opts=opts.TitleOpts(title=chart_details.name),
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
        ),
        toolbox_opts=opts.ToolboxOpts(
            feature=opts.ToolBoxFeatureOpts(
                data_zoom=opts.ToolBoxFeatureDataZoomOpts(is_show=True, zoom_title="Zoom", back_title="Back"),
                restore=opts.ToolBoxFeatureRestoreOpts(is_show=True, title="Reset"),
                data_view=opts.ToolBoxFeatureDataViewOpts(is_show=True, title="View Data", lang=["View Data", "Close", "Refresh"]),
                save_as_image=opts.ToolBoxFeatureSaveAsImageOpts(is_show=True, title="Save Image")
            )
        ),
        legend_opts=opts.LegendOpts(
            pos_top="5%",
            pos_left="center",
            padding=[0, 10, 20, 10],
            textstyle_opts=opts.TextStyleOpts(font_size=12)
        )
    )
    return map_chart
