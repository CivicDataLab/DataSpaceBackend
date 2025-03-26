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
        if value_mapping is None:
            value_mapping = {}
        data = []
        for val in y_values:
            # Keep original numeric value for plotting
            value = float(val) if val is not None else 0.0
            data.append(value)

        chart.add_yaxis(
            series_name=series_name,
            y_axis=data,
            label_opts=opts.LabelOpts(is_show=False),
            # tooltip_opts=opts.TooltipOpts(
            #     formatter="{a}: {c}"
            # ),
            itemstyle_opts=opts.ItemStyleOpts(color=color) if color else None,
            linestyle_opts=opts.LineStyleOpts(width=2, type_="solid"),
            is_smooth=True,
            is_symbol_show=True,
        )

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

        # Add x-axis
        chart.add_xaxis(x_axis_data)

        # Add series for each y-axis column
        for y_axis_column in self._get_y_axis_columns():
            field = y_axis_column["field"]
            field_name = field.field_name
            series_name = self._get_series_name(y_axis_column)

            # Get y values from the dataframe
            column_data = filtered_data[field_name]
            if hasattr(column_data, "tolist"):
                y_values = column_data.tolist()
            elif isinstance(column_data, pd.DataFrame):
                y_values = column_data.iloc[:, 0].tolist()

            self.add_series_to_chart(
                chart=chart,
                series_name=series_name,
                y_values=y_values,
                color=y_axis_column.get("color"),
                value_mapping=y_axis_column.get("value_mapping"),
            )
