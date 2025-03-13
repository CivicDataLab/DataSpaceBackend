import json
from typing import Any, Dict, List, Optional, Union, cast

import pandas as pd
from pyecharts import options as opts
from pyecharts.charts import Bar, Timeline
from pyecharts.charts.chart import Chart

from api.types.charts.base_chart import BaseChart, DjangoFieldLike
from api.types.charts.chart_registry import register_chart
from api.utils.enums import AggregateType


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

    def configure_chart(
        self, chart: Chart, filtered_data: Union[pd.DataFrame, None] = None
    ) -> None:
        """Configure grouped bar chart specific options.

        Args:
            chart (Chart): The chart to configure.
            filtered_data (Union[pd.DataFrame, None], optional): The filtered data. Defaults to None.
        """
        super().configure_chart(chart, filtered_data)

        if self.chart_details.chart_type == "GROUPED_BAR_HORIZONTAL":
            chart.reversal_axis()

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

    def _aggregate_value(
        self, data: pd.DataFrame, field_name: str, aggregate_type: str
    ) -> float:
        """Aggregate values based on specified aggregation type.

        Args:
            data: DataFrame containing the data to aggregate
            field_name: The column name to aggregate
            aggregate_type: Type of aggregation (sum, avg, count, etc.)

        Returns:
            Aggregated value as a float
        """
        if data.empty:
            return 0.0

        if aggregate_type.lower() == "sum":
            return float(data[field_name].sum())
        elif aggregate_type.lower() == "avg" or aggregate_type.lower() == "average":
            return float(data[field_name].mean())
        elif aggregate_type.lower() == "count":
            return float(data[field_name].count())
        elif aggregate_type.lower() == "min":
            return float(data[field_name].min())
        elif aggregate_type.lower() == "max":
            return float(data[field_name].max())
        else:
            # Default to sum if unknown aggregation type
            return float(data[field_name].sum())

    def _handle_regular_data(self, chart: Chart, filtered_data: pd.DataFrame) -> None:
        """Handle non-time-based data with aggregation.

        Args:
            chart (Chart): The chart to handle.
            filtered_data (pd.DataFrame): The filtered data.
        """
        x_axis_col = cast(DjangoFieldLike, self.options["x_axis_column"])
        x_field = x_axis_col.field_name

        # Get unique x-axis values and sort them
        x_axis_values = filtered_data[x_field].unique().tolist()
        x_axis_data = sorted(x_axis_values)  # type: ignore[assignment]
        chart.add_xaxis(x_axis_data)

        # Add data for each metric
        for y_axis_column in self._get_y_axis_columns():
            metric_name = self._get_series_name(y_axis_column)
            field = cast(DjangoFieldLike, y_axis_column["field"])
            field_name = field.field_name
            # Use local value mapping instead of calling a non-existent method
            value_mapping = y_axis_column.get("value_mapping", {})
            aggregate_type = y_axis_column.get(
                "aggregate_type", "sum"
            )  # Default to "sum" if not specified

            y_values = []
            for x_val in x_axis_data:
                # Filter data for current x value
                x_filtered_data = filtered_data[filtered_data[x_field] == x_val]
                # Use a local aggregation function instead of calling a non-existent method
                value = self._aggregate_value(
                    x_filtered_data, field_name, str(aggregate_type)
                )
                y_values.append(value)

            self.add_series_to_chart(
                chart=chart,
                series_name=metric_name,
                y_values=y_values,
                color=y_axis_column.get("color"),
                value_mapping=value_mapping,
            )
