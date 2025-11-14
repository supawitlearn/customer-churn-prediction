# import necessary libraries
from pathlib import Path
from datetime import datetime
from typing import Optional
from pyspark.sql import functions as F
from pyspark.sql import DataFrame

# import project modules
from src.churn_prediction.logger import logger
from src.churn_prediction.pydantic.data_ingestion_config import DataIngestionConfig
from src.churn_prediction.pydantic.pipeline_config import PipelineConfig
from src.churn_prediction.utils.common import load_single_config, get_execution_date, get_spark
from src.churn_prediction.utils.loaders import load_data
from src.churn_prediction.utils.writers import write_data

class DataIngester:
    """
    Ingests data based on ingestion configuration.
    """
    def __init__(self, config_path: str, execution_date: Optional[str] = None) -> None:
        """
        Initialize ingester with config file.
        
        Args:
            config_path (str): Path to config YAML file
        """
        try:
            logger.info("Initializing DataIngester...")

            # Load config
            self.config_path: Path = Path(config_path)
            self.pipeline_config: PipelineConfig = load_single_config(PipelineConfig, self.config_path)
            self.execution_date: str = get_execution_date(execution_date) if execution_date else datetime.now().strftime("%Y-%m-%d")

            self.ingestion_path: Path = Path(self.pipeline_config.ingestion.config_path)
            self.ingestion_config: DataIngestionConfig = load_single_config(DataIngestionConfig, self.ingestion_path)

            self.columns_config = self.ingestion_config.columns

            self.input_path: str = self.pipeline_config.ingestion.input.get("file_path").replace("${execution_date}", self.execution_date)
            self.output_path: str = self.pipeline_config.ingestion.output.get("file_path").replace("${execution_date}", self.execution_date)

        except Exception as e:
            logger.error(f"Error initializing DataIngester: {e}")
            raise e

    def select_columns(self, df: DataFrame) -> DataFrame:
        """
        Select columns based on ingestion config.
        
        Args:
            df (DataFrame): Input dataframe

        Returns:
            DataFrame: Processed dataframe
        """
        target_columns = [target_col.target_column for target_col in self.columns_config.values()]
        not_matched_columns = set(target_columns) - set(df.columns)
        if not_matched_columns:
            raise ValueError(f"Columns {not_matched_columns} not found in source data.")

        return df[target_columns]

    def rename_and_cast_columns(self, df: DataFrame) -> DataFrame:
        """
        Rename and cast columns based on ingestion config.

        Args:
            df (DataFrame): Input dataframe

        Returns:
            DataFrame: Processed dataframe
        """
        for col, target_col in self.columns_config.items():
            df = df.withColumnRenamed(target_col.target_column, col)
            df = df.withColumn(col, df[col].cast('string'))
        return df

    def run(self) -> None:
        """
        Ingest data from source, process it, and return the dataframe.

        Returns:
            None
        """
        try:
            logger.info("Starting data ingestion...")

            # 1. Load data
            df = load_data(source=self.input_path, header=True)

            # 2. Select columns
            df = self.select_columns(df)

            # 3. Rename and cast columns
            df = self.rename_and_cast_columns(df)

            # 4. Flag save time
            df = df.withColumn("dl_data_dt", F.lit(self.execution_date).cast('date'))
            df = df.withColumn("dl_load_ts", F.lit(datetime.now()))

            # 5. Save raw data
            write_data(df, file_path=self.output_path)

            logger.info("Data ingestion completed.")
        
        except Exception as e:
            logger.error(f"Error during data ingestion: {e}")
            raise e
