from typing import Any, Dict, Hashable, List, Optional, Protocol, TypeVar, Union, cast

import pandas as pd
import structlog
from pandas.core.groupby import DataFrameGroupBy
from pyecharts import options as opts
from pyecharts.charts import Bar, Line, Map
from pyecharts.charts.chart import Chart

from api.models import ResourceChartDetails, ResourceSchema
from api.utils.data_indexing import query_resource_data

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
    "BAR_VERTICAL": Bar,
    "BAR_HORIZONTAL": Bar,
    "GROUPED_BAR_VERTICAL": Bar,
    "GROUPED_BAR_HORIZONTAL": Bar,
    "LINE": Line,
    "ASSAM_DISTRICT": Map,
    "ASSAM_RC": Map,
    "MULTILINE": Line,
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

            return chart
        except Exception as e:
            import traceback

            logger.error(
                f"Error creating chart: {str(e)} , traceback: {traceback.format_exc()}"
            )
            return None

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
        agg_type = self.options.get("aggregate_type", "none")
        group_by = []
        if agg_type != "none":
            x_col = x_axis_col.field_name
            if x_col:
                group_by.append(f'"{x_col}"')
            if time_column:
                time_field = time_column.field_name
                if time_field:
                    group_by.append(f'"{time_field}"')

            # Update y-axis columns with aggregation
            select_cols = [
                col
                for col in select_cols
                if not any(
                    y_col.get("field", {}).field_name in col for y_col in y_axis_cols
                )
            ]
            for y_col in y_axis_cols:
                if field := y_col.get("field"):
                    field_name = field.field_name
                    select_cols.append(f'{agg_type}("{field_name}") as "{field_name}"')

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

    def get_chart_specific_opts(self) -> dict:
        """Get chart type specific options. Override in subclasses."""
        y_min, y_max = self.get_y_axis_bounds()

        return {
            "xaxis_opts": opts.AxisOpts(
                type_="category",
                name_location="middle",
                name_gap=25,
                axislabel_opts=opts.LabelOpts(margin=8),
            ),
            "yaxis_opts": opts.AxisOpts(
                type_="value",
                name_location="middle",
                name_gap=25,
                min_=y_min,
                max_=y_max,
                axislabel_opts=opts.LabelOpts(margin=8, formatter="{value}"),
            ),
            "tooltip_opts": opts.TooltipOpts(trigger="axis", axis_pointer_type="cross"),
            "legend_opts": opts.LegendOpts(
                is_show=True,
                selected_mode=True,
                pos_top="2%",
                pos_left="center",
                orient="horizontal",
                item_gap=25,
                padding=[5, 10, 5, 10],
                textstyle_opts=opts.TextStyleOpts(font_size=12),
                border_width=0,
                background_color="transparent",
            ),
            "toolbox_opts": opts.ToolboxOpts(
                is_show=True,
                pos_left="right",
                pos_top="8%",
                orient="horizontal",
                item_size=15,
                item_gap=10,
                feature={
                    "dataZoom": {
                        "show": True,
                        "title": {"zoom": "Area Zoom", "back": "Zoom Reset"},
                    },
                    "restore": {"show": True, "title": "Reset"},
                    "dataView": {
                        "show": True,
                        "title": "View Data",
                        "lang": ["Data View", "Close", "Refresh"],
                    },
                    "saveAsImage": {
                        "show": True,
                        "title": "Save as Image",
                        "type": "png",
                    },
                    "magicType": {
                        "show": True,
                        "type": ["line", "bar"],
                        "title": {"line": "Switch to Line", "bar": "Switch to Bar"},
                    },
                },
            ),
            "grid": {
                "top": "15%",
                "bottom": "15%",
                "left": "10%",
                "right": "5%",
                "containLabel": True,
            },
        }

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

    def initialize_chart(self, filtered_data: Optional[pd.DataFrame] = None) -> Chart:
        """Initialize the chart with common options."""
        chart = self.get_chart_class()(
            init_opts=opts.InitOpts(
                width=str(self.options.get("width", "100%")),
                height=str(self.options.get("height", "400px")),
                animation_opts=opts.AnimationOpts(animation=False),
            )
        )

        # Get all options
        opts_dict = self.get_chart_specific_opts()

        # Set grid options
        chart.options["grid"] = opts_dict["grid"]

        # Set global options
        chart.set_global_opts(
            title_opts=opts.TitleOpts(
                title=self.chart_details.name or "",
                subtitle=self.chart_details.description or "",
                pos_top="5%",
            ),
            xaxis_opts=opts_dict["xaxis_opts"],
            yaxis_opts=opts_dict["yaxis_opts"],
            tooltip_opts=opts_dict["tooltip_opts"],
            legend_opts=opts_dict["legend_opts"],
            toolbox_opts=opts_dict["toolbox_opts"],
            visualmap_opts=opts_dict.get("visualmap_opts"),
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
        # For numeric charts (Line, Bar), we need simple numeric values
        data = []
        for val in y_values:
            # Convert to float for plotting
            value = float(val) if val is not None else 0.0
            data.append(value)

        # Get series-specific styling options
        chart_opts = self.get_series_style_opts(color)

        # Add the series to the chart
        chart.add_yaxis(
            series_name=series_name,
            y_axis=data,
            label_opts=opts.LabelOpts(is_show=False),
            **chart_opts,
        )

    def get_series_style_opts(self, color: Optional[str] = None) -> Dict[str, Any]:
        """Get series-specific styling options.

        This method should be overridden by subclasses to provide series-specific styling options.
        """
        # Default options for all chart types
        return {
            "itemstyle_opts": opts.ItemStyleOpts(color=color) if color else None,
        }

    def _handle_regular_data(self, chart: Chart, filtered_data: pd.DataFrame) -> None:
        """Handle non-time-based data."""
        # Get x-axis field name
        x_axis_field = cast(DjangoFieldLike, self.options["x_axis_column"])
        x_field = x_axis_field.field_name
        x_axis_data = filtered_data[x_field].tolist()

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
                    x_to_y_map[x_val] = float(y_val)
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
