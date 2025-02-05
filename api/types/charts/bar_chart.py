import pandas as pd
from pyecharts import options as opts
from pyecharts.charts.chart import Chart

from api.types.charts.base_chart import BaseChart
from api.types.charts.chart_registry import register_chart
from api.utils.enums import AggregateType


@register_chart('BAR_HORIZONTAL')
@register_chart('BAR_VERTICAL')
@register_chart('LINE')
class BarChart(BaseChart):
    def create_chart(self) -> Chart | None:
        if 'x_axis_column' not in self.options or 'y_axis_column' not in self.options:
            return None

        # Get the first y-axis column for single bar chart
        y_axis_columns = self.options['y_axis_column']
        if not y_axis_columns:
            return None
        self.options['y_axis_column'] = y_axis_columns[0]

        # Filter data
        filtered_data = self.filter_data()

        # Perform aggregation
        metrics = self.aggregate_data(filtered_data)

        # Initialize the chart
        chart = self.initialize_chart(metrics)

        self.configure_chart(chart)

        return chart

    def configure_chart(self, chart: Chart) -> None:
        """
        Configure global options and axis settings based on chart type (horizontal or vertical).
        """
        # Check if it's a horizontal bar chart
        is_horizontal = self.chart_details.chart_type == "BAR_HORIZONTAL"

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
            chart.set_series_opts(
                label_opts=opts.LabelOpts(position="right"))  # Labels on right side for horizontal bars

    def aggregate_data(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Aggregate data based on x and y axis columns and return the resulting DataFrame.
        """
        x_axis_column = self.options['x_axis_column']
        y_axis_column = self.options['y_axis_column']
        aggregate_type = self.options.get('aggregate_type', 'none')

        if aggregate_type != 'none':
            metrics = data.groupby(x_axis_column.field_name).agg(
                {y_axis_column.field_name: aggregate_type.lower()}
            ).reset_index()

            # Rename columns for clarity
            metrics.columns = [x_axis_column.field_name, y_axis_column.field_name]
            return metrics
        else:
            return data[[x_axis_column.field_name, y_axis_column.field_name]]

    def initialize_chart(self, metrics: pd.DataFrame) -> Chart:
        """
        Initialize the chart object, add x and y axis data.
        """
        chart_class = self.get_chart_class()  # Dynamically fetch the chart class
        chart = chart_class()

        x_axis_column = self.options['x_axis_column']
        y_axis_column = self.options['y_axis_column']

        # Add x and y axis data
        chart.add_xaxis(metrics[x_axis_column.field_name].tolist())
        chart.add_yaxis(
            self.options.get('y_axis_label', 'Y-Axis'), 
            metrics[y_axis_column.field_name].tolist()
        )

        return chart
