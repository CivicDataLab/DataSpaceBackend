from pyecharts.charts.chart import Chart

from api.types.charts.base_chart import BaseChart
from api.types.charts.chart_registry import register_chart
from api.types.charts.chart_utils import _get_map_chart


class MapChart(BaseChart):
    def create_chart(self) -> Chart | None:
        if not self.chart_details.region_column or not self.chart_details.value_column:
            return None
        region_col = self.chart_details.region_column.field_name
        value_col = self.chart_details.value_column.field_name
        region_values = self.process_data(region_col, value_col)
        return _get_map_chart(self.chart_details, self.data, region_values, value_col)


@register_chart('ASSAM_DISTRICT')
class AssamDistrictChart(MapChart):
    pass  # No extra logic needed if MapChart handles common behavior


@register_chart('ASSAM_RC')
class AssamRCChart(MapChart):
    pass
