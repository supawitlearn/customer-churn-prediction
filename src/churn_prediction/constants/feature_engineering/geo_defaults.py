from dataclasses import dataclass
from pathlib import Path

"""
Configuration constants for geo-feature engineering.

This module exposes:
- GeoConfig: dataclass containing configuration values with sensible defaults.
"""

@dataclass(frozen=True)
class GeoConfig:
    """
    Configuration container for geospatial feature engineering.

    Attributes:
        buffer_radius: Buffer radius in meters for POI extraction.
        crs_wgs84: CRS string for WGS84 geographic coordinates.
        crs_utm: CRS string for the projected coordinate system used for distance-based
                 operations (should be appropriate for the country/region).
        province_shapefile: Path to province-level shapefile.
        district_shapefile: Path to district-level shapefile.
        shapename_column: Column name in boundary shapefiles that contains the human
                          readable administrative name.
        predicate: Spatial predicate to use with GeoPandas spatial joins ('within', 'intersects', etc).
    """
    buffer_radius: int = 1000
    crs_wgs84: str = "EPSG:4326"
    crs_utm: str = "EPSG:32647"
    province_shapefile: Path = Path("resources/geoBoundaries/geoBoundaries-THA-ADM1_simplified.shp")
    district_shapefile: Path = Path("resources/geoBoundaries/geoBoundaries-THA-ADM2_simplified.shp")
    shapename_column: str = "shapeName"
    predicate: str = "within"
