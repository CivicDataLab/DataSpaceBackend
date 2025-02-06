import pandas as pd
from pyecharts import options as opts
from pyecharts.charts.chart import Chart
from pyecharts.commons.utils import JsCode

from api.types.charts.base_chart import BaseChart
from api.types.charts.chart_registry import register_chart


@register_chart('GROUPED_BAR_HORIZONTAL')
@register_chart('GROUPED_BAR_VERTICAL')
class GroupedBarChart(BaseChart):
    def create_chart(self) -> Chart | None:
        if 'x_axis_column' not in self.options or 'y_axis_column' not in self.options:
            return None

        # Check if we have multiple y-axis columns for grouped bar chart
        y_axis_columns = self.options['y_axis_column']
        if len(y_axis_columns) <= 1:
            return None

        # Filter data
        filtered_data = self.filter_data()        

        # Initialize the chart
        chart = self.initialize_chart(filtered_data)

        self.configure_chart(chart)

        return chart

    def configure_chart(self, chart: Chart) -> None:
        """
        Configure global options and axis settings based on chart type (horizontal or vertical).
        """
        # Check if it's a horizontal bar chart
        is_horizontal = self.chart_details.chart_type == "GROUPED_BAR_HORIZONTAL"

        # Common configuration
        chart.set_global_opts(
            legend_opts=opts.LegendOpts(is_show=self.options.get('show_legend', False)),
            xaxis_opts=opts.AxisOpts(
                type_="value" if is_horizontal else "category",
                name=self.options.get('y_axis_label', 'Y-Axis') if is_horizontal else self.options.get('x_axis_label', 'X-Axis')
            ),
            yaxis_opts=opts.AxisOpts(
                type_="category" if is_horizontal else "value",
                name=self.options.get('x_axis_label', 'X-Axis') if is_horizontal else self.options.get('y_axis_label', 'Y-Axis')
            )
        )

        if is_horizontal:
            chart.reversal_axis()  # Flip axis for horizontal bar chart

    def initialize_chart(self, filtered_data: pd.DataFrame) -> Chart:
        """
        Initialize the chart object, add x and y axis data.
        """
        chart_class = self.get_chart_class()  # Dynamically fetch the chart class
        chart = chart_class()

        x_axis_column = self.options['x_axis_column']
        y_axis_columns = self.options['y_axis_column']

        # Add x and y axis data
        chart.add_xaxis(filtered_data[x_axis_column.field_name].tolist())
        for y_axis_column in y_axis_columns:
            series_name = y_axis_column.get('label', y_axis_column['field'].field_name)
            is_horizontal = self.chart_details.chart_type == "GROUPED_BAR_HORIZONTAL"
            
            chart.add_yaxis(
                series_name=series_name,
                y_axis=filtered_data[y_axis_column['field'].field_name].tolist(),
                itemstyle_opts=opts.ItemStyleOpts(color=y_axis_column.get('color')),
                label_opts=opts.LabelOpts(
                    position="insideRight" if is_horizontal else "inside",
                    rotate=0 if is_horizontal else 90,
                    font_size=12,
                    color='#000',
                    formatter=series_name,
                    vertical_align="middle",
                    horizontal_align="center",
                    distance=0
                ),
                color=y_axis_column.get('color')
            )

        return chart
