"""
Data writers for S3 and local sources using AWS Wrangler."""

from typing import Optional, Dict, Any, Iterable, List, Union
from pyspark.sql import DataFrame
from pathlib import Path
from urllib.parse import urlparse

from src.churn_prediction.utils.common import get_spark
from src.churn_prediction.logger import logger


class S3Writer:
    """Save data to AWS S3 using AWS Wrangler.
    
    AWS Wrangler simplifies working with data on AWS:
    - Handles format detection automatically
    - Supports CSV, Parquet, JSON, Excel, Glue Catalog, etc.
    - Optimized for S3 operations
    - Integrates with Pandas seamlessly
    """
    spark = get_spark()

    @classmethod
    def parse_s3_uri(s3_uri: str):
        parsed = urlparse(s3_uri)
        if parsed.scheme != "s3":
            raise ValueError(f"Invalid S3 URI: {s3_uri}, must start with s3://")
        bucket = parsed.netloc
        key = parsed.path.lstrip("/")
        return bucket, key

    @classmethod
    def ensure_trailing_slash(path: str) -> str:
        return path if path.endswith("/") else path + "/"

    @classmethod
    def write_to_s3_on_glue(
        cls,
        df: DataFrame,
        s3_path: str,
        format: str = "parquet",
        glue_context: Optional[Any] = None,
        partition: Optional[Union[str, Iterable[str]]] = None,
        mode: str = "overwrite",
        compression: Optional[str] = None,
        options: Optional[Dict[str, Any]] = None,
        coalesce: Optional[int] = None,
        repartition: Optional[int] = None,
        use_dynamic_frame: bool = False,
    ) -> Dict[str, Any]:
        """
        Write a Spark DataFrame or Glue DynamicFrame to S3 using PySpark (works on AWS Glue).

        Args:
            df: pyspark.sql.DataFrame or awsglue.dynamicframe.DynamicFrame to write.
            s3_path: destination S3 URI, e.g. "s3://my-bucket/path/to/output/"
            format: output format (parquet, csv, json, orc, avro, etc.)
            glue_context: optional GlueContext (if you want to write a DynamicFrame via Glue APIs)
            partition: column name or iterable of column names to partition by
            mode: write mode ("overwrite", "append", "errorifexists", "ignore")
            compression: compression codec name (e.g. "snappy", "gzip", "gzip")
            options: additional writer options forwarded to DataFrameWriter or Glue writer
            coalesce: if provided, coalesce to this many files before writing (overrides repartition)
            repartition: if provided and coalesce not set, repartition to this number of partitions
            use_dynamic_frame: if True and glue_context provided, prefer writing using Glue DynamicFrame

        Returns:
            dict with keys:
            - "path": the s3_path that was written to
            - "format": format used
            - "mode": mode used
            - "files_written": None or estimated file count (spark-side quick check)
        """
        spark = get_spark(spark)
        options = options or {}

        fmt = format.lower()

        # Basic validation of S3 path (syntactic)
        try:
            cls.parse_s3_uri(s3_path)
        except Exception as e:
            logger.error("Provided s3_path is invalid: %s", e)
            raise

        # Normalize partition to list
        if partition is None:
            partition_cols: List[str] = []
        elif isinstance(partition, str):
            partition_cols = [partition]
        else:
            partition_cols = list(partition)

        # If a Glue DynamicFrame was passed in but user wants DataFrame ops, convert
        is_dynamic_frame = False
        try:
            # awsglue DynamicFrame has attribute 'toDF'
            if hasattr(df, "toDF") and not isinstance(df, DataFrame):
                is_dynamic_frame = True
        except Exception:
            is_dynamic_frame = False

        # Decide writer path:
        # - If use_dynamic_frame=True and glue_context supplied, use Glue DynamicFrame writer.
        # - Otherwise convert dynamic -> DataFrame and use spark DataFrameWriter.
        dest_path = cls.ensure_trailing_slash(s3_path)

        # Optional light validation: warn if user tries to write a directory that looks like a file
        if not dest_path.endswith("/"):
            dest_path = cls.ensure_trailing_slash(dest_path)

        # Prepare the DataFrame
        if is_dynamic_frame and not use_dynamic_frame:
            try:
                df: DataFrame = df.toDF()
            except Exception as e:
                logger.error("Failed to convert DynamicFrame to DataFrame: %s", e)
                raise
        elif is_dynamic_frame and use_dynamic_frame:
            # We'll handle dynamic frame writing below
            df = None
        else:
            if isinstance(df, DataFrame):
                df = df
            else:
                raise TypeError("data must be a pyspark.sql.DataFrame or an AWS Glue DynamicFrame")

        # Repartition/coalesce if requested
        if df is not None:
            if coalesce is not None:
                if coalesce <= 0:
                    raise ValueError("coalesce must be > 0")
                df = df.coalesce(coalesce)
            elif repartition is not None:
                if repartition <= 0:
                    raise ValueError("repartition must be > 0")
                df = df.repartition(repartition)

        # If user requested DynamicFrame write and we have a GlueContext, try that path
        if use_dynamic_frame and glue_context is not None and is_dynamic_frame:
            try:
                # Use Glue dynamic writer
                connection_options = {"path": dest_path}
                if partition_cols:
                    connection_options["partitionKeys"] = partition_cols

                format_options = {}
                # Glue expects boolean values for some options (e.g. "withHeader" for CSV) — map common ones:
                if fmt == "csv":
                    format_options["withHeader"] = options.get("header", True)
                    format_options["separator"] = options.get("sep", ",")
                    if compression:
                        format_options["compression"] = compression
                if fmt == "json":
                    format_options["multiline"] = options.get("multiLine", False)
                    if compression:
                        format_options["compression"] = compression

                # Glue DynamicFrame writer
                glue_context.write_dynamic_frame.from_options(
                    frame=df,
                    connection_type="s3",
                    connection_options=connection_options,
                    format=fmt,
                    format_options=format_options,
                )
                # We won't attempt to count files from Glue writer; return metadata
                return {"path": dest_path, "format": fmt, "mode": mode, "files_written": None}
            except Exception as e:
                logger.warning("Glue DynamicFrame write failed: %s; falling back to spark.write", e)
                # fall through to spark writer (convert to DF)
                df = df.toDF()

        # Use Spark DataFrameWriter
        writer = df.write.mode(mode)
        if partition_cols:
            writer = writer.partitionBy(*partition_cols)

        # apply compression if provided
        if compression:
            # Some formats use option key "compression"
            writer = writer.option("compression", compression)

        # Merge additional options (stringify booleans where appropriate)
        for k, v in options.items():
            writer = writer.option(k, v)

        # For parquet we can set "parquet.enable.summary-metadata" or other advanced options via option()
        # Write out
        try:
            # Spark's DataFrameWriter accepts format() with options; pass the path to .save()
            writer.format(fmt).save(dest_path)
        except Exception as e:
            logger.error("Failed to write to S3 path %s: %s", dest_path, e)
            raise


