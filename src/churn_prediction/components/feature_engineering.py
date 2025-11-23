# import necessary libraries
from pathlib import Path
from datetime import datetime
from typing import Optional
from pyspark.sql import functions as F
from pyspark.sql import DataFrame

# import project modules
from src.churn_prediction.logger import logger
from src.churn_prediction.pydantic.pipeline_config import PipelineConfig
from src.churn_prediction.feature.feature_modules import feature_modules
from src.churn_prediction.utils.common import load_single_config


class FeatureEngineering:
    """
    Class to handle feature engineering based on specified module in configuration.
    """
    def __init__(self, config_path: str, execution_date: Optional[str] = None) -> None:
        try:
            logger.info("Initializing FeatureEngineering...")

            # Load config using project's config loader(s)
            self.config_path: Path = Path(config_path)
            self.execution_date: str = execution_date
            self.pipeline_config: PipelineConfig = load_single_config(PipelineConfig, self.config_path)
            self.module: str = self.pipeline_config.feature_engineering.module
            self.feature_modules = feature_modules()

        except Exception as e:
            logger.error(f"Error initializing FeatureEngineering: {e}")
            raise e

    def run(self) -> None:
        """
        Main function to run feature engineering based on the specified module.

        Returns:
            None
        """
        try:
            logger.info("Starting feature engineering...")

            feature_class = self.feature_modules.get(self.module)
            if not feature_class:
                raise ValueError(f"Feature engineering module '{self.module}' not found.")

            feature_instance = feature_class(self.config_path, self.execution_date)
            feature_instance.run()

            logger.info("Feature engineering completed.")
        
        except Exception as e:
            logger.error(f"Error during feature engineering: {e}")
            raise e
