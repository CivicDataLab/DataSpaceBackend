import pandas as pd
from pyecharts import options as opts
from pyecharts.charts.chart import Chart
from pyecharts.charts import Line
import json

from api.types.charts.base_chart import BaseChart
from api.types.charts.chart_registry import register_chart
from api.utils.enums import AggregateType

@register_chart('MULTILINE')
class MultiLineChart(BaseChart):
    def get_chart_class(self):
        """
        Override to return Line chart class instead of Bar
        """
        return Line

    def get_chart_specific_opts(self) -> dict:
        """Override chart specific options for line chart."""
        base_opts = super().get_chart_specific_opts()
        base_opts['xaxis_opts'].axislabel_opts = opts.LabelOpts(
            rotate=45,
            interval=0,
            margin=8
        )
        # Add line chart specific options
        base_opts.update({
            'datazoom_opts': [
                opts.DataZoomOpts(
                    is_show=True,
                    type_="slider",
                    range_start=0,
                    range_end=100
                ),
                opts.DataZoomOpts(type_="inside")
            ],
            'tooltip_opts': opts.TooltipOpts(
                trigger="axis",
                axis_pointer_type="cross"
            )
        })
        return base_opts

    def add_series_to_chart(self, chart: Chart, series_name: str, y_values: list, color: str = None, value_mapping: dict = None) -> None:
        """Override to add line chart specific styling."""
        # Create a list of value objects with original and formatted values
        data = []
        for val in y_values:
            # Keep original numeric value for plotting
            value = float(val) if val is not None else 0.0
            # Get mapped string value for display
            label = value_mapping.get(str(value), str(value)) if value_mapping else str(value)
            data.append(opts.LineItem(
                name=label,
                value=value,
                symbol_size=8,
                symbol="emptyCircle"
            ))
        
        chart.add_yaxis(
            series_name=series_name,
            y_axis=data,
            label_opts=opts.LabelOpts(is_show=False),
            tooltip_opts=opts.TooltipOpts(
                formatter="{a}: {c}"
            ),
            itemstyle_opts=opts.ItemStyleOpts(color=color) if color else None,
            linestyle_opts=opts.LineStyleOpts(
                width=2,
                type_="solid"
            ),
            is_smooth=True,
            is_symbol_show=True
        )

    def configure_chart(self, chart: Chart, filtered_data: pd.DataFrame = None) -> None:
        """Configure line chart specific options."""
        super().configure_chart(chart, filtered_data)
        
        # Add line chart specific visual map if needed
        if filtered_data is not None:
            y_columns = self._get_y_axis_columns()
            if len(y_columns) > 1:
                chart.set_global_opts(
                    visualmap_opts=opts.VisualMapOpts(
                        is_show=False,
                        type_="continuous",
                        min_=0,
                        max_=len(y_columns) - 1
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
