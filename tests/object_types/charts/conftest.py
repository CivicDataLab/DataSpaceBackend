"""
Pytest configuration for chart tests.
"""
import os
import sys
import pytest
import pandas as pd
from unittest.mock import MagicMock

# Add the project root directory to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

# Mock ResourceChartDetails for testing
@pytest.fixture
def mock_chart_details():
    """Create a mock ResourceChartDetails instance."""
    class MockResourceChartDetails:
        def __init__(self, chart_type, title="Test Chart", description="Test Description"):
            self.chart_type = chart_type
            self.title = title
            self.description = description
    return MockResourceChartDetails

@pytest.fixture(autouse=True)
def enable_db_access_for_all_tests(db):
    """
    Enable DB access for all tests.
    This avoids having to use the db fixture explicitly for each test.
    """
    pass

@pytest.fixture
def sample_data():
    """Create sample data for testing."""
    return pd.DataFrame({
        'category': ['A', 'B', 'C', 'A', 'B', 'C'],
        'metric1': [10, 20, 30, 15, 25, 35],
        'metric2': [5, 15, 25, 10, 20, 30],
        'time': ['2023-01', '2023-01', '2023-01', '2023-02', '2023-02', '2023-02']
    })

@pytest.fixture
def mock_fields():
    """Create mock field objects for testing."""
    x_field = MagicMock()
    x_field.field_name = 'category'
    
    y_field1 = MagicMock()
    y_field1.field_name = 'metric1'
    
    y_field2 = MagicMock()
    y_field2.field_name = 'metric2'
    
    time_field = MagicMock()
    time_field.field_name = 'time'
    
    return {
        'x_field': x_field,
        'y_field1': y_field1,
        'y_field2': y_field2,
        'time_field': time_field
    }

@pytest.fixture
def chart_options(mock_fields):
    """Create chart options for testing."""
    return {
        'x_axis_column': mock_fields['x_field'],
        'y_axis_column': [
            {'field': mock_fields['y_field1'], 'label': 'Metric 1'},
            {'field': mock_fields['y_field2'], 'label': 'Metric 2'}
        ],
        'time_column': mock_fields['time_field']
    }
