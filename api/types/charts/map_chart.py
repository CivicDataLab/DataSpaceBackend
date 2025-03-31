from typing import Any, List, Optional, cast

import pandas as pd
import structlog
from pandas import DataFrame, Series
from pyecharts import options as opts
from pyecharts.charts.chart import Chart

from api.types.charts.base_chart import BaseChart, DjangoFieldLike
from api.types.charts.chart_registry import register_chart
from api.types.charts.chart_utils import _get_map_chart

logger = structlog.get_logger(__name__)


@register_chart("ASSAM_DISTRICT")
@register_chart("ASSAM_RC")
class MapChart(BaseChart):
    def create_chart(self) -> Optional[Chart]:
        """Create a map chart.

        For map charts, we need to process the data differently than other charts.
        """
        if "region_column" not in self.options or "value_column" not in self.options:
            return None

        try:
            # Get filtered data using _get_data method
            filtered_data = self._get_data()
            if filtered_data is None or filtered_data.empty:
                return None

            # Process data for map chart
            processed_data = self._process_data(filtered_data)

            # Extract region and value columns
            region_column = cast(DjangoFieldLike, self.options["region_column"])
            value_column = cast(DjangoFieldLike, self.options["value_column"])

            if not region_column or not value_column:
                return None

            region_field = region_column.field_name
            value_field = value_column.field_name

            # Convert region names to uppercase for consistent mapping
            processed_data = processed_data.assign(
                **{region_field: lambda x: x[region_field].astype(str).str.upper()}
            )

            # Extract region-value pairs for map chart
            # This creates a List[List[Any]] where each inner list is a [region, value] pair
            # The _get_map_chart function expects the third argument to be List[List[Any]]
            region_values = processed_data[[region_field, value_field]].values.tolist()

            # Validate that region_values is a list of lists as required by _get_map_chart
            if not region_values or not isinstance(region_values, list):
                logger.warning(f"No region-value pairs found for map chart")
                return None

            # Create the map chart using the utility function
            return _get_map_chart(self.chart_details, processed_data, region_values)
        except Exception as e:
            import traceback

            logger.error(
                f"Error while creating map chart: {e}. {traceback.format_exc()}"
            )
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
                        is_show=False, zoom_title="Zoom", back_title="Back"
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
