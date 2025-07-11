import traceback
from typing import Any, Dict, List, Optional, cast

import pandas as pd
import structlog
from pyecharts import options as opts
from pyecharts.charts import TreeMap
from pyecharts.charts.chart import Chart

from api.types.charts.base_chart import BaseChart, DjangoFieldLike
from api.types.charts.chart_registry import register_chart

logger = structlog.get_logger("dataspace.charts")


@register_chart("TREEMAP")
class TreeMapChart(BaseChart):
    """Implementation of TreeMap chart."""

    def create_chart(self) -> Optional[TreeMap]:
        """Create a TreeMap chart.

        Returns:
            TreeMap chart instance or None if there was an error.
        """
        try:
            # Get data from SQL query
            data = self._get_data()
            if data is None or data.empty:
                logger.warning("No data available for TreeMap chart")
                return None

            # Create TreeMap chart
            chart = self.get_chart_class()()
            self.configure_chart(chart, data)
            return chart
        except Exception as e:
            logger.error(
                f"Error creating TreeMap chart: {str(e)}, traceback: {traceback.format_exc()}"
            )
            return None

    def configure_chart(
        self, chart: Chart, filtered_data: Optional[pd.DataFrame] = None
    ) -> None:
        """Configure the TreeMap chart with data and options.

        Args:
            chart: TreeMap chart instance.
            data: DataFrame containing the chart data.

        Returns:
            Configured TreeMap chart.
        """
        # Get chart options
        title = cast(str, self.options.get("title", ""))
        width = cast(str, self.options.get("width", "800px"))
        height = cast(str, self.options.get("height", "600px"))

        # Get columns for the chart
        x_axis_column = cast(DjangoFieldLike, self.options["x_axis_column"])
        y_axis_columns = self._get_y_axis_columns()

        if not x_axis_column or not y_axis_columns:
            logger.warning("Missing required columns for TreeMap chart")
            return

        # Prepare data for TreeMap
        if filtered_data is None:
            logger.warning("No data available for TreeMap chart")
            return

        treemap_data = self._prepare_treemap_data(
            filtered_data, x_axis_column, y_axis_columns
        )

        # Configure the chart with improved label options
        chart.add(
            series_name=title,
            data=treemap_data,
            visual_min=0,
            leaf_depth=1,
            # Improved label configuration
            label_opts=opts.LabelOpts(
                position="bottom",  # Position labels at the bottom
                font_size=12,
                font_weight="bold",
                formatter="{b}: {c}",  # Show both name and value
                is_show=True,  # Ensure labels are shown
            ),
        )

        # Set global options
        chart.set_global_opts(
            title_opts=opts.TitleOpts(title=title),
            tooltip_opts=opts.TooltipOpts(formatter="{b}: {c}"),
            # Add layout options for better responsiveness
            legend_opts=opts.LegendOpts(is_show=False),  # Hide legend for more space
        )

        # Set chart size with responsive configuration
        chart.width = width
        chart.height = height

        # Set renderer to canvas for better performance
        chart.renderer = "canvas"

        # Add responsive configuration
        chart.js_host = ""

        # Add additional initialization options for responsiveness
        chart.options.update(
            {
                "animation": False,  # Disable animation for better performance
            }
        )

    def _prepare_treemap_data(
        self,
        data: pd.DataFrame,
        x_axis_column: DjangoFieldLike,
        y_axis_columns: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Prepare data for TreeMap chart.

        Args:
            data: DataFrame containing the chart data.
            x_axis_column: Column to use for x-axis (categories).
            y_axis_columns: Columns to use for y-axis (values).

        Returns:
            List of dictionaries with TreeMap data.
        """
        result: List[Dict[str, Any]] = []

        # Get the field names

        x_field_name = x_axis_column.field_name

        if not x_field_name or x_field_name not in data.columns:
            logger.warning(f"X-axis field '{x_field_name}' not found in data columns")
            return result

        # Get the first y-axis column (treemap typically uses one value column)
        if not y_axis_columns:
            logger.warning("No y-axis columns specified for TreeMap chart")
            return result

        y_field = cast(DjangoFieldLike, y_axis_columns[0]["field"])
        y_field_name = y_field.field_name

        if not y_field_name or y_field_name not in data.columns:
            logger.warning(f"Y-axis field '{y_field_name}' not found in data columns")
            return result

        # Group data by the x-axis column and sum the y-axis values
        grouped_data = data.groupby(x_field_name)[y_field_name].sum().reset_index()

        # Convert to TreeMap format
        for _, row in grouped_data.iterrows():
            category = row[x_field_name]
            value = row[y_field_name]

            # TreeMap data format
            result.append(
                {
                    "name": str(category),  # Category name
                    "value": float(value),  # Value
                }
            )

        return result
