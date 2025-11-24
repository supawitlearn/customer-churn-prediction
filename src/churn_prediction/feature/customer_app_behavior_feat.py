# import necessary libraries
from datetime import datetime, date
from typing import List, Optional
from pathlib import Path
from pyspark.sql import DataFrame, functions as F

# import project modules
from src.churn_prediction.logger import logger
from src.churn_prediction.constants.feature_engineering.app_const import SESSION_TIMEOUT, WINDOW_SIZE
from src.churn_prediction.pydantic.pipeline_config import PipelineConfig
from src.churn_prediction.utils.common import load_single_config, get_execution_date, get_spark
from src.churn_prediction.utils.loaders import load_data
from src.churn_prediction.utils.writers import write_data

def _first_day_n_months_ago(input_date: date, n: int) -> date:
    """
    Return the first day of the month that is `n` months before `input_date`.
    """
    # Normalize to first of current month
    first_this_month = input_date.replace(day=1)

    # Month arithmetic (1–12)
    month_index = first_this_month.month + 1 - n  # can be <= 0
    year = first_this_month.year
    while month_index <= 0:
        month_index += 12
        year -= 1

    return date(year, month_index, 1)


def start_of_month_n_months_ago(date_str: str, n: int = 3) -> str:
    """
    Return the start-of-month timestamp string (YYYY-MM-DD HH:MM:SS)
    for the month that is `n` months before the month of `date_str`.

    Example:
        date_str = '2025-09-30', n = 3  -> '2025-06-01 00:00:00'
    """
    d = datetime.strptime(date_str, "%Y-%m-%d").date()
    first_target_month = _first_day_n_months_ago(d, n)
    # explicitly start at midnight
    return f"{first_target_month.strftime('%Y-%m-%d')} 00:00:00"


def _fill_nulls_and_cast(agg_df: DataFrame) -> DataFrame:
    """
    Replace null/NaN values and cast columns based on naming convention.

    - Columns starting with 'cnt_' are cast to int.
    - All other non-key columns are cast to Decimal(28,4).
    - 'user_id' is left untouched.
    """
    for column in agg_df.columns:
        if column == "user_id":
            continue

        # Handle null and NaN
        agg_df = agg_df.withColumn(
            column,
            F.when(F.col(column).isNull() | F.isnan(column), F.lit(0.0)).otherwise(
                F.col(column)
            ),
        )

        # Type casting
        if column.startswith("cnt_"):
            agg_df = agg_df.withColumn(column, F.col(column).cast("int"))
        else:
            agg_df = agg_df.withColumn(column, F.col(column).cast("decimal(28,4)"))

    return agg_df


