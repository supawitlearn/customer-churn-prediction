"""
Reservation behavioral feature engineering module.

This module generates features based on reservation patterns, temporal characteristics,
and distance imputation for churn prediction modeling.
"""

# import necessary libraries
from typing import List, Tuple
from pyspark.sql import DataFrame, Window, functions as F
from sklearn.linear_model import LinearRegression
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# import project modules
from src.churn_prediction.logger import logger
from src.churn_prediction.constants.feature_engineering.reserv_const import (
    WEEKDAYS,
    DATE_TYPES,
    TIME_PERIODS,
    DISTANCE_IMPUTATION_COLS,
    PREDICTORS,
    TARGET,
)
from src.churn_prediction.pydantic.pipeline_config import PipelineConfig
from src.churn_prediction.utils.common import get_execution_date, get_spark, load_single_config
from src.churn_prediction.utils.loaders import load_data
from src.churn_prediction.utils.writers import write_data

def distance_imputation(base_df: DataFrame) -> DataFrame:
    """
    Impute missing distance values using linear regression.

    Uses trip_hour as a predictor to fill in missing distance values
    via a trained linear regression model.

    Args:
        base_df: Input Spark DataFrame with distance values to impute.

    Returns:
        Spark DataFrame with imputed distance values.
    """
    logger.info("Starting distance imputation")
    spark = get_spark()
    
    try:
        # Convert to pandas for imputation
        logger.debug("Converting distance data to pandas")
        distance_df = base_df.select(DISTANCE_IMPUTATION_COLS).toPandas()
        
        # Split into training and prediction datasets
        df_train = distance_df[distance_df[TARGET].notna()].copy()
        df_pred = distance_df[distance_df[TARGET].isna()].copy()
        logger.info(f"Training samples: {len(df_train)}, Prediction samples: {len(df_pred)}")

        # Train regression model
        logger.debug("Training linear regression model for distance imputation")
        X_train = df_train[PREDICTORS].values
        y_train = df_train[TARGET].values
        model = LinearRegression()
        model.fit(X_train, y_train)
        logger.debug(f"Model trained with coefficient: {model.coef_[0]:.4f}")

        # Predict missing values
        logger.debug("Predicting missing distance values")
        X_pred = df_pred[PREDICTORS].values
        y_pred = model.predict(X_pred)
        logger.info(f"Predicted {len(y_pred)} missing distance values")

        distance_df.loc[distance_df[TARGET].isna(), TARGET] = y_pred
        logger.info("Distance imputation completed successfully")
        return spark.createDataFrame(distance_df)
    except Exception as e:
        logger.error(f"Error during distance imputation: {e}")
        raise

def _categorize_time_period(hour_col: str) -> F.Column:
    """
    Create a time period category based on hour of day.

    Args:
        hour_col: Column name containing hour values.

    Returns:
        Spark Column expression with time period categorization.
    """
    return (
        F.when((F.hour(hour_col) >= 0) & (F.hour(hour_col) < 6), "early_morning")
        .when((F.hour(hour_col) >= 6) & (F.hour(hour_col) < 10), "morning_peak")
        .when((F.hour(hour_col) >= 10) & (F.hour(hour_col) < 16), "daytime")
        .when((F.hour(hour_col) >= 16) & (F.hour(hour_col) < 20), "evening_peak")
        .otherwise("late_night")
    )

def _pivot_and_summarize(
    df: DataFrame, groupby_col: str, pivot_col: str, pivot_values: List[str]
) -> DataFrame:
    """
    Pivot a DataFrame and calculate percentages for each category.

    Args:
        df: Input Spark DataFrame.
        groupby_col: Column to group by.
        pivot_col: Column to pivot on.
        pivot_values: List of values to pivot.

    Returns:
        Pivoted DataFrame with counts and percentages.
    """
    logger.debug(f"Pivoting {pivot_col} grouped by {groupby_col}")
    try:
        counts_df = df.groupBy(groupby_col, pivot_col).count()
        pivot_df = counts_df.groupBy(groupby_col).pivot(pivot_col, pivot_values).agg(F.first("count"))
        pivot_df = pivot_df.fillna(0)
        
        sum_col = f"sum_{pivot_col}"
        pivot_df = pivot_df.withColumn(sum_col, sum(F.col(val) for val in pivot_values))
        
        for value in pivot_values:
            pivot_df = pivot_df.withColumnRenamed(value, f"cnt_{value}")
            pivot_df = pivot_df.withColumn(
                f"perc_{value}",
                F.round(F.col(f"cnt_{value}") / F.col(sum_col), 3),
            )
        
        logger.debug(f"Successfully pivoted {pivot_col}")
        return pivot_df
    except Exception as e:
        logger.error(f"Error during pivot and summarize for {pivot_col}: {e}")
        raise

