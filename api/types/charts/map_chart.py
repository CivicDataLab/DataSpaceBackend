import pandas as pd
from pyecharts.charts.chart import Chart

from api.types.charts.base_chart import BaseChart
from api.types.charts.chart_registry import register_chart
from api.types.charts.chart_utils import _get_map_chart
from api.utils.enums import AggregateType


class MapChart(BaseChart):
    def create_chart(self) -> Chart | None:
        if not self.chart_details.region_column or not self.chart_details.value_column:
            return None
        try:
            region_values = self.process_data()
            return _get_map_chart(self.chart_details, self.data, region_values)
        except Exception as e:
            print("Error while creating chart", e)
            return None

    def aggregate_data(self) -> pd.DataFrame:
        """
        Aggregate data based on region and value columns and return the resulting DataFrame.
        """
        if self.chart_details.aggregate_type != AggregateType.NONE:
            metrics = self.data.groupby(self.chart_details.region_column.field_name).agg(
                {self.chart_details.value_column.field_name: self.chart_details.aggregate_type.lower()}
            ).reset_index()

            metrics.columns = [self.chart_details.region_column.field_name, self.chart_details.value_column.field_name]
            return metrics
        else:
            return self.data[[self.chart_details.region_column.field_name, self.chart_details.value_column.field_name]]

    def process_data(self) -> list:
        data = self.aggregate_data()
        region_col = self.chart_details.region_column.field_name
        value_col = self.chart_details.value_column.field_name
        data[region_col] = data[region_col].str.upper()
        return data[[region_col, value_col]].values.tolist()


@register_chart('ASSAM_DISTRICT')
class AssamDistrictChart(MapChart):
    pass


@register_chart('ASSAM_RC')
class AssamRCChart(MapChart):
    pass
