# import necessary libraries
from pathlib import Path
from datetime import datetime
from pyspark.sql import functions as F
from pyspark.sql import DataFrame
from typing import Dict, Any, Union, List
from dateutil.relativedelta import relativedelta

# import project modules
from src.churn_prediction.logger import logger
from src.churn_prediction.pydantic.data_transformation_config import DataTransformationConfig
from src.churn_prediction.pydantic.pipeline_config import PipelineConfig
from src.churn_prediction.utils.common import load_single_config, get_execution_date, get_spark
from src.churn_prediction.utils.loaders import load_data
from src.churn_prediction.utils.writers import write_data

class DataTransformer:
    """
    Transforms data based on transformation configuration.
    """
    
    def __init__(self, config_path: str, execution_date: str = None) -> None:
        """
        Initialize transformer with config file.
        
        Args:
            config_path (str): Path to config YAML file
        """
        try:
            logger.info("Initializing DataTransformer...")

            # Load config
            self.config_path = Path(config_path)
            self.pipeline_config = load_single_config(PipelineConfig, self.config_path)
            self.execution_date = get_execution_date(execution_date) if execution_date else datetime.now().strftime("%Y-%m-%d")

            self.transformation_path = Path(self.pipeline_config.transformation.config_path)
            self.transformation_config = load_single_config(DataTransformationConfig, self.transformation_path)

            self.columns_config = self.transformation_config.columns
            self.transformation_config = self.transformation_config.transformation

            self.input_path = self.pipeline_config.transformation.input.get("file_path").replace("${execution_date}", self.execution_date)
            self.output_path = self.pipeline_config.transformation.output.get("file_path").replace("${execution_date}", self.execution_date)

        except Exception as e:
            logger.error(f"Error initializing DataTransformer: {e}")
            raise e
        
    def cast_data_types(self, df: DataFrame) -> DataFrame:
        """
        Cast columns to specified data types.
        
        Args:
            df (DataFrame): Input Spark DataFrame
            
        Returns:
            DataFrame: DataFrame with casted data types
        """
        logger.info("Casting data types...")
        for col_name, col_param in self.columns_config.items():
            if col_param.type:
                df = df.withColumn(col_name, F.col(col_name).cast(col_param.type))
        return df

    def first_date_of_month(self, df: DataFrame, target_column: Union[str, List[str]]) -> DataFrame:
        """
        Transform date column to first day of the month.
        
        Args:
            df (DataFrame): Input Spark DataFrame
            target_column (str): Name of the date column
            
        Returns:
            DataFrame: Transformed DataFrame
        """
        logger.info(f"Transforming {target_column} to first day of the month...")
        if isinstance(target_column, list):
            for column in target_column:
                df = df.withColumn(column, F.trunc(F.col(column), "MM"))
        else:
            df = df.withColumn(target_column, F.trunc(F.col(target_column), "MM"))
        return df


    def date_range(self, df: DataFrame, target_column: str, min: str, max: str) -> DataFrame:
        """
        Transform date column to be within a specific range.

        Args:
            df (DataFrame): Input Spark DataFrame
            target_column (str): Name of the date column
            min_years (int): Minimum age in years
            max_years (int): Maximum age in years

        Returns:
            DataFrame: Transformed DataFrame
        """

        def apply_date_offset(date_str: str, date_offset: str) -> str:
            """
            Apply a date offset like "Y=-3" or "M=+2" to a given date string.

            Args:
                date_str (str): Input date in 'YYYY-MM-DD' format.
                date_offset (str): Offset string, e.g., "Y=-3", "M=+2", "D=-10".

            Returns:
                str: Adjusted date in 'YYYY-MM-DD' format.
            """
            # Parse input date
            base_date = datetime.strptime(date_str, "%Y-%m-%d")

            # Parse offset
            if "=" not in date_offset:
                raise ValueError("Invalid date_offset format. Expected like 'Y=-3' or 'M=+2'.")
            
            unit, value = date_offset.split("=")
            value = int(value)

            # Apply offset using relativedelta
            if unit.upper() == "Y":
                result_date = base_date + relativedelta(years=value)
            elif unit.upper() == "M":
                result_date = base_date + relativedelta(months=value)
            elif unit.upper() == "D":
                result_date = base_date + relativedelta(days=value)
            else:
                raise ValueError("Invalid offset unit. Use 'Y', 'M', or 'D'.")

            return result_date.strftime("%Y-%m-%d")
        
        logger.info(f"Transforming {target_column} to be within {min} and {max} years...")
        min_date = apply_date_offset(self.execution_date, min)
        max_date = apply_date_offset(self.execution_date, max)
        df = df.withColumn(target_column, F.when(F.col(target_column) > max_date, F.lit(max_date))
                                           .when(F.col(target_column) < min_date, F.lit(min_date))
                                           .otherwise(F.col(target_column)))
        return df

    def not_future(self, df: DataFrame, target_column: str) -> DataFrame:
        """
        Transform date column to not exceed the execution date.

        Args:
            df (DataFrame): Input Spark DataFrame
            target_column (str): Name of the date column

        Returns:
            DataFrame: Transformed DataFrame
        """
        logger.info(f"Transforming {target_column} to not exceed execution date {self.execution_date}...")
        col_type = self.columns_config.get(target_column).type
        df = df.withColumn(target_column, F.when(F.col(target_column) > self.execution_date, F.lit(self.execution_date).cast(col_type))
                                           .otherwise(F.col(target_column)))
        return df


    def get_transformation_operations(self) -> Dict[str, Any]:
        """
        Get available transformation operations.
        """
        return {
            "first_date_of_month": self.first_date_of_month,
            "date_range": self.date_range,
            "not_future": self.not_future
        }

    def run(self) -> None:
        """
        Apply transformations to the DataFrame based on config.
        
        Args:
            df (DataFrame): Input Spark DataFrame
            
        Returns:
            DataFrame: Transformed DataFrame
        """
        try:
            logger.info("Starting data transformation process...")
            
            # Load data
            df = load_data(self.input_path)

            # Cast data types first
            df = self.cast_data_types(df)
            
            # Apply each transformation operation
            input_df = df
            if self.transformation_config:
                for _, transform in self.transformation_config.items():
                    kind = transform.kind
                    params = transform.parameters
                    params['df'] = input_df
                    func = getattr(self, kind, None)
                    if func is None:
                        raise AttributeError(f"Transformation function '{kind}' not found.")
                    input_df = func(**params)

            # Add dl_load_ts timestamps
            now_ts = datetime.now()
            input_df = input_df.withColumn("dl_load_ts", F.lit(now_ts))

            # Write transformed data
            write_data(input_df, self.output_path)

            logger.info("Data transformation completed.")

        except Exception as e:
            logger.exception(f"Error during data validation: {e}")
            raise e
