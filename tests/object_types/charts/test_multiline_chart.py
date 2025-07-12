import unittest
from unittest.mock import MagicMock

import pandas as pd

from api.types.charts.unified_chart import UnifiedChart


class MockResourceChartDetails:
    """Mock class for ResourceChartDetails to avoid Django dependency"""

    def __init__(
        self,
        chart_type="MULTILINE",
        title="Test Chart",
        description="Test Description",
        options=None,
    ):
        self.chart_type = chart_type
        self.title = title
        self.description = description
        self.options = options or {}
        self.filters = []


class TestMultiLineChart(unittest.TestCase):
    def setUp(self):
        """Set up test fixtures."""
        # Sample data for testing
        self.test_data = pd.DataFrame(
            {
                "date": ["2023-01", "2023-02", "2023-03", "2023-04"],
                "metric1": [10, 20, 15, 25],
                "metric2": [5, 15, 10, 20],
                "category": ["A", "A", "B", "B"],
            }
        )

        # Mock field objects
        self.x_field = MagicMock()
        self.x_field.field_name = "date"

        self.y_field1 = MagicMock()
        self.y_field1.field_name = "metric1"

        self.y_field2 = MagicMock()
        self.y_field2.field_name = "metric2"

        self.category_field = MagicMock()
        self.category_field.field_name = "category"

    def test_line_chart_creation(self):
        """Test basic line chart creation."""
        options = {
            "x_axis_column": self.x_field,
            "y_axis_column": [
                {"field": self.y_field1, "label": "Metric 1"},
                {"field": self.y_field2, "label": "Metric 2"},
            ],
        }
        chart_details = MockResourceChartDetails(options=options)
        chart = UnifiedChart(chart_details, self.test_data)
        result = chart.create_chart()

        self.assertIsNotNone(result)
        self.assertEqual(len(result.options.get("series")), 2)
        # Check if it's using Line chart specific options
        self.assertTrue(result.options.get("series")[0].get("smooth"))
        self.assertTrue(result.options.get("series")[0].get("symbol"))

    def test_line_styling(self):
        """Test line chart styling options."""
        options = {
            "x_axis_column": self.x_field,
            "y_axis_column": [
                {"field": self.y_field1, "label": "Metric 1", "color": "#FF0000"},
                {"field": self.y_field2, "label": "Metric 2", "color": "#00FF00"},
            ],
        }
        chart_details = MockResourceChartDetails(options=options)
        chart = UnifiedChart(chart_details, self.test_data)
        result = chart.create_chart()

        series = result.options.get("series")
        # Check line styles
        self.assertEqual(series[0].get("itemStyle").get("color"), "#FF0000")
        self.assertEqual(series[1].get("itemStyle").get("color"), "#00FF00")

        # Check line specific options
        self.assertEqual(series[0].get("symbol"), "emptyCircle")
        self.assertEqual(series[0].get("symbolSize"), 8)
        self.assertTrue(series[0].get("smooth"))

    def test_data_zoom(self):
        """Test data zoom functionality."""
        options = {
            "x_axis_column": self.x_field,
            "y_axis_column": [{"field": self.y_field1, "label": "Metric 1"}],
        }
        chart_details = MockResourceChartDetails(options=options)
        chart = UnifiedChart(chart_details, self.test_data)
        result = chart.create_chart()

        # Check data zoom options
        datazoom = result.options.get("dataZoom")
        self.assertIsNotNone(datazoom)
        self.assertEqual(len(datazoom), 2)  # Should have both slider and inside zoom
        self.assertEqual(datazoom[0].get("type"), "slider")
        self.assertEqual(datazoom[1].get("type"), "inside")

    def test_time_based_data(self):
        """Test handling of time-based data."""
        options = {
            "x_axis_column": self.x_field,
            "y_axis_column": [{"field": self.y_field1, "label": "Metric 1"}],
            "time_column": self.x_field,
        }
        chart_details = MockResourceChartDetails(options=options)
        chart = UnifiedChart(chart_details, self.test_data)
        result = chart.create_chart()

        # Check x-axis data
        x_axis_data = result.options.get("xAxis")[0].get("data")
        self.assertEqual(len(x_axis_data), 4)  # Should have all time periods
        self.assertTrue(
            all(
                period in x_axis_data
                for period in ["2023-01", "2023-02", "2023-03", "2023-04"]
            )
        )

    def test_value_aggregation(self):
        """Test value aggregation in line chart."""
        # Create test data with duplicate dates
        test_data = pd.DataFrame(
            {
                "date": ["2023-01", "2023-01", "2023-02", "2023-02"],
                "metric1": [10, 20, 15, 25],
                "category": ["A", "B", "A", "B"],
            }
        )

        options = {
            "x_axis_column": self.x_field,
            "y_axis_column": [
                {
                    "field": self.y_field1,
                    "label": "Metric 1",
                    "aggregate_type": "AVERAGE",
                }
            ],
        }
        chart_details = MockResourceChartDetails(options=options)
        chart = UnifiedChart(chart_details, test_data)
        result = chart.create_chart()

        series = result.options.get("series")[0]
        values = [item.get("value") for item in series.get("data")]
        # Check average values
        self.assertEqual(values[0], 15.0)  # (10 + 20) / 2
        self.assertEqual(values[1], 20.0)  # (15 + 25) / 2

    def test_tooltip_configuration(self):
        """Test tooltip configuration."""
        options = {
            "x_axis_column": self.x_field,
            "y_axis_column": [
                {"field": self.y_field1, "label": "Metric 1"},
                {"field": self.y_field2, "label": "Metric 2"},
            ],
        }
        chart_details = MockResourceChartDetails(options=options)
        chart = UnifiedChart(chart_details, self.test_data)
        result = chart.create_chart()

        tooltip = result.options.get("tooltip")
        self.assertEqual(tooltip.get("trigger"), "axis")
        self.assertEqual(tooltip.get("axisPointer").get("type"), "cross")


if __name__ == "__main__":
    unittest.main()
