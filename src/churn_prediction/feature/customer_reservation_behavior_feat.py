from datetime import datetime, date
from functools import reduce
from typing import Dict, List, Optional
from pyspark.sql import DataFrame
from pyspark.sql import functions as F
from pathlib import Path

# import project modules
from src.churn_prediction.logger import logger
from src.churn_prediction.constants.feature_engineering.churn_const import OBSERVE_PERIOD, ACTIVE_PERIOD
from src.churn_prediction.constants.feature_engineering.reserv_const import STATE_GROUPS, STATE_KEYS, CAPPED_MAX
from src.churn_prediction.pydantic.pipeline_config import PipelineConfig
from src.churn_prediction.utils.common import load_single_config, get_execution_date, get_spark, start_of_month_n_months_ago, end_of_month_n_months_ago
from src.churn_prediction.utils.loaders import load_data
from src.churn_prediction.utils.writers import write_data


# ---------------------------------------------------------------------------
# Core aggregation helpers
# ---------------------------------------------------------------------------

def _aggregate_for_state(
    base_df: DataFrame,
    state_key: str,
    suffix: str,
) -> DataFrame:
    """
    Aggregate reservation features for a given state group and window suffix.
    """
    state_values = STATE_GROUPS[state_key]
    reserv_df = base_df.filter(F.col("reservation_state").isin(state_values))

    agg_df = reserv_df.groupBy("user_id").agg(
        # Reservation stats
        F.count("txn_id").alias(f"reserv_cnt_{state_key}_reservations{suffix}"),
        F.sum(F.when(F.col("promotion_code").isNotNull(), 1).otherwise(0)).alias(
            f"reserv_cnt_{state_key}_promotions_used{suffix}"
        ),

        # Amount stats (avg + total only)
        F.round(F.avg("discount"), 4).alias(
            f"reserv_avg_{state_key}_discount_amount{suffix}"
        ),
        F.round(F.sum("discount"), 4).alias(
            f"reserv_tot_{state_key}_discount_amount{suffix}"
        ),
        F.round(F.avg("hour_price"), 4).alias(
            f"reserv_avg_{state_key}_hour_price{suffix}"
        ),
        F.round(F.sum("hour_price"), 4).alias(
            f"reserv_tot_{state_key}_hour_price{suffix}"
        ),
        F.round(F.avg("distance_price"), 4).alias(
            f"reserv_avg_{state_key}_distance_price{suffix}"
        ),
        F.round(F.sum("distance_price"), 4).alias(
            f"reserv_tot_{state_key}_distance_price{suffix}"
        ),
        F.round(F.avg("total_price"), 4).alias(
            f"reserv_avg_{state_key}_total_price{suffix}"
        ),
        F.round(F.sum("total_price"), 4).alias(
            f"reserv_tot_{state_key}_total_price{suffix}"
        ),

        # Station location stats
        F.sum(F.when(F.col("province") == "Bangkok", 1).otherwise(0)).alias(
            f"reserv_cnt_{state_key}_station_in_bkk{suffix}"
        ),
        F.sum(F.when(F.col("province") != "Bangkok", 1).otherwise(0)).alias(
            f"reserv_cnt_{state_key}_station_outside_bkk{suffix}"
        ),
        F.round(
            F.try_divide(
                F.sum(F.when(F.col("province") == "Bangkok", 1).otherwise(0)),
                F.count("reservation_state"),
            ),
            4,
        ).alias(f"reserv_ratio_{state_key}_station_in_bkk{suffix}"),

        # Station POI stats (means + dominant ratios + entropy)
        F.round(F.mean("perc_poi_cnt_daily_life"), 4).alias(
            f"reserv_avg_{state_key}_poi_daily_life{suffix}"
        ),
        F.round(F.mean("perc_poi_cnt_shopping"), 4).alias(
            f"reserv_avg_{state_key}_poi_shopping{suffix}"
        ),
        F.round(F.mean("perc_poi_cnt_leisure"), 4).alias(
            f"reserv_avg_{state_key}_poi_leisure{suffix}"
        ),
        F.round(F.mean("perc_poi_cnt_travel_tourism"), 4).alias(
            f"reserv_avg_{state_key}_poi_travel_tourism{suffix}"
        ),
        # dominant category counts
        F.sum((F.col("dominant_poi_type") == "daily_life").cast("int")).alias(
            f"reserv_cnt_{state_key}_dominant_daily_life{suffix}"
        ),
        F.sum((F.col("dominant_poi_type") == "shopping").cast("int")).alias(
            f"reserv_cnt_{state_key}_dominant_shopping{suffix}"
        ),
        F.sum((F.col("dominant_poi_type") == "leisure").cast("int")).alias(
            f"reserv_cnt_{state_key}_dominant_leisure{suffix}"
        ),
        F.sum((F.col("dominant_poi_type") == "travel_tourism").cast("int")).alias(
            f"reserv_cnt_{state_key}_dominant_travel{suffix}"
        ),
        # dominant category ratios
        F.round(
            F.try_divide(
                F.sum((F.col("dominant_poi_type") == "daily_life").cast("int")),
                F.count("dominant_poi_type"),
            ),
            4,
        ).alias(f"reserv_ratio_{state_key}_dominant_daily_life{suffix}"),
        F.round(
            F.try_divide(
                F.sum((F.col("dominant_poi_type") == "shopping").cast("int")),
                F.count("dominant_poi_type"),
            ),
            4,
        ).alias(f"reserv_ratio_{state_key}_dominant_shopping{suffix}"),
        F.round(
            F.try_divide(
                F.sum((F.col("dominant_poi_type") == "leisure").cast("int")),
                F.count("dominant_poi_type"),
            ),
            4,
        ).alias(f"reserv_ratio_{state_key}_dominant_leisure{suffix}"),
        F.round(
            F.try_divide(
                F.sum((F.col("dominant_poi_type") == "travel_tourism").cast("int")),
                F.count("dominant_poi_type"),
            ),
            4,
        ).alias(f"reserv_ratio_{state_key}_dominant_travel{suffix}"),
        # entropy mean
        F.round(F.mean("entropy"), 4).alias(
            f"reserv_avg_{state_key}_poi_entropy{suffix}"
        ),

        # Reservation day stats (totals + ratios)
        F.sum("cnt_holiday").alias(f"reserv_tot_{state_key}_holiday{suffix}"),
        F.sum("cnt_weekend").alias(f"reserv_tot_{state_key}_weekend{suffix}"),
        F.sum("cnt_weekday").alias(f"reserv_tot_{state_key}_weekday{suffix}"),
        F.round(
            F.try_divide(F.sum("cnt_holiday"), F.sum("sum_date_type")), 4
        ).alias(f"reserv_ratio_{state_key}_holiday{suffix}"),
        F.round(
            F.try_divide(F.sum("cnt_weekend"), F.sum("sum_date_type")), 4
        ).alias(f"reserv_ratio_{state_key}_weekend{suffix}"),
        F.round(
            F.try_divide(F.sum("cnt_weekday"), F.sum("sum_date_type")), 4
        ).alias(f"reserv_ratio_{state_key}_weekday{suffix}"),

        # Reservation time-of-day stats (counts + ratios)
        F.sum((F.col("reserve_start_period") == "daytime").cast("int")).alias(
            f"reserv_cnt_{state_key}_daytime{suffix}"
        ),
        F.sum((F.col("reserve_start_period") == "early_morning").cast("int")).alias(
            f"reserv_cnt_{state_key}_early_morning{suffix}"
        ),
        F.sum((F.col("reserve_start_period") == "morning_peak").cast("int")).alias(
            f"reserv_cnt_{state_key}_morning_peak{suffix}"
        ),
        F.sum((F.col("reserve_start_period") == "late_night").cast("int")).alias(
            f"reserv_cnt_{state_key}_late_night{suffix}"
        ),
        F.sum((F.col("reserve_start_period") == "evening_peak").cast("int")).alias(
            f"reserv_cnt_{state_key}_evening_peak{suffix}"
        ),
        F.round(
            F.try_divide(
                F.sum((F.col("reserve_start_period") == "daytime").cast("int")),
                F.count("reserve_start_period"),
            ),
            4,
        ).alias(f"reserv_ratio_{state_key}_daytime{suffix}"),
        F.round(
            F.try_divide(
                F.sum((F.col("reserve_start_period") == "early_morning").cast("int")),
                F.count("reserve_start_period"),
            ),
            4,
        ).alias(f"reserv_ratio_{state_key}_early_morning{suffix}"),
        F.round(
            F.try_divide(
                F.sum((F.col("reserve_start_period") == "morning_peak").cast("int")),
                F.count("reserve_start_period"),
            ),
            4,
        ).alias(f"reserv_ratio_{state_key}_morning_peak{suffix}"),
        F.round(
            F.try_divide(
                F.sum((F.col("reserve_start_period") == "late_night").cast("int")),
                F.count("reserve_start_period"),
            ),
            4,
        ).alias(f"reserv_ratio_{state_key}_late_night{suffix}"),
        F.round(
            F.try_divide(
                F.sum((F.col("reserve_start_period") == "evening_peak").cast("int")),
                F.count("reserve_start_period"),
            ),
            4,
        ).alias(f"reserv_ratio_{state_key}_evening_peak{suffix}"),

        # Trip hour and distance (avg + total)
        F.round(F.avg("trip_hour"), 4).alias(
            f"reserv_avg_{state_key}_trip_hour{suffix}"
        ),
        F.round(F.sum("trip_hour"), 4).alias(
            f"reserv_tot_{state_key}_trip_hour{suffix}"
        ),
        F.round(F.avg("distance"), 4).alias(
            f"reserv_avg_{state_key}_distance{suffix}"
        ),
        F.round(F.sum("distance"), 4).alias(
            f"reserv_tot_{state_key}_distance{suffix}"
        ),

        # Booking lead time & days between reservations (averages only)
        F.round(F.avg("booking_lead_time_hours"), 4).alias(
            f"reserv_avg_{state_key}_booking_lead_time_hours{suffix}"
        ),
        F.round(F.avg("days_btw_reservations"), 4).alias(
            f"reserv_avg_{state_key}_days_btw_reservations{suffix}"
        ),
    )

    return agg_df


