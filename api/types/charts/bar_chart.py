import pandas as pd
from pyecharts import options as opts
from pyecharts.charts.chart import Chart

from api.types.charts.base_chart import BaseChart
from api.types.charts.chart_registry import register_chart
from api.utils.enums import AggregateType


@register_chart('BAR_HORIZONTAL')
@register_chart('BAR_VERTICAL')
class BarChart(BaseChart):
    def create_chart(self) -> Chart | None:
        if not self.chart_details.x_axis_column or not self.chart_details.y_axis_column:
            return None

        # Perform aggregation
        metrics = self.aggregate_data()

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
            legend_opts=opts.LegendOpts(is_show=self.chart_details.show_legend),
            xaxis_opts=opts.AxisOpts(
                type_="value" if is_horizontal else "category",
                name=self.chart_details.y_axis_label if is_horizontal else self.chart_details.x_axis_label
            ),
            yaxis_opts=opts.AxisOpts(
                type_="category" if is_horizontal else "value",
                name=self.chart_details.x_axis_label if is_horizontal else self.chart_details.y_axis_label
            )
        )

        if is_horizontal:
            chart.reversal_axis()  # Flip axis for horizontal bar chart
            chart.set_series_opts(
                label_opts=opts.LabelOpts(position="right"))  # Labels on right side for horizontal bars

    def aggregate_data(self) -> pd.DataFrame:
        """
        Aggregate data based on x and y axis columns and return the resulting DataFrame.
        """
        if self.chart_details.aggregate_type is not AggregateType.NONE:
            metrics = self.data.groupby(self.chart_details.x_axis_column.field_name).agg(
                {self.chart_details.y_axis_column.field_name: self.chart_details.aggregate_type.lower()}
            ).reset_index()

            # Rename columns for clarity
            metrics.columns = [self.chart_details.x_axis_column.field_name, self.chart_details.y_axis_column.field_name]
            return metrics
        else:
            return self.data[[self.chart_details.x_axis_column.field_name, self.chart_details.y_axis_column.field_name]]

    def initialize_chart(self, metrics: pd.DataFrame) -> Chart:
        """
        Initialize the chart object, add x and y axis data.
        """
        chart_class = self.get_chart_class()  # Dynamically fetch the chart class
        chart = chart_class()

        # Add x and y axis data
        chart.add_xaxis(metrics[self.chart_details.x_axis_column.field_name].tolist())
        chart.add_yaxis(self.chart_details.y_axis_label, metrics[self.chart_details.y_axis_column.field_name].tolist())

        return chart
