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

            if filtered_data is None or filtered_data.empty:
                print("No data to display after aggregation")
                return None

            # Initialize the chart
            chart = self.initialize_chart(filtered_data)

            self._handle_regular_data(chart, filtered_data)

            # Configure chart
            self.configure_chart(chart, filtered_data)

            return chart

        except Exception as e:
            print("Error while creating chart", e)
            import traceback
            traceback.print_exc()
            return None

    def _handle_regular_data(self, chart: Chart, filtered_data: pd.DataFrame) -> None:
        """Override to handle single y-axis column."""
        # Get x-axis field name
        x_field = self.options['x_axis_column'].field_name
        x_axis_data = filtered_data[x_field].tolist()

        # Add x-axis data
        chart.add_xaxis(x_axis_data)

        # For bar chart, only use the first y-axis column
        y_axis_column = self.options['y_axis_column']
        if isinstance(y_axis_column, list):
            y_axis_column = y_axis_column[0]

        # Get y-axis field name
        y_field = y_axis_column['field'].field_name
        y_values = filtered_data[y_field].tolist()

        # Get series name from configuration
        series_name = self._get_series_name(y_axis_column)

        # Get value mapping from configuration
        value_mapping = self._get_value_mapping(y_axis_column)

        # Add series to chart
        self.add_series_to_chart(
            chart=chart,
            series_name=series_name,
            y_values=y_values,
            color=y_axis_column.get('color'),
            value_mapping=value_mapping
        )

    def get_chart_specific_opts(self) -> dict:
        """Override chart specific options for bar chart."""
        base_opts = super().get_chart_specific_opts()
        base_opts['xaxis_opts'].axislabel_opts = opts.LabelOpts(
            rotate=45,
            interval=0,
            margin=8
        )
        return base_opts

    def add_series_to_chart(self, chart: Chart, series_name: str, y_values: list, color: str = None, value_mapping: dict = None) -> None:
        """Override to add bar-specific styling."""
        super().add_series_to_chart(chart, series_name, y_values, color, value_mapping)
        # Add bar-specific options
        chart.options["series"][-1].update({
            "barGap": "30%",
            "barCategoryGap": "20%"
        })

    def configure_chart(self, chart: Chart, filtered_data: pd.DataFrame = None) -> None:
        """Configure bar chart specific options."""
        super().configure_chart(chart, filtered_data)
        
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

    def initialize_chart(self, filtered_data: pd.DataFrame = None) -> Chart:
        """Initialize a new chart instance with basic options."""
        chart = super().initialize_chart(filtered_data)
        
        # Set axis options
        opts_dict = self.get_chart_specific_opts()
        if self.chart_details.chart_type == "BAR_HORIZONTAL":
            chart.set_global_opts(
                xaxis_opts=opts.AxisOpts(type_="value"),
                yaxis_opts=opts.AxisOpts(type_="category")
            )
        else:
            chart.set_global_opts(
                xaxis_opts=opts_dict['xaxis_opts'],
                yaxis_opts=opts_dict['yaxis_opts']
            )
        
        return chart