def _clean_and_cast_agg(result_df: DataFrame) -> DataFrame:
    """
    Replace null/NaN with 0 and cast counts to int, others to Decimal(28,4).
    """
    for col_name in result_df.columns:
        if col_name == "user_id":
            continue

        # Fill nulls / NaNs with 0.0
        result_df = result_df.withColumn(
            col_name,
            F.when(F.col(col_name).isNull(), 0.0).otherwise(F.col(col_name)),
        )
        result_df = result_df.withColumn(
            col_name,
            F.when(F.isnan(col_name), 0.0).otherwise(F.col(col_name)),
        )

        # Cast types by naming convention
        if col_name.startswith("reserv_cnt_"):
            result_df = result_df.withColumn(col_name, F.col(col_name).cast("int"))
        else:
            result_df = result_df.withColumn(
                col_name, F.col(col_name).cast("decimal(28,4)")
            )

    return result_df


# ---------------------------------------------------------------------------
# Main feature builder
# ---------------------------------------------------------------------------

def build_reservation_features(
    execution_date: str,
    reserv_feat_df: DataFrame,
    cust_active_feat_df: DataFrame,
) -> DataFrame:
    """
    Build reservation-based features for 30/60/90 day windows from execution_date.

    Parameters
    ----------
    execution_date : str
        As-of date in 'YYYY-MM-DD' format.
    reserv_feat_df : DataFrame
        Reservation feature DataFrame.
    cust_app_feat_df : DataFrame
        Customer app behavior feature DataFrame.

    Returns
    -------
    DataFrame
        One row per user_id with aggregated reservation features.
    """
    # Global observation window filter
    observ_start_date = start_of_month_n_months_ago(execution_date, OBSERVE_PERIOD)
    observ_end_date = end_of_month_n_months_ago(execution_date, 0)
    reserv_feat_df = reserv_feat_df.filter(
        (F.col("txn_ts") <= observ_end_date)
        & (F.col("txn_ts") >= observ_start_date)
    )

    # Filter active users only
    reserv_feat_df = reserv_feat_df.join(F.broadcast(cust_active_feat_df), on="user_id", how="inner")

    # Per-window aggregates (30 / 60 / 90 days)
    result_df_list: List[DataFrame] = []

    for i in range(1, 4):
        suffix = f"_last_{i * 30}d"
        start_date = start_of_month_n_months_ago(execution_date, i)

        base_df = reserv_feat_df.filter(F.col("txn_ts") >= start_date)

        agg_df_list: List[DataFrame] = []

        for state_key in STATE_KEYS:
            agg_df_list.append(_aggregate_for_state(base_df, state_key, suffix))

        # Join all per-state aggregates for this window
        window_df = reduce(
            lambda df1, df2: df1.join(df2, on="user_id", how="outer"),
            agg_df_list,
        )

        # Ratios of reservations by state vs overall for this window
        window_df = window_df.withColumn(
            f"reserv_ratio_completed_reservations{suffix}",
            F.round(
                F.try_divide(
                    F.col(f"reserv_cnt_completed_reservations{suffix}"),
                    F.col(f"reserv_cnt_overall_reservations{suffix}"),
                ),
                4,
            ),
        )
        window_df = window_df.withColumn(
            f"reserv_ratio_cancelled_reservations{suffix}",
            F.round(
                F.try_divide(
                    F.col(f"reserv_cnt_cancelled_reservations{suffix}"),
                    F.col(f"reserv_cnt_overall_reservations{suffix}"),
                ),
                4,
            ),
        )
        window_df = window_df.withColumn(
            f"reserv_ratio_rejected_reservations{suffix}",
            F.round(
                F.try_divide(
                    F.col(f"reserv_cnt_rejected_reservations{suffix}"),
                    F.col(f"reserv_cnt_overall_reservations{suffix}"),
                ),
                4,
            ),
        )

        window_df = _clean_and_cast_agg(window_df)
        result_df_list.append(window_df)

    # Join all windows together
    stat_df = reduce(
        lambda df1, df2: df1.join(df2, on="user_id", how="outer"),
        result_df_list,
    )

    # -----------------------------------------------------------------------
    # Customer info features
    # -----------------------------------------------------------------------
    cust_info_df = reserv_feat_df.groupBy("user_id").agg(
        F.any_value("birthdate").alias("birthdate"),
        F.any_value("registed_time").alias("registed_time"),
    )

    cust_info_df = cust_info_df.withColumn(
        "reserv_age",
        F.floor(F.months_between(F.lit(execution_date), F.col("birthdate")) / 12),
    ).withColumn(
        "reserv_membership_duration",
        F.round(
            F.months_between(F.lit(execution_date), F.col("registed_time")),
            2,
        ),
    ).drop("birthdate", "registed_time")

    # -----------------------------------------------------------------------
    # Recency features (per user, per state, by different timestamps)
    # -----------------------------------------------------------------------
    recency_base_df = reserv_feat_df  # already filtered to 90d; if you want lifetime, use original data

    recency_df = recency_base_df.groupBy("user_id").agg(
        # txn_ts recency
        F.max(
            F.when(
                F.col("reservation_state").isin(["COMPLETE", "FINISH", "RESERVE", "DRIVE"]),
                F.col("txn_ts"),
            )
        ).alias("reserv_last_completed_txn_ts"),
        F.max(
            F.when(F.col("reservation_state") == "CANCEL", F.col("txn_ts"))
        ).alias("reserv_last_cancelled_txn_ts"),
        F.max(
            F.when(F.col("reservation_state") == "REJECT", F.col("txn_ts"))
        ).alias("reserv_last_rejected_txn_ts"),

        # reserve_start_time recency
        F.max(
            F.when(
                F.col("reservation_state").isin(["COMPLETE", "FINISH", "RESERVE", "DRIVE"]),
                F.col("reserve_start_time"),
            )
        ).alias("reserv_last_completed_reserve_start_time"),
        F.max(
            F.when(F.col("reservation_state") == "CANCEL", F.col("reserve_start_time"))
        ).alias("reserv_last_cancelled_reserve_start_time"),
        F.max(
            F.when(F.col("reservation_state") == "REJECT", F.col("reserve_start_time"))
        ).alias("reserv_last_rejected_reserve_start_time"),

        # reserve_stop_time recency
        F.max(
            F.when(
                F.col("reservation_state").isin(["COMPLETE", "FINISH", "RESERVE", "DRIVE"]),
                F.col("reserve_stop_time"),
            )
        ).alias("reserv_last_completed_reserve_stop_time"),
        F.max(
            F.when(F.col("reservation_state") == "CANCEL", F.col("reserve_stop_time"))
        ).alias("reserv_last_cancelled_reserve_stop_time"),
        F.max(
            F.when(F.col("reservation_state") == "REJECT", F.col("reserve_stop_time"))
        ).alias("reserv_last_rejected_reserve_stop_time"),
    )

    # Turn last_* timestamps into capped recency (days) features
    for col_name in recency_df.columns:
        if col_name == "user_id":
            continue

        recency_name = col_name.replace("last", "recency")
        recency_df = recency_df.withColumn(
            recency_name,
            F.datediff(F.lit(execution_date), F.col(col_name)).cast("int"),
        )
        recency_df = recency_df.withColumn(
            recency_name,
            F.when(F.col(recency_name) < 0, 0)  # clip future events
             .when(F.col(recency_name).isNull(), CAPPED_MAX)
             .otherwise(F.col(recency_name)),
        ).drop(col_name)

    # Final join
    final_df = (
        stat_df
        .join(cust_info_df, on="user_id", how="left")
        .join(recency_df, on="user_id", how="left")
    )

    return final_df

