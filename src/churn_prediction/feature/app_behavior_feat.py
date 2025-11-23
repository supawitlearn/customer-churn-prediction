# import necessary libraries
from pyspark.sql import functions as F
from pyspark.sql import Window, DataFrame
from datetime import datetime
from typing import Dict, List, Tuple, Optional
from pathlib import Path

# import project modules
from src.churn_prediction.logger import logger
from src.churn_prediction.constants.feature_engineering.app_const import SESSION_TIMEOUT, EVENT_TYPE_MAPPING
from src.churn_prediction.pydantic.pipeline_config import PipelineConfig
from src.churn_prediction.utils.common import load_single_config, get_execution_date, get_spark
from src.churn_prediction.utils.loaders import load_data
from src.churn_prediction.utils.writers import write_data

def add_time_difference_column(
    df: DataFrame,
    partition_col: str = "user_id",
    order_col: str = "app_log_ts",
    output_col: str = "time_diff_min"
) -> DataFrame:
    """
    Calculate time difference in minutes between consecutive events per user.
    
    Args:
        df: Input Spark DataFrame
        partition_col: Column to partition by (typically user_id)
        order_col: Column to order by (typically timestamp)
        output_col: Name of output column
    
    Returns:
        DataFrame with time difference column added
    """
    window_spec = Window.partitionBy(partition_col).orderBy(order_col)
    
    return (df
        .withColumn(
            "previous_ts",
            F.lag(order_col).over(window_spec)
        )
        .withColumn(
            output_col,
            F.round(
                (F.col(order_col).cast('long') - F.col('previous_ts').cast('long')) 
                / 60,
                2
            )
        )
        .withColumn(
            output_col,
            F.coalesce(F.col(output_col), F.lit(0.0))
        )
        .drop('previous_ts')
    )

def add_period_column(
    df: DataFrame,
    partition_col: str = "user_id",
    order_col: str = "app_log_ts",
    threshold_col: str = "time_diff_min",
    threshold_value: float = None,
    output_col: str = "period"
) -> DataFrame:
    """
    Add a period column that increments when threshold is exceeded.
    
    Args:
        df: Input Spark DataFrame
        partition_col: Column to partition by
        order_col: Column to order by
        threshold_col: Column to check threshold against
        threshold_value: Threshold value (uses SESSION_TIMEOUT if None)
        output_col: Name of output column
    
    Returns:
        DataFrame with period column added
    """
    threshold = threshold_value or SESSION_TIMEOUT
    
    window_spec = Window.partitionBy(partition_col).orderBy(order_col)
    
    return (df
        .withColumn(
            "_threshold_flag",
            F.when(F.col(threshold_col) > threshold, 1).otherwise(0)
        )
        .withColumn(
            output_col,
            F.sum("_threshold_flag").over(window_spec) + 1
        )
        .withColumn(
            output_col,
            F.when(F.col(threshold_col).isNull(), None).otherwise(F.col(output_col))
        )
        .drop("_threshold_flag")
    )

def normalize_event_types(
    df: DataFrame,
    event_type_mapping: Dict[str, List[str]] = EVENT_TYPE_MAPPING,
    event_col: str = "event_type"
) -> DataFrame:
    """
    Normalize event types using mapping dictionary.
    
    Args:
        df: Input Spark DataFrame
        event_type_mapping: Dictionary mapping normalized types to list of original types
        event_col: Name of event type column
    
    Returns:
        DataFrame with normalized event types
    """
    current_df = df
    
    for normalized_type, original_types in event_type_mapping.items():
        current_df = current_df.withColumn(
            event_col,
            F.when(
                F.col(event_col).isin(original_types),
                F.lit(normalized_type)
            ).otherwise(F.col(event_col))
        )
    
    return current_df

def join_station_features(
    app_logs_df: DataFrame,
    station_features_df: DataFrame,
    station_id_col: str = "parameter_1",
    event_type_col: str = "event_type",
    target_event: str = "checkavailablevehiclelist"
) -> DataFrame:
    """
    Join app logs with station location features.
    
    Args:
        app_logs_df: Application logs DataFrame
        station_features_df: Station features DataFrame
        station_id_col: Column name for station ID in app logs
        event_type_col: Column name for event type
        target_event: Event type to join on
    
    Returns:
        Joined DataFrame
    """
    join_condition = (
        (F.col('app.' + station_id_col) == F.col('sta.station_id')) &
        (F.col(f'app.{event_type_col}') == target_event)
    )
    
    return (app_logs_df
        .alias('app')
        .join(
            station_features_df.alias('sta'),
            on=join_condition,
            how='left'
        )
    )

class AppBehaviorFeatures:
    """
    Application behavior feature engineering module.
    """

    def __init__(self, config_path: Path, execution_date: Optional[str] = None) -> None:
        self.spark = get_spark()
        self.spark.conf.set("spark.sql.debug.maxToStringFields", "100")
        self.config_path = config_path
        self.execution_date = get_execution_date(execution_date)

    def run(self) -> None:
        """
        Main data processing pipeline.
        
        Returns:
            None
        """
        logger.info(f"Starting application behavioral feature engineering with config: {self.config_path}")
        try:
            # Load pipeline configuration
            pipeline_config = load_single_config(PipelineConfig, self.config_path)
            input = pipeline_config.feature_engineering.input
            output = pipeline_config.feature_engineering.output

            # Load data
            app_log_df = load_data(input.get('app_log_fact').get('file_path')).filter(F.col('dl_data_dt') == self.execution_date).drop('dl_data_dt','dl_load_ts')          
            station_feat_df = load_data(input.get('station_location_profile_feat').get('file_path')).filter(F.col('dl_data_dt') == self.execution_date).drop('dl_data_dt','dl_load_ts') 
            
            # Transform app logs
            app_log_df = (app_log_df
                # Add time difference
                .transform(add_time_difference_column)
                # Normalize event types
                .transform(lambda df: normalize_event_types(df, EVENT_TYPE_MAPPING))
                # Add period grouping
                .transform(add_period_column)
            )
            
            # Join with station features
            result_df = join_station_features(app_log_df, station_feat_df)
            
            # Flag save time
            result_df = result_df.withColumn("dl_data_dt", F.lit(self.execution_date).cast('date'))
            result_df = result_df.withColumn("dl_load_ts", F.lit(datetime.now()))

            # Write data
            write_data(result_df, output.get('file_path'))
            logger.info("Reservation behavioral feature engineering completed successfully")
            
        except Exception as e:
            logger.error(f"Pipeline failed: {str(e)}")
            raise
