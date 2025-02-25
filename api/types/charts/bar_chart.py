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
    def create_chart(self) -> Chart:
        """
        Create a bar chart with the given data and options.
        """
        try:
            # First aggregate the data
            filtered_data = self.filter_data()
            print("Options:", self.options)
            print("X-axis column:", self.options['x_axis_column'])
            print("Y-axis column:", self.options['y_axis_column'])

            # Get the first y-axis column for single bar chart
            if isinstance(self.options['y_axis_column'], list):
                self.options['y_axis_column'] = self.options['y_axis_column'][0]

            filtered_data = self.aggregate_data(filtered_data)
            if filtered_data is None or filtered_data.empty:
                print("No data to display after aggregation")
                return None

            # Initialize the chart
            chart = self.initialize_chart(filtered_data)
            
            # Handle regular bar chart
            is_horizontal = self.chart_details.chart_type == "BAR_HORIZONTAL"
            value_mappings = self.options.get('value_mappings', {})
            time_column = self.options.get('time_column')

            # Get field names from column objects
            x_field = self.options['x_axis_column'].field_name
            y_field = self.options['y_axis_column']['field'].field_name if isinstance(self.options['y_axis_column'], dict) else self.options['y_axis_column'].field_name

            print("X field:", x_field)
            print("Y field:", y_field)
            print("DataFrame columns:", filtered_data.columns)

            # Get axis data
            x_axis_data = filtered_data[x_field].tolist()
            y_axis_data = filtered_data[y_field].tolist()

            # Apply value mappings if they exist
            if value_mappings:
                if time_column:
                    # If time_column exists, we need to map both x and y values
                    mapped_x_data = [value_mappings.get(str(x), x) for x in x_axis_data]
                    mapped_y_data = [value_mappings.get(str(y), y) for y in y_axis_data]
                else:
                    # If no time_column, only map the category values (x_axis for vertical, y_axis for horizontal)
                    if is_horizontal:
                        mapped_x_data = x_axis_data
                        mapped_y_data = [value_mappings.get(str(y), y) for y in y_axis_data]
                    else:
                        mapped_x_data = [value_mappings.get(str(x), x) for x in x_axis_data]
                        mapped_y_data = y_axis_data
            else:
                mapped_x_data = x_axis_data
                mapped_y_data = y_axis_data

            # Add data to chart based on orientation
            if is_horizontal:
                chart.add_yaxis(
                    series_name=y_field,
                    y_axis=mapped_y_data,
                    label_opts=opts.LabelOpts(is_show=False)
                )
                chart.add_xaxis(mapped_x_data)
            else:
                chart.add_xaxis(mapped_x_data)
                chart.add_yaxis(
                    series_name=y_field,
                    y_axis=mapped_y_data,
                    label_opts=opts.LabelOpts(is_show=False)
                )

            return chart

        except Exception as e:
            print("Error while creating chart", e)
            import traceback
            traceback.print_exc()
            return None

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
                name=self.options.get('y_axis_label', 'Y-Axis') if is_horizontal else self.options.get('x_axis_label', 'X-Axis'),
                name_location="end",  # Place name at the end (bottom) of axis
                name_gap=25,  # Gap between axis and name
                axislabel_opts=opts.LabelOpts(
                    margin=8  # Add margin between axis and labels
                )
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
        # Get field names from column objects
        x_field = self.options['x_axis_column'].field_name
        y_field = self.options['y_axis_column']['field'].field_name if isinstance(self.options['y_axis_column'], dict) else self.options['y_axis_column'].field_name

        aggregate_type = self.options.get('aggregate_type', 'none')

        if aggregate_type != 'none':
            metrics = data.groupby(x_field).agg(
                {y_field: aggregate_type.lower()}
            ).reset_index()

            # Keep column names the same
            metrics.columns = [x_field, y_field]
            return metrics
        else:
            return data[[x_field, y_field]]

    def initialize_chart(self, metrics: pd.DataFrame) -> Chart:
        """
        Initialize a new bar chart instance with basic options.
        """
        chart_class = self.get_chart_class()  # Dynamically fetch the chart class
        chart = chart_class(
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
                name_location="end",  # Place name at the end (bottom) of axis
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

        # Get field names from column objects
        x_field = self.options['x_axis_column'].field_name
        y_field = self.options['y_axis_column']['field'].field_name if isinstance(self.options['y_axis_column'], dict) else self.options['y_axis_column'].field_name

        # Get x-axis values for label formatting
        x_values = metrics[x_field].tolist()
        y_values = metrics[y_field].tolist()

        # Get series name from label or field name
        series_name = self.options['y_axis_column'].get('label', y_field) if isinstance(self.options['y_axis_column'], dict) else y_field
        is_horizontal = self.chart_details.chart_type == "BAR_HORIZONTAL"

        # Add data to chart based on orientation
        if is_horizontal:
            chart.add_yaxis(
                series_name=series_name,
                y_axis=y_values,
                itemstyle_opts=opts.ItemStyleOpts(
                    color=self.options['y_axis_column'].get('color') if isinstance(self.options['y_axis_column'], dict) else None
                ),
                label_opts=opts.LabelOpts(
                    position="insideRight",
                    rotate=0,
                    font_size=12,
                    color='#000',
                    vertical_align="middle",
                    horizontal_align="center",
                    distance=0
                )
            )
            chart.add_xaxis(x_values)
        else:
            chart.add_xaxis(x_values)
            chart.add_yaxis(
                series_name=series_name,
                y_axis=[float(y) for y in y_values],
                itemstyle_opts=opts.ItemStyleOpts(
                    color=self.options['y_axis_column'].get('color') if isinstance(self.options['y_axis_column'], dict) else None
                ),
                label_opts=opts.LabelOpts(
                    position="inside",
                    rotate=90,
                    font_size=12,
                    color='#000',
                    vertical_align="middle",
                    horizontal_align="center",
                    distance=0
                )
            )

        return chart
