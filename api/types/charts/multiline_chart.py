from typing import Any, Dict, List, Optional, cast

import pandas as pd
import structlog
from pyecharts import options as opts
from pyecharts.charts.basic_charts.line import Line
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
            position="bottom",  # Position labels at the bottom
            rotate=45,
            interval=0,
            margin=10,
            font_size=12,
            is_show=True,  # Ensure labels are shown
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
            renderer="canvas",  # Use canvas renderer for better performance and responsiveness
            animation_opts=opts.AnimationOpts(
                animation=False
            ),  # Disable animation for better performance
        )

    def add_series_to_chart(
        self,
        chart: Chart,
        series_name: str,
        y_values: List[Any],
        color: Optional[str] = None,
        value_mapping: Optional[Dict[Any, Any]] = None,
    ) -> None:
        """Override to add line chart specific styling."""
        # Create a list of value objects with original and formatted values
        data = []
        for val in y_values:
            try:
                # Keep original numeric value for plotting
                value = float(val) if val is not None else 0.0
                # Get mapped string value for display
                label = (
                    value_mapping.get(str(value), str(value))
                    if value_mapping
                    else str(value)
                )
                data.append(
                    opts.LineItem(
                        name=label, value=value, symbol_size=8, symbol="emptyCircle"
                    )
                )
            except (ValueError, TypeError) as e:
                logger.warning(f"Could not convert y_value to float: {val}, error: {e}")
                # Add a default value if conversion fails
                data.append(
                    opts.LineItem(
                        name="0", value=0.0, symbol_size=8, symbol="emptyCircle"
                    )
                )

        # Add the series to the chart with improved label positioning
        chart.add_yaxis(
            series_name=series_name,
            y_axis=data,
            label_opts=opts.LabelOpts(
                is_show=True,
                position="bottom",  # Position labels at the bottom
                font_size=12,
                font_weight="normal",
                color="#333",
            ),
            itemstyle_opts=opts.ItemStyleOpts(color=color) if color else None,
            linestyle_opts=opts.LineStyleOpts(width=2, type_="solid"),
            is_smooth=True,
            is_symbol_show=True,
        )

        # Set chart renderer for better responsiveness
        chart.renderer = "canvas"

        # Add responsive configuration
        chart.js_host = ""

        # Add additional initialization options for responsiveness
        if not hasattr(chart, "options") or not chart.options:
            chart.options = {}

        chart.options.update(
            {
                "animation": False,  # Disable animation for better performance
            }
        )