class CustomerReservationBehaviorFeatures:
    """
    Customer reservation behavior feature engineering module.
    """

    def __init__(self, config_path: Path, execution_date: Optional[str] = None) -> None:
        """
        Parameters
        ----------
        config_path : Path
            Path to the pipeline configuration file.
        execution_date : str, optional
            As-of date in 'YYYY-MM-DD' format. If None, uses get_execution_date()
            to infer the last day of the previous month.
        """
        self.spark = get_spark()
        # Allow large schema debug in logs when needed
        self.spark.conf.set("spark.sql.debug.maxToStringFields", "1000")

        self.config_path = config_path
        self.execution_date = get_execution_date(execution_date)

    def run(self) -> None:
        """
        Main data processing pipeline.
        
        Returns:
            None
        """
        logger.info(f"Starting customer reservation behavioral feature engineering with config: {self.config_path}")
        try:
            # Load pipeline configuration
            pipeline_config = load_single_config(PipelineConfig, self.config_path)
            input = pipeline_config.feature_engineering.input
            output = pipeline_config.feature_engineering.output

            # Load data
            reserv_feat_df = load_data(input.get('reservation_behavioral_feat').get('file_path')).drop('dl_data_dt','dl_load_ts')
            cust_active_feat_df = load_data(input.get('customer_active_feat').get('file_path').replace('${execution_date}', self.execution_date)).drop('dl_data_dt','dl_load_ts')

            # Build features
            logger.info("Building customer reservation behavioral features...")
            result_df = build_reservation_features(
                execution_date=self.execution_date,
                reserv_feat_df=reserv_feat_df,
                cust_active_feat_df=cust_active_feat_df,
            )
            
            # Flag save time
            result_df = result_df.withColumn("dl_data_dt", F.lit(self.execution_date).cast('date'))
            result_df = result_df.withColumn("dl_load_ts", F.lit(datetime.now()))

            # Write data
            write_data(result_df, output.get('file_path').replace('${execution_date}', self.execution_date))
            logger.info("Customer reservation behavioral feature engineering completed successfully")
            
        except Exception as e:
            logger.error(f"Pipeline failed: {str(e)}")
            raise
