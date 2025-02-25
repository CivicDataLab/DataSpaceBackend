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
        chart = self.initialize_chart(filtered_data)

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

    def get_chart_specific_opts(self) -> dict:
        """Get chart type specific options. Override in subclasses for specific chart types."""
        return {
            'xaxis_opts': opts.AxisOpts(
                type_="category" if self.chart_details.chart_type != "GROUPED_BAR_HORIZONTAL" else "value",
                name=self.options.get('x_axis_label', 'X-Axis'),
                name_gap=35,  # Add space for axis label
                axislabel_opts=opts.LabelOpts(rotate=45)
            ),
            'yaxis_opts': opts.AxisOpts(
                type_="value" if self.chart_details.chart_type != "GROUPED_BAR_HORIZONTAL" else "category",
                name=self.options.get('y_axis_label', 'Y-Axis'),
                name_gap=50,  # Add space for axis label
                min_=None,  # Let pyecharts auto-calculate the bounds
                max_=None,
                splitline_opts=opts.SplitLineOpts(is_show=True),
                axistick_opts=opts.AxisTickOpts(is_show=True),
                axisline_opts=opts.AxisLineOpts(is_show=True),
                axislabel_opts=opts.LabelOpts(formatter="{value}")
            ),
            'tooltip_opts': opts.TooltipOpts(
                trigger="axis",
                axis_pointer_type="shadow",
                background_color="rgba(255,255,255,0.9)",
                border_color="#ccc",
                border_width=1,
                textstyle_opts=opts.TextStyleOpts(color="#333"),
                formatter="""
                    function(params) {
                        var colorSpan = color => '<span style="display:inline-block;margin-right:5px;border-radius:10px;width:10px;height:10px;background-color:' + color + '"></span>';
                        var result = params[0].axisValue + '<br/>';
                        params.forEach(param => {
                            result += colorSpan(param.color) + param.seriesName + ': ' + param.value + '<br/>';
                        });
                        return result;
                    }
                """
            )
        }

    def configure_chart(self, chart: Chart, filtered_data: pd.DataFrame = None) -> None:
        """
        Configure global options and axis settings for grouped bar chart.
        """
        # Get value mappings from all y-axis columns to create y-axis labels
        value_mappings = {}
        for y_axis_column in self.options['y_axis_column']:
            if y_axis_column.get('value_mapping'):
                value_mappings.update(y_axis_column.get('value_mapping', {}))

        # Common configuration
        global_opts = {
            'legend_opts': opts.LegendOpts(
                is_show=True,
                selected_mode=True,
                pos_top="5%",  # Move legend higher
                pos_left="center",  # Center horizontally
                orient="horizontal",
                item_gap=25,  # Add more space between legend items
                padding=[5, 10, 20, 10],  # Add padding [top, right, bottom, left]
                textstyle_opts=opts.TextStyleOpts(font_size=12),
                border_width=0,  # Remove border
                background_color="transparent"  # Make background transparent
            ),
            **self.get_chart_specific_opts()  # Add chart specific options
        }

        # Add data zoom options only if time_column is present and we have enough data points
        time_column = self.options.get('time_column')
        if time_column and filtered_data is not None:
            unique_times = filtered_data[time_column.field_name].nunique()
            if unique_times > 5:  # Only show data zoom if we have more than 5 time periods
                global_opts['datazoom_opts'] = [
                    opts.DataZoomOpts(
                        is_show=True,
                        type_="slider",
                        range_start=max(0, (unique_times - 5) * 100 / unique_times),  # Show last 5 periods by default
                        range_end=100,
                        pos_bottom="0%"
                    ),
                    opts.DataZoomOpts(
                        type_="inside",
                        range_start=max(0, (unique_times - 5) * 100 / unique_times),
                        range_end=100
                    )
                ]

        chart.set_global_opts(**global_opts)

        if self.chart_details.chart_type == "GROUPED_BAR_HORIZONTAL":
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
            # label_opts=opts.LabelOpts(
            #     position="insideRight" if self.chart_details.chart_type == "GROUPED_BAR_HORIZONTAL" else "inside",
            #     rotate=0 if self.chart_details.chart_type == "GROUPED_BAR_HORIZONTAL" else 90,
            #     font_size=12,
            #     color='#000',
            #     # formatter="{b}"  # Use name field for label
            # ),
            tooltip_opts=opts.TooltipOpts(
                formatter="{a}: {b}"  # Use name field for tooltip
            ),
            itemstyle_opts=opts.ItemStyleOpts(color=kwargs.get('color')),
            category_gap="20%",
            gap="30%"
        )

    def initialize_chart(self, filtered_data: pd.DataFrame) -> Chart:
        """
        Initialize a new chart instance with basic options.
        """
        self.filtered_data = filtered_data

        if self.chart_details.chart_type == "GROUPED_BAR_HORIZONTAL":
            chart = self.get_chart_class()(
                init_opts=opts.InitOpts(
                    width=self.options.get('width', '100%'),
                    height=self.options.get('height', '400px'),
                    animation_opts=opts.AnimationOpts(animation=False)
                )
            )
        else:
            chart = self.get_chart_class()(
                init_opts=opts.InitOpts(
                    width=self.options.get('width', '100%'),
                    height=self.options.get('height', '400px'),
                    animation_opts=opts.AnimationOpts(animation=False)
                )
            )
            
        # Set global options
        chart.set_global_opts(
            title_opts=opts.TitleOpts(pos_top="5%"),
            legend_opts=opts.LegendOpts(pos_top="5%", pos_left="center")
        )

        # Set series options to hide labels
        chart.set_series_opts(
            label_opts=opts.LabelOpts(is_show=False)
        )

        return chart
