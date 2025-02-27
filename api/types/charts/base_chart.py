from abc import ABC, abstractmethod

import pandas as pd
from pandas.core.groupby import DataFrameGroupBy
from pyecharts.charts import Line, Bar, Map
from pyecharts.charts.chart import Chart
from pyecharts import options as opts

from api.models import ResourceChartDetails

CHART_TYPE_MAP = {
    "BAR_VERTICAL": Bar,
    "BAR_HORIZONTAL": Bar,
    "GROUPED_BAR_VERTICAL": Bar,
    "GROUPED_BAR_HORIZONTAL": Bar,
    "LINE": Line,
    "ASSAM_DISTRICT": Map,
    "ASSAM_RC": Map,
    "MULTILINE": Line
}


class BaseChart(ABC):
    def __init__(self, chart_details: ResourceChartDetails, data: pd.DataFrame):
        self.chart_details = chart_details
        self.data = data
        self.options = chart_details.options

    @abstractmethod
    def create_chart(self) -> Chart:
        pass

    def get_chart_class(self):
        return CHART_TYPE_MAP.get(self.chart_details.chart_type)

    def _process_value(self, value: str, operator: str) -> any:
        """Process the filter value based on the operator."""
        if operator in ('in', 'not in'):
            return [val.strip() for val in value.split(",")] if "," in value else [value]
        return value

    def filter_data(self) -> pd.DataFrame:
        """
        Filter the data based on the chart_details filters.
        """
        filtered_data = self.data
        if not self.chart_details.filters or len(self.chart_details.filters) == 0:
            return filtered_data

        operator_map = {
            '==': lambda col, val: col == val,
            '!=': lambda col, val: col != val,
            '>': lambda col, val: col > val,
            '<': lambda col, val: col < val,
            '>=': lambda col, val: col >= val,
            '<=': lambda col, val: col <= val,
            'in': lambda col, val: col.isin(val),
            'not in': lambda col, val: ~col.isin(val)
        }

        conditions = []
        for filter_condition in self.chart_details.filters:
            column = filter_condition['column'].field_name
            operator = filter_condition['operator']
            value = self._process_value(filter_condition['value'], operator)
            
            if operator in operator_map:
                conditions.append(operator_map[operator](filtered_data[column], value))

        return filtered_data[pd.concat(conditions, axis=1).all(axis=1)] if conditions else filtered_data

    def get_y_axis_bounds(self, filtered_data: pd.DataFrame) -> tuple:
        """
        Calculate min and max bounds for y-axis from the data
        """
        y_values = []
        for y_axis_column in self.options['y_axis_column']:
            column_name = y_axis_column['field'].field_name
            if column_name in filtered_data.columns:
                y_values.extend(filtered_data[column_name].dropna().astype(float).tolist())
        
        if not y_values:
            return 0, 5  # Default bounds if no data
            
        min_val = min(y_values)
        max_val = max(y_values)
        
        # Add a small buffer (10%) for better visualization
        range_val = max_val - min_val
        buffer = range_val * 0.1
        
        # For min, don't go below 0 unless data contains negative values
        min_bound = max(0, min_val - buffer) if min_val >= 0 else min_val - buffer
        max_bound = max_val + buffer
        
        return min_bound, max_bound

    def get_init_opts(self) -> opts.InitOpts:
        """
        Get common initialization options.
        Override in subclasses if needed.
        """
        return opts.InitOpts(
            width=self.options.get('width', '100%'),
            height=self.options.get('height', '400px'),
            animation_opts=opts.AnimationOpts(animation=False)
        )

    def get_chart_specific_opts(self) -> dict:
        """
        Get chart type specific options. Override in subclasses for specific chart types.
        """
        y_min, y_max = self.get_y_axis_bounds(self.data)
        
        return {
            'xaxis_opts': opts.AxisOpts(
                type_="category",
                name_location="middle",
                name_gap=25,
                axislabel_opts=opts.LabelOpts(
                    margin=8
                )
            ),
            'yaxis_opts': opts.AxisOpts(
                type_="value",
                name_location="middle",
                name_gap=25,
                min_=y_min,
                max_=y_max,
                axislabel_opts=opts.LabelOpts(
                    margin=8,
                    formatter="{value}"
                )
            ),
            'tooltip_opts': opts.TooltipOpts(
                trigger="axis",
                axis_pointer_type="cross"
            ),
            'legend_opts': opts.LegendOpts(
                is_show=True,
                selected_mode=True,
                pos_top="2%",
                pos_left="center",
                orient="horizontal",
                item_gap=25,
                padding=[5, 10, 5, 10],
                textstyle_opts=opts.TextStyleOpts(font_size=12),
                border_width=0,
                background_color="transparent"
            ),
            'toolbox_opts': opts.ToolboxOpts(
                is_show=True,
                pos_left="right",
                pos_top="8%",
                orient="horizontal",
                item_size=15,
                item_gap=10,
                feature={
                    'dataZoom': {
                        'show': True,
                        'title': {
                            'zoom': 'Area Zoom',
                            'back': 'Zoom Reset'
                        }
                    },
                    'restore': {
                        'show': True,
                        'title': 'Reset'
                    },
                    'dataView': {
                        'show': True,
                        'title': 'View Data',
                        'lang': ['Data View', 'Close', 'Refresh']
                    },
                    'saveAsImage': {
                        'show': True,
                        'title': 'Save as Image',
                        'type': 'png'
                    },
                    'magicType': {
                        'show': True,
                        'type': ['line', 'bar'],
                        'title': {
                            'line': 'Switch to Line',
                            'bar': 'Switch to Bar'
                        }
                    }
                }
            ),
            'grid': {
                "top": "15%",
                "bottom": "15%",
                "left": "10%",
                "right": "5%",
                "containLabel": True
            }
        }

    def initialize_chart(self, filtered_data: pd.DataFrame = None) -> Chart:
        """Initialize the chart with common options."""
        chart = self.get_chart_class()(
            init_opts=self.get_init_opts()
        )
        
        # Get all options
        opts_dict = self.get_chart_specific_opts()
        
        # Set grid options directly
        chart.options["grid"] = opts_dict['grid']
        
        # Set global options
        chart.set_global_opts(
            title_opts=opts.TitleOpts(pos_top="5%"),
            legend_opts=opts_dict['legend_opts'],
            toolbox_opts=opts_dict['toolbox_opts'],
            tooltip_opts=opts_dict['tooltip_opts'],
            visualmap_opts=opts_dict.get('visualmap_opts')  # Optional for some charts
        )
        
        return chart

    def add_series_to_chart(self, chart: Chart, series_name: str, y_values: list, color: str = None, value_mapping: dict = None) -> None:
        """
        Add a series to the chart with specific styling. Override in subclasses for specific styling.
        """
        # Create a list of value objects with original and formatted values
        data = []
        for val in y_values:
            # Keep original numeric value for plotting
            value = float(val) if val is not None else 0.0
            # Get mapped string value for display
            label = value_mapping.get(str(value), str(value)) if value_mapping else str(value)
            
            # Use appropriate item type based on chart class
            if isinstance(chart, Line):
                data.append(opts.LineItem(
                    name=label,
                    value=value,
                    symbol_size=8,
                    symbol="emptyCircle"
                ))
            else:
                data.append(opts.BarItem(
                    name=label,
                    value=value
                ))
        
        chart.add_yaxis(
            series_name=series_name,
            y_axis=data,
            label_opts=opts.LabelOpts(is_show=False),
            itemstyle_opts=opts.ItemStyleOpts(color=color) if color else None,
            linestyle_opts=opts.LineStyleOpts(
                width=2,
                type_="solid"
            ) if isinstance(chart, Line) else None,
            is_smooth=True if isinstance(chart, Line) else None,
            is_symbol_show=True if isinstance(chart, Line) else None
        )

    def _handle_time_based_data(self, chart: Chart, filtered_data: pd.DataFrame, time_column) -> None:
        """
        Handle time-based data with aggregation.
        
        Args:
            chart (Chart): The chart instance to update
            filtered_data (pd.DataFrame): Filtered dataframe
            time_column: Time column configuration
        """
        # Group data by time periods
        time_groups = filtered_data.groupby(time_column.field_name)
        selected_groups = self.options.get('time_groups', [])
        
        # If no time groups specified, use all periods
        if not selected_groups:
            all_periods = sorted([str(time) for time in time_groups.groups.keys()])
            selected_groups = all_periods

        # If x-axis is same as time column, use time periods directly
        x_field = self.options['x_axis_column'].field_name
        if x_field == time_column.field_name:
            x_axis_data = sorted([str(time) for time in time_groups.groups.keys() if str(time) in selected_groups])
            chart.add_xaxis(x_axis_data)

            # Add data for each metric
            for y_axis_column in self._get_y_axis_columns():
                metric_name = self._get_series_name(y_axis_column)
                field_name = y_axis_column['field'].field_name
                value_mapping = self._get_value_mapping(y_axis_column)
                aggregate_type = y_axis_column.get('aggregate_type')
                
                y_values = []
                for time_val in x_axis_data:
                    period_data = time_groups.get_group(time_val)
                    value = self._apply_aggregation(period_data, field_name, aggregate_type)
                    y_values.append(value)
                
                self.add_series_to_chart(
                    chart=chart,
                    series_name=metric_name,
                    y_values=y_values,
                    color=y_axis_column.get('color'),
                    value_mapping=value_mapping
                )
        else:
            # Get unique x-axis values from original data
            all_x_values = filtered_data[x_field].unique().tolist()
            all_x_values.sort()

            # Create x-axis labels with time periods
            x_axis_data = []
            for x_val in all_x_values:
                for time_val in time_groups.groups.keys():
                    if str(time_val) in selected_groups:
                        x_axis_data.append(f"{x_val} ({time_val})")
            chart.add_xaxis(x_axis_data)

            # Add data for each metric
            for y_axis_column in self._get_y_axis_columns():
                metric_name = self._get_series_name(y_axis_column)
                field_name = y_axis_column['field'].field_name
                value_mapping = self._get_value_mapping(y_axis_column)
                aggregate_type = y_axis_column.get('aggregate_type')
                
                y_values = []
                for x_val in all_x_values:
                    for time_val in time_groups.groups.keys():
                        if str(time_val) not in selected_groups:
                            continue
                        
                        period_data = time_groups.get_group(time_val)
                        # Filter data for current x value
                        x_filtered_data = period_data[period_data[x_field] == x_val]
                        value = self._apply_aggregation(x_filtered_data, field_name, aggregate_type)
                        y_values.append(value)
                
                self.add_series_to_chart(
                    chart=chart,
                    series_name=metric_name,
                    y_values=y_values,
                    color=y_axis_column.get('color'),
                    value_mapping=value_mapping
                )

    def _handle_regular_data(self, chart: Chart, filtered_data: pd.DataFrame) -> None:
        """Handle non-time-based data."""
        # Get x-axis field name
        x_field = self.options['x_axis_column'].field_name
        x_axis_data = filtered_data[x_field].tolist()

        # Add x-axis data
        chart.add_xaxis(x_axis_data)

        # Get y-axis columns configuration
        y_axis_columns = self._get_y_axis_columns()

        # Add series for each y-axis column
        for y_axis_column in y_axis_columns:
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

    def configure_chart(self, chart: Chart, filtered_data: pd.DataFrame) -> None:
        """
        Configure chart with specific options.
        Override in subclasses for specific chart types.
        """
        if filtered_data is None:
            return
            
        # Handle time-based data if time column is specified
        time_column = self.options.get('time_column')
        if time_column:
            self._handle_time_based_data(chart, filtered_data, time_column)
        else:
            self._handle_regular_data(chart, filtered_data)

    def _apply_aggregation(self, data: pd.DataFrame, field_name: str, aggregate_type: str) -> float:
        """Helper method to apply aggregation on data"""
        try:
            # Try different field name formats
            field_variants = [
                field_name,
                field_name.replace('-', '_'),
                field_name.replace('_', '-'),
                field_name.lower(),
                field_name.upper()
            ]
            
            # Find the correct field name variant
            actual_field = None
            for variant in field_variants:
                if variant in data.columns:
                    actual_field = variant
                    break
            
            if actual_field is None:
                return 0.0

            if aggregate_type and aggregate_type != 'none':
                if aggregate_type == 'SUM':
                    value = data[actual_field].astype(float).sum()
                elif aggregate_type == 'AVERAGE':
                    value = data[actual_field].astype(float).mean()
                elif aggregate_type == 'COUNT':
                    value = data[actual_field].count()
                else:
                    # Default to first value if unknown aggregation type
                    value = float(data[actual_field].iloc[0])
            else:
                # If no aggregation specified, take the first value
                value = float(data[actual_field].iloc[0])
            
            return 0.0 if pd.isna(value) else float(value)
        except Exception as e:
            print(f"Error in aggregation: {e}")
            return 0.0

    def _get_y_axis_columns(self) -> list:
        """Get y-axis columns configuration."""
        y_axis_columns = self.options['y_axis_column']
        return y_axis_columns if isinstance(y_axis_columns, list) else [y_axis_columns]

    def _get_series_name(self, y_axis_column: dict) -> str:
        """Get series name from y-axis column configuration."""
        if isinstance(y_axis_column, dict):
            return (y_axis_column.get('label') or 
                   y_axis_column['field'].field_name)
        return y_axis_column.field_name

    def _get_value_mapping(self, y_axis_column: dict) -> dict:
        """Get value mapping from y-axis column configuration."""
        return y_axis_column.get('value_mapping', {}) if isinstance(y_axis_column, dict) else {}

    def create_chart(self) -> Chart:
        """
        Create a chart with the given data and options.
        """
        try:
            # Filter and validate data
            filtered_data = self.filter_data()
            if filtered_data is None or filtered_data.empty:
                print("No data to display after filtering")
                return None

            # Initialize the chart
            chart = self.initialize_chart(filtered_data)

            # Configure chart with data
            self.configure_chart(chart, filtered_data)

            return chart

        except Exception as e:
            print("Error while creating chart", e)
            import traceback
            traceback.print_exc()
            return None