def clean_registed_time(base_df: DataFrame) -> DataFrame:
    """
    Clean and impute missing registed_time values.

    Imputes missing registed_time with the earliest txn_ts per user.

    Args:
        base_df: Input Spark DataFrame with registed_time.
    
    Returns:
        DataFrame with cleaned registed_time.
    """
    logger.info("Starting registed_time cleaning and imputation")
    try:
        logger.debug("Calculating earliest txn_ts per user for imputation")
        imputed_registed_time_df = base_df.groupBy("user_id").agg(
            F.min(F.col("txn_ts")).alias("imputed_registed_time")
        )
        
        logger.debug("Imputing missing registed_time values")
        base_df = base_df.join(
            imputed_registed_time_df, on="user_id", how="left"
        ).withColumn(
            "registed_time",
            F.when(
                F.col("registed_time").isNull(), F.col("imputed_registed_time")
            ).otherwise(F.col("registed_time")),
        ).drop("imputed_registed_time")
        
        logger.info("registed_time cleaning and imputation completed successfully")
        return base_df
    except Exception as e:
        logger.error(f"Error during registed_time cleaning: {e}")
        raise

def reservation_date_features(
    base_df: DataFrame, holiday_master_df: DataFrame
) -> DataFrame:
    """
    Extract reservation date-based features.

    Features include:
    - Weekday distribution (counts and percentages)
    - Date type distribution (holiday, weekend, weekday)
    - Start and stop time periods

    Args:
        base_df: Input Spark DataFrame with reservation data.
        holiday_master_df: DataFrame containing holiday information.

    Returns:
        DataFrame with added reservation date features.
    """
    logger.info("Starting reservation date features extraction")
    try:
        # Filter holidays and prepare weekday data
        logger.debug("Filtering holiday master data")
        holiday_master_df = holiday_master_df.filter(
            F.col("type") == "National holiday"
        ).select(["date", "type"])
        
        logger.debug("Preparing weekday data")
        weekday_df = base_df.select(
            ["txn_id", "reserve_start_time", "reserve_stop_time"]
        ).withColumn("date_seq", F.expr("sequence(reserve_start_time, reserve_stop_time)"))
        
        weekday_df = (
            weekday_df.withColumn("date", F.explode("date_seq"))
            .withColumn("date", F.col("date").cast("date"))
            .withColumn("weekday", F.lower(F.date_format("date", "EEEE")))
        )

        # Weekday features
        logger.debug("Extracting weekday features")
        weekday_pivot = _pivot_and_summarize(weekday_df, "txn_id", "weekday", WEEKDAYS)

        # Date type features
        logger.debug("Extracting date type features")
        date_type_df = weekday_df.join(holiday_master_df, on="date", how="left").withColumn(
            "date_type",
            F.when(F.col("type").isNotNull(), "holiday")
            .when(F.col("weekday").isin(["saturday", "sunday"]), "weekend")
            .otherwise(F.lit("weekday")),
        )
        date_type_pivot = _pivot_and_summarize(
            date_type_df, "txn_id", "date_type", DATE_TYPES
        )

        # Time period features
        logger.debug("Extracting time period features")
        start_time_df = weekday_df.withColumn(
            "reserve_start_period", _categorize_time_period("reserve_start_time")
        )
        stop_time_df = weekday_df.withColumn(
            "reserve_stop_period", _categorize_time_period("reserve_stop_time")
        )

        # Join all features
        logger.debug("Joining all date features")
        result_df = (
            base_df.join(weekday_pivot, on="txn_id", how="left")
            .join(date_type_pivot, on="txn_id", how="left")
            .join(
                start_time_df.select("txn_id", "reserve_start_period").distinct(),
                on="txn_id",
                how="left",
            )
            .join(
                stop_time_df.select("txn_id", "reserve_stop_period").distinct(),
                on="txn_id",
                how="left",
            )
        )
        logger.info("Reservation date features extraction completed")
        return result_df
    except Exception as e:
        logger.error(f"Error during reservation date features extraction: {e}")
        raise

