import unittest
from unittest.mock import MagicMock

import pandas as pd

from api.types.charts.unified_chart import UnifiedChart


class MockResourceChartDetails:
    """Mock class for ResourceChartDetails to avoid Django dependency"""

    def __init__(
        self,
        chart_type="BAR",
        title="Test Chart",
        description="Test Description",
        options=None,
    ):
        self.chart_type = chart_type
        self.title = title
        self.description = description
        self.options = options or {}
        self.filters = []


class TestBarChart(unittest.TestCase):
    def setUp(self):
        """Set up test fixtures."""
        # Sample data for testing
        self.test_data = pd.DataFrame(
            {
                "category": ["A", "B", "C", "A", "B"],
                "value": [10, 20, 30, 15, 25],
                "time": ["2023-01", "2023-01", "2023-01", "2023-02", "2023-02"],
            }
        )

        # Mock field objects
        self.x_field = MagicMock()
        self.x_field.field_name = "category"

        self.y_field = MagicMock()
        self.y_field.field_name = "value"

        self.time_field = MagicMock()
        self.time_field.field_name = "time"

    def test_vertical_bar_chart(self):
        """Test vertical bar chart creation."""
        options = {
            "x_axis_column": self.x_field,
            "y_axis_column": [{"field": self.y_field, "label": "Value"}],
        }
        chart_details = MockResourceChartDetails(chart_type="BAR", options=options)
        chart = UnifiedChart(chart_details, self.test_data)
        result = chart.create_chart()

        self.assertIsNotNone(result)
        self.assertEqual(result.options.get("xAxis")[0]["type"], "category")
        self.assertEqual(result.options.get("yAxis")[0]["type"], "value")

    def test_horizontal_bar_chart(self):
        """Test horizontal bar chart creation."""
        options = {
            "x_axis_column": self.x_field,
            "y_axis_column": [{"field": self.y_field, "label": "Value"}],
        }
        options_with_orientation = {**options, "orientation": "horizontal"}
        chart_details = MockResourceChartDetails(
            chart_type="BAR", options=options_with_orientation
        )
        chart = UnifiedChart(chart_details, self.test_data)
        result = chart.create_chart()

        self.assertIsNotNone(result)
        self.assertEqual(result.options.get("xAxis")[0]["type"], "value")
        self.assertEqual(result.options.get("yAxis")[0]["type"], "category")

    def test_bar_styling(self):
        """Test bar chart styling options."""
        options = {
            "x_axis_column": self.x_field,
            "y_axis_column": [
                {"field": self.y_field, "label": "Value", "color": "#FF0000"}
            ],
        }
        chart_details = MockResourceChartDetails(chart_type="BAR", options=options)
        chart = UnifiedChart(chart_details, self.test_data)
        result = chart.create_chart()

        series = result.options.get("series")[0]
        self.assertEqual(series.get("itemStyle").get("color"), "#FF0000")
        self.assertEqual(series.get("type"), "bar")

    def test_value_aggregation(self):
        """Test value aggregation in bar chart."""
        options = {
            "x_axis_column": self.x_field,
            "y_axis_column": [
                {"field": self.y_field, "label": "Value", "aggregate_type": "SUM"}
            ],
        }
        chart_details = MockResourceChartDetails(chart_type="BAR", options=options)
        chart = UnifiedChart(chart_details, self.test_data)
        result = chart.create_chart()

        series = result.options.get("series")[0]
        data = series.get("data")
        # Check sum aggregation for category A (10 + 15)
        self.assertEqual(data[0].get("value"), 25)

    def test_axis_labels(self):
        """Test axis label configuration."""
        options = {
            "x_axis_column": self.x_field,
            "y_axis_column": [{"field": self.y_field, "label": "Custom Value Label"}],
            "x_axis_label": "Custom Category Label",
        }
        chart_details = MockResourceChartDetails(chart_type="BAR", options=options)
        print(chart_details)
        chart = UnifiedChart(chart_details, self.test_data)
        result = chart.create_chart()

        x_axis = result.options.get("xAxis")[0]
        y_axis = result.options.get("yAxis")[0]
        self.assertEqual(x_axis.get("name"), "Custom Category Label")
        self.assertEqual(y_axis.get("name"), "Custom Value Label")


if __name__ == "__main__":
    unittest.main()
