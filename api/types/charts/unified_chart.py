import json
from typing import Any, Dict, List, Optional, Union, cast

import pandas as pd
import structlog
from pyecharts import options as opts
from pyecharts.charts import Timeline
from pyecharts.charts.basic_charts.line import Line
from pyecharts.charts.chart import Chart
from pyecharts.commons.utils import JsCode

from api.types.charts.base_chart import BaseChart, ChartOptions, DjangoFieldLike
from api.types.charts.chart_registry import register_chart
from api.utils.enums import AggregateType

logger = structlog.get_logger("dataspace.charts")


@register_chart("BAR")
@register_chart("LINE")
class UnifiedChart(BaseChart):
    """
    Chart class for creating bar and line visualizations.
    This class automatically handles all bar and line chart types including:
    - Single bar charts (vertical/horizontal)
    - Grouped bar charts (vertical/horizontal)
    - Line charts (single/multi-series)

    Chart behavior is determined by the chart_type and options like 'orientation', 'allow_multi_series', and 'stacked'.
    """

    def create_chart(self) -> Optional[Chart]:
        """Create a chart (bar or line, single or multi-series).

        Returns:
            Optional[Chart]: The created chart or None if requirements are not met.
        """
        # Validate basic requirements
        if "x_axis_column" not in self.options or "y_axis_column" not in self.options:
            return None

        # Use base chart's implementation
        return super().create_chart()

    def get_chart_specific_opts(self) -> Dict[str, Any]:
        """Override chart specific options based on chart type.

        Returns:
            Dict[str, Any]: The chart-specific options.
        """
        base_opts = super().get_chart_specific_opts()

        # Configure x-axis labels
        base_opts["xaxis_opts"].axislabel_opts = opts.LabelOpts(
            rotate=45, interval=0, margin=8
        )

        # Get y-axis columns for potential use in options
        y_axis_columns = self._get_y_axis_columns()

        # Set axis options based on orientation option for bar charts
        if self.chart_details.chart_type == "BAR":
            orientation = self.options.get("orientation", "vertical")
            if orientation == "horizontal":
                base_opts.update(
                    {
                        "xaxis_opts": opts.AxisOpts(type_="value"),
                        "yaxis_opts": opts.AxisOpts(type_="category"),
                    }
                )

        # Add line chart specific options
        if self.chart_details.chart_type == "LINE":
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
        """Override to provide chart-specific initialization options."""
        return opts.InitOpts(
            width=self.options.get("width", "100%"),
            height=self.options.get("height", "400px"),
            theme=self.options.get("theme", "white"),
        )

    def add_series_to_chart(
        self,
        chart: Chart,
        series_name: str,
        y_values: List[Any],
        color: Optional[str] = None,
        value_mapping: Optional[Dict[Any, Any]] = None,
    ) -> None:
        """Override to add chart-specific styling based on chart type."""

        # For bar charts, use the standard approach with bar-specific styling
        if self.chart_details.chart_type == "BAR":
            super().add_series_to_chart(
                chart, series_name, y_values, color, value_mapping
            )
            # Add bar-specific options
            bar_options = {
                "barGap": "30%",
                "barCategoryGap": "20%",
                "label": {
                    "show": False,  # Hide bar value labels
                },
                "itemStyle": {
                    "opacity": 0.8,  # Slightly transparent bars
                    "color": (
                        color if color else None
                    ),  # Explicitly set color in itemStyle
                },
            }

            # Add stack option if stacked bar is enabled
            is_stacked = self.options.get("stacked", False)

            if is_stacked and self._is_multi_series():
                bar_options["stack"] = "total"

            chart.options["series"][-1].update(bar_options)

        # For line charts, use specialized line styling
        elif self.chart_details.chart_type == "LINE":
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
                    logger.warning(
                        f"Could not convert y_value to float: {val}, error: {e}"
                    )
                    # Add a default value if conversion fails
                    data.append(
                        opts.LineItem(
                            name="0", value=0.0, symbol_size=8, symbol="emptyCircle"
                        )
                    )

            # Add the series to the chart
            chart.add_yaxis(
                series_name=series_name,
                y_axis=data,
                label_opts=opts.LabelOpts(is_show=False),
                color=color if color else None,
                linestyle_opts=opts.LineStyleOpts(width=2, type_="solid"),
                is_smooth=True,
                is_symbol_show=True,
            )
        else:
            # For any other chart types, use the base implementation
            super().add_series_to_chart(
                chart, series_name, y_values, color, value_mapping
            )

    def _is_multi_series(self) -> bool:
        """Determine if this chart has multiple series based on y-axis columns.

        Returns:
            bool: True if there are multiple y-axis columns, False otherwise.
        """
        y_axis_columns = self._get_y_axis_columns()
        return len(y_axis_columns) > 1

    def map_value(self, value: float, value_mapping: Dict[str, str]) -> str:
        """Map a numeric value to its string representation.

        Args:
            value (float): The value to map.
            value_mapping (Dict[str, str]): The value mapping.

        Returns:
            str: The mapped value.
        """
        if pd.isna(value):
            return "0"

        return str(value_mapping.get(str(value), str(value)))

    def configure_chart(
        self, chart: Chart, filtered_data: Optional[pd.DataFrame] = None
    ) -> None:
        """Configure chart with data.

        This implementation handles both single and grouped bar charts.
        For single bar charts, it uses only the first y-axis column.
        For grouped bar charts, it uses multiple y-axis columns.
        """
        if filtered_data is None or filtered_data.empty:
            return

        # Process data based on chart type
        processed_data = self._process_data(filtered_data)

        # Get x-axis data
        x_axis_field = cast(DjangoFieldLike, self.options["x_axis_column"])
        x_field = x_axis_field.field_name
        x_axis_data = self._get_x_axis_data(processed_data, x_field)

        # Add x-axis
        chart.add_xaxis(x_axis_data)

        # Get y-axis columns
        y_axis_columns = self._get_y_axis_columns()

        # Determine if this is a multi-series chart based on y-axis columns count
        is_multi_series = self._is_multi_series()

        # For LINE chart type with single y-column, we always use all columns
        # For BAR chart type, we check the 'allow_multi_series' option
        allow_multi_series = self.options.get("allow_multi_series", True)

        # Check if we should use stacked bar chart
        is_stacked = self.options.get("stacked", False)

        # If it's a bar chart and multi-series is not allowed, use only the first column
        if (
            self.chart_details.chart_type == "BAR"
            and not allow_multi_series
            and is_multi_series
        ):
            y_axis_columns = [y_axis_columns[0]]

        # Add series for each y-axis column
        for y_axis_column in y_axis_columns:
            field = cast(DjangoFieldLike, y_axis_column["field"])
            if not field:
                continue

            field_name = field.field_name
            series_name = self._get_series_name(y_axis_column)
            color = y_axis_column.get("color")

            # Get y values aligned with x-axis data
            y_values = self._get_y_values(
                processed_data, x_axis_data, x_field, field_name
            )

            # Add the series to the chart
            self.add_series_to_chart(
                chart=chart,
                series_name=series_name,
                y_values=y_values,
                color=color,
                value_mapping=y_axis_column.get("value_mapping", {}),
            )

        # Apply chart-specific customizations for horizontal orientation in bar charts
        if self.chart_details.chart_type == "BAR":
            orientation = self.options.get("orientation", "vertical")
            if orientation == "horizontal":
                chart.reversal_axis()
