from typing import Any, Dict, List, Optional, Protocol, Union, cast

import numpy as np
import pandas as pd
import structlog
from pyecharts import options as opts
from pyecharts.charts import Bar, Line, Map, TreeMap
from pyecharts.charts.chart import Chart

from api.models import ResourceChartDetails
from api.utils.data_indexing import query_resource_data
from api.utils.enums import AggregateType

logger = structlog.get_logger("dataspace.charts")


class DjangoFieldLike(Protocol):
    """Protocol for Django-like field objects."""

    field_name: str


class ChartFilter(Protocol):
    column: DjangoFieldLike
    operator: str
    value: str


class ChartOptions(Protocol):
    x_axis_column: DjangoFieldLike
    y_axis_column: List[Dict[str, Any]]
    time_column: Optional[DjangoFieldLike]
    time_groups: Optional[List[str]]
    width: str
    height: str


CHART_TYPE_MAP = {
    "LINE": Line,
    "ASSAM_DISTRICT": Map,
    "ASSAM_RC": Map,
    "POLYGON_MAP": Map,
    "POINT_MAP": Map,
    "GEOSPATIAL_MAP": Map,
    "TREEMAP": TreeMap,
    "BAR": Bar,
    "BIG_NUMBER": Bar,
}


class BaseChart:
    """Base class for all chart types."""

    def __init__(self, chart_details: ResourceChartDetails):
        """Initialize chart with details."""
        self.chart_details = chart_details
        self.options: Dict[str, Union[DjangoFieldLike, Dict[str, Any], List, Any]] = (
            chart_details.options
        )
        self.filters = chart_details.filters or []

    def get_chart_class(self) -> Chart:
        """Get the chart class to use."""
        return CHART_TYPE_MAP.get(self.chart_details.chart_type)

    def _get_data(self) -> Optional[pd.DataFrame]:
        """Get data for the chart using SQL query."""
        try:
            query, params = self._build_sql_query()
            return query_resource_data(self.chart_details.resource, query)
        except Exception as e:
            logger.error(f"Error getting chart data: {str(e)}")
            return None

    def create_chart(self) -> Optional[Chart]:
        """Create a chart with the given data and options."""
        try:
            # Get filtered data
            filtered_data = self._get_data()
            if filtered_data is None or filtered_data.empty:
                return None

            # Initialize chart
            chart = self.initialize_chart(filtered_data)

            # Configure chart
            self.configure_chart(chart, filtered_data)

            chart.set_global_opts(
                legend_opts=opts.LegendOpts(
                    is_show=self.options.get("show_legend", True),
                    pos_bottom="0%",  # Position at the very bottom
                    pos_top="auto",
                    orient="horizontal",
                    textstyle_opts=opts.TextStyleOpts(font_size=12),
                ),
                toolbox_opts=opts.ToolboxOpts(
                    is_show=True,
                    orient="vertical",
                    pos_left=None,  # Explicitly set to None to override the default 80%
                    pos_right="0%",
                    pos_top="center",
                    feature={
                        "saveAsImage": {
                            "show": True,
                            "title": "",
                            "type": [
                                "png",
                                "jpeg",
                                "svg",
                            ],  # Support multiple export formats
                            "pixelRatio": 2,  # Higher quality export
                            "backgroundColor": "#fff",
                        },
                        "dataView": {
                            "show": True,
                            "title": "",
                            "readOnly": False,  # Allow editing in data view
                            "lang": [
                                "Data View",
                                "Close",
                                "Refresh",
                            ],  # Customize buttons
                        },
                        "restore": {"show": True, "title": ""},
                        "dataZoom": {"show": True, "title": ""},
                    },
                ),
                datazoom_opts=[
                    opts.DataZoomOpts(
                        is_show=True,
                        type_="slider",
                        range_start=0,
                        range_end=100,
                        pos_bottom="10%",
                        xaxis_index=[0],
                    ),
                    opts.DataZoomOpts(type_="inside"),
                ],
            )

            return chart
        except Exception as e:
            import traceback

            logger.error(
                f"Error creating chart: {str(e)} , traceback: {traceback.format_exc()}"
            )
            return None

    def _get_sql_function_for_aggregate_type(self, agg_type: AggregateType) -> str:
        """Convert AggregateType enum value to the corresponding SQL function name.

        Args:
            agg_type: The aggregation type enum value

        Returns:
            The SQL function name to use in the query
        """
        # Map AggregateType enum values to SQL function names
        if agg_type == AggregateType.SUM:
            return "sum"
        elif agg_type == AggregateType.AVERAGE:
            return "avg"
        elif agg_type == AggregateType.COUNT:
            return "count"
        else:
            # Default to sum if unknown
            logger.warning(f"Unknown aggregation type: {agg_type}, defaulting to sum")
            return "sum"

    def _process_value(self, value: str, operator: str) -> Any:
        """Process the filter value based on the operator."""
        if operator in ["contains", "not_contains"]:
            return f"%{value}%"
        elif operator in ["in", "not_in"]:
            return value.split(",") if "," in value else [value]
        return value

    def _build_sql_filter(self, filter_dict: Dict[str, Any]) -> tuple[str, Any]:
        """Build SQL WHERE clause from filter dict."""
        column = cast(DjangoFieldLike, filter_dict.get("column", {}))
        operator = filter_dict.get("operator", "")
        value = self._process_value(filter_dict.get("value", ""), operator)

        field_name = column.field_name
        if not field_name:
            return "", None

        operator_map = {
            "equals": "=",
            "not_equals": "!=",
            "greater_than": ">",
            "less_than": "<",
            "greater_than_equals": ">=",
            "less_than_equals": "<=",
            "contains": "LIKE",
            "not_contains": "NOT LIKE",
            "in": "IN",
            "not_in": "NOT IN",
        }

        sql_operator = operator_map.get(operator)
        if not sql_operator:
            return "", None

        if operator in ["in", "not_in"]:
            placeholders = ",".join(["%s"] * len(value))
            return f'"{field_name}" {sql_operator} ({placeholders})', value

        return f'"{field_name}" {sql_operator} %s', value

    def _build_sql_query(self) -> tuple[str, List[Any]]:
        """Build SQL query from chart options."""
        # Get columns
        select_cols = []
        params = []

        x_axis_col = cast(DjangoFieldLike, self.options.get("x_axis_column", {}))
        if x_col := x_axis_col.field_name:
            select_cols.append(f'"{x_col}"')

        y_axis_cols = self._get_y_axis_columns()
        for y_col in y_axis_cols:
            if field := y_col.get("field"):
                field_name = field.field_name
                select_cols.append(f'"{field_name}"')

        # Handle time-based data
        time_column = cast(DjangoFieldLike, self.options.get("time_column", {}))
        if time_column:
            time_field = time_column.field_name
            if time_field and time_field not in select_cols:
                select_cols.append(f'"{time_field}"')

        # Build query
        query = f"SELECT {', '.join(select_cols)} FROM {{{{table}}}}"

        # Add filters
        where_clauses = []
        for filter_dict in self.filters:
            clause, value = self._build_sql_filter(filter_dict)
            if clause:
                where_clauses.append(clause)
                if isinstance(value, list):
                    params.extend(value)
                else:
                    params.append(value)

        if where_clauses:
            query += f" WHERE {' AND '.join(where_clauses)}"

        # Handle aggregation
        agg_type = cast(
            AggregateType, self.options.get("aggregate_type", AggregateType.NONE)
        )
        group_by = []

        # Determine if we need to group by any columns
        if agg_type != AggregateType.NONE:
            x_col = x_axis_col.field_name
            if x_col:
                group_by.append(f'"{x_col}"')
            if time_column:
                time_field = time_column.field_name
                if time_field:
                    group_by.append(f'"{time_field}"')

        # Always rebuild the select columns for consistent handling
        # Remove y-axis columns from the select list as we'll add them back with proper handling
        select_cols = [
            col
            for col in select_cols
            if not any(
                y_col.get("field", {}).field_name in col for y_col in y_axis_cols
            )
        ]

        # Add back y-axis columns with proper handling based on aggregation type
        for y_col in y_axis_cols:
            if field := y_col.get("field"):
                field_name = field.field_name
                if agg_type == AggregateType.NONE:
                    # For NONE, just use the column name directly
                    select_cols.append(f'"{field_name}"')
                else:
                    # For other aggregation types, wrap in the appropriate function
                    # Need to convert from enum value to SQL function name
                    sql_function = self._get_sql_function_for_aggregate_type(agg_type)
                    select_cols.append(
                        f'{sql_function}("{field_name}") as "{field_name}"'
                    )

        # Rebuild the query with the updated select columns
        query = f"SELECT {', '.join(select_cols)} FROM {{{{table}}}}"

        # Add group by
        if group_by:
            query += f" GROUP BY {', '.join(group_by)}"

        # Add order by
        order_by = []
        if time_column:
            time_field = time_column.field_name
            if time_field:
                order_by.append(f'"{time_field}"')
        if x_col := x_axis_col.field_name:
            order_by.append(f'"{x_col}"')

        if order_by:
            sort_order_value = self.options.get("sort_order", "asc")
            if isinstance(sort_order_value, str):
                sort_order = sort_order_value.upper()
            else:
                sort_order = "ASC"  # Default to ASC if not a string
            query += f' ORDER BY {", ".join(order_by)} {sort_order}'

        return query, params

    def get_y_axis_bounds(self) -> tuple[float, float]:
        """Calculate min and max bounds for y-axis."""
        try:
            data = self._get_data()
            if data is None or data.empty:
                return 0, 5

            y_values = []
            for y_axis_column in self._get_y_axis_columns():
                if field := y_axis_column.get("field"):
                    field_name = field.field_name

                    # Check if the field exists in the DataFrame
                    if field_name not in data.columns:
                        logger.warning(
                            f"Field '{field_name}' not found in data columns"
                        )
                        continue

                    # Get the column data directly
                    column_data = data[field_name]

                    # Handle case where column_data is a DataFrame (can happen with SQL queries)
                    if isinstance(column_data, pd.DataFrame):
                        logger.debug(
                            f"Column {field_name} is a DataFrame, using first column"
                        )
                        if column_data.empty:
                            continue
                        column_data = column_data.iloc[:, 0]  # Take the first column

                    # Drop NA values and convert to float
                    try:
                        # For Series, convert to float and extend y_values
                        clean_values = column_data.dropna()
                        if not clean_values.empty:
                            float_values = clean_values.astype(float).tolist()
                            y_values.extend(float_values)
                    except (ValueError, TypeError) as e:
                        logger.warning(f"Error converting values for {field_name}: {e}")
                    except Exception as e:
                        logger.warning(
                            f"Unexpected error processing values for {field_name}: {e}"
                        )

            if not y_values:
                return 0, 5

            min_val = min(y_values)
            max_val = max(y_values)

            # Add buffer for better visualization
            range_val = max_val - min_val
            buffer = range_val * 0.1 if range_val > 0 else 0.5  # Ensure non-zero buffer

            min_bound = max(0, min_val - buffer) if min_val >= 0 else min_val - buffer
            max_bound = max_val + buffer

            return min_bound, max_bound
        except Exception as e:
            logger.error(f"Error calculating y-axis bounds: {str(e)}")
            return 0, 5

    def get_chart_specific_opts(self) -> dict:
        """Get chart type specific options. Override in subclasses."""
        y_min, y_max = self.get_y_axis_bounds()

        # Create basic options with improved responsiveness and label positioning
        return {
            "title_opts": opts.TitleOpts(
                title=self.options.get("title", ""),
                subtitle=self.options.get("subtitle", ""),
                title_textstyle_opts=opts.TextStyleOpts(
                    font_size=16,
                    font_weight="bold",
                ),
            ),
            "tooltip_opts": opts.TooltipOpts(
                trigger="axis",
                axis_pointer_type="cross",
                background_color="rgba(50,50,50,0.9)",
                border_width=0,
                textstyle_opts=opts.TextStyleOpts(color="#ffffff", font_size=12),
            ),
            "toolbox_opts": opts.ToolboxOpts(
                is_show=True,
                feature={
                    "dataZoom": {"yAxisIndex": "none"},
                    "restore": {},
                    "saveAsImage": {},
                },
                pos_left="right",
                orient="vertical",
            ),
            "xaxis_opts": opts.AxisOpts(
                type_="category",
                boundary_gap=True,
                axislabel_opts=opts.LabelOpts(
                    position="bottom",
                    rotate=30,
                    margin=10,
                    font_size=12,
                    is_show=True,
                ),
            ),
            "yaxis_opts": opts.AxisOpts(
                type_="value",
                min_=y_min,
                max_=y_max,
                axislabel_opts=opts.LabelOpts(font_size=12, is_show=True),
            ),
        }

    def initialize_chart(self, filtered_data: Optional[pd.DataFrame] = None) -> Chart:
        """Initialize the chart with common options."""
        chart_class = self.get_chart_class()
        if not chart_class:
            raise ValueError(f"Unknown chart type: {self.chart_details.chart_type}")

        # Store chart ID for cross-chart interactions
        self.chart_id = f"chart_{self.chart_details.id}"
        # Store for potential linked charts
        self._linked_charts: List[Chart] = []

        # Get chart options with responsive sizing
        width = cast(str, self.options.get("width", "auto"))
        height = cast(str, self.options.get("height", "600px"))
        theme = cast(str, self.options.get("theme", "white"))

        # Determine font size based on container width for responsiveness
        base_font_size = 12
        if width == "auto" or width == "100%":
            # Auto-responsive font size
            label_font_size = base_font_size
            title_font_size = base_font_size + 2
        elif isinstance(width, str) and width.endswith("px"):
            # Try to extract pixel width and adjust font size accordingly
            try:
                pixel_width = int(width.rstrip("px"))
                if pixel_width < 400:
                    label_font_size = (
                        base_font_size - 2
                    )  # Smaller font for small containers
                    title_font_size = base_font_size
                elif pixel_width > 1200:
                    label_font_size = (
                        base_font_size + 2
                    )  # Larger font for large containers
                    title_font_size = base_font_size + 4
                else:
                    label_font_size = base_font_size
                    title_font_size = base_font_size + 2
            except ValueError:
                label_font_size = base_font_size
                title_font_size = base_font_size + 2
        else:
            label_font_size = base_font_size
            title_font_size = base_font_size + 2

        # Store font sizes for use in other methods
        self._responsive_label_font_size = label_font_size
        self._responsive_title_font_size = title_font_size

        # Create chart instance with responsive options
        chart = chart_class(
            init_opts=opts.InitOpts(
                width=width,
                height=height,
                theme=theme,
                renderer="canvas",
                animation_opts=opts.AnimationOpts(animation=False),
            )
        )

        # Get chart options
        chart_opts = self.get_chart_specific_opts()

        # Enhance tooltip styling for better readability
        if "tooltip_opts" not in chart_opts:
            chart_opts["tooltip_opts"] = opts.TooltipOpts(
                trigger="axis",
                axis_pointer_type="cross",
                background_color="rgba(50,50,50,0.9)",  # Darker background
                border_color="#ccc",
                border_width=0,
                textstyle_opts=opts.TextStyleOpts(
                    color="#fff",  # White text for contrast
                    font_size=14,
                ),
            )

        chart.set_global_opts(**chart_opts)

        # Add responsive configuration
        chart.js_host = ""

        # Add additional initialization options for responsiveness
        if not hasattr(chart, "options") or not chart.options:
            chart.options = {}

        chart.options.update(
            {
                "animation": False,
                "grid": {
                    "top": "10%",
                    "right": "15%",
                    "bottom": "15%",
                    "left": "10%",
                    "containLabel": True,
                },
                # Accessibility options
                "aria": {
                    "show": True,
                    "description": getattr(self.chart_details, "title", None)
                    or "Chart",
                    "general": {
                        "withTitle": True,
                        "withDesc": True,
                    },
                    "label": {
                        "enabled": True,
                    },
                },
                "dataZoom": [
                    {
                        "type": "slider",
                        "show": True,
                        "realtime": True,
                        "start": 0,
                        "end": 100,
                        "bottom": "10%",
                        "xAxisIndex": [0],
                        "height": 20,
                    },
                    {"type": "inside", "xAxisIndex": [0], "start": 0, "end": 100},
                ],
            }
        )

        return chart

    def configure_chart(
        self, chart: Chart, filtered_data: Optional[pd.DataFrame] = None
    ) -> None:
        """Configure chart with data. This method handles common data processing for all chart types.

        Individual chart classes should override this method only if they need to change the basic
        data processing logic. Otherwise, they should override get_chart_specific_opts() and
        add_series_to_chart() to customize chart appearance.
        """
        if filtered_data is None:
            return

        # Process data based on chart type
        processed_data = self._process_data(filtered_data)

        # Get x-axis data
        x_axis_field = cast(DjangoFieldLike, self.options["x_axis_column"])
        x_field = x_axis_field.field_name
        x_axis_data = self._get_x_axis_data(processed_data, x_field)

        # Add x-axis
        chart.add_xaxis(x_axis_data)

        # Add series for each y-axis column
        for y_axis_column in self._get_y_axis_columns():
            field = y_axis_column["field"]
            field_name = field.field_name
            series_name = self._get_series_name(y_axis_column)

            # Get y values aligned with x-axis data
            y_values = self._get_y_values(
                processed_data, x_axis_data, x_field, field_name
            )

            # Add the series to the chart
            self.add_series_to_chart(
                chart=chart,
                series_name=series_name,
                y_values=y_values,
                color=y_axis_column.get("color"),
                value_mapping=y_axis_column.get("value_mapping"),
            )

    def _get_y_axis_columns(self) -> List[Dict[str, Any]]:
        """Get y-axis columns configuration."""
        y_axis_columns = self.options["y_axis_column"]
        if not isinstance(y_axis_columns, list):
            y_axis_columns = [y_axis_columns]
        return cast(List[Dict[str, Any]], y_axis_columns)

    def _get_series_name(self, y_axis_column: Dict[str, Any]) -> str:
        """Get series name from y-axis column configuration."""
        return str(y_axis_column.get("label") or y_axis_column["field"].field_name)

    def add_series_to_chart(
        self,
        chart: Chart,
        series_name: str,
        y_values: List[Any],
        color: Optional[str] = None,
        value_mapping: Optional[Dict[Any, Any]] = None,
    ) -> None:
        """Add a series to the chart with specific styling.

        This method can be overridden by subclasses to provide chart-specific styling.
        """
        # Add series to chart
        # This is a base implementation that will be overridden by subclasses
        if not hasattr(chart, "add_yaxis"):
            logger.warning("Chart does not have add_yaxis method")
            return

        # Get style options
        style_opts = self.get_series_style_opts(color)

        # Add label options to position labels at the bottom
        if "label_opts" not in style_opts:
            style_opts["label_opts"] = opts.LabelOpts(
                is_show=True,
                position="bottom",  # Position labels at the bottom
                font_size=12,
                font_weight="normal",
                color="#333",
            )

        # Add series to chart
        chart.add_yaxis(
            series_name=series_name,
            y_axis=y_values,
            **style_opts,
        )

    def get_series_style_opts(self, color: Optional[str] = None) -> Dict[str, Any]:
        """Get series-specific styling options.

        This method should be overridden by subclasses to provide series-specific styling options.
        """
        # Default options for all chart types
        return {
            "itemstyle_opts": opts.ItemStyleOpts(color=color) if color else None,
        }

    def add_series(self, chart: Chart, filtered_data: pd.DataFrame) -> Chart:
        """Add series data to the chart."""
        raise NotImplementedError("Subclasses must implement add_series")

    def _optimize_dataset(
        self, data: pd.DataFrame, max_points: int = 1000
    ) -> pd.DataFrame:
        """Optimize large datasets by sampling to improve performance.

        For large datasets, this method will sample the data to reduce the number of points
        while preserving the overall shape of the data.

        Args:
            data: The input DataFrame
            max_points: Maximum number of data points to display

        Returns:
            Optimized DataFrame with reduced number of points if necessary
        """
        if data is None or len(data) <= max_points:
            return data

        # Calculate sampling rate
        sample_rate = max_points / len(data)

        # Use systematic sampling to preserve data shape
        if "date" in data.columns or "time" in data.columns:
            # For time series data, preserve time distribution
            time_col = "date" if "date" in data.columns else "time"
            # Sort by time column
            data = data.sort_values(by=time_col)
            # Sample evenly across time
            indices = np.linspace(0, len(data) - 1, max_points).astype(int)
            return data.iloc[indices].copy()  # Return explicit DataFrame
        else:
            # For non-time series data, use random sampling
            return data.sample(n=max_points)

    def _handle_regular_data(self, chart: Chart, filtered_data: pd.DataFrame) -> None:
        """Handle non-time-based data."""
        # Optimize large datasets for performance
        optimized_data = self._optimize_dataset(filtered_data)

        # Get x-axis field name
        x_axis_field = cast(DjangoFieldLike, self.options["x_axis_column"])
        x_field = x_axis_field.field_name
        x_axis_data = optimized_data[x_field].tolist()

        # Sort values if needed
        sort_order = self.options.get("sort_order", "asc")
        x_axis_data = sorted(x_axis_data, reverse=(sort_order == "desc"))  # type: ignore[type-var]

        # Add x-axis data
        chart.add_xaxis(x_axis_data)

        # Get y-axis columns configuration
        y_axis_columns = self._get_y_axis_columns()

        # Add series for each y-axis column
        for y_axis_column in y_axis_columns:
            # Get y-axis field name
            y_field = cast(DjangoFieldLike, y_axis_column["field"])
            field_name = y_field.field_name
            y_values = filtered_data[field_name].tolist()

            # Get series name from configuration
            series_name = self._get_series_name(y_axis_column)

            # Get value mapping from configuration
            value_mapping = self._get_value_mapping(y_axis_column)

            # Add series to chart
            self.add_series_to_chart(
                chart=chart,
                series_name=series_name,
                y_values=y_values,
                color=y_axis_column.get("color"),
                value_mapping=value_mapping,
            )

    def _process_data(self, filtered_data: pd.DataFrame) -> pd.DataFrame:
        """Process data based on chart type and options.

        This method can be overridden by subclasses to perform chart-specific data processing.
        """
        # By default, just return the filtered data as is
        return filtered_data

    def _get_x_axis_data(self, processed_data: pd.DataFrame, x_field: str) -> List[Any]:
        """Get x-axis data from processed data."""
        # Extract x-axis values
        x_axis_data = processed_data[x_field].tolist()

        # Sort if needed
        sort_order = self.options.get("sort_order", "asc")
        return sorted(x_axis_data, reverse=(sort_order == "desc"))

    def _get_y_values(
        self,
        processed_data: pd.DataFrame,
        x_axis_data: List[Any],
        x_field: str,
        y_field: str,
    ) -> List[float]:
        """Get y-axis values aligned with x-axis data.

        Assumes that the data is already properly aggregated from SQL queries.
        Simply maps the values to ensure alignment with the x-axis order.
        """
        # Create a mapping from x values to their corresponding y values
        x_to_y_map = {}

        # Check if the y_field exists in the DataFrame
        if y_field not in processed_data.columns:
            logger.warning(f"Y-field '{y_field}' not found in processed data")
            return [0.0] * len(x_axis_data)

        # Get the column data directly
        y_column = processed_data[y_field]

        # Check if y_column is a DataFrame (can happen with SQL queries)
        if isinstance(y_column, pd.DataFrame):
            logger.debug(f"Y-column '{y_field}' is a DataFrame, using first column")
            if y_column.empty:
                return [0.0] * len(x_axis_data)
            y_column = y_column.iloc[:, 0]  # Take the first column

        # Create the mapping efficiently
        for idx, row in processed_data.iterrows():
            x_val = row[x_field]
            y_val = row[y_field]

            try:
                # Handle different data types efficiently
                if isinstance(y_val, pd.Series):
                    if not y_val.empty:
                        value = y_val.iloc[0]
                        if pd.notna(value):
                            x_to_y_map[x_val] = float(value)
                elif pd.notna(y_val):
                    x_to_y_map[x_val] = float(y_val)  # type: ignore
            except (ValueError, TypeError) as e:
                logger.warning(f"Error converting y-value for {x_val}: {e}")
            except Exception as e:
                logger.warning(f"Unexpected error processing y-value for {x_val}: {e}")

        # Create y_values array aligned with x_axis_data (list comprehension is more efficient)
        return [x_to_y_map.get(x_val, 0.0) for x_val in x_axis_data]

    def _get_value_mapping(self, y_axis_column: Dict[str, Any]) -> Dict[str, Any]:
        """Get value mapping from y-axis column configuration."""
        if not isinstance(y_axis_column, dict):
            return {}
        mapping = y_axis_column.get("value_mapping")
        return cast(Dict[str, Any], mapping) if mapping is not None else {}
