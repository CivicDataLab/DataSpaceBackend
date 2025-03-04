import pandas as pd
from pyecharts import options as opts
from pyecharts.charts.chart import Chart
from pyecharts.charts import Timeline, Bar
import json

from api.types.charts.base_chart import BaseChart
from api.types.charts.chart_registry import register_chart
from api.utils.enums import AggregateType

@register_chart('GROUPED_BAR_HORIZONTAL')
@register_chart('GROUPED_BAR_VERTICAL')
class GroupedBarChart(BaseChart):
    def create_chart(self) -> Chart | None:
        """Create a grouped bar chart."""
        # Validate requirements for grouped bar
        if 'x_axis_column' not in self.options or 'y_axis_column' not in self.options:
            return None

        # Check if we have multiple y-axis columns for grouped bar chart
        y_axis_columns = self.options['y_axis_column']
        if len(y_axis_columns) <= 1:
            return None

        # Use base chart's implementation
        return super().create_chart()

    def get_chart_class(self):
        """Get the chart class to use"""
        return Bar

    def get_chart_specific_opts(self) -> dict:
        """Override chart specific options for grouped bar chart."""
        base_opts = super().get_chart_specific_opts()
        
        # Configure x-axis labels
        base_opts['xaxis_opts'].axislabel_opts = opts.LabelOpts(
            rotate=45,
            interval=0,
            margin=8
        )

        # Set axis options based on chart type
        if self.chart_details.chart_type == "GROUPED_BAR_HORIZONTAL":
            base_opts.update({
                'xaxis_opts': opts.AxisOpts(type_="value"),
                'yaxis_opts': opts.AxisOpts(type_="category")
            })
            
        return base_opts

    def add_series_to_chart(self, chart: Chart, series_name: str, y_values: list, color: str = None, value_mapping: dict = None) -> None:
        """Override to add grouped bar specific styling."""
        super().add_series_to_chart(chart, series_name, y_values, color, value_mapping)
        # Add bar-specific options
        chart.options["series"][-1].update({
            "barGap": "30%",
            "barCategoryGap": "20%"
        })

    def configure_chart(self, chart: Chart, filtered_data: pd.DataFrame = None) -> None:
        """Configure grouped bar chart specific options."""
        super().configure_chart(chart, filtered_data)
        
        if self.chart_details.chart_type == "GROUPED_BAR_HORIZONTAL":
            chart.reversal_axis()

    def map_value(self, value: float, value_mapping: dict) -> str:
        """Map a numeric value to its string representation."""
        if pd.isna(value):
            return "0"
            
        return value_mapping.get(str(value), str(value))

    def _handle_regular_data(self, chart: Chart, filtered_data: pd.DataFrame) -> None:
        """Handle non-time-based data with aggregation"""
        x_field = self.options['x_axis_column'].field_name
        
        # Get unique x-axis values and sort them
        x_axis_data = filtered_data[x_field].unique().tolist()
        x_axis_data.sort()
        chart.add_xaxis(x_axis_data)

        # Add data for each metric
        for y_axis_column in self._get_y_axis_columns():
            metric_name = self._get_series_name(y_axis_column)
            field_name = y_axis_column['field'].field_name
            value_mapping = self._get_value_mapping(y_axis_column)
            aggregate_type = y_axis_column.get('aggregate_type')
            
            y_values = []
            for x_val in x_axis_data:
                # Filter data for current x value
                x_filtered_data = filtered_data[filtered_data[x_field] == x_val]
                value = self._apply_aggregation(x_filtered_data, field_name, aggregate_type)
                y_values.append(value)
            
            self.add_series_to_chart(
                chart=chart,
                series_name=metric_name,
                y_values=y_values,
                color=y_axis_column.get('color'),
                value_mapping=value_mapping
            )