def add_time_difference_column(
    df: DataFrame,
    partition_col: str = "user_id",
    order_col: str = "txn_ts",
    output_col: str = "days_btw_reservations"
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
                / 60 / 60 / 24,
                2
            )
        )
        .drop('previous_ts')
    )

def _prepare_base_dataframe(
    reservation_txn_fact_df: DataFrame,
    customer_profile_dim_df: DataFrame,
    customer_group_dim_df: DataFrame,
    station_location_profile_feat_df: DataFrame,
) -> DataFrame:
    """
    Prepare base DataFrame by joining fact and dimension tables.

    Args:
        reservation_txn_fact_df: Transaction fact table.
        customer_profile_dim_df: Customer profile dimension.
        customer_group_dim_df: Customer group dimension.
        station_location_profile_feat_df: Station location features.

    Returns:
        Joined base DataFrame with irrelevant columns dropped.
    """
    logger.info("Starting base DataFrame preparation")
    try:
        logger.debug("Joining fact and dimension tables")
        base_df = (
            reservation_txn_fact_df.join(
                customer_profile_dim_df, on="user_id", how="left"
            )
            .join(customer_group_dim_df, on="group_id", how="left")
            .join(station_location_profile_feat_df, on="station_id", how="left")
        )
        
        logger.debug("Dropping irrelevant columns")
        base_df = base_df.drop("dl_data_dt", "dl_load_ts")
        logger.info(f"Base DataFrame prepared with {base_df.count()} rows")
        return base_df
    except Exception as e:
        logger.error(f"Error during base DataFrame preparation: {e}")
        raise


def _filter_base_dataframe(base_df: DataFrame) -> DataFrame:
    """
    Apply business logic filters to base DataFrame.

    Filters out invalid users, stations, groups, admins, and foreigners.

    Args:
        base_df: Input DataFrame to filter.

    Returns:
        Filtered DataFrame.
    """
    logger.info("Applying business logic filters to base DataFrame")
    try:
        initial_count = base_df.count()
        filtered_df = base_df.filter(
            (F.col("user_id") != "0")
            & (F.col("station_id") != "0")
            & (~F.col("group_id").isin(["", "1", "2", "4", "330", "356"]))
            & (F.col("admin_id") == "0")
            & (F.col("foreigner") == "0")
        )
        final_count = filtered_df.count()
        logger.info(f"Filtering completed: {initial_count} -> {final_count} rows (removed {initial_count - final_count})")
        return filtered_df
    except Exception as e:
        logger.error(f"Error during base DataFrame filtering: {e}")
        raise

def _add_duration_features(base_df: DataFrame) -> DataFrame:
    """
    Add duration-based features and apply filters.

    Args:
        base_df: Input DataFrame.

    Returns:
        DataFrame with duration features added.
    """
    logger.info("Adding duration features")
    try:
        logger.debug("Calculating trip_hour feature")
        base_df = base_df.withColumn(
            "trip_hour",
            F.round(
                (F.col("reserve_stop_time").cast("long") - F.col("reserve_start_time").cast("long")) / 3600,
                2,
            ),
        )
        
        initial_count = base_df.count()
        base_df = base_df.filter(F.col("trip_hour") < 720)
        after_filter_count = base_df.count()
        logger.info(f"Duration filter applied: removed {initial_count - after_filter_count} rows with duration >= 720 hours")
        
        # Outlier detection: unrealistic distance for short duration
        logger.debug("Applying outlier detection for distance")
        base_df = base_df.withColumn(
            "distance",
            F.when(
                (F.col("distance") > 4000) & (F.col("trip_hour") < 600), None
            ).otherwise(F.col("distance")),
        )
        logger.info("Duration features added successfully")
        return base_df
    except Exception as e:
        logger.error(f"Error during duration features addition: {e}")
        raise

