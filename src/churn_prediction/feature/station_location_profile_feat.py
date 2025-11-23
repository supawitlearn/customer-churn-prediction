"""
Station Location Profile Feature Engineering Module.

This module provides classes and methods to clean geospatial data related to station locations,
enrich them with administrative boundaries, and extract Points of Interest (POI) features around
these locations using spatial operations.
"""

# import necessary libraries
import geopandas as gpd
import osmnx as ox
import pandas as pd
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from shapely.geometry import Point
from pyspark.sql import functions as F

# import project modules
from src.churn_prediction.logger import logger
from src.churn_prediction.pydantic.pipeline_config import PipelineConfig
from src.churn_prediction.constants.feature_engineering.geo_defaults import GeoConfig
from src.churn_prediction.utils.common import get_execution_date, get_spark, load_single_config, load_yaml
from src.churn_prediction.utils.loaders import load_data
from src.churn_prediction.utils.writers import write_data


class GeoDataCleaner:
    """
    Geospatial data cleaner that enriches station locations with administrative boundaries.

    Notes:
        - The class works with pandas DataFrames and GeoPandas GeoDataFrames for spatial operations.
        - It is intentionally side-effect free: methods return new objects and the class instance holds
          working state for convenience.
    """

    SPATIAL_JOIN_CLEANUP_COLS = ["index_right", "shapeISO", "shapeID", "shapeGroup", "shapeType"]

    def __init__(self, df: pd.DataFrame, config: Optional[GeoConfig] = None):
        if df is None:
            raise ValueError("df must be provided")
        self._df = df.copy()
        self.config = config or GeoConfig()

    @property
    def pandas_df(self) -> pd.DataFrame:
        return self._df

    def create_geodataframe(self, lon_col: str = "longitude", lat_col: str = "latitude") -> gpd.GeoDataFrame:
        """Create a GeoDataFrame from longitude/latitude columns"""
        if lon_col not in self._df.columns or lat_col not in self._df.columns:
            raise KeyError(f"Expected columns '{lon_col}' and '{lat_col}' in the dataframe")
        gdf = gpd.GeoDataFrame(
            self._df,
            geometry=gpd.points_from_xy(self._df[lon_col].astype(float), self._df[lat_col].astype(float)),
            crs=self.config.crs_wgs84,
        )
        return gdf

    def load_shapefile(self, shapefile_path: Path, name: str = "") -> gpd.GeoDataFrame:
        """Load a shapefile and reproject to the configured WGS84 CRS."""
        shapefile_path = Path(shapefile_path)
        if not shapefile_path.exists():
            logger.error("Shapefile not found: %s", shapefile_path)
            raise FileNotFoundError(f"Shapefile not found: {shapefile_path}")
        gdf = gpd.read_file(shapefile_path)
        gdf = gdf.to_crs(self.config.crs_wgs84)
        logger.info("Loaded %s (%d features)", name or shapefile_path.name, len(gdf))
        return gdf

    def perform_spatial_join(self, points: gpd.GeoDataFrame, boundaries: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
        """Spatially join point geometries to polygon boundaries using configured predicate."""
        joined = gpd.sjoin(points, boundaries, how="left", predicate=self.config.predicate)
        logger.info("Spatial join complete: %d points enriched", joined['station_id'].nunique() if 'station_id' in joined.columns else len(joined))
        return joined

    @staticmethod
    def _clean_name_series(series: pd.Series, suffix_to_strip: str) -> pd.Series:
        """Helper to clean admin names (strip suffix, NaN handling)"""
        return (
            series.astype(str)
            .str.replace(suffix_to_strip, "", regex=False)
            .str.strip()
            .replace({"nan": "Unknown", "None": "Unknown"})
        )

    def clean_column_name(self, df: pd.DataFrame, name_column: str, suffix: str) -> pd.DataFrame:
        """
        Rename and clean a shapefile name column.

        The function maps the incoming name column to a canonical output:
            - If suffix == ' Province' -> column becomes 'province'
            - If suffix == ' District' -> column becomes 'district'
        """
        df_copy = df.copy()
        output_col = "province" if suffix.strip().lower().endswith("province") else "district"
        if name_column in df_copy.columns:
            df_copy = df_copy.rename(columns={name_column: output_col})
        if output_col in df_copy.columns:
            df_copy[output_col] = self._clean_name_series(df_copy[output_col], suffix)
            logger.info("Cleaned %s. Unique values: %d", output_col, df_copy[output_col].nunique())
        return df_copy

    def remove_unnecessary_columns(self, df: pd.DataFrame, cols_to_remove: Optional[List[str]] = None) -> pd.DataFrame:
        cols_to_remove = cols_to_remove or self.SPATIAL_JOIN_CLEANUP_COLS
        df_copy = df.copy()
        for col in cols_to_remove:
            if col in df_copy.columns:
                df_copy.drop(columns=[col], inplace=True)
        logger.debug("Removed columns: %s", cols_to_remove)
        return df_copy

    def enrich_with_province(self) -> "GeoDataCleaner":
        """Enrich station rows with province names by spatial join."""
        logger.info("STEP: Enrich with province")
        points = self.create_geodataframe()
        provinces = self.load_shapefile(self.config.province_shapefile, "Province shapefile")
        joined = self.perform_spatial_join(points, provinces)
        self._df = self.clean_column_name(joined, self.config.shapename_column, " Province")
        # drop geometry (we'll recreate as needed)
        self._df = self.remove_unnecessary_columns(self._df, self.SPATIAL_JOIN_CLEANUP_COLS + ["geometry"])
        return self

    def enrich_with_district(self) -> "GeoDataCleaner":
        """Enrich station rows with district names by spatial join and preserve geometry for later analysis."""
        logger.info("STEP: Enrich with district")
        points = self.create_geodataframe()
        districts = self.load_shapefile(self.config.district_shapefile, "District shapefile")
        joined = self.perform_spatial_join(points, districts)
        joined = self.clean_column_name(joined, self.config.shapename_column, " District")
        # rename geometry column for clarity
        if "geometry" in joined.columns:
            joined = joined.rename(columns={"geometry": "locationgeometry"})
        # optionally join district polygon geometry back by shapeID if available
        if "shapeID" in joined.columns:
            try:
                joined = joined.join(
                    districts[["geometry", "shapeID"]].set_index("shapeID"),
                    on="shapeID",
                    how="left",
                    rsuffix="_district"
                )
            except Exception:
                logger.debug("Could not join district polygon geometries by shapeID; skipping.")
        # cleanup metadata but keep 'shapeID' (if needed downstream)
        self._df = self.remove_unnecessary_columns(joined, [c for c in self.SPATIAL_JOIN_CLEANUP_COLS if c != "shapeID"])
        return self

    def get_result(self) -> pd.DataFrame:
        """Return the cleaned pandas DataFrame."""
        logger.info("Result summary: total stations = %d", len(self._df))
        return self._df.copy()


class POIAnalyzer:
    """
    POI analysis helper that identifies and summarizes POIs around station locations.

    - Uses GeoPandas spatial joins and buffering in a projected CRS for accurate distance measures.
    - Returns pandas DataFrames for summary outputs and GeoDataFrames for joined records.
    """

    def __init__(self, config: Optional[GeoConfig] = None):
        self.config = config or GeoConfig()
        if self.config.buffer_radius <= 0:
            raise ValueError("buffer_radius must be positive")

    def validate_inputs(self, joined_gdf: gpd.GeoDataFrame, poi_groups_dict: Dict[str, Dict[str, List[str]]]) -> None:
        if joined_gdf is None or joined_gdf.empty:
            raise ValueError("joined_gdf cannot be empty")
        if not poi_groups_dict:
            raise ValueError("poi_groups_dict cannot be empty")
        if "station_id" not in joined_gdf.columns:
            raise KeyError("'station_id' column not found in joined_gdf")

    @staticmethod
    def count_group_pois(station_data: pd.DataFrame, group_tags: Dict[str, List[str]]) -> int:
        """Counts POIs matching any of the tag/value pairs in group_tags for a single station subset."""
        count = 0
        for tag_key, tag_values in group_tags.items():
            if tag_key not in station_data.columns:
                continue
            # station_data[tag_key] may be a list-like or scalar; use isin for robust matching
            count += int(station_data[tag_key].isin(tag_values).sum())
        return count

    def count_pois_by_groups(self, joined_gdf: gpd.GeoDataFrame, poi_groups_dict: Dict[str, Dict[str, List[str]]]) -> pd.DataFrame:
        """Produce a summary DataFrame with counts of POI groups per station_id."""
        self.validate_inputs(joined_gdf, poi_groups_dict)
        results = []
        for station_id in joined_gdf["station_id"].unique():
            station_data = joined_gdf[joined_gdf["station_id"] == station_id]
            row = {"station_id": station_id}
            for group_name, group_tags in poi_groups_dict.items():
                row[f"poi_cnt_{group_name}"] = self.count_group_pois(station_data, group_tags)
            results.append(row)
        return pd.DataFrame(results)

    def calculate_poi_percentages(self, poi_summary_df: pd.DataFrame, poi_cols: List[str], suffix: str = "perc_") -> pd.DataFrame:
        """Add percentage columns based on provided POI count columns."""
        result_df = poi_summary_df.copy()
        result_df["sum_poi"] = result_df[poi_cols].sum(axis=1)
        for col in poi_cols:
            result_df[f"{suffix}{col}"] = (result_df[col] / result_df["sum_poi"]).fillna(0).round(4)
        return result_df

    def extract_poi_features(self, station_gps_df: gpd.GeoDataFrame, pois: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
        """
        Buffer station points and spatially join POIs to stations.

        Returns a GeoDataFrame where each POI is associated with the station(s) whose buffer it falls into.
        """
        if station_gps_df.empty or pois is None or pois.empty:
            return gpd.GeoDataFrame()

        # convert to projected CRS to do buffering in meters
        station_proj = station_gps_df.to_crs(self.config.crs_utm).copy()
        station_proj["geometry"] = station_proj.geometry.buffer(self.config.buffer_radius)

        pois_proj = pois.to_crs(self.config.crs_utm)
        joined = gpd.sjoin(pois_proj, station_proj, how="inner", predicate=self.config.predicate)
        # return joined in WGS84 to keep downstream consistent with original CRS
        try:
            return joined.to_crs(self.config.crs_wgs84)
        except Exception:
            return joined

    def identify_dominant_poi_type(self, summary_df: pd.DataFrame) -> pd.DataFrame:
        """
        Identify dominant POI group for each station based on highest percentage column.
        Expects percentage columns to be named with the prefix 'perc_poi_cnt_'.
        """
        df_copy = summary_df.copy()
        perc_cols = [c for c in df_copy.columns if c.startswith("perc_poi_cnt_")]
        if not perc_cols:
            raise ValueError("No percentage columns found. Run calculate_poi_percentages first.")
        group_names = [c.replace("perc_poi_cnt_", "") for c in perc_cols]

        def dominant(row):
            idx = row[perc_cols].idxmax()
            if pd.isna(row[idx]) or row[idx] == 0:
                return "none"
            return idx.replace("perc_poi_cnt_", "")

        df_copy["dominant_poi_type"] = df_copy.apply(dominant, axis=1)
        return df_copy

    def run_full_pipeline(
        self,
        station_gps_df: gpd.GeoDataFrame,
        pois: gpd.GeoDataFrame,
        poi_groups_dict: Dict[str, Dict[str, List[str]]],
    ) -> Tuple[pd.DataFrame, gpd.GeoDataFrame]:
        """
        Run a full POI extraction and summarization pipeline.

        Returns:
            (summary_df, joined_gdf)
        """
        joined = self.extract_poi_features(station_gps_df, pois)
        if joined.empty:
            return pd.DataFrame(), gpd.GeoDataFrame()

        summary_df = self.count_pois_by_groups(joined, poi_groups_dict)
        poi_cols = [c for c in summary_df.columns if c.startswith("poi_cnt_")]
        summary_df = self.calculate_poi_percentages(summary_df, poi_cols, suffix="perc_")
        # rename percentage columns to include 'poi_cnt' marker used in identification
        # the calculate function already creates 'perc_poi_cnt_{group}'
        summary_df = self.identify_dominant_poi_type(summary_df)
        return summary_df, joined

class StationLocationProfileFeatures:
    """
    Station Location Profile Feature Engineering Module.
    """

    def __init__(self, config_path: Path, execution_date: Optional[str] = None) -> None:
        self.config_path = config_path
        self.execution_date = get_execution_date(execution_date)

    def run(self) -> None:
        """
        Main entry point to run geospatial cleansing and POI extraction.

        Returns:
            None.
        """
        logger.info(f"Starting station location profile feature engineering with config: {self.config_path}")
        try:
            spark = get_spark()
            config = GeoConfig()
            
            # Load pipeline configuration
            pipeline_config = load_single_config(PipelineConfig, self.config_path)
            input = pipeline_config.feature_engineering.input
            output = pipeline_config.feature_engineering.output
            resources = pipeline_config.feature_engineering.resources
            logger.debug(f"Configuration loaded successfully")

            POI_GROUPS = load_yaml(resources.get('poi_groups')).poi_groups
            POI_TAGS: Dict[str, List[str]] = {tag: vals for _, grp in POI_GROUPS.items() for tag, vals in grp.items()}

            logger.info("Starting geospatial pipeline for execution date: %s", self.execution_date)

            # Load station dimension data
            station_dim_df = load_data(input.get('station_dim').get('file_path'))
            station_dim_df = station_dim_df.filter(station_dim_df["dl_data_dt"] == self.execution_date)

            # Convert to pandas early only for GeoPandas processing (small-ish dataset expected).
            station_pd = station_dim_df.toPandas()
            if station_pd.empty:
                logger.warning("No station data found for date: %s", self.execution_date)
                return pd.DataFrame()

            # Enrich with administrative boundaries
            cleaner = GeoDataCleaner(station_pd, config)
            cleaner.enrich_with_province().enrich_with_district()
            cleaned_df = cleaner.get_result()

            # prepare list of unique station geometries for POI queries
            if "geometry" not in cleaned_df.columns:
                # create a point geometry column if not present (lon/lat)
                cleaned_df["geometry"] = gpd.points_from_xy(cleaned_df["longitude"], cleaned_df["latitude"])
            geometry_list = cleaned_df["geometry"].drop_duplicates().tolist()

            analyzer = POIAnalyzer(config=config)

            poi_group_summary_list = []
            # expected columns returned by osmnx.features_from_polygon - we only keep name and geometry and tag fields
            for geometry in geometry_list:
                try:
                    poi = ox.features_from_polygon(geometry, tags=POI_TAGS)
                    if poi is None or poi.empty:
                        continue
                    # Ensure we have at least "name" and "geometry" columns plus tag keys
                    expected_columns = ["name", "geometry"] + list(POI_TAGS.keys())
                    # avoid KeyError by intersecting available columns
                    keep_cols = [c for c in expected_columns if c in poi.columns]
                    pois = poi.reindex(columns=keep_cols).reset_index(drop=True)

                    # station subset that corresponds to the geometry
                    station_area_df = cleaned_df[cleaned_df["geometry"] == geometry]
                    station_gps_df = gpd.GeoDataFrame(
                        station_area_df.copy(),
                        geometry=gpd.points_from_xy(station_area_df["longitude"], station_area_df["latitude"]),
                        crs=config.crs_wgs84,
                    )

                    summary_df, _joined = analyzer.run_full_pipeline(station_gps_df, pois, POI_GROUPS)
                    if not summary_df.empty:
                        # ensure station_id column exists and append
                        poi_group_summary_list.append(summary_df)
                except Exception as exc:
                    logger.exception("Failed POI extraction for a geometry: %s", exc)

            if poi_group_summary_list:
                poi_group_final_summary_df = pd.concat(poi_group_summary_list, ignore_index=True)
            else:
                poi_group_final_summary_df = pd.DataFrame()

            logger.info("POI analysis completed.")

            cleaned_df.head()
            poi_group_final_summary_df.head()

            # Merge POI features back to station dataframe
            station_feat_df = cleaned_df.merge(
                poi_group_final_summary_df,
                on="station_id",
                how="left"
            )
            selected_columns = ['station_id','station_code','station_status','station_name','province','district',
                                'poi_cnt_daily_life','poi_cnt_shopping','poi_cnt_leisure','poi_cnt_travel_tourism','sum_poi',
                                'perc_poi_cnt_daily_life','perc_poi_cnt_shopping','perc_poi_cnt_leisure',
                                'perc_poi_cnt_travel_tourism','dominant_poi_type']
            station_feat_df = station_feat_df[selected_columns]
            station_feat_df = spark.createDataFrame(station_feat_df)

            # Calculate entropy of POI distribution
            station_feat_df = station_feat_df.withColumn(
                    "entropy",
                    -(
                        F.col("perc_poi_cnt_daily_life") * F.log(F.col("perc_poi_cnt_daily_life") + 1e-9) +
                        F.col("perc_poi_cnt_shopping") * F.log(F.col("perc_poi_cnt_shopping") + 1e-9) +
                        F.col("perc_poi_cnt_leisure") * F.log(F.col("perc_poi_cnt_leisure") + 1e-9) +
                        F.col("perc_poi_cnt_travel_tourism") * F.log(F.col("perc_poi_cnt_travel_tourism") + 1e-9)
                    )
                )

            # Flag save time
            station_feat_df = station_feat_df.withColumn("dl_data_dt", F.lit(self.execution_date).cast('date'))
            station_feat_df = station_feat_df.withColumn("dl_load_ts", F.lit(datetime.now()))

            # Write data
            write_data(station_feat_df, output.get('file_path'))
            logger.info("Station location profile feature engineering completed successfully")

        except Exception as e:
            logger.exception("Error in feature engineering station_location_profile_feat: %s", e)
            raise
