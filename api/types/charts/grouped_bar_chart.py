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

        # Check if time_column is specified for timeline
        # time_column = self.options.get('time_column')
        # if time_column:
        #     # Handle time-based data
        #     self._handle_time_based_data(chart, filtered_data, time_column)
        # else:
        #     # Handle non-time-based data
        #     self._handle_regular_data(chart, filtered_data)

        # Configure the chart
        self.configure_chart(chart, filtered_data)
        return chart

    def _apply_aggregation(self, data: pd.DataFrame, field_name: str, aggregate_type: str) -> float:
        """Helper method to apply aggregation on data"""
        try:
            # Try different field name formats
            field_variants = [
                field_name,
                field_name.replace('-', '_'),
                field_name.replace('_', '-'),
                field_name.lower(),
                field_name.upper()
            ]
            
            # Find the correct field name variant
            actual_field = None
            for variant in field_variants:
                if variant in data.columns:
                    actual_field = variant
                    break
            
            if actual_field is None:
                return 0.0

            if aggregate_type and aggregate_type != 'none':
                if aggregate_type == AggregateType.SUM:
                    value = data[actual_field].astype(float).sum()
                elif aggregate_type == AggregateType.AVERAGE:
                    value = data[actual_field].astype(float).mean()
                elif aggregate_type == AggregateType.COUNT:
                    value = data[actual_field].count()
                else:
                    # Default to first value if unknown aggregation type
                    value = float(data[actual_field].iloc[0])
            else:
                # If no aggregation specified, take the first value
                value = float(data[actual_field].iloc[0])
            
            return 0.0 if pd.isna(value) else float(value)
        except Exception as e:
            print(f"Error in aggregation: {e}")
            return 0.0

    def _handle_time_based_data(self, chart: Chart, filtered_data: pd.DataFrame, time_column) -> None:
        """Handle time-based data with aggregation"""
        # Group data by time periods
        time_groups = filtered_data.groupby(time_column.field_name)
        selected_groups = self.options.get('time_groups', [])
        
        # If no time groups specified, use all periods
        if not selected_groups:
            all_periods = sorted([str(time) for time in time_groups.groups.keys()])
            selected_groups = all_periods

        # If x-axis is same as time column, use time periods directly
        x_field = self.options['x_axis_column'].field_name
        if x_field == time_column.field_name:
            x_axis_data = sorted([str(time) for time in time_groups.groups.keys() if str(time) in selected_groups])
            chart.add_xaxis(x_axis_data)

            # Add data for each metric
            for y_axis_column in self.options['y_axis_column']:
                metric_name = y_axis_column.get('label') or y_axis_column['field'].field_name
                y_values = []
                y_labels = []
                field_name = y_axis_column['field'].field_name
                value_mapping = y_axis_column.get('value_mapping', {})
                aggregate_type = y_axis_column.get('aggregate_type')
                
                for time_val in x_axis_data:
                    period_data = time_groups.get_group(time_val)
                    value = self._apply_aggregation(period_data, field_name, aggregate_type)
                    y_values.append(value)
                    y_labels.append(value_mapping.get(str(value), value))
                
                self.add_series_to_chart(
                    chart=chart,
                    series_name=metric_name,
                    y_values=y_values,
                    color=y_axis_column.get('color'),
                    value_mapping=value_mapping
                )
        else:
            # Get unique x-axis values from original data
            all_x_values = filtered_data[x_field].unique().tolist()
            all_x_values.sort()

            # Create x-axis labels with time periods
            x_axis_data = []
            for x_val in all_x_values:
                for time_val in time_groups.groups.keys():
                    if str(time_val) in selected_groups:
                        x_axis_data.append(f"{x_val} ({time_val})")
            chart.add_xaxis(x_axis_data)

            # Add data for each metric
            for y_axis_column in self.options['y_axis_column']:
                metric_name = y_axis_column.get('label') or y_axis_column['field'].field_name
                y_values = []
                y_labels = []
                field_name = y_axis_column['field'].field_name
                value_mapping = y_axis_column.get('value_mapping', {})
                aggregate_type = y_axis_column.get('aggregate_type')
                
                for x_val in all_x_values:
                    for time_val in time_groups.groups.keys():
                        if str(time_val) not in selected_groups:
                            continue
                        
                        period_data = time_groups.get_group(time_val)
                        # Filter data for current x value
                        x_filtered_data = period_data[period_data[x_field] == x_val]
                        value = self._apply_aggregation(x_filtered_data, field_name, aggregate_type)
                        y_values.append(value)
                        y_labels.append(value_mapping.get(str(value), value))
                
                self.add_series_to_chart(
                    chart=chart,
                    series_name=metric_name,
                    y_values=y_values,
                    color=y_axis_column.get('color'),
                    value_mapping=value_mapping
                )

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

    def get_chart_class(self):
        """
        Get the chart class to use
        """
        return Bar

    def get_chart_specific_opts(self) -> dict:
        """Override chart specific options for grouped bar chart."""
        base_opts = super().get_chart_specific_opts()
        base_opts['xaxis_opts'].axislabel_opts = opts.LabelOpts(
            rotate=45,
            interval=0,
            margin=8
        )
        return base_opts

    def add_series_to_chart(self, chart: Chart, series_name: str, y_values: list, color: str = None, value_mapping: dict = None) -> None:
        """Override to add grouped bar specific styling."""
        super().add_series_to_chart(chart, series_name, y_values, color, value_mapping)
        # Add grouped bar specific options
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

    def initialize_chart(self, filtered_data: pd.DataFrame = None) -> Chart:
        """Initialize a new chart instance with basic options."""
        chart = super().initialize_chart(filtered_data)
        
        # Set axis options based on chart type
        opts_dict = self.get_chart_specific_opts()
        if self.chart_details.chart_type == "GROUPED_BAR_HORIZONTAL":
            chart.set_global_opts(
                xaxis_opts=opts.AxisOpts(type_="value"),
                yaxis_opts=opts.AxisOpts(type_="category")
            )
        else:
            chart.set_global_opts(
                xaxis_opts=opts_dict['xaxis_opts'],
                yaxis_opts=opts_dict['yaxis_opts']
            )
        
        return chart
