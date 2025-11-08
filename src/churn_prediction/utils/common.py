from pydantic import BaseModel
from typing import Type
import yaml
import pandas as pd
from src.churn_prediction.logger import logger

def generate_sk_key(df: pd.DataFrame) -> pd.DataFrame:
    """Generate a surrogate key (SK) by assigning a unique integer to each row.

    Args:
        df (pd.DataFrame): Input DataFrame for which to generate the surrogate key.
    Returns:
        pd.DataFrame: DataFrame with an additional 'sk_key' column.

    """
    df["sk_key"] = [str(i) for i in range(1, len(df) + 1)]
    return df

def load_single_config(
    ConfigClass: Type[BaseModel],
    file_path: str
) -> BaseModel:
    """Load a single configuration file and parse it into a Pydantic model.

    Args:
        ConfigClass (Type[BaseModel]): The Pydantic model class to parse the config into.
        file_path (str): The path to the configuration file.

    Returns:
        BaseModel: An instance of the Pydantic model populated with the config data.
    """
    try:
        with open(file_path, 'r') as file:
            config_dict = yaml.safe_load(file)
        config = ConfigClass(**config_dict)
        logger.info(f"Successfully loaded schema: {file_path}")
        return config
    except FileNotFoundError:
        logger.error(f"Schema file not found: {file_path}")
        raise
    except yaml.YAMLError as e:
        logger.error(f"Error parsing YAML schema: {e}")
        raise
