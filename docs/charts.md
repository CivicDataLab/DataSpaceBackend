# Charts Module Documentation

## Overview

The charts module provides a unified approach to creating and configuring various chart types in the DataExchange backend. The primary class is `UnifiedChart`, which handles multiple chart types including bar charts, line charts, and their variants.

## Key Components

### UnifiedChart

`UnifiedChart` is a versatile chart class that supports:
- Single bar charts (vertical/horizontal)
- Grouped bar charts (vertical/horizontal)
- Line charts (single/multi-series)

The behavior of the chart is determined by the `chart_type` and options like `orientation`, `allow_multi_series`, and `stacked`.

### Chart Types

The following chart types are supported:
- `BAR`: Standard bar chart (supports vertical/horizontal orientation and grouped/stacked options)
- `LINE`: Line chart (supports single and multi-series)
- `BIG_NUMBER`: Displays a single metric value prominently with optional title, subtitle, and trend indicator
- `TREEMAP`: Hierarchical visualization where rectangles represent data values
- `ASSAM_DISTRICT` and `ASSAM_RC`: Map charts for visualizing geographical data

## Usage Examples

### Creating a Bar Chart

```python
from api.types.charts.unified_chart import UnifiedChart
from api.utils.enums import ChartTypes

# Assuming chart_details is a ResourceChartDetails instance with chart_type="BAR"
# and data is a pandas DataFrame
chart = UnifiedChart(chart_details, data)
result = chart.create_chart()
```

### Creating a Line Chart

```python
from api.types.charts.unified_chart import UnifiedChart
from api.utils.enums import ChartTypes

# Assuming chart_details is a ResourceChartDetails instance with chart_type="LINE"
# and data is a pandas DataFrame
chart = UnifiedChart(chart_details, data)
result = chart.create_chart()
```

### Creating a Big Number Chart

```python
from api.types.charts.big_number_chart import BigNumberChart
from api.utils.enums import ChartTypes

# Assuming chart_details is a ResourceChartDetails instance with chart_type="BIG_NUMBER"
# and data is a pandas DataFrame
chart_details.options = {
    "y_axis_column": {"field": field_object, "label": "Value"},
    "title": "Total Revenue",
    "subtitle": "Year to Date",
    "value_prefix": "$",
    "value_font_size": 42
}
chart = BigNumberChart(chart_details, data)
result = chart.create_chart()
```

### Creating a TreeMap Chart

```python
from api.types.charts.treemap_chart import TreeMapChart
from api.utils.enums import ChartTypes

# Assuming chart_details is a ResourceChartDetails instance with chart_type="TREEMAP"
# and data is a pandas DataFrame
chart_details.options = {
    "x_axis_column": category_field,
    "y_axis_column": {"field": value_field, "label": "Value"},
    "title": "Budget Allocation"
}
chart = TreeMapChart(chart_details, data)
result = chart.create_chart()
```

### Creating a Map Chart

```python
from api.types.charts.map_chart import MapChart
from api.utils.enums import ChartTypes

# Assuming chart_details is a ResourceChartDetails instance with chart_type="ASSAM_DISTRICT"
# and data is a pandas DataFrame with region and value columns
chart_details.options = {
    "region_column": region_field,
    "value_column": value_field,
    "title": "Population by District"
}
chart = MapChart(chart_details, data)
result = chart.create_chart()
```

### Converting Between Chart Types

```python
from api.types.charts.unified_chart import UnifiedChart

# Create a bar chart first
chart = UnifiedChart(chart_details, data)
bar_result = chart.create_chart()

# Convert to line chart
line_result = chart.convert_to_line()
```

## Configuration Options

### Common Options

- `x_axis_column`: Field object for the x-axis
- `y_axis_column`: List of field objects for the y-axis
- `width`: Chart width (default: "100%")
- `height`: Chart height (default: "400px")
- `theme`: Chart theme (default: "white")

### Bar Chart Specific Options

- `orientation`: "vertical" or "horizontal"
- `stacked`: Boolean to enable stacked bars
- `allow_multi_series`: Boolean to allow multiple series

### Line Chart Specific Options

- `is_smooth`: Boolean to enable smooth lines (default: true)
- `symbol`: Symbol type for data points (default: "emptyCircle")
- `symbol_size`: Size of data point symbols (default: 8)

### Big Number Chart Specific Options

- `title`: Title text displayed above the value
- `subtitle`: Subtitle text displayed below the title
- `label`: Label text displayed below the value
- `value_prefix`: Text to display before the value (e.g., "$")
- `value_suffix`: Text to display after the value (e.g., "%")
- `value_font_size`: Font size for the main value (default: 36)
- `title_font_size`: Font size for the title (default: 16)
- `subtitle_font_size`: Font size for the subtitle (default: 12)
- `label_font_size`: Font size for the label (default: 14)
- `value_color`: Color for the main value (default: "#000000")
- `title_color`: Color for the title (default: "#333333")
- `subtitle_color`: Color for the subtitle (default: "#666666")
- `label_color`: Color for the label (default: "#666666")
- `background_color`: Background color for the chart (default: "transparent")

### TreeMap Chart Specific Options

- `x_axis_column`: Field object for the category (rectangle names)
- `y_axis_column`: Field object for the values (rectangle sizes)
- `title`: Title for the TreeMap

### Map Chart Specific Options

- `region_column`: Field object for the region names
- `value_column`: Field object for the values to display on the map
- `title`: Title for the map

## Responsive Design

The `UnifiedChart` class includes responsive options that adapt to different container sizes:

```python
# Example of responsive options
responsive_opts = chart.get_responsive_options()
```

## Validation

The `UnifiedChart` class includes validation to ensure that chart options are properly configured:

```python
# Example of validation
errors = chart.validate_options()
```
