import pandas as pd
from pyecharts import options as opts
from pyecharts.charts.chart import Chart
from pyecharts.charts import Line
import json

from api.types.charts.base_chart import BaseChart
from api.types.charts.chart_registry import register_chart
from api.utils.enums import AggregateType

@register_chart('MULTILINE')
class MultiLineChart(BaseChart):
    def get_chart_class(self):
        """
        Override to return Line chart class instead of Bar
        """
        return Line

    def get_chart_specific_opts(self) -> dict:
        """Override chart specific options for line chart."""
        base_opts = super().get_chart_specific_opts()
        base_opts['xaxis_opts'].axislabel_opts = opts.LabelOpts(
            rotate=45,
            interval=0,
            margin=8
        )
        # Add line chart specific options
        base_opts.update({
            'datazoom_opts': [
                opts.DataZoomOpts(
                    is_show=True,
                    type_="slider",
                    range_start=0,
                    range_end=100
                ),
                opts.DataZoomOpts(type_="inside")
            ],
            'tooltip_opts': opts.TooltipOpts(
                trigger="axis",
                axis_pointer_type="cross"
            )
        })
        return base_opts

    def add_series_to_chart(self, chart: Chart, series_name: str, y_values: list, color: str = None, value_mapping: dict = None) -> None:
        """Override to add line chart specific styling."""
        # Create a list of value objects with original and formatted values
        data = []
        for val in y_values:
            # Keep original numeric value for plotting
            value = float(val) if val is not None else 0.0
            # Get mapped string value for display
            label = value_mapping.get(str(value), str(value)) if value_mapping else str(value)
            data.append(opts.LineItem(
                name=label,
                value=value,
                symbol_size=8,
                symbol="emptyCircle"
            ))
        
        chart.add_yaxis(
            series_name=series_name,
            y_axis=data,
            label_opts=opts.LabelOpts(is_show=False),
            tooltip_opts=opts.TooltipOpts(
                formatter="{a}: {c}"
            ),
            itemstyle_opts=opts.ItemStyleOpts(color=color) if color else None,
            linestyle_opts=opts.LineStyleOpts(
                width=2,
                type_="solid"
            ),
            is_smooth=True,
            is_symbol_show=True
        )

    def configure_chart(self, chart: Chart, filtered_data: pd.DataFrame = None) -> None:
        """Configure line chart specific options."""
        super().configure_chart(chart, filtered_data)
        
        # Add line chart specific visual map if needed
        if filtered_data is not None:
            y_columns = self._get_y_axis_columns()
            if len(y_columns) > 1:
                chart.set_global_opts(
                    visualmap_opts=opts.VisualMapOpts(
                        is_show=False,
                        type_="continuous",
                        min_=0,
                        max_=len(y_columns) - 1
                    )
                )

    def get_init_opts(self) -> opts.InitOpts:
        """Override to provide line chart specific initialization options."""
        return opts.InitOpts(
            width=self.options.get('width', '100%'),
            height=self.options.get('height', '400px'),
            theme=self.options.get('theme', 'white')
        )
