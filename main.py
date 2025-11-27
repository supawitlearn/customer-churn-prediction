from typing import Optional
from pathlib import Path
from datetime import datetime
import sys
import argparse

# import project modules
from src.churn_prediction.logger import logger
from src.churn_prediction.pydantic.pipeline_config import PipelineConfig
from src.churn_prediction.components.data_ingestion import DataIngester
from src.churn_prediction.components.data_validation import DataValidator
from src.churn_prediction.components.data_transformation import DataTransformer
from src.churn_prediction.components.feature_engineering import FeatureEngineering
from src.churn_prediction.utils.common import load_single_config, get_execution_date

def execute(
    config_path: str,
    execution_date: Optional[str] = None,
) -> None:
    """
    Execute the data and ml pipeline stages base on configuration.

    Args:
        config_path (str): Path to the configuration file.
        execution_date (Optional[str]): Execution date for the pipeline run.

    Returns:
        None
    """
    # Load config
    config_path: Path = Path(config_path)
    pipeline_config: PipelineConfig = load_single_config(PipelineConfig, config_path)
    execution_date: str = get_execution_date(execution_date)

    pipeline_process = {
        "ingestion": DataIngester,
        "validation": DataValidator,
        "transformation": DataTransformer,
        "feature_engineering": FeatureEngineering,
    }

    for process_name, process_class in pipeline_process.items():
        process_method = getattr(pipeline_config, process_name, None)
        if not process_method:
            continue
        process_class(config_path, execution_date).run()

    logger.info("Pipeline execution completed.")

def main():
    """
    Main function to execute the pipeline with command-line arguments.

    Command-line Arguments:
        1. config_path (str): Path to the configuration file.
        2. execution_date (Optional[str]): Execution date for the pipeline run.

    Example:
        python main.py config/config.yaml 2024-01-01

    This function retrieves command-line arguments and calls the execute function.
    """
    try:
        parser = argparse.ArgumentParser()
        parser.add_argument("config_path", type=str, help="Path to the configuration file.")
        parser.add_argument("--execution_date", "-e", type=str, default=None, help="Execution date for the pipeline run.", required=False)
        args = parser.parse_args()

        execute(
            config_path=args.config_path,
            execution_date=args.execution_date,
        )
    except Exception as e:
        logger.error(f"Error in main execution: {e}")
        raise e
    
if __name__ == "__main__":
    main()