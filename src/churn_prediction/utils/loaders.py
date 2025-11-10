"""
Load data from various sources (local, S3) into a Spark DataFrame.
"""

from typing import Any, Optional, Dict
from pyspark.sql import DataFrame
from pathlib import Path

from src.churn_prediction.utils.common import get_spark
from src.churn_prediction.logger import logger

class S3Loader:
    """
    Load data from S3 using PySpark, with optional AWS Glue DynamicFrame support.
    """
    spark = get_spark()

    @classmethod
    def ensure_glue_context(cls, glue_context: Optional[Any]) -> Optional[Any]:
        """
        Return a GlueContext if one was provided or can be created in the current environment.
        This avoids importing awsglue at module import time when not running on Glue.
        """
        if glue_context is not None:
            return glue_context
        try:
            from awsglue.context import GlueContext  # type: ignore
            return GlueContext(cls.spark.sparkContext)
        except Exception:
            return None

    @classmethod
    def load_from_s3_on_glue(
        cls,
        s3_path: str,
        format: str = 'parquet',
        glue_context: Optional[Any] = None,
        return_dynamic_frame: bool = False,
        options: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """
        Generic loader for S3 using Spark on AWS Glue.

        Args:
            s3_path: full s3 URI, e.g. "s3://my-bucket/path/to/file_or_prefix"
            format: data format, e.g. "parquet", "csv", "json"
            glue_context: optional GlueContext (if you want a DynamicFrame)
            return_dynamic_frame: if True and GlueContext available, returns a Glue DynamicFrame
            options: dict of spark read options (e.g. {"header": True, "inferSchema": True} for CSV)

        Returns:
            pyspark.sql.DataFrame or awsglue.dynamicframe.DynamicFrame
        """
        options = options or {}

        # If user asked for a DynamicFrame, ensure we have a GlueContext (or try to create one)
        if return_dynamic_frame:
            glue_ctx = cls.ensure_glue_context(glue_context)
            if glue_ctx is not None:
                # Glue DynamicFrame reader expects different option naming for some formats.
                # Use from_options for generality.
                fmt = format.lower()
                format_options = {}
                # Map some common options for CSV / JSON; Parquet typically needs no format_options.
                if fmt == "csv":
                    format_options["withHeader"] = options.get("header", True)
                    format_options["separator"] = options.get("sep", ",")
                if fmt == "json":
                    # Glue expects "multiline" as boolean in format_options
                    format_options["multiline"] = options.get("multiLine", False)

                connection_options = {"paths": [s3_path], "recurse": True}
                try:
                    dynf = glue_ctx.create_dynamic_frame.from_options(
                        connection_type="s3",
                        connection_options=connection_options,
                        format=fmt,
                        format_options=format_options,
                    )
                    return dynf
                except Exception as e:
                    logger.warning(f"GlueContext DynamicFrame read failed, falling back to spark.read: {e}")
            else:
                logger.warning("return_dynamic_frame=True requested but GlueContext not available; falling back to DataFrame")

        # Use Spark's native reader
        # Spark expects string values for options; booleans are accepted too but convert for safety
        spark_options = {k: (str(v).lower() if isinstance(v, bool) else str(v)) for k, v in options.items()}

        df: DataFrame = cls.spark.read.format(format).options(**spark_options).load(s3_path)
        return df
    
class LocalLoader:
    """
    Load data from the local filesystem using PySpark.
    """
    spark = get_spark()

    @staticmethod
    def ensure_file_path(file_path: str) -> Path:
        file_path_check = Path(file_path)
        if not file_path_check.exists():
            logger.warning(f"File not found: {file_path_check}")
            raise FileNotFoundError(f"File not found: {file_path_check}")
        return file_path

    @classmethod
    def load_from_local(
        cls,
        file_path: str,
        delimiter: Optional[str] = None,
        header: Optional[bool] = None,
    ) -> DataFrame:
        """
        Load a DataFrame from the local filesystem.

        Args:
            file_path: Path to the local file.
            delimiter: Delimiter for CSV files (if applicable).
            header: Whether the file has a header row (if applicable).

        Returns:
            pyspark.sql.DataFrame
        """
        file_path = cls.ensure_file_path(file_path)
        if '.' in file_path:
            format = file_path.split('.')[-1].lower()
            reader = cls.spark.read.format(format)
        else:
            reader = cls.spark.read

        if delimiter is not None:
            reader = reader.option("delimiter", delimiter)
        if header is not None:
            reader = reader.option("header", str(header).lower())

        return reader.load(file_path)

def load_data(source: str, **kwargs) -> DataFrame:
    """
    Universal data loader that auto-detects source type.

    Supports:
    - Local files: 'path/to/file.csv'
    - S3 paths: 's3://bucket/path/file.csv'

    Args:
        source (str): Data source path or S3 URI
        **kwargs: Additional arguments for specific loaders

    Returns:
        pd.DataFrame: Loaded data

    Example:
        >>> # Load from local
        >>> df = load_data('data/customers.csv')
        >>> 
        >>> # Load from S3
        >>> df = load_data('s3://my-bucket/data/customers.csv')
    """
    if source.startswith("s3://"):
        try:
            logger.info(f"Loading data from S3: {source}")
            return S3Loader().load_from_s3_on_glue(s3_path=source, **kwargs)
        except Exception as e:
            logger.error(f"✗ Failed to load from S3: {str(e)}")
            raise
    else:
        try:
            logger.info(f"Loading data from local: {source}")
            return LocalLoader().load_from_local(file_path=source, **kwargs)
        except Exception as e:
            logger.error(f"✗ Failed to load from local: {str(e)}")
            raise
