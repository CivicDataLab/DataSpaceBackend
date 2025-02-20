import pandas as pd
from pyecharts import options as opts
from pyecharts.charts.chart import Chart
from pyecharts.charts import Timeline
import json

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

        # Check if time_column is specified for timeline
        time_column = self.options.get('time_column')
        if time_column:
            # Initialize the chart
            chart_class = self.get_chart_class()
            chart = chart_class(
                init_opts=opts.InitOpts(width="100%", height="600px")
            )

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
                # Sort time periods
                x_axis_data = sorted([str(time) for time in time_groups.groups.keys() if str(time) in selected_groups])
                chart.add_xaxis(x_axis_data)

                # Add data for the y-axis column
                y_axis_column = self.options['y_axis_column']
                metric_name = y_axis_column.get('label', y_axis_column['field'].field_name)
                y_values = []
                y_labels = []
                field_name = y_axis_column['field'].field_name
                value_mapping = y_axis_column.get('value_mapping', {})
                
                for time_val in x_axis_data:
                    period_data = time_groups.get_group(time_val)
                    # Try different field name formats
                    field_variants = [
                        field_name,
                        field_name.replace('-', '_'),
                        field_name.replace('_', '-'),
                        field_name.lower(),
                        field_name.upper()
                    ]
                    
                    value = None
                    for variant in field_variants:
                        if variant in period_data.columns:
                            value = float(period_data[variant].iloc[0])
                            break
                    
                    if value is None:
                        value = 0.0
                        
                    y_values.append(value)
                    # Map the value to its label if available
                    y_labels.append(str(value_mapping.get(value, value)))
                
                chart.add_yaxis(
                    series_name=metric_name,
                    y_axis=y_values,
                    label_opts=opts.LabelOpts(
                        position="insideRight" if self.chart_details.chart_type == "BAR_HORIZONTAL" else "inside",
                        rotate=0 if self.chart_details.chart_type == "BAR_HORIZONTAL" else 90,
                        font_size=12,
                        color='#000',
                        formatter="{c}"
                    ),
                    tooltip_opts=opts.TooltipOpts(
                        formatter="{a}: {c}"
                    ),
                    itemstyle_opts=opts.ItemStyleOpts(color=y_axis_column.get('color'))
                ).set_series_opts(
                    label_opts=opts.LabelOpts(formatter="{c}")
                )
                
                # Update the series data with mapped values
                if value_mapping:
                    chart.options["series"][-1]["data"] = [
                        {"value": val, "label": label}
                        for val, label in zip(y_values, y_labels)
                    ]

            else:
                # Get unique x-axis values from original data
                all_x_values = filtered_data[x_field].unique().tolist()
                all_x_values.sort()  # Sort for consistent ordering

                # Create x-axis labels with time periods
                x_axis_data = []
                for x_val in all_x_values:
                    for time_val in time_groups.groups.keys():
                        if str(time_val) in selected_groups:
                            x_axis_data.append(f"{x_val} ({time_val})")

                # Add x-axis
                chart.add_xaxis(x_axis_data)

                # Add data for each y-axis column
                for y_axis_column in self.options['y_axis_column']:
                    metric_name = y_axis_column.get('label', f"Series {y_axis_column['field'].id}")
                y_values = []
                
                # Generate y values for each x value and time period
                for x_val in all_x_values:
                    for time_val, period_data in time_groups:
                        if str(time_val) not in selected_groups:
                            continue
                            
                        # Get the value for this x value and time period
                        period_value_map = dict(zip(period_data[x_field], period_data[y_axis_column['field'].field_name]))
                        value = period_value_map.get(x_val, 0.0)
                        # Convert null/None values to 0.0 and ensure float type
                        y_values.append(0.0 if pd.isna(value) else float(value))
                
                chart.add_yaxis(
                    series_name=metric_name,
                    y_axis=y_values,
                    label_opts=opts.LabelOpts(
                        position="insideRight" if self.chart_details.chart_type == "BAR_HORIZONTAL" else "inside",
                        rotate=0 if self.chart_details.chart_type == "BAR_HORIZONTAL" else 90,
                        font_size=12,
                        color='#000'
                    ),
                    itemstyle_opts=opts.ItemStyleOpts(color=y_axis_column.get('color')),
                    is_selected=True
                )

            # Configure global options
            chart.set_global_opts(
                legend_opts=opts.LegendOpts(
                    is_show=True,
                    pos_top="5%",
                    orient="horizontal"
                ),
                xaxis_opts=opts.AxisOpts(
                    type_="category" if self.chart_details.chart_type != "BAR_HORIZONTAL" else "value",
                    name=self.options.get('x_axis_label', 'X-Axis'),
                    axislabel_opts=opts.LabelOpts(rotate=45)
                ),
                yaxis_opts=opts.AxisOpts(
                    type_="value" if self.chart_details.chart_type != "BAR_HORIZONTAL" else "category",
                    name=self.options.get('y_axis_label', 'Y-Axis')
                ),
                tooltip_opts=opts.TooltipOpts(
                    trigger="axis",
                    axis_pointer_type="shadow"
                ),
                datazoom_opts=[
                    opts.DataZoomOpts(
                        is_show=True,
                        type_="slider",
                        range_start=max(0, (len(x_axis_data) - 5) * 100 / len(x_axis_data)) if len(x_axis_data) > 5 else 0,
                        range_end=100,
                        pos_bottom="0%"
                    ),
                    opts.DataZoomOpts(
                        type_="inside",
                        range_start=max(0, (len(x_axis_data) - 5) * 100 / len(x_axis_data)) if len(x_axis_data) > 5 else 0,
                        range_end=100
                    )
                ]
            )

            if self.chart_details.chart_type == "BAR_HORIZONTAL":
                chart.reversal_axis()

            return chart
        else:
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

    def aggregate_data(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        Aggregate data based on x and y axis columns and return the resulting DataFrame.
        """
        x_axis_column = self.options['x_axis_column']
        y_axis_column = self.options['y_axis_column']['field']
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
        
        # Get x-axis values for label formatting
        x_values = metrics[x_axis_column.field_name].tolist()
        y_values = metrics[y_axis_column['field'].field_name].tolist()

        # Get series name from label or field name
        series_name = y_axis_column.get('label', y_axis_column['field'].field_name)
        is_horizontal = self.chart_details.chart_type == "BAR_HORIZONTAL"

        # Add x and y axis data
        chart.add_xaxis(x_values)
        chart.add_yaxis(
            series_name=series_name,
            y_axis=[float(y) for y in y_values],
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
