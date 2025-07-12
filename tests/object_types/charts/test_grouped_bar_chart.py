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


class TestGroupedBarChart(unittest.TestCase):
    def setUp(self):
        """Set up test fixtures."""
        # Sample data for testing
        self.test_data = pd.DataFrame(
            {
                "category": ["A", "A", "B", "B", "C", "C"],
                "group": ["G1", "G2", "G1", "G2", "G1", "G2"],
                "value": [10, 15, 20, 25, 30, 35],
                "time": [
                    "2023-01",
                    "2023-01",
                    "2023-02",
                    "2023-02",
                    "2023-03",
                    "2023-03",
                ],
            }
        )

        # Mock field objects
        self.x_field = MagicMock()
        self.x_field.field_name = "category"

        self.y_field = MagicMock()
        self.y_field.field_name = "value"

        self.group_field = MagicMock()
        self.group_field.field_name = "group"

        self.time_field = MagicMock()
        self.time_field.field_name = "time"

    def test_vertical_grouped_bar_chart(self):
        """Test vertical grouped bar chart creation."""
        options = {
            "x_axis_column": self.x_field,
            "y_axis_column": {"field": self.y_field, "label": "Value"},
            "group_column": self.group_field,
        }
        chart_details = MockResourceChartDetails(
            chart_type="BAR",
            options={**options, "allow_multi_series": true},
            options=options,
        )
        chart = UnifiedChart(chart_details, self.test_data)
        result = chart.create_chart()

        self.assertIsNotNone(result)
        self.assertEqual(len(result.options.get("series")), 2)  # Two groups
        self.assertEqual(result.options.get("xAxis")[0]["type"], "category")
        self.assertEqual(result.options.get("yAxis")[0]["type"], "value")

    def test_horizontal_grouped_bar_chart(self):
        """Test horizontal grouped bar chart creation."""
        options = {
            "x_axis_column": self.x_field,
            "y_axis_column": {"field": self.y_field, "label": "Value"},
            "group_column": self.group_field,
        }
        chart_details = MockResourceChartDetails(
            chart_type="GROUPED_BAR_HORIZONTAL", options=options
        )
        chart = UnifiedChart(chart_details, self.test_data)
        result = chart.create_chart()

        self.assertIsNotNone(result)
        self.assertEqual(len(result.options.get("series")), 2)  # Two groups
        self.assertEqual(result.options.get("xAxis")[0]["type"], "value")
        self.assertEqual(result.options.get("yAxis")[0]["type"], "category")

    def test_styling_options(self):
        """Test styling options for grouped bar chart."""
        options = {
            "x_axis_column": self.x_field,
            "y_axis_column": {"field": self.y_field, "label": "Value"},
            "group_column": self.group_field,
            "colors": ["#FF0000", "#00FF00"],
        }
        chart_details = MockResourceChartDetails(
            chart_type="BAR",
            options={**options, "allow_multi_series": true},
            options=options,
        )
        chart = UnifiedChart(chart_details, self.test_data)
        result = chart.create_chart()

        series = result.options.get("series")
        self.assertEqual(series[0].get("itemStyle").get("color"), "#FF0000")
        self.assertEqual(series[1].get("itemStyle").get("color"), "#00FF00")

    def test_value_aggregation(self):
        """Test value aggregation in grouped bar chart."""
        # Create test data with duplicate categories and groups
        test_data = pd.DataFrame(
            {
                "category": ["A", "A", "B", "B"],
                "group": ["G1", "G1", "G2", "G2"],
                "value": [10, 20, 30, 40],
            }
        )

        options = {
            "x_axis_column": self.x_field,
            "y_axis_column": {
                "field": self.y_field,
                "label": "Value",
                "aggregate_type": "AVERAGE",
            },
            "group_column": self.group_field,
        }
        chart_details = MockResourceChartDetails(
            chart_type="BAR",
            options={**options, "allow_multi_series": true},
            options=options,
        )
        chart = UnifiedChart(chart_details, test_data)
        result = chart.create_chart()

        series = result.options.get("series")
        # Check average values
        self.assertEqual(series[0].get("data")[0], 15.0)  # (10 + 20) / 2
        self.assertEqual(series[1].get("data")[0], 35.0)  # (30 + 40) / 2

    def test_time_based_grouped_bar_chart(self):
        """Test time-based grouped bar chart."""
        options = {
            "x_axis_column": self.time_field,
            "y_axis_column": {"field": self.y_field, "label": "Value"},
            "group_column": self.group_field,
        }
        chart_details = MockResourceChartDetails(
            chart_type="BAR",
            options={**options, "allow_multi_series": true},
            options=options,
        )
        chart = UnifiedChart(chart_details, self.test_data)
        result = chart.create_chart()

        x_axis = result.options.get("xAxis")[0]
        self.assertEqual(len(x_axis.get("data")), 3)  # Three unique time periods
        self.assertTrue(
            all(
                period in x_axis.get("data")
                for period in ["2023-01", "2023-02", "2023-03"]
            )
        )

    def test_value_mapping(self):
        """Test value mapping in grouped bar chart."""
        # Create test data with string values that need mapping
        test_data = pd.DataFrame(
            {"category": ["A", "B"], "group": ["G1", "G2"], "value": ["High", "Low"]}
        )

        value_map = {"High": 100, "Low": 50}
        options = {
            "x_axis_column": self.x_field,
            "y_axis_column": {
                "field": self.y_field,
                "label": "Value",
                "value_map": value_map,
            },
            "group_column": self.group_field,
        }
        chart_details = MockResourceChartDetails(
            chart_type="BAR",
            options={**options, "allow_multi_series": true},
            options=options,
        )
        chart = UnifiedChart(chart_details, test_data)
        result = chart.create_chart()

        series = result.options.get("series")
        self.assertEqual(series[0].get("data")[0], 100)  # 'High' mapped to 100
        self.assertEqual(series[1].get("data")[0], 50)  # 'Low' mapped to 50


if __name__ == "__main__":
    unittest.main()
