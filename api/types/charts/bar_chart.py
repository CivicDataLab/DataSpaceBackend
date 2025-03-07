import json
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union, cast

import pandas as pd
from pyecharts import options as opts
from pyecharts.charts import Timeline
from pyecharts.charts.chart import Chart
from pyecharts.commons.utils import JsCode

from api.types.charts.base_chart import BaseChart, DjangoFieldLike
from api.types.charts.chart_registry import register_chart
from api.utils.enums import AggregateType


@register_chart("BAR_HORIZONTAL")
@register_chart("BAR_VERTICAL")
@register_chart("LINE")
class BarChart(BaseChart):
    def _handle_regular_data(self, chart: Chart, filtered_data: pd.DataFrame) -> None:
        """Override to handle single y-axis column."""
        # For bar chart, only use the first y-axis column but preserve original options
        y_axis_column = self.options["y_axis_column"]
        chart_options = self.options.copy()  # Create a copy to avoid modifying original

        if isinstance(y_axis_column, list):
            chart_options["y_axis_column"] = y_axis_column[0]

        # Temporarily set options to our modified version
        original_options = self.options
        self.options = chart_options

        try:
            # Use base chart's implementation
            super()._handle_regular_data(chart, filtered_data)
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
