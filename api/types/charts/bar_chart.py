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

            # Get axis data
            x_axis_data = filtered_data[x_field].tolist()
            y_axis_data = filtered_data[y_field].tolist()

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
            chart.add_xaxis(x_axis_data)

            # Get series name and color
            series_name = self.options['y_axis_column'].get('label', y_field) if isinstance(self.options['y_axis_column'], dict) else y_field
            series_color = self.options['y_axis_column'].get('color') if isinstance(self.options['y_axis_column'], dict) else None
            value_mapping = self.options['y_axis_column'].get('value_mapping', {}) if isinstance(self.options['y_axis_column'], dict) else {}

            # Create data with value mapping
            data = []
            for val in y_axis_data:
                value = float(val) if val is not None else 0.0
                label = value_mapping.get(str(value), str(value)) if value_mapping else str(value)
                data.append(opts.BarItem(
                    name=label,
                    value=value
                ))

            # Add y-axis data
            chart.add_yaxis(
                series_name=series_name,
                y_axis=data,
                label_opts=opts.LabelOpts(is_show=False),
                tooltip_opts=opts.TooltipOpts(
                    formatter="{a}: {b}"
                ),
                itemstyle_opts=opts.ItemStyleOpts(color=series_color) if series_color else None,
                category_gap="20%",
                gap="30%"
            )

            # Configure chart
            self.configure_chart(chart, filtered_data)

            return chart

        except Exception as e:
            print("Error while creating chart", e)
            import traceback
            traceback.print_exc()
            return None

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

        # Common configuration
        global_opts = {
            'legend_opts': opts.LegendOpts(
                is_show=True,
                selected_mode=True,
                pos_top="5%",
                pos_left="center",
                orient="horizontal",
                item_gap=25,
                padding=[5, 10, 20, 10],
                textstyle_opts=opts.TextStyleOpts(font_size=12),
                border_width=0,
                background_color="transparent"
            ),
            'xaxis_opts': opts.AxisOpts(
                type_="category" if self.chart_details.chart_type != "BAR_HORIZONTAL" else "value",
                name=self.options.get('x_axis_label', ''),
                name_gap=25,
                axislabel_opts=opts.LabelOpts(
                    margin=8,
                    rotate=45 if self.chart_details.chart_type != "BAR_HORIZONTAL" else 0
                ),
                name_location="middle"
            ),
            'yaxis_opts': opts.AxisOpts(
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
            'tooltip_opts': opts.TooltipOpts(
                trigger="axis",
                axis_pointer_type="shadow",
                background_color="rgba(255,255,255,0.9)",
                border_color="#ccc",
                border_width=1,
                textstyle_opts=opts.TextStyleOpts(color="#333")
            )
        }

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

        if self.chart_details.chart_type == "BAR_HORIZONTAL":
            chart.reversal_axis()

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
