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

    def filter_data(self) -> pd.DataFrame:
        """
        Filter the data based on the chart_details filters.
        """
        filtered_data = self.data

        if self.chart_details.filters:
            conditions = []
            for filter_condition in self.chart_details.filters:
                column = filter_condition['column'].field_name
                operator = filter_condition['operator']
                value = filter_condition['value']

                if operator == '==':
                    conditions.append(filtered_data[column] == value)
                elif operator == '!=':
                    conditions.append(filtered_data[column] != value)
                elif operator == '>':
                    conditions.append(filtered_data[column] > value)
                elif operator == '<':
                    conditions.append(filtered_data[column] < value)
                elif operator == '>=':
                    conditions.append(filtered_data[column] >= value)
                elif operator == '<=':
                    conditions.append(filtered_data[column] <= value)
                elif operator == 'in':
                    conditions.append(filtered_data[column].isin(value))
                elif operator == 'not in':
                    conditions.append(~filtered_data[column].isin(value))

            combined_condition = conditions[0]
            for condition in conditions[1:]:
                combined_condition &= condition

            filtered_data = filtered_data[combined_condition]

        return filtered_data