def _add_booking_lead_time(base_df: DataFrame) -> DataFrame:
    """
    Add booking lead time feature.

    Args:
        base_df: Input DataFrame.

    Returns:
        DataFrame with booking lead time added.
    """
    logger.info("Adding booking lead time features")
    try:
        logger.debug("Calculating booking_lead_time_hours feature")
        base_df = base_df.withColumn(
            "booking_lead_time_hours",
            F.round(
                (F.col("reserve_start_time").cast("long") - F.col("txn_ts").cast("long")) / 3600,
                2,
            ),
        )
        logger.info("Booking lead time features added successfully")
        return base_df
    except Exception as e:
        logger.error(f"Error during booking lead time feature addition: {e}")
        raise

class ReservationBehavioralFeatures:
    """
    Reservation Behavioral Features Engineering Module.
    """

    def __init__(self, config_path: Path, execution_date: Optional[str] = None) -> None:
        self.config_path = config_path
        self.execution_date = get_execution_date(execution_date)

    def run(self) -> None:
        """
        Main function to create all reservation behavioral features.

        Returns:
            None
        """
        logger.info(f"Starting reservation behavioral feature engineering with config: {self.config_path}")
        try:
            # Load pipeline configuration
            pipeline_config = load_single_config(PipelineConfig, self.config_path)
            input = pipeline_config.feature_engineering.input
            output = pipeline_config.feature_engineering.output
            logger.debug(f"Configuration loaded successfully")
        
            # Load data
            reservation_txn_fact_df = load_data(input.get('reservation_txn_fact').get('file_path'))            
            customer_profile_dim_df = load_data(input.get('customer_profile_dim').get('file_path'))            
            customer_group_dim_df = load_data(input.get('customer_group_dim').get('file_path'))            
            station_location_profile_feat_df = load_data(input.get('station_location_profile_feat').get('file_path'))            
            holiday_master_df = load_data(input.get('holiday_master').get('file_path'))
            
            # Prepare and filter base data
            logger.info("Preparing base dataframe")
            base_df = _prepare_base_dataframe(
                reservation_txn_fact_df,
                customer_profile_dim_df,
                customer_group_dim_df,
                station_location_profile_feat_df,
            )
            
            logger.info("Filtering base dataframe")
            base_df = _filter_base_dataframe(base_df)

            # Add duration features and filter
            logger.info("Adding duration features")
            base_df = _add_duration_features(base_df)

            # Impute missing distances
            logger.info("Imputing missing distances")
            distance_imputed_df = distance_imputation(base_df)
            base_df = base_df.drop("distance").join(
                distance_imputed_df.select("txn_id", "distance"), on="txn_id", how="left"
            )
            logger.debug(f"Distance imputation completed")

            # Add reservation date features
            logger.info("Adding reservation date features")
            base_df = reservation_date_features(base_df, holiday_master_df)

            # Clean total_price
            base_df = base_df.withColumn("total_price", F.col("hour_price") + F.col("distance_price") - F.col("discount"))

            # Clean registed_time
            logger.info("Cleaning registed_time features")
            base_df = clean_registed_time(base_df)

            # Add booking lead time
            logger.info("Adding booking lead time features")
            base_df = _add_booking_lead_time(base_df)

            # Add days between reservations
            base_df = add_time_difference_column(
                base_df,
                partition_col="user_id",
                order_col="txn_ts",
                output_col="days_btw_reservations"
            )

            # Flag save time
            base_df = base_df.withColumn("dl_data_dt", F.lit(self.execution_date).cast('date'))
            base_df = base_df.withColumn("dl_load_ts", F.lit(datetime.now()))

            # Write data
            write_data(base_df, output.get('file_path'))
            logger.info("Reservation behavioral feature engineering completed successfully")

        except Exception as e:
            logger.exception("Error in feature engineering reservation_behavioral_feat: %s", e)
            raise