# Example usage (Glue job or local Spark):
if __name__ == "__main__":
    from pyspark.sql import SparkSession

    spark = SparkSession.builder.getOrCreate()

    # Example DataFrame
    df = spark.createDataFrame(
        [
            (1, "Alice", "US"),
            (2, "Bob", "CA"),
            (3, "Carol", "US"),
        ],
        ["id", "name", "country"],
    )

    # Write to S3 as parquet, partitioned by country, coalesce to 1 file per partition
    result = write_df_to_s3(
        df,
        "s3://my-bucket/output/customer_profile/",
        format="parquet",
        spark=spark,
        partition_by=["country"],
        mode="overwrite",
        compression="snappy",
        coalesce=None,
        repartition=3,
        options={},
        use_dynamic_frame=False,
    )
    print(result)


class LocalWriter:
    """
    Save data to local filesystem using PySpark.
    """
    spark = get_spark()

    @classmethod
    def write_to_local(
        cls,
        df: DataFrame,
        file_path: str,
        format: str = "parquet",
        mode: str = "overwrite",
        delimiter: Optional[str] = None,
        header: Optional[bool] = None,
        options: Optional[dict] = None,
        partition: Optional[List[str]] = None,
    ) -> None:
        """
        Save a DataFrame to the local filesystem.

        Args:
            df: pyspark.sql.DataFrame to save.
            file_path: Path to save the file.
            format: File format (e.g., 'csv', 'parquet', 'json'). Defaults to 'parquet'.
            mode: Save mode ('overwrite', 'append', etc.). Defaults to 'overwrite'.
            delimiter: Delimiter for CSV files (if applicable).
            header: Whether to write a header row (if applicable).
            options: Additional options for the writer.
            partition: List of columns to partition by (if applicable).

        Returns:
            None
        """
        if options is None:
            options = {}

        writer = df.write.format(format).mode(mode).options(**options)

        if delimiter is not None:
            writer = writer.option("delimiter", delimiter)
        if header is not None:
            writer = writer.option("header", str(header).lower())
        if partition is not None:
            writer = writer.partitionBy(*partition)

        writer.save(file_path)

def write_data(
    df: DataFrame,
    file_path: str,
    **kwargs,
) -> None:
    """
    Write a DataFrame to a file.

    Args:
        df (DataFrame): DataFrame to save
        file_path (str): Path to save the file
        **kwargs: Additional arguments for file saving functions

    Example:
        >>> write_data(df, 'output/result.parquet')
    """
    if file_path.startswith("s3://"):
        try:
            logger.info(f"Writing data to S3: {file_path}")
            return S3Writer().write_to_s3_on_glue(df=df, s3_path=file_path, **kwargs)
        except Exception as e:
            logger.error(f"✗ Failed to save to S3: {str(e)}")
            raise
    else:
        try:
            logger.info(f"Writing data to local: {file_path}")
            return LocalWriter().write_to_local(df=df, file_path=file_path, **kwargs)
        except Exception as e:
            logger.error(f"✗ Failed to write to local: {str(e)}")
            raise