def _build_agg_for_window(app_feat_df: DataFrame, execution_date: str, n_months: int) -> DataFrame:
    """
    Build aggregation DataFrame for a given window (n_months back from execution_date).
    """
    suffix = f"_last_{n_months * 30}d"
    start_date = start_of_month_n_months_ago(execution_date, n_months)

    base_df = app_feat_df.filter(
        (F.col("app_log_ts") < execution_date) & (F.col("app_log_ts") >= start_date)
    )

    agg_df = base_df.groupBy("user_id").agg(
        # session stats
        F.countDistinct("period").alias(f"app_cnt_sessions{suffix}"),
        F.sum(F.when(F.col("event_type") == "login", 1).otherwise(0)).alias(
            f"app_cnt_login_events{suffix}"
        ),
        F.sum(
            F.when(F.col("event_type") == "checkavailablevehiclelist", 1).otherwise(0)
        ).alias(f"app_cnt_checkvehicle_events{suffix}"),
        F.sum(F.when(F.col("event_type") == "getstationlist", 1).otherwise(0)).alias(
            f"app_cnt_getstation_events{suffix}"
        ),
        F.sum(F.when(F.col("event_type") == "estimateextension", 1).otherwise(0)).alias(
            f"app_cnt_extension_events{suffix}"
        ),
        F.sum(
            F.when(
                (F.col("event_type") == "checkavailablevehiclelist")
                & (F.col("parameter_2") == 0),
                1,
            ).otherwise(0)
        ).alias(f"app_cnt_checkvehicle_but_no_vehicle{suffix}"),
        F.round(
            F.try_divide(
                F.sum(
                    F.when(
                        (F.col("event_type") == "checkavailablevehiclelist")
                        & (F.col("parameter_2") == 0),
                        1,
                    ).otherwise(0)
                ),
                F.sum(
                    F.when(
                        F.col("event_type") == "checkavailablevehiclelist", 1
                    ).otherwise(0)
                ),
            ),
            2,
        ).alias(f"app_ratio_checkvehicle_but_no_vehicle{suffix}"),
        # duration between sessions
        F.min(
            F.when(F.col("time_diff_min") < SESSION_TIMEOUT, None).otherwise(
                F.col("time_diff_min")
            )
        ).alias(f"app_min_duration_btw_session_min{suffix}"),
        F.max(
            F.when(F.col("time_diff_min") < SESSION_TIMEOUT, None).otherwise(
                F.col("time_diff_min")
            )
        ).alias(f"app_max_duration_btw_session_min{suffix}"),
        F.round(
            F.avg(
                F.when(F.col("time_diff_min") < SESSION_TIMEOUT, None).otherwise(
                    F.col("time_diff_min")
                )
            ),
            2,
        ).alias(f"app_avg_duration_btw_session_min{suffix}"),
        F.round(
            F.stddev(
                F.when(F.col("time_diff_min") < SESSION_TIMEOUT, None).otherwise(
                    F.col("time_diff_min")
                )
            ),
            2,
        ).alias(f"app_stddev_duration_btw_session_min{suffix}"),
        # duration within sessions
        F.min(
            F.when(F.col("time_diff_min") >= SESSION_TIMEOUT, None).otherwise(
                F.col("time_diff_min")
            )
        ).alias(f"app_min_duration_within_session_min{suffix}"),
        F.max(
            F.when(F.col("time_diff_min") >= SESSION_TIMEOUT, None).otherwise(
                F.col("time_diff_min")
            )
        ).alias(f"app_max_duration_within_session_min{suffix}"),
        F.round(
            F.avg(
                F.when(F.col("time_diff_min") >= SESSION_TIMEOUT, None).otherwise(
                    F.col("time_diff_min")
                )
            ),
            2,
        ).alias(f"app_avg_duration_within_session_min{suffix}"),
        F.round(
            F.stddev(
                F.when(F.col("time_diff_min") >= SESSION_TIMEOUT, None).otherwise(
                    F.col("time_diff_min")
                )
            ),
            2,
        ).alias(f"app_stddev_duration_within_session_min{suffix}"),
        # station stats
        F.sum(
            F.when(
                (F.col("province") == "Bangkok")
                & (F.col("event_type") == "checkavailablevehiclelist"),
                1,
            ).otherwise(0)
        ).alias(f"app_cnt_check_station_in_bangkok{suffix}"),
        F.sum(
            F.when(
                (F.col("province") != "Bangkok")
                & (F.col("event_type") == "checkavailablevehiclelist"),
                1,
            ).otherwise(0)
        ).alias(f"app_cnt_check_station_not_in_bangkok{suffix}"),
        F.round(
            F.try_divide(
                F.sum(
                    F.when(
                        (F.col("province") == "Bangkok")
                        & (F.col("event_type") == "checkavailablevehiclelist"),
                        1,
                    ).otherwise(0)
                ),
                F.sum(
                    F.when(
                        F.col("event_type") == "checkavailablevehiclelist", 1
                    ).otherwise(0)
                ),
            ),
            2,
        ).alias(f"app_ratio_check_station_in_bangkok{suffix}"),
        # station poi stats: means
        F.round(F.mean("perc_poi_cnt_daily_life"), 4).alias(
            f"app_avg_poi_daily_life{suffix}"
        ),
        F.round(F.mean("perc_poi_cnt_shopping"), 4).alias(f"app_avg_poi_shopping{suffix}"),
        F.round(F.mean("perc_poi_cnt_leisure"), 4).alias(f"app_avg_poi_leisure{suffix}"),
        F.round(F.mean("perc_poi_cnt_travel_tourism"), 4).alias(
            f"app_avg_poi_travel_tourism{suffix}"
        ),
        # stddev
        F.round(F.stddev("perc_poi_cnt_daily_life"), 4).alias(
            f"app_std_poi_daily_life{suffix}"
        ),
        F.round(F.stddev("perc_poi_cnt_shopping"), 4).alias(
            f"app_std_poi_shopping{suffix}"
        ),
        F.round(F.stddev("perc_poi_cnt_leisure"), 4).alias(f"app_std_poi_leisure{suffix}"),
        F.round(F.stddev("perc_poi_cnt_travel_tourism"), 4).alias(
            f"app_std_poi_travel_tourism{suffix}"
        ),
        # max / min
        F.round(F.max("perc_poi_cnt_daily_life"), 4).alias(
            f"app_max_poi_daily_life{suffix}"
        ),
        F.round(F.max("perc_poi_cnt_shopping"), 4).alias(f"app_max_poi_shopping{suffix}"),
        F.round(F.max("perc_poi_cnt_leisure"), 4).alias(f"app_max_poi_leisure{suffix}"),
        F.round(F.max("perc_poi_cnt_travel_tourism"), 4).alias(
            f"app_max_poi_travel_tourism{suffix}"
        ),
        F.round(F.min("perc_poi_cnt_daily_life"), 4).alias(
            f"app_min_poi_daily_life{suffix}"
        ),
        F.round(F.min("perc_poi_cnt_shopping"), 4).alias(f"app_min_poi_shopping{suffix}"),
        F.round(F.min("perc_poi_cnt_leisure"), 4).alias(f"app_min_poi_leisure{suffix}"),
        F.round(F.min("perc_poi_cnt_travel_tourism"), 4).alias(
            f"app_min_poi_travel_tourism{suffix}"
        ),
        # dominant category counts
        F.sum((F.col("dominant_poi_type") == "daily_life").cast("int")).alias(
            f"app_cnt_dominant_daily_life{suffix}"
        ),
        F.sum((F.col("dominant_poi_type") == "shopping").cast("int")).alias(
            f"app_cnt_dominant_shopping{suffix}"
        ),
        F.sum((F.col("dominant_poi_type") == "leisure").cast("int")).alias(
            f"app_cnt_dominant_leisure{suffix}"
        ),
        F.sum((F.col("dominant_poi_type") == "travel_tourism").cast("int")).alias(
            f"app_cnt_dominant_travel{suffix}"
        ),
        # dominant category ratios
        F.round(
            F.try_divide(
                F.sum((F.col("dominant_poi_type") == "daily_life").cast("int")),
                F.count("dominant_poi_type"),
            ),
            4,
        ).alias(f"app_ratio_dominant_daily_life{suffix}"),
        F.round(
            F.try_divide(
                F.sum((F.col("dominant_poi_type") == "shopping").cast("int")),
                F.count("dominant_poi_type"),
            ),
            4,
        ).alias(f"app_ratio_dominant_shopping{suffix}"),
        F.round(
            F.try_divide(
                F.sum((F.col("dominant_poi_type") == "leisure").cast("int")),
                F.count("dominant_poi_type"),
            ),
            4,
        ).alias(f"app_ratio_dominant_leisure{suffix}"),
        F.round(
            F.try_divide(
                F.sum((F.col("dominant_poi_type") == "travel_tourism").cast("int")),
                F.count("dominant_poi_type"),
            ),
            4,
        ).alias(f"app_ratio_dominant_travel{suffix}"),
        # entropy mean
        F.round(F.mean("entropy"), 4).alias(f"app_avg_poi_entropy{suffix}"),
    )

    return _fill_nulls_and_cast(agg_df)

