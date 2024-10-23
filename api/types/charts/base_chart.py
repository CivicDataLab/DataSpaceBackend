from abc import ABC, abstractmethod

import pandas as pd
from pyecharts.charts import Line, Bar, Map
from pyecharts.charts.chart import Chart

from api.models import ResourceChartDetails

CHART_TYPE_MAP = {
    "BAR_VERTICAL": Bar,
    "BAR_HORIZONTAL": Bar,
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
