# import necessary libraries
import yaml
import pandas as pd
from pydantic import BaseModel
from typing import Type
from dateutil import parser
from datetime import datetime
from dateutil.relativedelta import relativedelta
from typing import Optional
from pyspark.sql import SparkSession

# import project modules
from src.churn_prediction.logger import logger

class AttrDict(dict):
    """Dictionary subclass that allows attribute-style access to its items."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__dict__ = self

    @classmethod
    def from_dict(cls, data: dict):
        """Recursively convert a dictionary to an AttrDict."""
        return cls({k: cls.from_dict(v) if isinstance(v, dict) else v for k, v in data.items()})

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

def get_execution_date(date_input: Optional[str] = None) -> Optional[str]:
    """
    Convert any date-like input (string, timestamp, etc.)
    into a standardized string format 'YYYYMMDD'.

    Args:
        date_input (str | datetime | None): Input date value.

    Returns:
        str | None: Standardized date string 'YYYYMMDD' or None if invalid.
    """
    if date_input is None:
        today = datetime.now()
        first_day_this_month = today.replace(day=1)
        last_day_prev_month = first_day_this_month - relativedelta(days=1)
        return last_day_prev_month.strftime("%Y-%m-%d")

    # Try parsing the date using dateutil
    try:
        dt = parser.parse(str(date_input), dayfirst=False, yearfirst=True)
        return dt.strftime('%Y-%m-%d')
    except Exception:
        return None

def get_spark() -> SparkSession:
    """
    Initialize and return a SparkSession.

    Returns:
        SparkSession: An active Spark session.
    """
    spark = SparkSession.builder \
        .appName("ChurnPrediction") \
        .getOrCreate()
    return spark

def load_yaml(file_path: str) -> dict:
    """
    Load a YAML file and return its contents as a dictionary.

    Args:
        file_path (str): Path to the YAML file.
    """
    try:
        with open(file_path, 'r') as file:
            data = yaml.safe_load(file)
        logger.info(f"Successfully loaded YAML file: {file_path}")
        return AttrDict.from_dict(data)
    except FileNotFoundError:
        logger.error(f"YAML file not found: {file_path}")
        raise
    except yaml.YAMLError as e:
        logger.error(f"Error parsing YAML file: {e}")
        raise