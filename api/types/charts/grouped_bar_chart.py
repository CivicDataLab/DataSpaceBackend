import pandas as pd
from pyecharts import options as opts
from pyecharts.charts.chart import Chart
from pyecharts.charts import Timeline
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
        chart_class = self.get_chart_class()
        chart = chart_class(
            init_opts=opts.InitOpts(width="100%", height="600px")
        )

        # Check if time_column is specified for timeline
        time_column = self.options.get('time_column')
        if time_column:
            # Handle time-based data
            self._handle_time_based_data(chart, filtered_data, time_column)
        else:
            # Handle non-time-based data
            self._handle_regular_data(chart, filtered_data)

        # Configure the chart
        self.configure_chart(chart, filtered_data)
        return chart

    def _apply_aggregation(self, data: pd.DataFrame, field_name: str, aggregate_type: str) -> float:
        """Helper method to apply aggregation on data"""
        value = None
        if aggregate_type and aggregate_type != AggregateType.NONE:
            if aggregate_type == AggregateType.SUM:
                value = data[field_name].sum()
            elif aggregate_type == AggregateType.AVERAGE:
                value = data[field_name].mean()
            elif aggregate_type == AggregateType.COUNT:
                value = data[field_name].count()
        else:
            value = float(data[field_name].iloc[0])
        
        return 0.0 if pd.isna(value) else float(value)

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
                        if not x_filtered_data.empty:
                            value = self._apply_aggregation(x_filtered_data, field_name, aggregate_type)
                        else:
                            value = 0.0
                        
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
        
        # Get unique x-axis values
        x_axis_data = filtered_data[x_field].unique().tolist()
        x_axis_data.sort()
        chart.add_xaxis(x_axis_data)

        # Add data for each metric
        for y_axis_column in self.options['y_axis_column']:
            metric_name = y_axis_column.get('label') or y_axis_column['field'].field_name
            field_name = y_axis_column['field'].field_name
            value_mapping = y_axis_column.get('value_mapping', {})
            aggregate_type = y_axis_column.get('aggregate_type')
            
            y_values = []
            y_labels = []
            
            for x_val in x_axis_data:
                # Filter data for current x value
                x_filtered_data = filtered_data[filtered_data[x_field] == x_val]
                if not x_filtered_data.empty:
                    value = self._apply_aggregation(x_filtered_data, field_name, aggregate_type)
                else:
                    value = 0.0
                
                y_values.append(value)
                y_labels.append(value_mapping.get(str(value), value))
            
            self.add_series_to_chart(
                chart=chart,
                series_name=metric_name,
                y_values=y_values,
                color=y_axis_column.get('color'),
                value_mapping=value_mapping
            )

    def configure_chart(self, chart: Chart, filtered_data: pd.DataFrame = None) -> None:
        """
        Configure global options and axis settings based on chart type (horizontal or vertical).
        """
        # Check if it's a horizontal bar chart
        is_horizontal = self.chart_details.chart_type == "GROUPED_BAR_HORIZONTAL"

        # Get value mappings from all y-axis columns to create y-axis labels
        value_mappings = {}
        for y_axis_column in self.options['y_axis_column']:
            if y_axis_column.get('value_mapping'):
                value_mappings.update(y_axis_column.get('value_mapping', {}))

        # Get y-axis bounds from data
        min_bound, max_bound = self.get_y_axis_bounds(filtered_data) if filtered_data is not None else (0, 5)

        # Common configuration
        chart.set_global_opts(
            legend_opts=opts.LegendOpts(
                is_show=self.options.get('show_legend', True),
                selected_mode=True
            ),
            xaxis_opts=opts.AxisOpts(
                type_="value" if is_horizontal else "category",
                name=self.options.get('y_axis_label', 'Y-Axis') if is_horizontal else self.options.get('x_axis_label', 'X-Axis')
            ),
            yaxis_opts=opts.AxisOpts(
                type_="category" if value_mappings else "value",
                name=self.options.get('x_axis_label', 'X-Axis') if is_horizontal else self.options.get('y_axis_label', 'Y-Axis'),
                min_=None if value_mappings else min_bound,
                max_=None if value_mappings else max_bound,
                interval=None if value_mappings else None,
                position="bottom" if is_horizontal else "left"
            )
        )

        if is_horizontal:
            chart.reversal_axis()

        # If we have value mappings, update the axis configuration
        if value_mappings:
            # Sort values for consistent order
            sorted_values = sorted([float(k) for k in value_mappings.keys()])
            sorted_labels = [value_mappings[str(val)] for val in sorted_values]
            
            # Update the y-axis configuration directly in the options
            chart.options["yAxis"][0].update({
                "type": "category",
                "data": sorted_labels,
                "axisLabel": {"show": True},
                "boundaryGap": False
            })
            
            # Store the mapping in the options for reference
            if "extra" not in chart.options:
                chart.options["extra"] = {}
            chart.options["extra"]["value_mapping"] = {
                str(val): label for val, label in zip(sorted_values, sorted_labels)
            }

    def map_value(self, value: float, value_mapping: dict) -> str:
        """
        Map a single numeric value to its string representation using value_mapping
        """
        if not value_mapping:
            return str(value)
            
        return value_mapping.get(str(value), str(value))

    def add_series_to_chart(self, chart: Chart, series_name: str, y_values: list, **kwargs) -> None:
        """
        Add a series to the chart with specific styling
        """
        value_mapping = kwargs.get('value_mapping', {})
        
        # Create a list of value objects with original and formatted values
        data = []
        for val in y_values:
            # Keep original numeric value for plotting
            value = float(val) if val is not None else 0.0
            # Get mapped string value for display
            label = self.map_value(value, value_mapping)
            data.append(opts.BarItem(
                name=label,
                value=value
            ))
        
        chart.add_yaxis(
            series_name=series_name,
            y_axis=data,
            label_opts=opts.LabelOpts(
                position="insideRight" if self.chart_details.chart_type == "GROUPED_BAR_HORIZONTAL" else "inside",
                rotate=0 if self.chart_details.chart_type == "GROUPED_BAR_HORIZONTAL" else 90,
                font_size=12,
                color='#000',
                # formatter="{b}"  # Use name field for label
            ),
            tooltip_opts=opts.TooltipOpts(
                formatter="{a}: {b}"  # Use name field for tooltip
            ),
            itemstyle_opts=opts.ItemStyleOpts(color=kwargs.get('color')),
            category_gap="20%",
            gap="30%"
        )

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
            series_name = y_axis_column.get('label') or y_axis_column['field'].field_name
            is_horizontal = self.chart_details.chart_type == "GROUPED_BAR_HORIZONTAL"
            
            chart.add_yaxis(
                series_name=series_name,
                y_axis=[0.0 if pd.isna(value) else float(value) for value in filtered_data[y_axis_column['field'].field_name].tolist()],  
                itemstyle_opts=opts.ItemStyleOpts(color=y_axis_column.get('color')),
                label_opts=opts.LabelOpts(
                    position="insideRight" if is_horizontal else "inside",
                    rotate=0 if is_horizontal else 90,
                    font_size=12,
                    color='#000',
                    # formatter="{a}",
                    vertical_align="middle",
                    horizontal_align="center",
                    distance=0
                ),
                color=y_axis_column.get('color')
            )

        return chart
