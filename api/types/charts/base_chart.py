from abc import ABC, abstractmethod

import pandas as pd
from pyecharts.charts import Line, Bar, Map
from pyecharts.charts.chart import Chart

from api.models import ResourceChartDetails

CHART_TYPE_MAP = {
    "BAR_VERTICAL": Bar,
    "BAR_HORIZONTAL": Bar,
    "GROUPED_BAR_VERTICAL": Bar,
    "GROUPED_BAR_HORIZONTAL": Bar,
    "LINE": Line,
    "ASSAM_DISTRICT": Map,
    "ASSAM_RC": Map
}


class BaseChart(ABC):
    def __init__(self, chart_details: ResourceChartDetails, data: pd.DataFrame):
        self.chart_details = chart_details
        self.data = data

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
        if not self.chart_details.filters:
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
