import pandas as pd
from pyecharts.charts.chart import Chart

from api.types.charts.base_chart import BaseChart
from api.types.charts.chart_registry import register_chart
from api.types.charts.chart_utils import _get_map_chart
from api.utils.enums import AggregateType


class MapChart(BaseChart):
    def create_chart(self) -> Chart | None:
        if 'region_column' not in self.options or 'value_column' not in self.options:
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
        region_column = self.options['region_column']
        value_column = self.options['value_column']
        aggregate_type = self.options.get('aggregate_type', 'none')

        if aggregate_type != 'none':
            metrics = self.data.groupby(region_column.field_name).agg(
                {value_column.field_name: aggregate_type.lower()}
            ).reset_index()

            metrics.columns = [region_column.field_name, value_column.field_name]
            return metrics
        else:
            return self.data[[region_column.field_name, value_column.field_name]]

    def process_data(self) -> list:
        data = self.aggregate_data()
        region_column = self.options['region_column']
        value_column = self.options['value_column']
        region_col = region_column.field_name
        value_col = value_column.field_name
        data[region_col] = data[region_col].str.upper()
        return data[[region_col, value_col]].values.tolist()


@register_chart('ASSAM_DISTRICT')
class AssamDistrictChart(MapChart):
    pass


@register_chart('ASSAM_RC')
class AssamRCChart(MapChart):
    pass
