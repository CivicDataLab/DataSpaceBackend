import json
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union, cast

import pandas as pd
from pyecharts import options as opts
from pyecharts.charts import Timeline
from pyecharts.charts.chart import Chart
from pyecharts.commons.utils import JsCode

from api.types.charts.base_chart import BaseChart, ChartOptions, DjangoFieldLike
from api.types.charts.chart_registry import register_chart
from api.utils.enums import AggregateType


@register_chart("BAR_HORIZONTAL")
@register_chart("BAR_VERTICAL")
# @register_chart("LINE")
class BarChart(BaseChart):
    def configure_chart(
        self, chart: Chart, filtered_data: Optional[pd.DataFrame] = None
    ) -> None:
        """Configure chart with data.

        For bar charts, we only use the first y-axis column if multiple are provided.
        """
        if filtered_data is None or filtered_data.empty:
            return

        # For bar chart, only use the first y-axis column but preserve original options
        y_axis_column = self.options.get("y_axis_column", [])
        chart_options = self.options.copy()  # Create a copy to avoid modifying original

        if isinstance(y_axis_column, list) and y_axis_column:
            chart_options["y_axis_column"] = y_axis_column[0]

        # Temporarily set options to our modified version
        original_options = self.options
        self.options = chart_options

        try:
            # Process data based on chart type
            processed_data = self._process_data(filtered_data)

            # Get x-axis data
            x_axis_field = cast(DjangoFieldLike, self.options["x_axis_column"])
            x_field = x_axis_field.field_name
            x_axis_data = self._get_x_axis_data(processed_data, x_field)

            # Add x-axis
            chart.add_xaxis(x_axis_data)

            # Add series for the y-axis column
            y_axis_col = chart_options.get("y_axis_column")
            if not y_axis_col or not isinstance(y_axis_col, dict):
                return

            field = cast(DjangoFieldLike, y_axis_col.get("field"))
            if not field:
                return

            field_name = field.field_name
            series_name = self._get_series_name(y_axis_col)
            color = y_axis_col.get("color")

            # Get y values aligned with x-axis data using BaseChart method
            y_values = self._get_y_values(
                processed_data, x_axis_data, x_field, field_name
            )

            # Add the series to the chart
            self.add_series_to_chart(
                chart=chart,
                series_name=series_name,
                y_values=y_values,
                color=color,
                value_mapping=y_axis_col.get("value_mapping", {}),
            )

            # Apply chart-specific customizations for horizontal orientation
            if self.chart_details.chart_type == "BAR_HORIZONTAL":
                chart.reversal_axis()

            # Set chart size with responsive configuration
            width = cast(str, self.options.get("width", "800px"))
            height = cast(str, self.options.get("height", "600px"))
            chart.width = width
            chart.height = height
        finally:
            # Restore original options
            self.options = original_options

    def get_chart_specific_opts(self) -> dict:
        """Override chart specific options for bar chart."""
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

        # Set axis options based on chart type
        if self.chart_details.chart_type == "BAR_HORIZONTAL":
            base_opts.update(
                {
                    "xaxis_opts": opts.AxisOpts(type_="value"),
                    "yaxis_opts": opts.AxisOpts(
                        type_="category",
                        # For horizontal bars, position labels on the left
                        axislabel_opts=opts.LabelOpts(
                            position="left", font_size=12, is_show=True
                        ),
                    ),
                }
            )
        else:
            # For vertical bars, ensure labels are at the bottom
            base_opts.update(
                {
                    "xaxis_opts": opts.AxisOpts(
                        type_="category",
                        axislabel_opts=opts.LabelOpts(
                            position="bottom",
                            rotate=45,
                            interval=0,
                            margin=10,
                            font_size=12,
                            is_show=True,
                        ),
                    )
                }
            )

        return base_opts

    def add_series_to_chart(
        self,
        chart: Chart,
        series_name: str,
        y_values: List[Any],
        color: Optional[str] = None,
        value_mapping: Optional[Dict[Any, Any]] = None,
    ) -> None:
        """Override to add bar-specific styling."""
        super().add_series_to_chart(chart, series_name, y_values, color, value_mapping)

        # Add bar-specific options with improved styling
        chart.options["series"][-1].update(
            {
                "barGap": "30%",
                "barCategoryGap": "20%",
                # Add label configuration
                "label": {
                    "show": True,
                    "position": "top",
                    "fontSize": 12,
                    "fontWeight": "normal",
                },
                # Make bars responsive
                "emphasis": {"focus": "series"},
            }
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
