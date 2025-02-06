import pandas as pd
from pyecharts import options as opts
from pyecharts.charts.chart import Chart
from pyecharts.charts import Timeline
from pyecharts.commons.utils import JsCode

from api.types.charts.base_chart import BaseChart
from api.types.charts.chart_registry import register_chart


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

        # Check if time_column is specified for timeline
        time_column = self.options.get('time_column')
        if time_column:
            # Create timeline instance
            timeline = Timeline(
                init_opts=opts.InitOpts(width="100%", height="600px")
            )
            timeline.add_schema(
                orient="horizontal",
                play_interval=2000,
                pos_bottom="0%",
                pos_left="5%",
                pos_right="5%",
                width="90%",
                is_auto_play=False,
                is_inverse=False,
                is_timeline_show=True,
                linestyle_opts=opts.LineStyleOpts(color="#ddd", width=1),
                label_opts=opts.LabelOpts(is_show=True, color="#999"),
                itemstyle_opts=opts.ItemStyleOpts(color="#A4B7D4")
            )

            # Group data by time periods
            time_groups = filtered_data.groupby(time_column.field_name)
            selected_groups = self.options.get('time_groups', [])
            
            for time_val, period_data in time_groups:
                # Skip if time_groups is specified and this time_val is not in it
                if selected_groups and str(time_val) not in selected_groups:
                    continue
                    
                chart = self.initialize_chart(period_data)
                self.configure_chart(chart)
                timeline.add(chart, str(time_val))

            # If no charts were added (all time groups were filtered out), return None
            if not timeline.charts:
                return None

            return timeline
        else:
            # Initialize the chart without timeline
            chart = self.initialize_chart(filtered_data)
            self.configure_chart(chart)
            return chart

    def configure_chart(self, chart: Chart) -> None:
        """
        Configure global options and axis settings based on chart type (horizontal or vertical).
        """
        # Check if it's a horizontal bar chart
        is_horizontal = self.chart_details.chart_type == "GROUPED_BAR_HORIZONTAL"

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
            series_name = y_axis_column.get('label', y_axis_column['field'].field_name)
            is_horizontal = self.chart_details.chart_type == "GROUPED_BAR_HORIZONTAL"
            
            chart.add_yaxis(
                series_name=series_name,
                y_axis=filtered_data[y_axis_column['field'].field_name].tolist(),
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
