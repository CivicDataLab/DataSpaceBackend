import pandas as pd
from pyecharts import options as opts
from pyecharts.charts.chart import Chart
from pyecharts.charts import Timeline
import json
from pyecharts.commons.utils import JsCode

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

            # Get field names from column objects
            x_field = self.options['x_axis_column'].field_name
            y_field = self.options['y_axis_column']['field'].field_name if isinstance(self.options['y_axis_column'], dict) else self.options['y_axis_column'].field_name

            print("X field:", x_field)
            print("Y field:", y_field)
            print("DataFrame columns:", filtered_data.columns)

            # Initialize the chart
            chart_class = self.get_chart_class()
            chart = chart_class(
                init_opts=opts.InitOpts(
                    width=self.options.get('width', '100%'),
                    height=self.options.get('height', '400px'),
                    animation_opts=opts.AnimationOpts(animation=False)
                )
            )

            # Add x-axis data
            x_axis_data = filtered_data[x_field].tolist()
            chart.add_xaxis(x_axis_data)

            # Get series name and color
            series_name = self.options['y_axis_column'].get('label', y_field) if isinstance(self.options['y_axis_column'], dict) else y_field
            series_color = self.options['y_axis_column'].get('color') if isinstance(self.options['y_axis_column'], dict) else None
            value_mapping = self.options['y_axis_column'].get('value_mapping', {}) if isinstance(self.options['y_axis_column'], dict) else {}

            # Add y-axis data
            y_axis_data = filtered_data[y_field].tolist()
            self.add_series_to_chart(
                chart=chart,
                series_name=series_name,
                y_values=y_axis_data,
                color=series_color,
                value_mapping=value_mapping
            )

            # Configure chart
            self.configure_chart(chart, filtered_data)

            return chart

        except Exception as e:
            print("Error while creating chart", e)
            import traceback
            traceback.print_exc()
            return None

    def add_series_to_chart(self, chart: Chart, series_name: str, y_values: list, color: str = None, value_mapping: dict = None) -> None:
        """
        Add a series to the chart with specific styling
        """
        # Create a list of value objects with original and formatted values
        data = []
        for val in y_values:
            # Keep original numeric value for plotting
            value = float(val) if val is not None else 0.0
            # Get mapped string value for display
            label = value_mapping.get(str(value), str(value)) if value_mapping else str(value)
            data.append(opts.BarItem(
                name=label,
                value=value
            ))
        
        chart.add_yaxis(
            series_name=series_name,
            y_axis=data,
            label_opts=opts.LabelOpts(is_show=False),
            tooltip_opts=opts.TooltipOpts(
                formatter="{a}: {c}"
            ),
            itemstyle_opts=opts.ItemStyleOpts(color=color) if color else None,
            category_gap="20%",
            gap="30%"
        )

    def configure_chart(self, chart: Chart, filtered_data: pd.DataFrame = None) -> None:
        """
        Configure global chart options.
        """
        # Set grid options directly
        chart.options["grid"] = {
            "top": "20%",  # Chart area starts 20% from top
            "bottom": "15%",  # Chart area ends 15% from bottom
            "left": "10%",  # Chart area starts 10% from left
            "right": "10%",  # Chart area ends 10% from right
            "containLabel": True  # Include axis labels in the grid size calculation
        }

        # Get value mappings
        value_mapping = self.options['y_axis_column'].get('value_mapping', {}) if isinstance(self.options['y_axis_column'], dict) else {}

        # Common configuration
        global_opts = dict(
            title_opts=opts.TitleOpts(
                title=self.chart_details.title if hasattr(self.chart_details, 'title') else None,
                subtitle=self.chart_details.subtitle if hasattr(self.chart_details, 'subtitle') else None,
            ),
            tooltip_opts=opts.TooltipOpts(trigger="axis", axis_pointer_type="shadow"),
            toolbox_opts=opts.ToolboxOpts(
                feature=opts.ToolBoxFeatureOpts(
                    data_zoom=opts.ToolBoxFeatureDataZoomOpts(is_show=True, zoom_title="Zoom", back_title="Back"),
                    restore=opts.ToolBoxFeatureRestoreOpts(is_show=True, title="Reset"),
                    data_view=opts.ToolBoxFeatureDataViewOpts(is_show=True, title="View Data", lang=["View Data", "Close", "Refresh"]),
                    save_as_image=opts.ToolBoxFeatureRestoreOpts(is_show=True, title="Save Image"),
                    magic_type=opts.ToolBoxFeatureMagicTypeOpts(
                        is_show=True,
                        type_=["line", "bar", "stack", "tiled"],
                        line_title="Switch to Line",
                        bar_title="Switch to Bar",
                        stack_title="Switch to Stack",
                        tiled_title="Switch to Tiled"
                    )
                )
            ),
            legend_opts=opts.LegendOpts(
                type_="scroll",
                pos_top="5%",
                orient="horizontal",
                page_button_position="end",
                is_show=True,
                textstyle_opts=opts.TextStyleOpts(font_size=12)
            ),
            xaxis_opts=opts.AxisOpts(
                type_="category" if self.chart_details.chart_type != "BAR_HORIZONTAL" else "value",
                name=self.options.get('x_axis_label', ''),
                name_gap=25,
                axislabel_opts=opts.LabelOpts(
                    margin=8
                ),
                name_location="middle"
            ),
            yaxis_opts=opts.AxisOpts(
                type_="value" if self.chart_details.chart_type != "BAR_HORIZONTAL" else "category",
                name=self.options.get('y_axis_label', ''),
                name_gap=25,
                min_=None,
                max_=None,
                splitline_opts=opts.SplitLineOpts(is_show=True),
                axistick_opts=opts.AxisTickOpts(is_show=True),
                axisline_opts=opts.AxisLineOpts(is_show=True),
                axislabel_opts=opts.LabelOpts(formatter="{value}", margin=8)
            ),
        )

        # Add data zoom if we have more than 5 data points
        if len(filtered_data) > 5:
            global_opts['datazoom_opts'] = [
                opts.DataZoomOpts(
                    is_show=True,
                    type_="slider",
                    range_start=max(0, (len(filtered_data) - 5) * 100 / len(filtered_data)),
                    range_end=100,
                    pos_bottom="0%"
                ),
                opts.DataZoomOpts(
                    type_="inside",
                    range_start=max(0, (len(filtered_data) - 5) * 100 / len(filtered_data)),
                    range_end=100
                )
            ]

        chart.set_global_opts(**global_opts)

        # Set responsive grid options
        chart.options["grid"] = {
            "left": "5%",
            "right": "5%",
            "top": "15%",
            "bottom": "15%",
            "containLabel": True
        }

        if self.chart_details.chart_type == "BAR_HORIZONTAL":
            chart.reversal_axis()

        # If we have value mappings, update the axis configuration
        if value_mapping:
            # Sort values for consistent order
            sorted_values = sorted([float(k) for k in value_mapping.keys()])
            sorted_labels = [value_mapping[str(val)] for val in sorted_values]
            
            # Update the y-axis configuration directly in the options
            if self.chart_details.chart_type == "BAR_HORIZONTAL":
                chart.options["yAxis"][0].update({
                    "type": "category",
                    "data": sorted_labels,
                    "axisLabel": {"show": True},
                    "boundaryGap": False
                })
            else:
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
