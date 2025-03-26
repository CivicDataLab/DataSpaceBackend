from typing import Any, Dict, List, Optional, cast

import pandas as pd
import structlog
from pyecharts import options as opts
from pyecharts.charts.chart import Chart

from api.types.charts.base_chart import BaseChart, DjangoFieldLike
from api.types.charts.chart_registry import register_chart

logger = structlog.get_logger("dataspace.charts")


@register_chart("MULTILINE")
class MultiLineChart(BaseChart):

    def get_chart_specific_opts(self) -> dict:
        """Override chart specific options for line chart."""
        base_opts = super().get_chart_specific_opts()

        # Configure x-axis labels
        base_opts["xaxis_opts"].axislabel_opts = opts.LabelOpts(
            rotate=45, interval=0, margin=8
        )

        # Add line chart specific options
        y_axis_columns = self._get_y_axis_columns()
        base_opts.update(
            {
                "datazoom_opts": [
                    opts.DataZoomOpts(
                        is_show=True, type_="slider", range_start=0, range_end=100
                    ),
                    opts.DataZoomOpts(type_="inside"),
                ],
                "visualmap_opts": (
                    opts.VisualMapOpts(
                        is_show=False,
                        type_="continuous",
                        min_=0,
                        max_=len(y_axis_columns) - 1,
                    )
                    if len(y_axis_columns) > 1
                    else None
                ),
            }
        )
        return base_opts

    def get_init_opts(self) -> opts.InitOpts:
        """Override to provide line chart specific initialization options."""
        return opts.InitOpts(
            width=self.options.get("width", "100%"),
            height=self.options.get("height", "400px"),
            theme=self.options.get("theme", "white"),
        )

    def get_series_style_opts(self, color: Optional[str] = None) -> Dict[str, Any]:
        """Get line chart specific styling options."""
        # Line chart specific options
        return {
            "itemstyle_opts": opts.ItemStyleOpts(color=color) if color else None,
            "linestyle_opts": opts.LineStyleOpts(width=2, type_="solid"),
            "is_smooth": True,
            "is_symbol_show": True,
        }

    def add_series_to_chart(
        self,
        chart: Chart,
        series_name: str,
        y_values: List[Any],
        color: Optional[str] = None,
        value_mapping: Optional[Dict[Any, Any]] = None,
    ) -> None:
        """Add a series to the chart with specific styling.

        For MultiLineChart, we need to format the data as [x, y] pairs for proper rendering.
        """
        # For line charts, we need to create [x, y] pairs
        data = []
        x_axis_data = chart.options.get("xAxis", [{}])[0].get("data", [])
        logger.debug(f"x_axis_data: {x_axis_data}")
        logger.debug(f"y_values: {y_values}")

        for i, val in enumerate(y_values):
            if i < len(x_axis_data):
                x_val = x_axis_data[i]
                # Convert to float for plotting
                y_val = float(val) if val is not None else 0.0
                data.append([x_val, y_val])

        # Get series-specific styling options
        chart_opts = self.get_series_style_opts(color)

        # Add the series to the chart with the proper format
        chart.add_yaxis(
            series_name=series_name,
            y_axis=data,
            label_opts=opts.LabelOpts(is_show=False),
            **chart_opts,
        )
