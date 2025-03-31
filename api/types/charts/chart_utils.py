from typing import Any, Dict, List, Optional, Union, cast

import pandas as pd
from pandas import DataFrame
from pyecharts import options as opts
from pyecharts.charts import Map

from api.models import ResourceChartDetails
from api.types.charts.base_chart import DjangoFieldLike


def _get_map_chart(
    chart_details: ResourceChartDetails, data: DataFrame, values: List[Any]
) -> Map:
    """Create a map chart with the given data and options."""
    options = cast(Dict[str, Any], chart_details.options)
    value_col = cast(DjangoFieldLike, options.get("value_column")).field_name

    map_chart = Map(init_opts=opts.InitOpts(width="1000px", height="100")).add(
        series_name=value_col,
        data_pair=values,
        maptype=f"{chart_details.chart_type.lower().replace('', '')}",
    )

    # Set series options
    show_legend = cast(bool, options.get("show_legend", True))
    map_chart.set_series_opts(label_opts=opts.LabelOpts(is_show=show_legend))

    # Set global options
    value_col_data = data[value_col] if value_col in data.columns else pd.Series([0])
    map_chart.set_global_opts(
        visualmap_opts=opts.VisualMapOpts(
            max_=int(value_col_data.max()),
            min_=int(value_col_data.min()),
            range_text=["High", "Low"],
            range_size=[10],
            is_calculable=True,
            orient="vertical",
            pos_left="right",
            pos_top="bottom",
        ),
        toolbox_opts=opts.ToolboxOpts(
            feature=opts.ToolBoxFeatureOpts(
                data_zoom=opts.ToolBoxFeatureDataZoomOpts(
                    is_show=False, zoom_title="Zoom", back_title="Back"
                ),
                restore=opts.ToolBoxFeatureRestoreOpts(is_show=True, title="Reset"),
                data_view=opts.ToolBoxFeatureDataViewOpts(
                    is_show=True,
                    title="View Data",
                    lang=["View Data", "Close", "Refresh"],
                ),
                save_as_image=opts.ToolBoxFeatureSaveAsImageOpts(
                    is_show=True, title="Save as Image"
                ),
            )
        ),
        legend_opts=opts.LegendOpts(
            is_show=True,
            selected_mode=True,
            pos_top="5%",  # Move legend higher
            pos_left="center",  # Center horizontally
            orient="horizontal",
            item_gap=25,  # Add more space between legend items
            padding=[5, 10, 20, 10],  # Add padding [top, right, bottom, left]
            textstyle_opts=opts.TextStyleOpts(font_size=12),
            border_width=0,  # Remove border
            background_color="transparent",  # Make background transparent
        ),
    )
    return map_chart
