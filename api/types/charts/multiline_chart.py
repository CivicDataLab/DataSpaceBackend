import pandas as pd
from pyecharts import options as opts
from pyecharts.charts.chart import Chart
from pyecharts.charts import Line

from api.types.charts.grouped_bar_chart import GroupedBarChart
from api.types.charts.chart_registry import register_chart


@register_chart('MULTILINE')
class MultiLineChart(GroupedBarChart):
    def get_chart_class(self):
        """
        Override to return Line chart class instead of Bar
        """
        return Line

    def configure_chart(self, chart: Chart) -> None:
        """
        Configure global options and axis settings for line chart.
        """
        # Common configuration
        chart.set_global_opts(
            legend_opts=opts.LegendOpts(
                is_show=self.options.get('show_legend', True),
                selected_mode=True,
                pos_top="5%",
                orient="horizontal"
            ),
            xaxis_opts=opts.AxisOpts(
                type_="category",
                name=self.options.get('x_axis_label', 'X-Axis'),
                axislabel_opts=opts.LabelOpts(rotate=45)
            ),
            yaxis_opts=opts.AxisOpts(
                type_="value",
                name=self.options.get('y_axis_label', 'Y-Axis')
            ),
            tooltip_opts=opts.TooltipOpts(
                trigger="axis",
                axis_pointer_type="cross"
            )
        )

    def add_series_to_chart(self, chart: Chart, series_name: str, y_values: list, **kwargs) -> None:
        """
        Add a line series to the chart with specific line styling
        """
        chart.add_yaxis(
            series_name=series_name,
            y_axis=y_values,
            label_opts=opts.LabelOpts(is_show=False),  # Hide point labels for cleaner look
            itemstyle_opts=opts.ItemStyleOpts(color=kwargs.get('color')),
            linestyle_opts=opts.LineStyleOpts(
                width=2,  # Line thickness
                type_="solid"  # Line style (solid, dashed, dotted)
            ),
            symbol_size=8,  # Size of data points
            is_smooth=True  # Enable smooth line
        )

    def initialize_chart(self, filtered_data: pd.DataFrame) -> Chart:
        """
        Initialize the line chart with custom styling
        """
        chart = self.get_chart_class()()

        x_axis_column = self.options['x_axis_column']
        y_axis_columns = self.options['y_axis_column']

        # Add x-axis data
        chart.add_xaxis(filtered_data[x_axis_column.field_name].tolist())

        # Add each line series
        for y_axis_column in y_axis_columns:
            series_name = y_axis_column.get('label') or y_axis_column['field'].field_name
            y_values = [0.0 if pd.isna(value) else float(value) 
                       for value in filtered_data[y_axis_column['field'].field_name].tolist()]
            
            self.add_series_to_chart(
                chart=chart,
                series_name=series_name,
                y_values=y_values,
                color=y_axis_column.get('color')
            )

        return chart
