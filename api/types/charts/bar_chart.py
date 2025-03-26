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
@register_chart("LINE")
class BarChart(BaseChart):
    def _handle_regular_data(self, chart: Chart, filtered_data: pd.DataFrame) -> None:
        """Handle non-time-based data with aggregation.

        This method overrides the base class method to handle single y-axis column for bar charts.

        Args:
            chart (Chart): The chart to handle.
            filtered_data (pd.DataFrame): The filtered data.
        """
        # For bar chart, only use the first y-axis column but preserve original options
        y_axis_column = self.options.get("y_axis_column", [])
        chart_options = self.options.copy()  # Create a copy to avoid modifying original

        if isinstance(y_axis_column, list) and y_axis_column:
            chart_options["y_axis_column"] = y_axis_column[0]

        # Temporarily set options to our modified version
        original_options = self.options
        self.options = chart_options

        try:
            # Process the data and add it to the chart
            x_axis_col = cast(DjangoFieldLike, self.options.get("x_axis_column"))
            if not x_axis_col:
                return

            x_field = x_axis_col.field_name
            if not x_field:
                return

            # Get unique x-axis values and sort them
            x_axis_data = sorted(filtered_data[x_field].unique().tolist())
            chart.add_xaxis(x_axis_data)

            # Add data for the y-axis column
            y_axis_col = chart_options.get("y_axis_column")
            if not y_axis_col or not isinstance(y_axis_col, dict):
                return

            field = cast(DjangoFieldLike, y_axis_col.get("field"))
            if not field:
                return

            field_name = field.field_name
            if not field_name:
                return

            display_name = y_axis_col.get("label") or field_name

            # Aggregate data for each x-axis value
            y_values = []
            for x_val in x_axis_data:
                # Filter data for current x value
                x_filtered_data = filtered_data[filtered_data[x_field] == x_val]

                # Aggregate the data
                aggregate_type = y_axis_col.get("aggregate_type", "sum")
                if x_filtered_data.empty:
                    value = 0.0
                elif aggregate_type.lower() == "sum":
                    value = float(x_filtered_data[field_name].sum())
                elif aggregate_type.lower() in ["avg", "average"]:
                    value = float(x_filtered_data[field_name].mean())
                elif aggregate_type.lower() == "count":
                    value = float(x_filtered_data[field_name].count())
                else:
                    value = float(x_filtered_data[field_name].sum())

                y_values.append(value)

            # Add the series to the chart
            self.add_series_to_chart(
                chart=chart,
                series_name=display_name,
                y_values=y_values,
                color=y_axis_col.get("color"),
                value_mapping=y_axis_col.get("value_mapping", {}),
            )
        finally:
            # Restore original options
            self.options = original_options

    def get_chart_specific_opts(self) -> dict:
        """Override chart specific options for bar chart."""
        base_opts = super().get_chart_specific_opts()

        # Configure x-axis labels
        base_opts["xaxis_opts"].axislabel_opts = opts.LabelOpts(
            rotate=45, interval=0, margin=8
        )

        # Set axis options based on chart type
        if self.chart_details.chart_type == "BAR_HORIZONTAL":
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
        """Override to add bar-specific styling."""
        super().add_series_to_chart(chart, series_name, y_values, color, value_mapping)
        # Add bar-specific options
        chart.options["series"][-1].update({"barGap": "30%", "barCategoryGap": "20%"})

    def configure_chart(
        self, chart: Chart, filtered_data: Union[pd.DataFrame, None] = None
    ) -> None:
        """Configure bar chart specific options."""
        super().configure_chart(chart, filtered_data)

        if self.chart_details.chart_type == "BAR_HORIZONTAL":
            chart.reversal_axis()

    def aggregate_data(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Aggregate data based on x and y axis columns and return the resulting DataFrame.
        """
        # Get field names from column objects
        x_axis_col = cast(DjangoFieldLike, self.options["x_axis_column"])
        x_field = x_axis_col.field_name

        y_axis_col = self.options["y_axis_column"]
        y_field = (
            cast(Dict[str, DjangoFieldLike], y_axis_col)["field"].field_name
            if isinstance(y_axis_col, dict)
            else cast(DjangoFieldLike, y_axis_col).field_name
        )

        agg_type = cast(
            AggregateType, self.options.get("aggregate_type", AggregateType.NONE)
        )

        if agg_type != AggregateType.NONE:
            metrics = data.groupby(x_field).agg({y_field: agg_type.value}).reset_index()

            # Keep column names the same
            metrics.columns = pd.Index([x_field, y_field])
            return metrics
        else:
            return data[[x_field, y_field]]
