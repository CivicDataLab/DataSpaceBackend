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

            # Configure chart options
            chart.set_global_opts(
                title_opts=opts.TitleOpts(pos_top="5%"),
                legend_opts=opts.LegendOpts(
                    pos_top="5%",
                    pos_left="center",
                    padding=[0, 10, 20, 10]
                ),
                xaxis_opts=opts.AxisOpts(
                    name_location="end",
                    name_gap=25,
                    axislabel_opts=opts.LabelOpts(
                        margin=8
                    )
                )
            )

            # Set grid options
            chart.options["grid"] = {
                "top": "20%",
                "bottom": "15%",
                "left": "10%",
                "right": "10%",
                "containLabel": True
            }

            # Get series name and color
            series_name = self.options['y_axis_column'].get('label', y_field) if isinstance(self.options['y_axis_column'], dict) else y_field
            series_color = self.options['y_axis_column'].get('color') if isinstance(self.options['y_axis_column'], dict) else None

            # Add data based on orientation
            is_horizontal = self.chart_details.chart_type == "BAR_HORIZONTAL"
            if is_horizontal:
                chart.add_yaxis(
                    series_name=series_name,
                    y_axis=y_axis_data,
                    itemstyle_opts=opts.ItemStyleOpts(color=series_color),
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
                chart.add_xaxis(x_axis_data)
            else:
                chart.add_xaxis(x_axis_data)
                chart.add_yaxis(
                    series_name=series_name,
                    y_axis=[float(y) for y in y_axis_data],
                    itemstyle_opts=opts.ItemStyleOpts(color=series_color),
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

        except Exception as e:
            print("Error while creating chart", e)
            import traceback
            traceback.print_exc()
            return None

    def configure_chart(self, chart: Chart) -> None:
        """
        Configure global chart options.
        """
        # Add axis titles
        chart.set_global_opts(
            xaxis_opts=opts.AxisOpts(
                name=self.options.get('x_axis_label', ''),
                name_location="end",
                name_gap=25,
                axislabel_opts=opts.LabelOpts(
                    rotate=45 if self.chart_details.chart_type != "BAR_HORIZONTAL" else 0
                )
            ),
            yaxis_opts=opts.AxisOpts(
                name=self.options.get('y_axis_label', ''),
                name_location="end",
                name_gap=25
            ),
            tooltip_opts=opts.TooltipOpts(
                trigger="axis",
                axis_pointer_type="shadow"
            )
        )

        # Add data zoom if there are more than 5 categories
        if len(self.data) > 5:
            chart.set_global_opts(
                datazoom_opts=[
                    opts.DataZoomOpts(
                        range_start=0,
                        range_end=100
                    )
                ]
            )

        return None

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
