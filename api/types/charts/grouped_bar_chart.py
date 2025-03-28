import json
from typing import Any, Dict, List, Optional, Union, cast

import pandas as pd
from pyecharts import options as opts
from pyecharts.charts.chart import Chart

from api.types.charts.base_chart import BaseChart, DjangoFieldLike
from api.types.charts.chart_registry import register_chart


@register_chart("GROUPED_BAR_HORIZONTAL")
@register_chart("GROUPED_BAR_VERTICAL")
class GroupedBarChart(BaseChart):
    """Chart class for creating grouped bar visualizations."""

    def create_chart(self) -> Optional[Chart]:
        """Create a grouped bar chart.

        Returns:
            Optional[Chart]: The created chart or None if requirements are not met.
        """
        # Validate requirements for grouped bar
        if "x_axis_column" not in self.options or "y_axis_column" not in self.options:
            return None

        # Check if we have multiple y-axis columns for grouped bar chart
        y_axis_columns = cast(List[Dict[str, Any]], self.options["y_axis_column"])
        if len(y_axis_columns) <= 1:
            return None

        # Use base chart's implementation
        return super().create_chart()

    def get_chart_specific_opts(self) -> Dict[str, Any]:
        """Override chart specific options for grouped bar chart.

        Returns:
            Dict[str, Any]: The chart-specific options.
        """
        base_opts = super().get_chart_specific_opts()

        # Configure x-axis labels
        base_opts["xaxis_opts"].axislabel_opts = opts.LabelOpts(
            rotate=45, interval=0, margin=8
        )

        # Set axis options based on chart type
        if self.chart_details.chart_type == "GROUPED_BAR_HORIZONTAL":
            base_opts.update(
                {
                    "xaxis_opts": opts.AxisOpts(type_="value"),
                    "yaxis_opts": opts.AxisOpts(type_="category"),
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
        """Override to add grouped bar specific styling."""
        super().add_series_to_chart(chart, series_name, y_values, color, value_mapping)
        # Add bar-specific options
        chart.options["series"][-1].update({"barGap": "30%", "barCategoryGap": "20%"})

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

        This implementation handles grouped bar charts with multiple y-axis columns.
        Includes chart-specific customizations for horizontal/vertical orientation.
        """
        # First call the parent class's configure_chart to handle basic configuration
        super().configure_chart(chart, filtered_data)

        # If there's no data, we can't proceed with additional configuration
        if filtered_data is None or filtered_data.empty:
            return

        # Process data based on chart type
        processed_data = self._process_data(filtered_data)

        # Get x-axis data
        x_axis_field = cast(DjangoFieldLike, self.options["x_axis_column"])
        x_field = x_axis_field.field_name
        x_axis_data = self._get_x_axis_data(processed_data, x_field)

        # Clear existing x-axis data and add our own
        chart.add_xaxis(x_axis_data)

        # Add series for each y-axis column
        for y_axis_column in self._get_y_axis_columns():
            field = y_axis_column["field"]
            field_name = field.field_name
            series_name = self._get_series_name(y_axis_column)
            color = y_axis_column.get("color")

            y_values = self._get_y_values(
                processed_data, x_axis_data, x_field, field_name
            )

            self.add_series_to_chart(
                chart=chart,
                series_name=series_name,
                y_values=y_values,
                color=color,
                value_mapping=y_axis_column.get("value_mapping", {}),
            )

        # Apply chart-specific customizations for horizontal bar charts
        if self.chart_details.chart_type == "GROUPED_BAR_HORIZONTAL":
            chart.reversal_axis()
