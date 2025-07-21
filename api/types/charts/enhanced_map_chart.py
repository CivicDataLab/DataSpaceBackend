import json
from typing import Any, Dict, List, Optional, Union, cast

import pandas as pd
import structlog
from pandas import DataFrame
from pyecharts import options as opts
from pyecharts.charts import Geo, Map, Scatter
from pyecharts.charts.chart import Chart

from api.types.charts.base_chart import BaseChart, DjangoFieldLike
from api.types.charts.chart_registry import register_chart

logger = structlog.get_logger(__name__)


class BaseMapChart(BaseChart):
    """Base class for all map chart types with common map functionality."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.base_map_config = self._get_base_map_config()

    def _get_base_map_config(self) -> Dict[str, Any]:
        """Get base map configuration from options."""
        base_map = str(self.options.get("base_map", "world"))

        # Predefined base map configurations
        base_map_configs = {
            "world": {"maptype": "world", "zoom": 1, "center": [0, 0], "roam": True},
            "india": {
                "maptype": "india",
                "zoom": 1,
                "center": [78.9629, 20.5937],
                "roam": True,
            },
            "assam": {
                "maptype": "assam",
                "zoom": 1,
                "center": [92.9376, 26.2006],
                "roam": True,
            },
            "assam_district": {
                "maptype": "assam_district",
                "zoom": 1,
                "center": [92.9376, 26.2006],
                "roam": True,
            },
            "assam_rc": {
                "maptype": "assam_rc",
                "zoom": 1,
                "center": [92.9376, 26.2006],
                "roam": True,
            },
        }

        return base_map_configs.get(base_map, base_map_configs["world"])

    def _get_common_map_options(self) -> Dict[str, Any]:
        """Get common map options for all map types."""
        return {
            "roam": self.options.get("roam", True),
            "zoom": self.options.get("zoom", self.base_map_config.get("zoom", 1)),
            "center": self.options.get("center", self.base_map_config.get("center")),
            "show_legend": self.options.get("show_legend", True),
            "show_toolbox": self.options.get("show_toolbox", True),
        }


@register_chart("POLYGON_MAP")
class PolygonMapChart(BaseMapChart):
    """Map chart that renders polygon data from specified polygon fields."""

    def create_chart(self) -> Optional[Chart]:
        """Create a polygon map chart."""
        if "polygon_field" not in self.options:
            logger.error("polygon_field is required for polygon map charts")
            return None

        try:
            # Get filtered data using the standard BaseChart method
            filtered_data = self._get_data()
            if filtered_data is None or filtered_data.empty:
                logger.warning("No data available for polygon map chart")
                return None

            # Initialize chart
            chart = self.initialize_chart(filtered_data)

            # Configure chart with polygon data
            self.configure_chart(chart, filtered_data)

            return chart

        except Exception as e:
            logger.error(f"Error creating polygon map chart: {e}")
            return None

    def initialize_chart(self, filtered_data: Optional[pd.DataFrame] = None) -> Chart:
        """Initialize a polygon map chart."""
        chart = Geo(
            init_opts=opts.InitOpts(
                width=str(self.options.get("width", "100%")),
                height=str(self.options.get("height", "600px")),
            )
        )

        # Add schema for the base map
        chart.add_schema(
            maptype=self.base_map_config["maptype"],
            roam=self._get_common_map_options()["roam"],
            zoom=self._get_common_map_options()["zoom"],
            center=self._get_common_map_options()["center"],
        )

        return chart

    def configure_chart(
        self, chart: Chart, filtered_data: Optional[pd.DataFrame] = None
    ) -> None:
        """Configure polygon map chart with data and styling."""
        if filtered_data is None or filtered_data.empty:
            return

        # Process polygon data
        processed_data = self._process_polygon_data(filtered_data)

        # Add polygon series to chart
        polygon_data = self._prepare_polygon_data(processed_data)
        if polygon_data:
            chart.add(
                series_name=self.options.get("series_name", "Polygons"),
                data_pair=polygon_data,
                type_="map",
            )

        # Set global options
        self._set_polygon_global_options(chart, processed_data)

    def _process_polygon_data(self, data: DataFrame) -> DataFrame:
        """Process polygon data for rendering."""
        polygon_field = cast(DjangoFieldLike, self.options["polygon_field"])
        polygon_column = polygon_field.field_name

        # Validate polygon field exists
        if polygon_column not in data.columns:
            raise ValueError(f"Polygon field '{polygon_column}' not found in data")

        # Process polygon data - convert to GeoJSON if needed
        processed_data = data.copy()

        # If polygon data is in string format, try to parse as JSON
        if data[polygon_column].dtype == "object":
            try:
                processed_data[polygon_column] = data[polygon_column].apply(
                    lambda x: json.loads(x) if isinstance(x, str) else x
                )
            except (json.JSONDecodeError, TypeError):
                logger.warning(
                    f"Could not parse polygon data as JSON in column '{polygon_column}'"
                )

        return processed_data

    def _prepare_polygon_data(self, data: DataFrame) -> List[List[Any]]:
        """Prepare polygon data for chart rendering."""
        polygon_field = cast(DjangoFieldLike, self.options["polygon_field"])
        polygon_column = polygon_field.field_name

        # Get value column if specified
        value_column = None
        if "value_column" in self.options:
            value_field = cast(DjangoFieldLike, self.options["value_column"])
            value_column = value_field.field_name

        polygon_data = []
        for idx, row in data.iterrows():
            # For polygon maps, we typically need region names and values
            # The polygon geometry itself is handled by the map definition
            region_name = f"region_{idx}"
            if "name_field" in self.options:
                name_field = cast(DjangoFieldLike, self.options["name_field"])
                name_column = name_field.field_name
                if name_column in data.columns:
                    region_name = str(row[name_column])

            value = 0.0
            if value_column and value_column in data.columns:
                try:
                    value = float(row[value_column])
                except (ValueError, TypeError):
                    value = 0.0

            polygon_data.append([region_name, value])

        return polygon_data

    def _set_polygon_global_options(self, chart: Chart, data: DataFrame) -> None:
        """Set global options for polygon chart."""
        common_opts = self._get_common_map_options()

        # Get value column for visual map if available
        value_column = None
        if "value_column" in self.options:
            value_field = cast(DjangoFieldLike, self.options["value_column"])
            value_column = value_field.field_name

        # Calculate min/max for visual map
        visual_map_opts = None
        if value_column and value_column in data.columns:
            try:
                min_val = float(data[value_column].min())
                max_val = float(data[value_column].max())
                visual_map_opts = opts.VisualMapOpts(
                    is_show=True,
                    min_=min_val,
                    max_=max_val,
                    range_color=["#50a3ba", "#eac736", "#d94e5d"],
                    orient="vertical",
                    pos_left="left",
                    pos_top="bottom",
                )
            except (ValueError, TypeError):
                pass

        chart.set_global_opts(
            title_opts=opts.TitleOpts(
                title=self.options.get("title", "Polygon Map"), pos_top="5%"
            ),
            legend_opts=opts.LegendOpts(
                is_show=common_opts["show_legend"],
                pos_top="5%",
                pos_left="center",
                orient="horizontal",
            ),
            toolbox_opts=opts.ToolboxOpts(
                is_show=common_opts["show_toolbox"],
                feature=opts.ToolBoxFeatureOpts(
                    save_as_image=opts.ToolBoxFeatureSaveAsImageOpts(is_show=True),
                    data_view=opts.ToolBoxFeatureDataViewOpts(is_show=True),
                    restore=opts.ToolBoxFeatureRestoreOpts(is_show=True),
                ),
            ),
            visualmap_opts=visual_map_opts,
        )

    def _create_polygon_map(self, data: DataFrame) -> Chart:
        """Create the actual polygon map chart."""
        polygon_field = cast(DjangoFieldLike, self.options["polygon_field"])
        polygon_column = polygon_field.field_name

        # Get value column if specified
        value_column = None
        if "value_column" in self.options:
            value_field = cast(DjangoFieldLike, self.options["value_column"])
            value_column = value_field.field_name

        # Create Geo chart for polygon rendering
        chart = Geo(
            init_opts=opts.InitOpts(
                width=str(self.options.get("width", "100%")),
                height=str(self.options.get("height", "600px")),
            )
        )

        # Prepare data for rendering
        polygon_data = []
        for idx, row in data.iterrows():
            polygon_info = {
                "name": f"polygon_{idx}",
                "geometry": row[polygon_column],
            }
            if value_column and value_column in data.columns:
                polygon_info["value"] = row[value_column]
            polygon_data.append(polygon_info)

        # Add polygon series
        chart.add_schema(
            maptype=self.base_map_config["maptype"],
            roam=self._get_common_map_options()["roam"],
            zoom=self._get_common_map_options()["zoom"],
            center=self._get_common_map_options()["center"],
        )

        # Configure chart options
        self._configure_polygon_chart(chart, polygon_data)

        return chart

    def _configure_polygon_chart(
        self, chart: Chart, polygon_data: List[Dict[str, Any]]
    ) -> None:
        """Configure polygon chart with styling and options."""
        common_opts = self._get_common_map_options()

        chart.set_global_opts(
            title_opts=opts.TitleOpts(
                title=self.options.get("title", "Polygon Map"), pos_top="5%"
            ),
            legend_opts=opts.LegendOpts(
                is_show=common_opts["show_legend"],
                pos_top="5%",
                pos_left="center",
                orient="horizontal",
            ),
            toolbox_opts=opts.ToolboxOpts(
                is_show=common_opts["show_toolbox"],
                feature=opts.ToolBoxFeatureOpts(
                    save_as_image=opts.ToolBoxFeatureSaveAsImageOpts(is_show=True),
                    data_view=opts.ToolBoxFeatureDataViewOpts(is_show=True),
                    restore=opts.ToolBoxFeatureRestoreOpts(is_show=True),
                ),
            ),
            visualmap_opts=(
                opts.VisualMapOpts(
                    is_show=True,
                    range_color=["#50a3ba", "#eac736", "#d94e5d"],
                    orient="vertical",
                    pos_left="left",
                    pos_top="bottom",
                )
                if "value_column" in self.options
                else None
            ),
        )


@register_chart("POINT_MAP")
class PointMapChart(BaseMapChart):
    """Map chart that renders points using latitude and longitude coordinates."""

    def create_chart(self) -> Optional[Chart]:
        """Create a point map chart."""
        if "lat_field" not in self.options or "lng_field" not in self.options:
            logger.error("lat_field and lng_field are required for point map charts")
            return None

        try:
            # Get filtered data using the standard BaseChart method
            filtered_data = self._get_data()
            if filtered_data is None or filtered_data.empty:
                logger.warning("No data available for point map chart")
                return None

            # Initialize chart
            chart = self.initialize_chart(filtered_data)

            # Configure chart with point data
            self.configure_chart(chart, filtered_data)

            return chart

        except Exception as e:
            logger.error(f"Error creating point map chart: {e}")
            return None

    def initialize_chart(self, filtered_data: Optional[pd.DataFrame] = None) -> Chart:
        """Initialize a point map chart."""
        chart = Geo(
            init_opts=opts.InitOpts(
                width=str(self.options.get("width", "100%")),
                height=str(self.options.get("height", "600px")),
            )
        )

        # Add schema for the base map
        chart.add_schema(
            maptype=self.base_map_config["maptype"],
            roam=self._get_common_map_options()["roam"],
            zoom=self._get_common_map_options()["zoom"],
            center=self._get_common_map_options()["center"],
        )

        return chart

    def configure_chart(
        self, chart: Chart, filtered_data: Optional[pd.DataFrame] = None
    ) -> None:
        """Configure point map chart with data and styling."""
        if filtered_data is None or filtered_data.empty:
            return

        # Process point data
        processed_data = self._process_point_data(filtered_data)
        if processed_data.empty:
            logger.warning("No valid point data after processing")
            return

        # Add point series to chart
        point_data = self._prepare_point_data(processed_data)
        if point_data:
            chart.add(
                series_name=self.options.get("series_name", "Points"),
                data_pair=point_data,
                type_="scatter",
                symbol_size=self.options.get("point_size", 10),
            )

        # Set global options
        self._set_point_global_options(chart, processed_data)

    def _process_point_data(self, data: DataFrame) -> DataFrame:
        """Process point data for rendering."""
        lat_field = cast(DjangoFieldLike, self.options["lat_field"])
        lng_field = cast(DjangoFieldLike, self.options["lng_field"])

        lat_column = lat_field.field_name
        lng_column = lng_field.field_name

        # Validate required fields exist
        if lat_column not in data.columns:
            raise ValueError(f"Latitude field '{lat_column}' not found in data")
        if lng_column not in data.columns:
            raise ValueError(f"Longitude field '{lng_column}' not found in data")

        # Convert to numeric and filter out invalid coordinates
        processed_data = data.copy()
        processed_data[lat_column] = pd.to_numeric(
            processed_data[lat_column], errors="coerce"
        )
        processed_data[lng_column] = pd.to_numeric(
            processed_data[lng_column], errors="coerce"
        )

        # Remove rows with invalid coordinates
        processed_data = processed_data.dropna(subset=[lat_column, lng_column])

        # Validate coordinate ranges
        processed_data = processed_data[
            (processed_data[lat_column] >= -90)
            & (processed_data[lat_column] <= 90)
            & (processed_data[lng_column] >= -180)
            & (processed_data[lng_column] <= 180)
        ]

        return processed_data

    def _prepare_point_data(self, data: DataFrame) -> List[List[Any]]:
        """Prepare point data for chart rendering."""
        lat_field = cast(DjangoFieldLike, self.options["lat_field"])
        lng_field = cast(DjangoFieldLike, self.options["lng_field"])

        lat_column = lat_field.field_name
        lng_column = lng_field.field_name

        # Get value column if specified
        value_column = None
        if "value_column" in self.options:
            value_field = cast(DjangoFieldLike, self.options["value_column"])
            value_column = value_field.field_name

        point_data = []
        for idx, row in data.iterrows():
            point_info = [
                row[lng_column],  # longitude first for ECharts
                row[lat_column],  # latitude second
            ]
            if value_column and value_column in data.columns:
                try:
                    point_info.append(float(row[value_column]))
                except (ValueError, TypeError):
                    point_info.append(0)
            point_data.append(point_info)

        return point_data

    def _set_point_global_options(self, chart: Chart, data: DataFrame) -> None:
        """Set global options for point chart."""
        common_opts = self._get_common_map_options()

        # Get value column for visual map if available
        value_column = None
        if "value_column" in self.options:
            value_field = cast(DjangoFieldLike, self.options["value_column"])
            value_column = value_field.field_name

        # Calculate min/max for visual map
        visual_map_opts = None
        if value_column and value_column in data.columns:
            try:
                min_val = float(data[value_column].min())
                max_val = float(data[value_column].max())
                visual_map_opts = opts.VisualMapOpts(
                    is_show=True,
                    min_=min_val,
                    max_=max_val,
                    range_color=["#50a3ba", "#eac736", "#d94e5d"],
                    orient="vertical",
                    pos_left="left",
                    pos_top="bottom",
                )
            except (ValueError, TypeError):
                pass

        chart.set_global_opts(
            title_opts=opts.TitleOpts(
                title=self.options.get("title", "Point Map"), pos_top="5%"
            ),
            legend_opts=opts.LegendOpts(
                is_show=common_opts["show_legend"],
                pos_top="5%",
                pos_left="center",
                orient="horizontal",
            ),
            toolbox_opts=opts.ToolboxOpts(
                is_show=common_opts["show_toolbox"],
                feature=opts.ToolBoxFeatureOpts(
                    save_as_image=opts.ToolBoxFeatureSaveAsImageOpts(is_show=True),
                    data_view=opts.ToolBoxFeatureDataViewOpts(is_show=True),
                    restore=opts.ToolBoxFeatureRestoreOpts(is_show=True),
                ),
            ),
            visualmap_opts=visual_map_opts,
        )

    def _create_point_map(self, data: DataFrame) -> Chart:
        """Create the actual point map chart."""
        lat_field = cast(DjangoFieldLike, self.options["lat_field"])
        lng_field = cast(DjangoFieldLike, self.options["lng_field"])

        lat_column = lat_field.field_name
        lng_column = lng_field.field_name

        # Get value column if specified
        value_column = None
        if "value_column" in self.options:
            value_field = cast(DjangoFieldLike, self.options["value_column"])
            value_column = value_field.field_name

        # Create Geo chart for point rendering
        chart = Geo(
            init_opts=opts.InitOpts(
                width=str(self.options.get("width", "100%")),
                height=str(self.options.get("height", "600px")),
            )
        )

        # Prepare point data
        point_data = []
        for idx, row in data.iterrows():
            point_info = [
                row[lng_column],  # longitude first for ECharts
                row[lat_column],  # latitude second
            ]
            if value_column and value_column in data.columns:
                point_info.append(row[value_column])
            point_data.append(point_info)

        # Add schema and point series
        chart.add_schema(
            maptype=self.base_map_config["maptype"],
            roam=self._get_common_map_options()["roam"],
            zoom=self._get_common_map_options()["zoom"],
            center=self._get_common_map_options()["center"],
        )

        # Add scatter points
        chart.add(
            series_name=self.options.get("series_name", "Points"),
            data_pair=point_data,
            type_="scatter",
            symbol_size=self.options.get("point_size", 10),
        )

        # Configure chart options
        self._configure_point_chart(chart, data)

        return chart

    def _configure_point_chart(self, chart: Chart, data: DataFrame) -> None:
        """Configure point chart with styling and options."""
        common_opts = self._get_common_map_options()

        chart.set_global_opts(
            title_opts=opts.TitleOpts(
                title=self.options.get("title", "Point Map"), pos_top="5%"
            ),
            legend_opts=opts.LegendOpts(
                is_show=common_opts["show_legend"],
                pos_top="5%",
                pos_left="center",
                orient="horizontal",
            ),
            toolbox_opts=opts.ToolboxOpts(
                is_show=common_opts["show_toolbox"],
                feature=opts.ToolBoxFeatureOpts(
                    save_as_image=opts.ToolBoxFeatureSaveAsImageOpts(is_show=True),
                    data_view=opts.ToolBoxFeatureDataViewOpts(is_show=True),
                    restore=opts.ToolBoxFeatureRestoreOpts(is_show=True),
                ),
            ),
            visualmap_opts=(
                opts.VisualMapOpts(
                    is_show=True,
                    range_color=["#50a3ba", "#eac736", "#d94e5d"],
                    orient="vertical",
                    pos_left="left",
                    pos_top="bottom",
                )
                if "value_column" in self.options
                else None
            ),
        )


@register_chart("GEOSPATIAL_MAP")
class GeospatialMapChart(BaseMapChart):
    """Map chart that renders geospatial files like GeoJSON, TopoJSON, etc."""

    def create_chart(self) -> Optional[Chart]:
        """Create a geospatial map chart."""
        # For geospatial maps, we can work with or without database data
        # The geospatial structure can come from options, and values from database

        try:
            # Get filtered data using the standard BaseChart method
            filtered_data = self._get_data()

            # Initialize chart
            chart = self.initialize_chart(filtered_data)

            # Configure chart with geospatial data
            self.configure_chart(chart, filtered_data)

            return chart

        except Exception as e:
            logger.error(f"Error creating geospatial map chart: {e}")
            return None

    def initialize_chart(self, filtered_data: Optional[pd.DataFrame] = None) -> Chart:
        """Initialize a geospatial map chart."""
        chart = Geo(
            init_opts=opts.InitOpts(
                width=str(self.options.get("width", "100%")),
                height=str(self.options.get("height", "600px")),
            )
        )

        # Add schema for the base map
        map_name = self.options.get("map_name", self.base_map_config["maptype"])
        chart.add_schema(
            maptype=map_name,
            roam=self._get_common_map_options()["roam"],
            zoom=self._get_common_map_options()["zoom"],
            center=self._get_common_map_options()["center"],
        )

        return chart

    def configure_chart(
        self, chart: Chart, filtered_data: Optional[pd.DataFrame] = None
    ) -> None:
        """Configure geospatial map chart with data and styling."""
        # Load geospatial structure from resource file field, options, or file
        geospatial_data = self._load_geospatial_data(filtered_data)

        # Prepare map data combining geospatial structure with database values
        map_data = self._prepare_geospatial_data(geospatial_data, filtered_data)

        if map_data:
            map_name = self.options.get("map_name", "custom_geospatial")
            chart.add(
                series_name=self.options.get("series_name", "Geospatial Data"),
                data_pair=map_data,
                maptype=map_name,
            )

        # Set global options
        self._set_geospatial_global_options(chart, filtered_data)

    def _load_geospatial_data(
        self, filtered_data: Optional[DataFrame] = None
    ) -> Optional[Dict[str, Any]]:
        """Load geospatial data from resource file field only."""
        if "geospatial_field" not in self.options:
            logger.error(
                "GeospatialMapChart requires 'geospatial_field' option to specify the field containing geospatial data"
            )
            return None

        if filtered_data is None or filtered_data.empty:
            logger.warning("No data available to load geospatial information from")
            return None

        geospatial_field = cast(DjangoFieldLike, self.options["geospatial_field"])
        geospatial_column = geospatial_field.field_name

        if geospatial_column not in filtered_data.columns:
            logger.error(
                f"Geospatial field '{geospatial_column}' not found in data columns"
            )
            return None

        # Get the first non-null geospatial data from the column
        for idx, row in filtered_data.iterrows():
            geospatial_value = row[geospatial_column]
            if pd.notna(geospatial_value) and geospatial_value:
                try:
                    # If it's already a dict, return it
                    if isinstance(geospatial_value, dict):
                        return cast(Dict[str, Any], geospatial_value)
                    # If it's a string, try to parse as JSON
                    elif isinstance(geospatial_value, str):
                        return cast(Dict[str, Any], json.loads(geospatial_value))
                except (json.JSONDecodeError, TypeError) as e:
                    logger.warning(
                        f"Error parsing geospatial data from field {geospatial_column}: {e}"
                    )
                    continue

        logger.error(f"No valid geospatial data found in field '{geospatial_column}'")
        return None

    def _prepare_geospatial_data(
        self,
        geospatial_data: Optional[Dict[str, Any]],
        filtered_data: Optional[DataFrame],
    ) -> List[List[Any]]:
        """Prepare geospatial data for chart rendering."""
        map_data = []

        # If no geospatial structure provided, use database data directly
        if (
            not geospatial_data
            and filtered_data is not None
            and not filtered_data.empty
        ):
            # Use database data directly - assume it has region names and values
            if "name_field" in self.options and "value_column" in self.options:
                name_field = cast(DjangoFieldLike, self.options["name_field"])
                value_field = cast(DjangoFieldLike, self.options["value_column"])

                name_column = name_field.field_name
                value_column = value_field.field_name

                if (
                    name_column in filtered_data.columns
                    and value_column in filtered_data.columns
                ):
                    for idx, row in filtered_data.iterrows():
                        try:
                            region_name = str(row[name_column])
                            value = float(row[value_column])
                            map_data.append([region_name, value])
                        except (ValueError, TypeError):
                            continue
            return map_data

        # Handle GeoJSON format with database values
        if geospatial_data and geospatial_data.get("type") == "FeatureCollection":
            features = geospatial_data.get("features", [])

            for feature in features:
                properties = feature.get("properties", {})

                # Get feature name/id
                feature_name = (
                    properties.get("name")
                    or properties.get("id")
                    or f"feature_{len(map_data)}"
                )

                # Get value from filtered data if available
                feature_value = 0.0
                if (
                    filtered_data is not None
                    and not filtered_data.empty
                    and "value_column" in self.options
                ):
                    value_field = cast(DjangoFieldLike, self.options["value_column"])
                    value_column = value_field.field_name

                    # Try to match feature with data
                    if "name_field" in self.options:
                        name_field = cast(DjangoFieldLike, self.options["name_field"])
                        name_column = name_field.field_name

                        if name_column in filtered_data.columns:
                            matching_rows = filtered_data[
                                filtered_data[name_column] == feature_name
                            ]
                            if (
                                not matching_rows.empty
                                and value_column in filtered_data.columns
                            ):
                                try:
                                    feature_value = float(
                                        matching_rows.iloc[0][value_column]
                                    )
                                except (ValueError, TypeError):
                                    feature_value = 0.0

                map_data.append([feature_name, feature_value])

        return map_data

    def _set_geospatial_global_options(
        self, chart: Chart, filtered_data: Optional[DataFrame]
    ) -> None:
        """Set global options for geospatial chart."""
        common_opts = self._get_common_map_options()

        # Get value column for visual map if available
        value_column = None
        visual_map_opts = None

        if (
            filtered_data is not None
            and not filtered_data.empty
            and "value_column" in self.options
        ):
            value_field = cast(DjangoFieldLike, self.options["value_column"])
            value_column = value_field.field_name

            if value_column in filtered_data.columns:
                try:
                    min_val = float(filtered_data[value_column].min())
                    max_val = float(filtered_data[value_column].max())
                    visual_map_opts = opts.VisualMapOpts(
                        is_show=True,
                        min_=min_val,
                        max_=max_val,
                        range_color=["#50a3ba", "#eac736", "#d94e5d"],
                        orient="vertical",
                        pos_left="left",
                        pos_top="bottom",
                    )
                except (ValueError, TypeError):
                    pass

        chart.set_global_opts(
            title_opts=opts.TitleOpts(
                title=self.options.get("title", "Geospatial Map"), pos_top="5%"
            ),
            legend_opts=opts.LegendOpts(
                is_show=common_opts["show_legend"],
                pos_top="5%",
                pos_left="center",
                orient="horizontal",
            ),
            toolbox_opts=opts.ToolboxOpts(
                is_show=common_opts["show_toolbox"],
                feature=opts.ToolBoxFeatureOpts(
                    save_as_image=opts.ToolBoxFeatureSaveAsImageOpts(is_show=True),
                    data_view=opts.ToolBoxFeatureDataViewOpts(is_show=True),
                    restore=opts.ToolBoxFeatureRestoreOpts(is_show=True),
                ),
            ),
            visualmap_opts=visual_map_opts,
        )

    def _create_geospatial_map(
        self, geospatial_data: Dict[str, Any], filtered_data: Optional[DataFrame]
    ) -> Chart:
        """Create the actual geospatial map chart."""
        # Create Geo chart for geospatial rendering
        chart = Geo(
            init_opts=opts.InitOpts(
                width=str(self.options.get("width", "100%")),
                height=str(self.options.get("height", "600px")),
            )
        )

        # Register custom map if needed
        map_name = self.options.get("map_name", "custom_map")

        # Add schema
        chart.add_schema(
            maptype=map_name,
            roam=self._get_common_map_options()["roam"],
            zoom=self._get_common_map_options()["zoom"],
            center=self._get_common_map_options()["center"],
        )

        # Process geospatial features
        map_data = self._process_geospatial_features(geospatial_data, filtered_data)

        # Add geospatial series
        if map_data:
            chart.add(
                series_name=self.options.get("series_name", "Geospatial Data"),
                data_pair=map_data,
                maptype=map_name,
            )

        # Configure chart options
        self._configure_geospatial_chart(chart)

        return chart

    def _process_geospatial_features(
        self, geospatial_data: Dict[str, Any], filtered_data: Optional[DataFrame]
    ) -> List[List[Any]]:
        """Process geospatial features for rendering."""
        map_data: List[List[Any]] = []

        # Handle GeoJSON format
        if geospatial_data.get("type") == "FeatureCollection":
            features = geospatial_data.get("features", [])

            for feature in features:
                properties = feature.get("properties", {})
                geometry = feature.get("geometry", {})

                # Get feature name/id
                feature_name = (
                    properties.get("name")
                    or properties.get("id")
                    or f"feature_{len(map_data)}"
                )

                # Get value from filtered data if available
                feature_value = 0.0
                if filtered_data is not None and "value_column" in self.options:
                    value_field = cast(DjangoFieldLike, self.options["value_column"])
                    value_column = value_field.field_name

                    # Try to match feature with data
                    if "name_field" in self.options:
                        name_field = cast(DjangoFieldLike, self.options["name_field"])
                        name_column = name_field.field_name

                        matching_rows = filtered_data[
                            filtered_data[name_column] == feature_name
                        ]
                        if not matching_rows.empty:
                            feature_value = matching_rows.iloc[0][value_column]

                map_data.append([feature_name, feature_value])

        return map_data

    def _configure_geospatial_chart(self, chart: Chart) -> None:
        """Configure geospatial chart with styling and options."""
        common_opts = self._get_common_map_options()

        chart.set_global_opts(
            title_opts=opts.TitleOpts(
                title=self.options.get("title", "Geospatial Map"), pos_top="5%"
            ),
            legend_opts=opts.LegendOpts(
                is_show=common_opts["show_legend"],
                pos_top="5%",
                pos_left="center",
                orient="horizontal",
            ),
            toolbox_opts=opts.ToolboxOpts(
                is_show=common_opts["show_toolbox"],
                feature=opts.ToolBoxFeatureOpts(
                    save_as_image=opts.ToolBoxFeatureSaveAsImageOpts(is_show=True),
                    data_view=opts.ToolBoxFeatureDataViewOpts(is_show=True),
                    restore=opts.ToolBoxFeatureRestoreOpts(is_show=True),
                ),
            ),
            visualmap_opts=(
                opts.VisualMapOpts(
                    is_show=True,
                    range_color=["#50a3ba", "#eac736", "#d94e5d"],
                    orient="vertical",
                    pos_left="left",
                    pos_top="bottom",
                )
                if "value_column" in self.options
                else None
            ),
        )
