# import necessary librariesv
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from pyspark.sql import DataFrame
from pyspark.sql import functions as F

# import project modules
from src.churn_prediction.logger import logger
from src.churn_prediction.pydantic.pipeline_config import PipelineConfig
from src.churn_prediction.utils.common import (
    get_execution_date,
    get_spark,
    start_of_month_n_months_ago,
    end_of_month_n_months_ago,
    load_single_config,
)
from src.churn_prediction.utils.loaders import load_data
from src.churn_prediction.utils.writers import write_data
from src.churn_prediction.constants.feature_engineering.app_const import ACTIVE_EVENTS
from src.churn_prediction.constants.feature_engineering.churn_const import ACTIVE_PERIOD
from src.churn_prediction.constants.feature_engineering.reserv_const import STATE_GROUPS


def get_app_active_users(
    app_feat_df: DataFrame,
    active_start_date: str,
    active_end_date: str,
    active_events: Optional[List[str]] = None,
) -> DataFrame:
    """
    Get active users based on app events within a specified date range.

    Parameters
    ----------
    app_feat_df : DataFrame
        DataFrame containing app event logs with 'user_id', 'app_log_ts', and 'event_type' columns.
    active_start_date : str
        Start date for the active period (inclusive), in 'YYYY-MM-DD' or timestamp-compatible string.
    active_end_date : str
        End date for the active period (inclusive), in 'YYYY-MM-DD' or timestamp-compatible string.
    active_events : list[str], optional
        List of app event types considered as active. Defaults to ACTIVE_EVENTS.

    Returns
    -------
    DataFrame
        DataFrame of distinct active user_ids.
    """
    if active_events is None:
        active_events = ACTIVE_EVENTS

    return (
        app_feat_df.filter(
            (F.col("app_log_ts") >= active_start_date)
            & (F.col("app_log_ts") <= active_end_date)
            & (F.col("event_type").isin(active_events))
        )
        .select("user_id")
        .distinct()
    )


def get_reserv_active_users(
    reserv_feat_df: DataFrame,
    active_start_date: str,
    active_end_date: str,
    active_state_keys: List[str],
) -> DataFrame:
    """
    Get active users based on reservation activity within a specified date range.

    A user is considered active if ANY of the following are true
    within [active_start_date, active_end_date]:

    - reserve_start_time is in range AND reservation_state in active_state_keys
    - reserve_stop_time is in range  AND reservation_state in active_state_keys
    - txn_ts is in range AND reservation_state in STATE_GROUPS['overall']

    Parameters
    ----------
    reserv_feat_df : DataFrame
        DataFrame containing reservation logs with
        'user_id', 'reserve_start_time', 'reserve_stop_time', 'txn_ts',
        and 'reservation_state' columns.
    active_start_date : str
        Start date for the active period (inclusive).
    active_end_date : str
        End date for the active period (inclusive).
    active_state_keys : list[str]
        List of reservation states considered as active for start/stop checks.

    Returns
    -------
    DataFrame
        DataFrame of distinct active user_ids.
    """
    overall_states = STATE_GROUPS.get("overall", [])

    cond_start = (
        (F.col("reserve_start_time") >= active_start_date)
        & (F.col("reserve_start_time") <= active_end_date)
        & (F.col("reservation_state").isin(active_state_keys))
    )
    cond_stop = (
        (F.col("reserve_stop_time") >= active_start_date)
        & (F.col("reserve_stop_time") <= active_end_date)
        & (F.col("reservation_state").isin(active_state_keys))
    )
    cond_txn = (
        (F.col("txn_ts") >= active_start_date)
        & (F.col("txn_ts") <= active_end_date)
        & (F.col("reservation_state").isin(overall_states))
    )

    return (
        reserv_feat_df.filter(cond_start | cond_stop | cond_txn)
        .select("user_id")
        .distinct()
    )


class CustomerActiveFeatures:
    """
    Customer active users identification module.

    Determines which customers are "active" in a given period based on:
    - App activity (ACTIVE_EVENTS) within [active_start_date, active_end_date]
    - Reservation activity (completed + cancelled states, plus any txn in overall states)
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

    def _compute_active_period(self) -> tuple[str, str]:
        """
        Compute active period [start_date, end_date] based on execution_date and ACTIVE_PERIOD.

        Returns
        -------
        (str, str)
            active_start_date, active_end_date in 'YYYY-MM-DD' format.
        """
        active_start_date = start_of_month_n_months_ago(
            self.execution_date,
            ACTIVE_PERIOD,
        )
        # end_of_month_n_months_ago(self.execution_date, 0) is equivalent to end of execution month
        active_end_date = end_of_month_n_months_ago(self.execution_date, 0)
        return active_start_date, active_end_date

    def run(self) -> None:
        """
        Identify active users based on app and reservation activity and write output.

        Side effects
        ------------
        - Reads input datasets specified in PipelineConfig.
        - Writes active user IDs with dl_data_dt and dl_load_ts columns.
        """
        logger.info(
            "Starting customer active user identification with config: %s "
            "and execution_date: %s",
            self.config_path,
            self.execution_date,
        )

        try:
            # Load pipeline configuration
            pipeline_config = load_single_config(PipelineConfig, self.config_path)
            fe_config = pipeline_config.feature_engineering
            input_cfg = fe_config.input
            output_cfg = fe_config.output

            # Define active period
            active_start_date, active_end_date = self._compute_active_period()
            active_state_keys = (
                STATE_GROUPS.get("completed", [])
                + STATE_GROUPS.get("cancelled", [])
            )

            logger.info(
                "Active period: %s to %s, active reservation states: %s",
                active_start_date,
                active_end_date,
                active_state_keys,
            )

            # Load data
            app_feat_path = input_cfg.get("app_behavior_feat", {}).get("file_path")
            reserv_feat_path = input_cfg.get("reservation_behavioral_feat", {}).get("file_path")

            if not app_feat_path or not reserv_feat_path:
                raise ValueError("Input file paths for app_behavior_feat or reservation_behavioral_feat are missing")

            app_feat_df = load_data(app_feat_path).drop("dl_data_dt", "dl_load_ts")
            reserv_feat_df = load_data(reserv_feat_path).drop("dl_data_dt", "dl_load_ts")

            # Active users from app events
            app_active_df = get_app_active_users(
                app_feat_df,
                active_start_date,
                active_end_date,
            )

            # Active users from reservations
            reserv_active_df = get_reserv_active_users(
                reserv_feat_df,
                active_start_date,
                active_end_date,
                active_state_keys,
            )

            # Union sources to get final active users
            active_users_df = app_active_df.union(reserv_active_df).distinct()

            # Add load metadata
            active_users_df = (
                active_users_df
                .withColumn("dl_data_dt", F.lit(self.execution_date).cast("date"))
                .withColumn("dl_load_ts", F.lit(datetime.now()))
            )

            # Write output
            output_path_template = output_cfg.get("file_path")
            if not output_path_template:
                raise ValueError("Output file_path is missing in pipeline configuration")

            output_path = output_path_template.replace(
                "${execution_date}",
                self.execution_date,
            )

            write_data(active_users_df, output_path)
            logger.info("Customer active user identification completed successfully")

        except Exception as e:
            logger.exception(
                "Error during customer active user identification: %s", e
            )
            raise
