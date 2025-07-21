# Enhanced Map Charts Documentation

This document provides comprehensive information about the enhanced map chart types available in the DataExchange backend.

## Overview

The enhanced map chart system supports four types of map visualizations:

1. **POLYGON_MAP** - Renders polygon data with configurable styling
2. **POINT_MAP** - Renders points using latitude/longitude coordinates
3. **GEOSPATIAL_MAP** - Renders geospatial files (GeoJSON, TopoJSON)
4. **ASSAM_DISTRICT** & **ASSAM_RC** - Legacy Assam-specific maps (existing)

## Chart Types

### 1. Polygon Map Chart (`POLYGON_MAP`)

Renders polygon data from database fields containing GeoJSON geometry.

**Required Options:**
- `polygon_field`: Field containing polygon geometry data

**Optional Options:**
- `value_column`: Field containing values for color-coding polygons
- `base_map`: Base map to use (default: "world")
- `title`: Chart title
- `width`, `height`: Chart dimensions

**Example Configuration:**
```python
{
    "chart_type": "POLYGON_MAP",
    "options": {
        "polygon_field": {"field_name": "district_boundary"},
        "value_column": {"field_name": "population_density"},
        "base_map": "india",
        "title": "Population Density by District",
        "width": "100%",
        "height": "600px"
    }
}
```

**Data Requirements:**
- `polygon_field`: GeoJSON geometry objects or JSON strings
- `value_column`: Numeric values (optional)

### 2. Point Map Chart (`POINT_MAP`)

Renders points on a map using latitude and longitude coordinates.

**Required Options:**
- `lat_field`: Field containing latitude values
- `lng_field`: Field containing longitude values

**Optional Options:**
- `value_column`: Field containing values for point sizing/coloring
- `point_size`: Size of points (default: 10)
- `base_map`: Base map to use (default: "world")

**Example Configuration:**
```python
{
    "chart_type": "POINT_MAP",
    "options": {
        "lat_field": {"field_name": "latitude"},
        "lng_field": {"field_name": "longitude"},
        "value_column": {"field_name": "hospital_capacity"},
        "point_size": 15,
        "base_map": "assam",
        "title": "Hospital Locations"
    }
}
```

**Data Requirements:**
- `lat_field`: Numeric values between -90 and 90
- `lng_field`: Numeric values between -180 and 180
- `value_column`: Numeric values (optional)

### 3. Geospatial Map Chart (`GEOSPATIAL_MAP`)

Renders geospatial files like GeoJSON or TopoJSON.

**Required Options (one of):**
- `geospatial_data`: GeoJSON FeatureCollection object
- `geospatial_file_path`: Path to GeoJSON/TopoJSON file

**Optional Options:**
- `value_column`: Field containing values for color-coding
- `name_field`: Field to match geospatial features with data
- `map_name`: Custom name for the map (default: "custom_map")

**Example Configuration:**
```python
{
    "chart_type": "GEOSPATIAL_MAP",
    "options": {
        "geospatial_file_path": "/path/to/districts.geojson",
        "value_column": {"field_name": "economic_index"},
        "name_field": {"field_name": "district_name"},
        "map_name": "economic_districts",
        "title": "Economic Index by District"
    }
}
```

## Base Map Options

All map charts support configurable base maps:

| Base Map | Description | Center | Zoom |
|----------|-------------|--------|------|
| `world` | World map | [0, 0] | 1 |
| `india` | India country map | [78.96, 20.59] | 1 |
| `assam` | Assam state map | [92.94, 26.20] | 2 |
| `assam_district` | Assam districts | [92.94, 26.20] | 2 |
| `assam_rc` | Assam revenue circles | [92.94, 26.20] | 2 |

## Common Options

All map chart types support these common options:

### Chart Dimensions
- `width`: Chart width (e.g., "100%", "800px")
- `height`: Chart height (e.g., "600px", "100vh")

### Map Interaction
- `roam`: Enable pan and zoom (default: true)
- `zoom`: Initial zoom level (default: 1)
- `center`: Initial center [longitude, latitude]

### Display Options
- `title`: Chart title
- `show_legend`: Show/hide legend (default: true)
- `show_toolbox`: Show/hide toolbox (default: true)
- `series_name`: Name for the data series