class CustomerAppBehaviorFeatures:
    """
    Customer application behavior feature engineering module.
    """

    def __init__(self, config_path: Path, execution_date: Optional[str] = None) -> None:
        self.spark = get_spark()
        self.spark.conf.set("spark.sql.debug.maxToStringFields", "1000")
        self.config_path = config_path
        self.execution_date = get_execution_date(execution_date)

    def run(self) -> None:
        """
        Main data processing pipeline.
        
        Returns:
            None
        """
        logger.info(f"Starting customer application behavioral feature engineering with config: {self.config_path}")
        try:
            # Load pipeline configuration
            pipeline_config = load_single_config(PipelineConfig, self.config_path)
            input = pipeline_config.feature_engineering.input
            output = pipeline_config.feature_engineering.output

            # Load data
            app_feat_df = load_data(input.get('app_behavior_feat').get('file_path')).drop('dl_data_dt','dl_load_ts')   
            start_date = start_of_month_n_months_ago(self.execution_date, WINDOW_SIZE)
            app_feat_df = app_feat_df.filter(
                (F.col("app_log_ts") < self.execution_date) & (F.col("app_log_ts") >= start_date)
            )

            agg_df_list: List[DataFrame] = []

            for i in range(1, WINDOW_SIZE + 1):
                agg_df = _build_agg_for_window(app_feat_df, self.execution_date, i)
                agg_df_list.append(agg_df)

            # Iteratively left-join on user_id
            result_df = agg_df_list[0]
            for df in agg_df_list[1:]:
                result_df = result_df.join(df, on="user_id", how="left")
            
            # Flag save time
            result_df = result_df.withColumn("dl_data_dt", F.lit(self.execution_date).cast('date'))
            result_df = result_df.withColumn("dl_load_ts", F.lit(datetime.now()))

            # Write data
            write_data(result_df, output.get('file_path').replace('${execution_date}', self.execution_date))
            logger.info("Customer application behavioral feature engineering completed successfully")
            
        except Exception as e:
            logger.error(f"Pipeline failed: {str(e)}")
            raise