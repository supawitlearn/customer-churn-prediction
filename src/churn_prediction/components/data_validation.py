from pathlib import Path
from datetime import datetime
from typing import Tuple, List, Optional, Dict, Any
from pyspark.sql import DataFrame, functions as F, types as T
from pyspark.sql.window import Window

# import project modules
from src.churn_prediction.logger import logger
from src.churn_prediction.pydantic.data_validation_config import DataValidationConfig
from src.churn_prediction.pydantic.pipeline_config import PipelineConfig
from src.churn_prediction.utils.common import load_single_config, get_spark, get_execution_date
from src.churn_prediction.utils.loaders import load_data
from src.churn_prediction.utils.writers import write_data

class DataValidator:
    """
    Data Validator class to perform data quality checks based on configuration.
    """

    def __init__(self, config_path: str, execution_date: Optional[str] = None) -> None:
        """
        Initialize validator with config file.

        Args:
            config_path (str): Path to config YAML file
            execution_date (Optional[str]): Execution date string in 'YYYY-MM-DD' format. Defaults to today's date.
        """
        try:
            logger.info("Initializing DataValidator...")

            self.spark = get_spark()

            # Load config using project's config loader(s)
            self.config_path: Path = Path(config_path)
            self.pipeline_config: PipelineConfig = load_single_config(PipelineConfig, self.config_path)
            self.execution_date: str = get_execution_date(execution_date) if execution_date else datetime.now().strftime("%Y-%m-%d")

            self.validation_path: Path = Path(self.pipeline_config.validation.config_path)
            self.validation_config: DataValidationConfig = load_single_config(DataValidationConfig, self.validation_path)

            self.columns_config = self.validation_config.columns
            self.quality_rules_config = self.validation_config.quality_rules

            self.input_path: str = self.pipeline_config.validation.input.get("file_path").replace("${execution_date}", self.execution_date)
            self.output_path: str = self.pipeline_config.validation.output.get("file_path").replace("${execution_date}", self.execution_date)

        except Exception as e:
            logger.error(f"Error initializing DataValidator: {e}")
            raise

    # Helpers
    @staticmethod
    def map_to_spark_type(type_str: str) -> T.DataType:
        """
        Map config type names to pyspark types.
        Extend mapping if your config has more granular types.
        """
        t = (type_str or "").lower().strip()
        if t in ("string", "str", "varchar", "text"):
            return T.StringType()
        if t in ("integer", "int", "long"):
            return T.LongType()
        if t in ("float", "double", "decimal"):
            return T.DoubleType()
        if t in ("bool", "boolean"):
            return T.BooleanType()
        if t in ("date",):
            return T.DateType()
        if t in ("datetime", "timestamp"):
            return T.TimestampType()
        # fallback
        return T.StringType()

    # Validation methods
    def validate_duplicates_records(self, df: DataFrame) -> Dict[str, Any]:
        """
        Identify duplicate records based on all columns except 'sk_key'.
        Returns dict with 'error' -> list of DataFrames (error reports) and 'clean_df' -> DataFrame with duplicates removed.
        """
        logger.info("Validating duplicate records (excluding sk_key)...")
        cols_to_check = [c for c in df.columns if c != "sk_key"]

        # Count duplicates
        grouped = df.groupBy(*cols_to_check).count()
        duplicates = grouped.filter("count > 1").drop("count")

        if duplicates.rdd.isEmpty():
            # no duplicates
            return {"error": [], "clean_df": df}

        # Join back to fetch duplicate rows
        dup_rows = df.join(duplicates, on=cols_to_check, how="inner") \
            .withColumn("error_type", F.lit("RecordDuplicateViolation")) \
            .withColumn("error_message", F.lit("Duplicate records found based on all columns except 'sk_key'"))

        # Remove duplicates and keep the first occurrence: create row_number over partition and filter row_number == 1
        w = Window.partitionBy(*cols_to_check).orderBy(F.lit(1))
        df_with_rn = df.withColumn("__rn", F.row_number().over(w))
        clean_df = df_with_rn.filter(F.col("__rn") == 1).drop("__rn")

        return {"error": [dup_rows], "clean_df": clean_df}

    def validate_duplicates_keys(self, df: DataFrame) -> Dict[str, Any]:
        """
        Identify duplicate keys based on configured primary key columns.
        """
        logger.info("Validating duplicate key constraints...")
        # Determine key columns from columns_config where primary_keys attribute is truthy.
        key_columns = [c for c, cfg in self.columns_config.items() if getattr(cfg, "primary_keys", False)]

        if not key_columns:
            logger.info("No primary key columns configured; skipping key-duplicate validation.")
            return {"error": [], "clean_df": df}

        grouped = df.groupBy(*key_columns).count()
        dup_keys = grouped.filter("count > 1").drop("count")

        if dup_keys.rdd.isEmpty():
            return {"error": [], "clean_df": df}

        dup_rows = df.join(dup_keys, on=key_columns, how="inner") \
            .withColumn("error_type", F.lit("UniqueKeyDuplicateViolation")) \
            .withColumn("error_message", F.lit(f"Duplicate values found in unique key column(s): {key_columns}"))

        # Remove duplicates
        clean_df = df.join(dup_keys, on=key_columns, how="left_anti")

        return {"error": [dup_rows], "clean_df": clean_df}

    def validate_data_types_and_nullability(self, df: DataFrame) -> Dict[str, Any]:
        """
        Validate data types and nullability:
        - Attempt to cast each column to the target Spark data type.
        - Rows where original is not null but cast yields null are marked as InvalidDataType.
        - Rows where column is null but configured nullable == False are marked as NullableViolation.
        Returns dict with 'error' list (DataFrames) and 'clean_df' (DataFrame with error rows removed).
        """
        logger.info("Validating data types and nullability...")

        errors: List[DataFrame] = []
        working_df = df

        for col_name, cfg in self.columns_config.items():
            expected_type = self.map_to_spark_type(getattr(cfg, "type", "string"))
            nullable = bool(getattr(cfg, "nullable", True))

            # Try cast
            cast_col_name = f"__cast_{col_name}"
            working_df = working_df.withColumn(cast_col_name, F.col(col_name).cast(expected_type))

            # Detect invalid data type: original not null but cast is null (and original not equal to cast when possible)
            invalid_type_mask = (F.col(col_name).isNotNull()) & (F.col(cast_col_name).isNull())
            invalid_rows = working_df.filter(invalid_type_mask).drop(cast_col_name) \
                .withColumn("error_type", F.lit("InvalidDataType")) \
                .withColumn("error_message", F.lit(f"Column '{col_name}' has invalid data type (expected {expected_type.simpleString()})"))

            if not invalid_rows.rdd.isEmpty():
                errors.append(invalid_rows)

            # Detect nullability violation: cast (or original) is null but nullable == False
            if not nullable:
                null_violation_rows = working_df.filter(F.col(col_name).isNull()).drop(cast_col_name) \
                    .withColumn("error_type", F.lit("NullableViolation")) \
                    .withColumn("error_message", F.lit(f"Column '{col_name}' is non-nullable but has null value"))
                if not null_violation_rows.rdd.isEmpty():
                    errors.append(null_violation_rows)

            # Cleanup temporary cast column for subsequent iterations (but keep original column)
            working_df = working_df.drop(cast_col_name)

        # Build clean_df by removing any rows appearing in any error frames.
        if not errors:
            return {"error": [], "clean_df": df}

        # Union all error DataFrames to get IDs of offending rows. To remove offending rows we need a reliable row identifier.
        # If there's a primary key defined use that, otherwise create a synthetic row id.
        key_columns = [c for c, cfg in self.columns_config.items() if getattr(cfg, "primary_keys", False)]
        if not key_columns:
            # create synthetic __row_id
            df_with_id = df.withColumn("__row_id", F.monotonically_increasing_id())
            error_union = None
            for e in errors:
                e_with_id = e.join(df_with_id, on=[c for c in df.columns], how="inner") if df.columns else e
                if error_union is None:
                    error_union = e
                else:
                    error_union = error_union.unionByName(e, allowMissingColumns=True)
            cols_common = [c for c in df.columns if c in error_union.columns]
            clean_df = df.join(error_union.select(*cols_common).distinct(), on=cols_common, how="left_anti")
        else:
            # Use primary keys to identify offending rows
            # Build a union of offending primary key values
            pk_errors = None
            for e in errors:
                pk_part = e.select(*key_columns).distinct()
                pk_errors = pk_part if pk_errors is None else pk_errors.union(pk_part)
            clean_df = df.join(pk_errors.distinct(), on=key_columns, how="left_anti")

        return {"error": errors, "clean_df": clean_df}

    def validate_foreign_keys(self, df: DataFrame) -> Dict[str, Any]:
        """
        Validate foreign key constraints by doing anti-joins against referenced child tables.
        Expects each column config that has foreign_keys to include child_path and child_column.
        """
        logger.info("Validating foreign keys...")
        errors: List[DataFrame] = []
        clean_df = df

        for column, cfg in self.columns_config.items():
            foreign_key = getattr(cfg, "foreign_keys", None)
            if not foreign_key:
                continue

            child_path = foreign_key.child_path
            child_column = foreign_key.child_column

            # Load child table
            try:
                child_df = self.load_data(child_path).select(child_column).distinct()
            except Exception as e:
                logger.warning(f"Failed to load child table for FK check: {child_path}: {e}")
                continue

            # Find invalid rows: left_anti join - rows in parent that don't have matching key in child
            invalid_rows = clean_df.join(child_df, clean_df[column] == child_df[child_column], how="left_anti") \
                .filter(F.col(column).isNotNull()) \
                .withColumn("error_type", F.lit("ForeignKeyViolation")) \
                .withColumn("error_message", F.lit(f"Column '{column}' has values not present in '{child_path}.{child_column}'"))

            if not invalid_rows.rdd.isEmpty():
                errors.append(invalid_rows)
                # Remove invalid rows from clean_df for downstream checks
                # Identify offending PK set if exists, otherwise remove by exact match
                key_columns = [c for c, cfg in self.columns_config.items() if getattr(cfg, "primary_keys", False)]
                if key_columns:
                    # remove by PK
                    invalid_pks = invalid_rows.select(*key_columns).distinct()
                    clean_df = clean_df.join(invalid_pks, on=key_columns, how="left_anti")
                else:
                    # remove rows that match all columns in invalid_rows (may be heavy)
                    cols_common = [c for c in clean_df.columns if c in invalid_rows.columns]
                    clean_df = clean_df.join(invalid_rows.select(*cols_common).distinct(), on=cols_common, how="left_anti")

        return {"error": errors, "clean_df": clean_df}

    # Utility to combine error frames into a single error DataFrame for reporting
    def union_error_dfs(self, errors: List[DataFrame]) -> DataFrame:
        if not errors:
            # Return empty DataFrame with same schema as input if possible
            # As a fallback create a DataFrame with columns: error_type, error_message
            return self.spark.createDataFrame([], schema=T.StructType([
                T.StructField("error_type", T.StringType(), True),
                T.StructField("error_message", T.StringType(), True)
            ]))
        union_df = errors[0]
        for e in errors[1:]:
            union_df = union_df.unionByName(e, allowMissingColumns=True)
        return union_df

    @staticmethod
    def extract_results_error_dfs(result: Dict[str, Any]) -> Tuple[DataFrame, List[DataFrame]]:
        """
        Extract clean_df and list of error DataFrames from a result dict returned by validation helpers.
        """
        clean_df = result.get("clean_df")
        errors = result.get("error", [])
        return clean_df, errors

    # Main validator orchestration
    def run(self) -> None:
        """
        Run the validation pipeline:
        1. Load data
        2. Drop internal columns
        3. Run duplicate record validation
        4. Run key uniqueness validation
        5. Validate types & nullability
        6. Validate foreign keys
        7. Save cleaned data + errors
        """
        try:
            logger.info("Starting data validation ...")

            all_error_dfs: List[DataFrame] = []

            # 1. Load data
            df = load_data(self.input_path)
            # Drop the dl_load_ts if present (as original code did)
            if "dl_load_ts" in df.columns:
                df = df.drop("dl_load_ts")

            # 2. Validate record duplicates (if configured)
            if not getattr(self.quality_rules_config.allow_record_duplicates, "enabled", False):
                res = self.validate_duplicates_records(df)
                df, errs = self.extract_results_error_dfs(res)
                all_error_dfs.extend(errs)

            # 3. Validate key duplicates
            if not getattr(self.quality_rules_config.allow_key_duplicates, "enabled", False):
                res = self.validate_duplicates_keys(df)
                df, errs = self.extract_results_error_dfs(res)
                all_error_dfs.extend(errs)

            # 4. Validate data types and nullability
            res = self.validate_data_types_and_nullability(df)
            df, errs = self.extract_results_error_dfs(res)
            all_error_dfs.extend(errs)

            # 5. Validate foreign keys
            if not getattr(self.quality_rules_config.foreign_key_checks, "enabled", False):
                res = self.validate_foreign_keys(df)
                df, errs = self.extract_results_error_dfs(res)
                all_error_dfs.extend(errs)

            # 6. Consolidate errors
            if all_error_dfs:
                error_df = self.union_error_dfs(all_error_dfs)
            else:
                # produce empty error dataframe with at least the same columns as df + error columns
                empty_err_schema = T.StructType([T.StructField(c, T.StringType(), True) for c in df.columns])
                empty_err_schema.add(T.StructField("error_type", T.StringType(), True))
                empty_err_schema.add(T.StructField("error_message", T.StringType(), True))
                error_df = self.spark.createDataFrame([], schema=empty_err_schema)

            # 7. Add dl_load_ts timestamps
            now_ts = datetime.now()
            df = df.withColumn("dl_load_ts", F.lit(now_ts))
            error_df = error_df.withColumn("dl_load_ts", F.lit(now_ts))

            # 8. Save results
            # Primary output - cleaned data
            write_data(df, file_path=self.output_path)

            # Error logs saved to a separate path - same as original code replaced 'validated' with 'errors'
            error_output_path = str(self.output_path).replace("validated", "errors")
            write_data(error_df, file_path=error_output_path)

            logger.info("Data validation completed.")

        except Exception as e:
            logger.exception(f"Error during data validation: {e}")
            raise
