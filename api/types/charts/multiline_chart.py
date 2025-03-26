from typing import Any, Dict, List, Optional, cast

import pandas as pd
from pyecharts import options as opts
from pyecharts.charts.chart import Chart

from api.types.charts.base_chart import BaseChart, DjangoFieldLike
from api.types.charts.chart_registry import register_chart


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

    def configure_chart(
        self, chart: Chart, filtered_data: Optional[pd.DataFrame] = None
    ) -> None:
        """Configure line chart with data.

        Args:
            chart (Chart): The chart to configure.
            filtered_data (Optional[pd.DataFrame], optional): The filtered data. Defaults to None.
        """
        if filtered_data is None:
            return

        # Get x-axis data
        x_axis_field = cast(DjangoFieldLike, self.options["x_axis_column"])
        x_field = x_axis_field.field_name
        x_axis_data = filtered_data[x_field].tolist()

        # Sort if needed
        sort_order = self.options.get("sort_order", "asc")
        x_axis_data = sorted(x_axis_data, reverse=(sort_order == "desc"))

        # Create a mapping of x values to indices for data alignment
        x_value_to_index = {x_val: i for i, x_val in enumerate(x_axis_data)}

        # Add x-axis
        chart.add_xaxis(x_axis_data)

        # Process and add series for each y-axis column
        for y_axis_column in self._get_y_axis_columns():
            field = y_axis_column["field"]
            field_name = field.field_name
            series_name = self._get_series_name(y_axis_column)

            # Create a dictionary mapping x values to y values
            x_to_y_map = {}
            for idx, x_val in enumerate(filtered_data[x_field]):
                y_val = filtered_data.iloc[idx][field_name]
                if pd.notna(y_val):
                    x_to_y_map[x_val] = float(y_val) if y_val is not None else 0.0

            # Create y_values array aligned with x_axis_data
            y_values = []
            for x_val in x_axis_data:
                y_values.append(x_to_y_map.get(x_val, 0.0))

            # Add the series to the chart
            chart.add_yaxis(
                series_name=series_name,
                y_axis=y_values,
                label_opts=opts.LabelOpts(is_show=False),
                itemstyle_opts=(
                    opts.ItemStyleOpts(color=y_axis_column.get("color"))
                    if y_axis_column.get("color")
                    else None
                ),
                linestyle_opts=opts.LineStyleOpts(width=2, type_="solid"),
                is_smooth=True,
                is_symbol_show=True,
            )
