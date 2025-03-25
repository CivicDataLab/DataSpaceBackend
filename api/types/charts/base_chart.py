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
            logger.error(f"Error creating chart: {str(e)}")
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
        column = cast(Dict[str, Any], filter_dict.get("column", {}))
        operator = filter_dict.get("operator", "")
        value = self._process_value(filter_dict.get("value", ""), operator)

        field_name = column.get("field_name", "")
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

        x_axis_col = cast(Dict[str, Any], self.options.get("x_axis_column", {}))
        if x_col := x_axis_col.get("field_name"):
            select_cols.append(f'"{x_col}"')

        y_axis_cols = self._get_y_axis_columns()
        for y_col in y_axis_cols:
            if field := y_col.get("field"):
                field_name = field.get("field_name")
                select_cols.append(f'"{field_name}"')

        # Handle time-based data
        time_column = self.options.get("time_column")
        if (
            time_column
            and isinstance(time_column, dict)
            and time_column.get("field_name")
        ):
            time_field = time_column.get("field_name")
            if time_field and time_field not in select_cols:
                select_cols.append(f'"{time_field}"')

        # Build query
        query = f"SELECT {', '.join(select_cols)} FROM {{table}}"

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

        # Handle time groups
        time_groups = self.options.get("time_groups", [])
        if (
            time_column
            and isinstance(time_column, dict)
            and isinstance(time_groups, list)
        ):
            time_field = time_column.get("field_name")
            if time_field:
                time_values = ",".join([f"'{group}'" for group in time_groups])
                where_clause = f'"{time_field}" IN ({time_values})'
                query += (
                    f" AND {where_clause}"
                    if where_clauses
                    else f" WHERE {where_clause}"
                )

        # Handle aggregation
        agg_type = self.options.get("aggregate_type", "none")
        group_by = []
        if agg_type != "none":
            x_col = x_axis_col.get("field_name")
            if x_col:
                group_by.append(f'"{x_col}"')
            if time_column:
                if isinstance(time_column, dict):
                    time_field = time_column.get("field_name")
                    if time_field:
                        group_by.append(f'"{time_field}"')

            # Update y-axis columns with aggregation
            select_cols = [
                col
                for col in select_cols
                if not any(
                    y_col.get("field", {}).get("field_name") in col
                    for y_col in y_axis_cols
                )
            ]
            for y_col in y_axis_cols:
                if field := y_col.get("field"):
                    field_name = field.get("field_name")
                    select_cols.append(f'{agg_type}("{field_name}") as "{field_name}"')

            query = f"SELECT {', '.join(select_cols)} FROM {{table}}"

        # Add group by
        if group_by:
            query += f" GROUP BY {', '.join(group_by)}"

        # Add order by
        order_by = []
        if (
            time_column
            and isinstance(time_column, dict)
            and "field_name" in time_column
        ):
            time_field = time_column.get("field_name")
            if time_field:
                order_by.append(f'"{time_field}"')
        if x_col := x_axis_col.get("field_name"):
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
                    field_name = field.get("field_name")
                    if field_name in data.columns:
                        y_values.extend(
                            data[field_name].dropna().astype(float).tolist()
                        )

            if not y_values:
                return 0, 5

            min_val = min(y_values)
            max_val = max(y_values)

            # Add buffer for better visualization
            range_val = max_val - min_val
            buffer = range_val * 0.1

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
        """Configure chart with data. Override in subclasses."""
        if filtered_data is None:
            return

        # Get x-axis data
        x_axis_field = cast(Dict[str, Any], self.options["x_axis_column"])
        x_field = x_axis_field["field_name"]
        x_axis_data = filtered_data[x_field].tolist()

        # Sort if needed
        sort_order = self.options.get("sort_order", "asc")
        x_axis_data = sorted(x_axis_data, reverse=(sort_order == "desc"))

        # Add x-axis
        chart.add_xaxis(x_axis_data)

        # Add series for each y-axis column
        for y_axis_column in self._get_y_axis_columns():
            field = y_axis_column["field"]
            field_name = field["field_name"]
            series_name = self._get_series_name(y_axis_column)
            y_values = filtered_data[field_name].tolist()

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
        return str(y_axis_column.get("label") or y_axis_column["field"]["field_name"])

    def add_series_to_chart(
        self,
        chart: Chart,
        series_name: str,
        y_values: List[Any],
        color: Optional[str] = None,
        value_mapping: Optional[Dict[Any, Any]] = None,
    ) -> None:
        """Add a series to the chart with specific styling."""
        # Create a list of value objects with original and formatted values
        data = []
        for val in y_values:
            # Keep original numeric value for plotting
            value = float(val) if val is not None else 0.0
            # Get mapped string value for display
            label = (
                value_mapping.get(str(value), str(value))
                if value_mapping
                else str(value)
            )

            # Use appropriate item type based on chart class
            if isinstance(chart, Line):
                data.append(
                    opts.LineItem(
                        name=label, value=value, symbol_size=8, symbol="emptyCircle"
                    )
                )
            else:
                data.append(opts.BarItem(name=label, value=value))

        chart.add_yaxis(
            series_name=series_name,
            y_axis=data,
            label_opts=opts.LabelOpts(is_show=False),
            itemstyle_opts=opts.ItemStyleOpts(color=color) if color else None,
            **(
                {
                    "linestyle_opts": opts.LineStyleOpts(width=2, type_="solid"),
                    "is_smooth": True,
                    "is_symbol_show": True,
                }
                if isinstance(chart, Line)
                else {}
            ),
        )

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

    def _get_value_mapping(self, y_axis_column: Dict[str, Any]) -> Dict[str, Any]:
        """Get value mapping from y-axis column configuration."""
        if not isinstance(y_axis_column, dict):
            return {}
        mapping = y_axis_column.get("value_mapping")
        return cast(Dict[str, Any], mapping) if mapping is not None else {}