## Usage Examples

### Creating a Polygon Map

```python
from api.types.charts.enhanced_map_chart import PolygonMapChart

# Chart configuration
chart_config = {
    "chart_type": "POLYGON_MAP",
    "options": {
        "polygon_field": {"field_name": "geometry"},
        "value_column": {"field_name": "population"},
        "base_map": "india",
        "title": "Population by District"
    }
}

# Create chart instance
chart = PolygonMapChart(chart_details)
rendered_chart = chart.create_chart()
```

### Creating a Point Map

```python
from api.types.charts.enhanced_map_chart import PointMapChart

# Chart configuration
chart_config = {
    "chart_type": "POINT_MAP",
    "options": {
        "lat_field": {"field_name": "lat"},
        "lng_field": {"field_name": "lng"},
        "value_column": {"field_name": "capacity"},
        "point_size": 12,
        "base_map": "assam"
    }
}

# Create chart instance
chart = PointMapChart(chart_details)
rendered_chart = chart.create_chart()
```

### Creating a Geospatial Map

```python
from api.types.charts.enhanced_map_chart import GeospatialMapChart

# Load geospatial data from resource file field
chart_config = {
    "chart_type": "GEOSPATIAL_MAP",
    "options": {
        "geospatial_field": {"field_name": "boundary_geojson"},  # Field containing GeoJSON data
        "value_column": {"field_name": "metric_value"},
        "name_field": {"field_name": "district_name"},
        "base_map": "india",
        "title": "District Metrics",
        "series_name": "District Data"
    }
}

# Create chart instance
chart = GeospatialMapChart(chart_details)
rendered_chart = chart.create_chart()
```

## Data Format Requirements

### Polygon Data Format
Polygon fields should contain GeoJSON geometry objects:
```json
{
    "type": "Polygon",
    "coordinates": [[[lng1, lat1], [lng2, lat2], [lng3, lat3], [lng1, lat1]]]
}
```

### Point Data Format
Latitude and longitude should be numeric values:
- Latitude: -90 to 90
- Longitude: -180 to 180

### GeoJSON Format
Geospatial data should follow the GeoJSON specification:
```json
{
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "properties": {"name": "Feature Name"},
            "geometry": {
                "type": "Polygon",
                "coordinates": [...]
            }
        }
    ]
}
```

## Error Handling

The enhanced map charts include comprehensive error handling:

- **Missing required fields**: Charts return `None` with error logging
- **Invalid coordinates**: Points outside valid ranges are filtered out
- **Invalid GeoJSON**: Malformed geospatial data is handled gracefully
- **File not found**: Missing geospatial files are handled with error messages

## Performance Considerations

- **Large datasets**: Point maps automatically filter invalid coordinates
- **Complex polygons**: Polygon rendering performance depends on geometry complexity
- **File loading**: Geospatial files are loaded synchronously; consider file size
- **Memory usage**: Large GeoJSON files may impact memory usage

## Integration with Existing System

The enhanced map charts integrate seamlessly with the existing chart system:

1. **Registry**: All new chart types are registered automatically
2. **Base class**: Inherit from `BaseChart` for common functionality
3. **Options**: Follow the same options pattern as existing charts
4. **Data loading**: Use the same data loading mechanisms

## Troubleshooting

### Common Issues

1. **Chart not rendering**: Check that required fields are present in options
2. **Points not showing**: Verify lat/lng values are within valid ranges
3. **Polygons not displaying**: Ensure polygon data is valid GeoJSON
4. **File not loading**: Check file path and permissions for geospatial files

### Debug Tips

- Enable debug logging to see detailed error messages
- Validate GeoJSON data using online validators
- Check coordinate reference systems (CRS) for geospatial data
- Verify field names match exactly with database columns

## Future Enhancements

Potential future improvements:

1. **Clustering**: Point clustering for large datasets
2. **Heatmaps**: Heat map overlays for point data
3. **Animation**: Time-based animations for temporal data
4. **Custom styling**: More granular styling options
5. **Projection support**: Different map projections
6. **Tile layers**: Custom tile layer support
