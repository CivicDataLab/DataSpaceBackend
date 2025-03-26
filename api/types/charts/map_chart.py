from typing import Any, Dict, List, Optional, TypeVar, Union, cast

import pandas as pd
from pandas import DataFrame, Series
from pyecharts import options as opts
from pyecharts.charts.chart import Chart

from api.types.charts.base_chart import BaseChart, DjangoFieldLike
from api.types.charts.chart_registry import register_chart
from api.types.charts.chart_utils import _get_map_chart
from api.utils.enums import AggregateType


@register_chart("ASSAM_DISTRICT")
@register_chart("ASSAM_RC")
class MapChart(BaseChart):
    def create_chart(self) -> Optional[Chart]:
        if "region_column" not in self.options or "value_column" not in self.options:
            return None
        try:
            # Get filtered data using _get_data method
            data = self._get_data()
            if data is None:
                return None

            # Store data temporarily for use by other methods
            self._filtered_data = data

            region_values = self.process_data()
            return _get_map_chart(self.chart_details, data, region_values)
        except Exception as e:
            print("Error while creating chart", e)
            return None

    def initialize_chart(self, filtered_data: Optional[pd.DataFrame] = None) -> Chart:
        """Initialize a new map chart instance with basic options."""
        chart = self.get_chart_class()(
            init_opts=opts.InitOpts(
                width=str(self.options.get("width", "100%")),
                height=str(self.options.get("height", "400px")),
                animation_opts=opts.AnimationOpts(animation=False),
            )
        )

        # Set global options
        chart.set_global_opts(
            title_opts=opts.TitleOpts(pos_top="5%"),  # Title 5% from top
            legend_opts=opts.LegendOpts(
                is_show=True,
                selected_mode=True,
                pos_top="5%",  # Move legend higher
                pos_left="center",  # Center horizontally
                orient="horizontal",
                item_gap=25,  # Add more space between legend items
                padding=[5, 10, 20, 10],  # Add padding [top, right, bottom, left]
                textstyle_opts=opts.TextStyleOpts(font_size=12),
                border_width=0,  # Remove border
                background_color="transparent",  # Make background transparent
            ),
            toolbox_opts=opts.ToolboxOpts(
                feature=opts.ToolBoxFeatureOpts(
                    data_zoom=opts.ToolBoxFeatureDataZoomOpts(
                        is_show=True, zoom_title="Zoom", back_title="Back"
                    ),
                    restore=opts.ToolBoxFeatureRestoreOpts(is_show=True, title="Reset"),
                    data_view=opts.ToolBoxFeatureDataViewOpts(
                        is_show=True,
                        title="Data View",
                        lang=["Data View", "Close", "Refresh"],
                    ),
                    save_as_image=opts.ToolBoxFeatureSaveAsImageOpts(
                        is_show=True, title="Save as Image"
                    ),
                )
            ),
        )

        # Set grid options through chart options
        chart.options["grid"] = {
            "top": "20%",  # Chart area starts 20% from top
            "bottom": "15%",  # Chart area ends 15% from bottom
            "left": "10%",  # Chart area starts 10% from left
            "right": "5%",  # Chart area ends 5% from right
            "containLabel": True,  # Include axis labels in the grid size calculation
        }

        return chart

    def aggregate_data(self) -> pd.DataFrame:
        """
        Aggregate data based on region and value columns and return the resulting DataFrame.
        """
        region_column = cast(DjangoFieldLike, self.options["region_column"])
        value_column = cast(DjangoFieldLike, self.options["value_column"])
        agg_type = cast(
            AggregateType, self.options.get("aggregate_type", AggregateType.NONE)
        )

        if agg_type != AggregateType.NONE:
            # Convert the enum value to lowercase for pandas aggregation
            pandas_agg_func = agg_type.value.lower()
            metrics = (
                self._filtered_data.groupby(region_column.field_name)
                .agg({value_column.field_name: pandas_agg_func})
                .reset_index()
            )

            # Ensure column names are preserved as strings
            metrics.columns = pd.Index(
                [region_column.field_name, value_column.field_name]
            )
            return metrics
        else:
            return self._filtered_data[
                [region_column.field_name, value_column.field_name]
            ]

    def process_data(self) -> List[List[Any]]:
        """Process data for the map chart."""
        data = self.aggregate_data()
        if data.empty:
            return []

        region_column = cast(DjangoFieldLike, self.options.get("region_column"))
        value_column = cast(DjangoFieldLike, self.options.get("value_column"))

        if not region_column or not value_column:
            return []

        region_col = region_column.field_name
        value_col = value_column.field_name

        # Convert region names to uppercase
        data = data.assign(
            **{region_col: lambda x: x[region_col].astype(str).str.upper()}
        )

        return cast(List[List[Any]], data[[region_col, value_col]].values.tolist())
