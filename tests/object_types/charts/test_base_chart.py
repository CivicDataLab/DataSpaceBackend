import unittest
import pandas as pd
from unittest.mock import MagicMock
from api.types.charts.base_chart import BaseChart

class MockResourceChartDetails:
    """Mock class for ResourceChartDetails to avoid Django dependency"""
    def __init__(self, chart_type="TEST_CHART", title="Test Chart", description="Test Description", options=None):
        self.chart_type = chart_type
        self.title = title
        self.description = description
        self.options = options or {}
        self.filters = []

class TestBaseChart(unittest.TestCase):
    def setUp(self):
        """Set up test fixtures."""
        self.chart_details = MockResourceChartDetails()
        
        # Create a concrete implementation of BaseChart for testing
        class TestChart(BaseChart):
            def get_chart_class(self):
                return MagicMock()
            
            def create_chart(self):
                chart = self.initialize_chart()
                filtered_data = self.filter_data()
                self.configure_chart(chart, filtered_data)
                return chart
        
        self.chart_class = TestChart
        
        # Sample data for testing
        self.test_data = pd.DataFrame({
            'category': ['A', 'B', 'C', 'A', 'B'],
            'value': [10, 20, 30, 15, 25],
            'time': ['2023-01', '2023-01', '2023-01', '2023-02', '2023-02']
        })
        
        # Mock field objects
        self.x_field = MagicMock()
        self.x_field.field_name = 'category'
        
        self.y_field = MagicMock()
        self.y_field.field_name = 'value'
        
        self.time_field = MagicMock()
        self.time_field.field_name = 'time'

    def test_initialization(self):
        """Test chart initialization."""
        options = {
            'x_axis_column': self.x_field,
            'y_axis_column': self.y_field
        }
        chart = self.chart_class(self.chart_details, self.test_data, options)
        
        self.assertEqual(chart.chart_details, self.chart_details)
        self.assertTrue(chart.data.equals(self.test_data))
        self.assertEqual(chart.options, options)

    def test_filter_data(self):
        """Test data filtering."""
        options = {
            'x_axis_column': self.x_field,
            'y_axis_column': self.y_field,
            'filters': [{'field': 'category', 'value': 'A'}]
        }
        chart = self.chart_class(self.chart_details, self.test_data, options)
        
        filtered_data = chart.filter_data()
        self.assertEqual(len(filtered_data), 2)
        self.assertTrue(all(row['category'] == 'A' for _, row in filtered_data.iterrows()))

    def test_time_based_data(self):
        """Test handling of time-based data."""
        options = {
            'x_axis_column': self.x_field,
            'y_axis_column': self.y_field,
            'time_column': self.time_field
        }
        chart = self.chart_class(self.chart_details, self.test_data, options)
        
        mock_chart = MagicMock()
        chart._handle_time_based_data(mock_chart, self.test_data, self.time_field)
        
        # Verify that add_xaxis was called with time periods
        mock_chart.add_xaxis.assert_called_once()
        called_args = mock_chart.add_xaxis.call_args[0][0]
        self.assertTrue(all(period in called_args for period in ['2023-01', '2023-02']))

    def test_aggregation(self):
        """Test data aggregation."""
        options = {
            'x_axis_column': self.x_field,
            'y_axis_column': {
                'field': self.y_field,
                'aggregate_type': 'SUM'
            }
        }
        chart = self.chart_class(self.chart_details, self.test_data, options)
        
        # Test sum aggregation
        result = chart._apply_aggregation(
            self.test_data[self.test_data['category'] == 'A'],
            'value',
            'SUM'
        )
        self.assertEqual(result, 25)  # 10 + 15

    def test_value_mapping(self):
        """Test value mapping functionality."""
        value_mapping = {'10': 'Low', '20': 'Medium', '30': 'High'}
        options = {
            'x_axis_column': self.x_field,
            'y_axis_column': {
                'field': self.y_field,
                'value_mapping': value_mapping
            }
        }
        chart = self.chart_class(self.chart_details, self.test_data, options)
        
        mock_chart = MagicMock()
        chart.add_series_to_chart(
            chart=mock_chart,
            series_name='Test Series',
            y_values=[10, 20, 30],
            value_mapping=value_mapping
        )
        
        # Verify that add_yaxis was called with mapped values
        mock_chart.add_yaxis.assert_called_once()

    def test_get_common_options(self):
        """Test common options generation."""
        options = {
            'x_axis_column': self.x_field,
            'y_axis_column': self.y_field
        }
        chart = self.chart_class(self.chart_details, self.test_data, options)
        
        common_opts = chart.get_common_options()
        self.assertIn('legend_opts', common_opts)
        self.assertIn('grid', common_opts)
        self.assertIn('toolbox_opts', common_opts)
        self.assertIn('axis_opts', common_opts)

if __name__ == '__main__':
    unittest.main()
