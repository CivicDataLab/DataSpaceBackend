import pandas as pd
from pyecharts import options as opts
from pyecharts.charts.chart import Chart
from pyecharts.charts import Line
import json

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
        # Get value mappings from all y-axis columns to create y-axis labels
        value_mappings = {}
        for y_axis_column in self.options['y_axis_column']:
            if y_axis_column.get('value_mapping'):
                value_mappings.update(y_axis_column.get('value_mapping', {}))

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
                name=self.options.get('y_axis_label', 'Y-Axis'),
                min_=0 if not value_mappings else min(float(k) for k in value_mappings.keys()),
                max_=5 if not value_mappings else max(float(k) for k in value_mappings.keys()),
                interval=1,
                axislabel_opts=opts.LabelOpts(
                    formatter="{value}"
                )
            ),
            tooltip_opts=opts.TooltipOpts(
                trigger="axis",
                axis_pointer_type="cross"
            )
        )

        # If we have value mappings, update the y-axis data in chart options
        if value_mappings:
            y_values = sorted([float(k) for k in value_mappings.keys()])
            chart.options["yAxis"][0]["data"] = [value_mappings[str(val)] for val in y_values]

    def add_series_to_chart(self, chart: Chart, series_name: str, y_values: list, **kwargs) -> None:
        """
        Override parent method to add a line series to the chart with specific line styling
        """
        value_mapping = kwargs.get('value_mapping', {})
        
        # Create a list of value objects with original and formatted values
        data = []
        for val in y_values:
            # Keep original numeric value for plotting
            value = float(val) if val is not None else 0.0
            # Get mapped string value for display
            label = self.map_value(value, value_mapping)
            data.append(opts.LineItem(
                name=label,
                value=value
            ))

        chart.add_yaxis(
            series_name=series_name,
            y_axis=data,
            label_opts=opts.LabelOpts(is_show=False),  # Hide point labels for cleaner look
            tooltip_opts=opts.TooltipOpts(
                formatter="{a}: {b}"  # Use name field for tooltip
            ),
            itemstyle_opts=opts.ItemStyleOpts(color=kwargs.get('color')),
            linestyle_opts=opts.LineStyleOpts(
                width=2,  # Line thickness
                type_="solid"  # Line style (solid, dashed, dotted)
            ),
            symbol="emptyCircle",  # Use empty circles for data points
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

        # Sort x-axis data if numeric
        x_data = filtered_data[x_axis_column.field_name].tolist()
        try:
            x_data = sorted([float(x) for x in x_data])
            x_data = [str(x) for x in x_data]
        except (ValueError, TypeError):
            pass

        # Add x-axis data
        chart.add_xaxis(x_data)

        # Add each line series
        for y_axis_column in y_axis_columns:
            series_name = y_axis_column.get('label') or y_axis_column['field'].field_name
            
            # Ensure y-values are in the same order as x-values
            y_dict = dict(zip(filtered_data[x_axis_column.field_name], 
                            filtered_data[y_axis_column['field'].field_name]))
            y_values = [0.0 if pd.isna(y_dict.get(x)) else float(y_dict.get(x, 0.0)) 
                       for x in x_data]
            
            self.add_series_to_chart(
                chart=chart,
                series_name=series_name,
                y_values=y_values,
                color=y_axis_column.get('color')
            )

        return chart
