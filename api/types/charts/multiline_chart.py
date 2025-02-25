import pandas as pd
from pyecharts import options as opts
from pyecharts.charts.chart import Chart
from pyecharts.charts import Line
import json

from api.types.charts.grouped_bar_chart import GroupedBarChart
from api.types.charts.chart_registry import register_chart
from api.utils.enums import AggregateType

@register_chart('MULTILINE')
class MultiLineChart(GroupedBarChart):
    def get_chart_class(self):
        """
        Override to return Line chart class instead of Bar
        """
        return Line

    def configure_chart(self, chart: Chart, filtered_data: pd.DataFrame = None) -> None:
        """
        Configure global options and axis settings for line chart.
        """
        # Get value mappings from all y-axis columns to create y-axis labels
        value_mappings = {}
        for y_axis_column in self.options['y_axis_column']:
            if y_axis_column.get('value_mapping'):
                value_mappings.update(y_axis_column.get('value_mapping', {}))

        # Get y-axis bounds from data, considering aggregation
        min_bound, max_bound = self.get_y_axis_bounds(filtered_data) if filtered_data is not None else (0, 5)

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
                name_location="middle",  # Place name at the end (bottom) of axis
                name_gap=25,  # Gap between axis and name
                boundary_gap=False,  # Remove gap between axis and line for line charts
                
                axislabel_opts=opts.LabelOpts(
                    # rotate=45,
                    interval=0,  # Show all labels
                    margin=8,  # Add margin between axis and labels
                    position="middle"
                )
            ),
            yaxis_opts=opts.AxisOpts(
                type_="category" if value_mappings else "value",
                name=self.options.get('y_axis_label', 'Y-Axis'),
                min_=None,
                max_=None,
                interval=None if value_mappings else None,
                axislabel_opts=opts.LabelOpts(
                    formatter="{value}"  # Show actual values for aggregated data
                )
            ),
            tooltip_opts=opts.TooltipOpts(
                trigger="axis",
                axis_pointer_type="cross",
                formatter="{b}: {c}"  # Show actual values in tooltip
            )
        )

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

    def get_chart_specific_opts(self) -> dict:
        """Override chart specific options for line chart."""
        base_opts = super().get_chart_specific_opts()
        
        # Get actual min/max from data
        min_val = float('inf')
        max_val = float('-inf')
        for y_axis_column in self.options['y_axis_column']:
            field_name = y_axis_column.get('field_name')
            if field_name in self.filtered_data:
                series_data = pd.to_numeric(self.filtered_data[field_name], errors='coerce')
                series_min = series_data.min()
                series_max = series_data.max()
                if not pd.isna(series_min) and series_min < min_val:
                    min_val = series_min
                if not pd.isna(series_max) and series_max > max_val:
                    max_val = series_max

        # Add a small buffer (5%) for better visualization
        value_range = max_val - min_val
        buffer = value_range * 0.05 if value_range > 0 else 0.5

        # Modify options specific to line chart
        base_opts.update({
            'tooltip_opts': opts.TooltipOpts(
                trigger="axis",
                axis_pointer_type="cross",  # Use cross pointer for line charts
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
            ),
            'xaxis_opts': opts.AxisOpts(
                type_="category",
                name=self.options.get('x_axis_label', 'X-Axis'),
                name_gap=25,  # Add space for axis label
                axislabel_opts=opts.LabelOpts(
                    margin=8,  # Add margin between axis and labels
                    interval=0,  # Show all labels
                    position="middle"  # Place name at the end (bottom) of axis
                ),
                boundary_gap=False  # Remove gap between axis and line for line charts
            ),
            'yaxis_opts': opts.AxisOpts(
                type_="value",
                name=self.options.get('y_axis_label', 'Y-Axis'),
                name_gap=50,  # Add space for axis label
                min_= None,
                max_= None,
                splitline_opts=opts.SplitLineOpts(is_show=True),
                axistick_opts=opts.AxisTickOpts(is_show=True),
                axisline_opts=opts.AxisLineOpts(is_show=True),
                axislabel_opts=opts.LabelOpts(formatter="{value}")
            )
        })
        
        return base_opts

    def add_series_to_chart(self, chart: Chart, series_name: str, y_values: list, **kwargs) -> None:
        """Override to add line-specific styling."""
        chart.add_yaxis(
            series_name=series_name,
            y_axis=y_values,
            label_opts=opts.LabelOpts(is_show=False),  # Hide point labels for cleaner look
            linestyle_opts=opts.LineStyleOpts(width=2),  # Slightly thicker lines
            symbol_size=8,  # Slightly larger points
            itemstyle_opts=opts.ItemStyleOpts(
                color=kwargs.get('color'),
                border_color="#fff",  # White border around points
                border_width=1
            )
        )

    def initialize_chart(self, filtered_data: pd.DataFrame) -> Chart:
        """Initialize a new line chart instance with basic options."""
        self.filtered_data = filtered_data
        
        chart = self.get_chart_class()(
            init_opts=opts.InitOpts(
                width=self.options.get('width', '100%'),
                height=self.options.get('height', '400px'),
                animation_opts=opts.AnimationOpts(animation=False)
            )
        )

        # Set global options
        chart.set_global_opts(
            title_opts=opts.TitleOpts(pos_top="5%"),  # Title 5% from top
            legend_opts=opts.LegendOpts(
                pos_top="5%",  # Legend 5% from top
                pos_left="center",  # Center horizontally
                padding=[0, 10, 20, 10]  # [top, right, bottom, left] padding
            ),
            xaxis_opts=opts.AxisOpts(
                name_location="middle",  # Place name at the end (bottom) of axis
                name_gap=25,  # Gap between axis and name
                axislabel_opts=opts.LabelOpts(
                    margin=8  # Add margin between axis and labels
                )
            )
        )

        # Set grid options through chart options
        chart.options["grid"] = {
            "top": "20%",  # Chart area starts 20% from top
            "bottom": "15%",  # Chart area ends 15% from bottom
            "left": "10%",  # Chart area starts 10% from left
            "right": "10%",  # Chart area ends 10% from right
            "containLabel": True  # Include axis labels in the grid size calculation
        }
        
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
        self.configure_chart(chart, filtered_data)
        
        return chart

    def get_y_axis_bounds(self, filtered_data: pd.DataFrame) -> tuple:
        """
        Calculate y-axis bounds from data
        """
        y_axis_columns = self.options['y_axis_column']
        min_bound = float('inf')
        max_bound = float('-inf')
        
        for y_axis_column in y_axis_columns:
            field_name = y_axis_column['field'].field_name
            values = filtered_data[field_name].tolist()
            values = [0.0 if pd.isna(val) else float(val) for val in values]
            min_bound = min(min_bound, min(values))
            max_bound = max(max_bound, max(values))
        
        # Add some padding to the bounds
        padding = (max_bound - min_bound) * 0.1
        min_bound -= padding
        max_bound += padding
        
        return min_bound, max_bound
