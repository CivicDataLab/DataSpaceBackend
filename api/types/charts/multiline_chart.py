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
                axislabel_opts=opts.LabelOpts(
                    rotate=45,
                    interval=0  # Show all labels
                )
            ),
            yaxis_opts=opts.AxisOpts(
                type_="value",  # Always use value type for line charts
                name=self.options.get('y_axis_label', 'Y-Axis'),
                min_=0,  # Start from 0
                max_=5,  # Set max to 5 for consistent scale
                interval=1
            ),
            tooltip_opts=opts.TooltipOpts(
                trigger="axis",
                axis_pointer_type="cross"
            )
        )

    def add_series_to_chart(self, chart: Chart, series_name: str, y_values: list, **kwargs) -> None:
        """
        Override parent method to add a line series to the chart with specific line styling
        """
        value_mapping = kwargs.get('value_mapping', {})
        
        # Process y values to handle NaN and convert to float
        processed_values = []
        for val in y_values:
            try:
                value = 0.0 if pd.isna(val) else float(val)
                processed_values.append(value)
            except (ValueError, TypeError):
                processed_values.append(0.0)

        # Format tooltip to show mapped value if available
        tooltip_formatter = "{a}: {c}"
        if value_mapping:
            tooltip_formatter = "{a}: " + value_mapping.get(str(processed_values[0]), str(processed_values[0]))

        chart.add_yaxis(
            series_name=series_name,
            y_axis=processed_values,
            label_opts=opts.LabelOpts(is_show=False),  # Hide point labels for cleaner look
            tooltip_opts=opts.TooltipOpts(
                formatter=tooltip_formatter
            ),
            itemstyle_opts=opts.ItemStyleOpts(
                color=kwargs.get('color'),
                border_width=2,
                border_color=kwargs.get('color')
            ),
            linestyle_opts=opts.LineStyleOpts(
                width=2,  # Line thickness
                type_="solid"  # Line style (solid, dashed, dotted)
            ),
            symbol="circle",  # Use filled circles for data points
            symbol_size=8,  # Size of data points
            is_smooth=True,  # Enable smooth line
            is_clip=False  # Don't clip lines at grid boundaries
        )

    def initialize_chart(self, filtered_data: pd.DataFrame) -> Chart:
        """
        Initialize the line chart with custom styling
        """
        chart = self.get_chart_class()()

        x_axis_column = self.options['x_axis_column']
        y_axis_columns = self.options['y_axis_column']

        # Get x-axis data
        x_data = filtered_data[x_axis_column.field_name].tolist()
        
        # Add x-axis data
        chart.add_xaxis(x_data)

        # Add each line series
        for y_axis_column in y_axis_columns:
            series_name = y_axis_column.get('label') or y_axis_column['field'].field_name
            field_name = y_axis_column['field'].field_name
            value_mapping = y_axis_column.get('value_mapping', {})
            
            # Get y-values in the same order as x-values
            y_values = []
            for x in x_data:
                row_data = filtered_data[filtered_data[x_axis_column.field_name] == x]
                if not row_data.empty:
                    val = row_data[field_name].iloc[0]
                    y_values.append(0.0 if pd.isna(val) else float(val))
                else:
                    y_values.append(0.0)
            
            self.add_series_to_chart(
                chart=chart,
                series_name=series_name,
                y_values=y_values,
                color=y_axis_column.get('color'),
                value_mapping=value_mapping
            )

        # Configure the chart
        self.configure_chart(chart)
        return chart
