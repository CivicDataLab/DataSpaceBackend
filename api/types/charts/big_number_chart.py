from typing import Any, Dict, List, Optional, Union, cast

import pandas as pd
from pyecharts import options as opts
from pyecharts.charts.chart import Chart

from api.types.charts.base_chart import BaseChart
from api.types.charts.chart_registry import register_chart


@register_chart("BIG_NUMBER")
class BigNumberChart(BaseChart):
    """Big Number Chart implementation using ECharts graphic elements.

    This chart displays a single metric value prominently, with optional title,
    subtitle, and trend indicator. It uses ECharts graphic components to create
    a fully serializable chart configuration without JavaScript functions.
    """

    def create_chart(self) -> Optional[Chart]:
        """Create a big number chart with the given data and options."""
        try:
            # Get filtered data
            filtered_data = self._get_data()
            if filtered_data is None or filtered_data.empty:
                return None

            # Initialize chart
            chart = self.initialize_chart(filtered_data)

            # Configure chart
            self.configure_chart(chart, filtered_data)

            return chart
        except Exception as e:
            import traceback

            import structlog

            logger = structlog.get_logger("dataspace.charts")
            logger.error(
                f"Error creating big number chart: {str(e)}, traceback: {traceback.format_exc()}"
            )
            return None

    def configure_chart(
        self, chart: Chart, filtered_data: Optional[pd.DataFrame] = None
    ) -> None:
        """Configure the big number chart with data.

        For big number charts, we only use the first y-axis column if multiple are provided.
        """
        if filtered_data is None or filtered_data.empty:
            return

        # Process data to get the main metric value
        value = self._get_metric_value(filtered_data)

        # Get chart configuration options
        chart_options = self._get_big_number_options(value)

        # Apply the graphic elements to the chart options
        chart.options.update(chart_options)

        # Remove default components that we don't need for big number charts
        self._remove_default_components(chart)

    def _get_metric_value(self, filtered_data: pd.DataFrame) -> Union[float, int, str]:
        """Extract the metric value from the filtered data."""
        # Get the y-axis column configuration
        y_axis_columns = self._get_y_axis_columns()

        if not y_axis_columns or not isinstance(y_axis_columns, list):
            return 0

        # Use the first y-axis column
        y_axis_column = y_axis_columns[0]
        if not isinstance(y_axis_column, dict):
            return 0

        # Get the field name
        field = cast(Any, y_axis_column.get("field"))
        if not field or not hasattr(field, "field_name"):
            return 0

        field_name = field.field_name

        # Check if the field exists in the data
        if field_name not in filtered_data.columns:
            return 0

        # Get the value (typically we want the first/only row)
        if len(filtered_data) > 0:
            value = filtered_data[field_name].iloc[0]

            # Apply formatting if specified
            format_spec = y_axis_column.get("format")
            if format_spec and isinstance(format_spec, str):
                try:
                    if isinstance(value, (int, float)):
                        return format(value, format_spec)
                except ValueError:
                    pass

            # Ensure we return one of the expected types (float, int, or str)
            if isinstance(value, (float, int, str)):
                return value
            else:
                # Convert to string if it's not one of the expected types
                return str(value) if value is not None else "0"

        return 0

    def _get_big_number_options(self, value: Union[float, int, str]) -> Dict[str, Any]:
        """Generate the ECharts options for the big number chart."""
        # Get chart configuration from options
        options = self.options

        # Extract configuration values with defaults
        title = options.get("title", "")
        subtitle = options.get("subtitle", "")
        label = options.get("label", "")
        value_prefix = options.get("value_prefix", "")
        value_suffix = options.get("value_suffix", "")

        # Font sizes with defaults
        title_font_size = options.get("title_font_size", 18)
        subtitle_font_size = options.get("subtitle_font_size", 14)
        value_font_size = options.get("value_font_size", 36)
        label_font_size = options.get("label_font_size", 14)

        # Colors with defaults
        title_color = options.get("title_color", "#333333")
        subtitle_color = options.get("subtitle_color", "#666666")
        value_color = options.get("value_color", "#000000")
        label_color = options.get("label_color", "#666666")

        # Font sizes
        title_font_size = options.get("title_font_size", 16)
        subtitle_font_size = options.get("subtitle_font_size", 12)
        value_font_size = options.get("value_font_size", 36)
        label_font_size = options.get("label_font_size", 14)

        # Trend indicator options
        show_trend = options.get("show_trend", False)
        trend_value = options.get("trend_value", 0)
        trend_up_color = options.get("trend_up_color", "#52c41a")
        trend_down_color = options.get("trend_down_color", "#ff4d4f")

        # Create the graphic elements array
        graphic_elements = []

        # Calculate positions (percentages of chart area)
        current_y = 10  # Start position (percentage from top)

        # Add title if provided
        if title:
            graphic_elements.append(
                {
                    "type": "text",
                    "left": "center",
                    "top": f"{current_y}%",
                    "style": {
                        "text": title,
                        "fontSize": title_font_size,
                        "fontWeight": "bold",
                        "fill": title_color,
                        "width": "100%",
                        "textAlign": "center",
                    },
                }
            )
            current_y += 8

        # Add subtitle if provided
        if subtitle:
            graphic_elements.append(
                {
                    "type": "text",
                    "left": "center",
                    "top": f"{current_y}%",
                    "style": {
                        "text": subtitle,
                        "fontSize": subtitle_font_size,
                        "fill": subtitle_color,
                        "width": "100%",
                        "textAlign": "center",
                    },
                }
            )
            current_y += 8

        # Add main value with prefix/suffix
        display_value = f"{value_prefix}{value}{value_suffix}"
        graphic_elements.append(
            {
                "type": "text",
                "left": "center",
                "top": f"{current_y}%",
                "style": {
                    "text": display_value,
                    "fontSize": value_font_size,
                    "fontWeight": "bold",
                    "fill": value_color,
                    "width": "100%",
                    "textAlign": "center",
                },
            }
        )
        current_y += 12

        # Add label if provided
        if label:
            graphic_elements.append(
                {
                    "type": "text",
                    "left": "center",
                    "top": f"{current_y}%",
                    "style": {
                        "text": label,
                        "fontSize": label_font_size,
                        "fill": label_color,
                        "width": "100%",
                        "textAlign": "center",
                    },
                }
            )

        # Create the complete options dictionary
        return {
            "graphic": graphic_elements,
            "backgroundColor": options.get("background_color", "transparent"),
            "tooltip": {"show": False},
        }

    def _remove_default_components(self, chart: Chart) -> None:
        """Remove default components that are not needed for big number charts."""
        # Remove axes, grid, legend, etc. that are not needed
        chart.options.update(
            {
                "xAxis": {"show": False},
                "yAxis": {"show": False},
                "grid": {"show": False},
                "legend": {"show": False},
                "series": [],  # No series needed for big number chart
            }
        )

    def get_chart_specific_opts(self) -> dict:
        """Override chart specific options for big number chart."""
        # For big number charts, we don't need most of the standard chart options
        return {}
