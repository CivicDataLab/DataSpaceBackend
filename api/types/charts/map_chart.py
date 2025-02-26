import pandas as pd
from pyecharts.charts.chart import Chart
from pyecharts import options as opts

from api.types.charts.base_chart import BaseChart
from api.types.charts.chart_registry import register_chart
from api.types.charts.chart_utils import _get_map_chart
from api.utils.enums import AggregateType


class MapChart(BaseChart):
    def create_chart(self) -> Chart | None:
        if 'region_column' not in self.options or 'value_column' not in self.options:
            return None
        try:
            region_values = self.process_data()
            return _get_map_chart(self.chart_details, self.data, region_values)
        except Exception as e:
            print("Error while creating chart", e)
            return None

    def initialize_chart(self, filtered_data: pd.DataFrame) -> Chart:
        """Initialize a new map chart instance with basic options."""
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
        )

        # Set grid options through chart options
        chart.options["grid"] = {
            "top": "20%",  # Chart area starts 20% from top
            "bottom": "15%",  # Chart area ends 15% from bottom
            "left": "10%",  # Chart area starts 10% from left
            "right": "5%",  # Chart area ends 5% from right
            "containLabel": True  # Include axis labels in the grid size calculation
        }

        return chart

    def aggregate_data(self) -> pd.DataFrame:
        """
        Aggregate data based on region and value columns and return the resulting DataFrame.
        """
        region_column = self.options['region_column']
        value_column = self.options['value_column']
        aggregate_type = self.options.get('aggregate_type', 'none')

        if aggregate_type != 'none':
            metrics = self.data.groupby(region_column.field_name).agg(
                {value_column.field_name: aggregate_type.lower()}
            ).reset_index()

            metrics.columns = [region_column.field_name, value_column.field_name]
            return metrics
        else:
            return self.data[[region_column.field_name, value_column.field_name]]

    def process_data(self) -> list:
        data = self.aggregate_data()
        region_column = self.options['region_column']
        value_column = self.options['value_column']
        region_col = region_column.field_name
        value_col = value_column.field_name
        data[region_col] = data[region_col].str.upper()
        return data[[region_col, value_col]].values.tolist()


@register_chart('ASSAM_DISTRICT')
class AssamDistrictChart(MapChart):
    pass


@register_chart('ASSAM_RC')
class AssamRCChart(MapChart):
    pass
