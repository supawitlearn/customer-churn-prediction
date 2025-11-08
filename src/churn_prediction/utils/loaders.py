"""Data loaders for S3 and local sources using AWS Wrangler."""

from typing import Optional, List
from pathlib import Path
import pandas as pd

from src.churn_prediction.logger import logger


class S3Loader:
    """Load data from AWS S3 using AWS Wrangler.
    
    AWS Wrangler simplifies working with data on AWS:
    - Handles format detection automatically
    - Supports CSV, Parquet, JSON, Excel, Glue Catalog, etc.
    - Optimized for S3 operations
    - Integrates with Pandas seamlessly
    """

    def __init__(
        self,
        region_name: str = "us-east-1",
        boto3_session=None,
    ):
        """Initialize S3 loader.

        Args:
            region_name (str): AWS region name. Defaults to "us-east-1".
            boto3_session: Optional boto3 Session object for custom credentials.

        Raises:
            ImportError: If awswrangler is not installed.
        """
        try:
            import awswrangler as wr
            self.wr = wr
        except ImportError:
            raise ImportError(
                "awswrangler is required for S3 operations. "
                "Install it with: pip install awswrangler"
            )

        self.region_name = region_name
        self.boto3_session = boto3_session
        logger.info(f"S3Loader initialized for region: {region_name}")

    def load_csv(
        self,
        path: str,
        **kwargs,
    ) -> pd.DataFrame:
        """Load CSV from S3.

        Args:
            path (str): S3 path (e.g., 's3://bucket/key/file.csv')
            **kwargs: Additional arguments for wr.s3.read_csv()

        Returns:
            pd.DataFrame: Loaded data

        Example:
            >>> loader = S3Loader()
            >>> df = loader.load_csv('s3://my-bucket/data/customers.csv')
            >>> print(df.head())
        """
        try:
            logger.info(f"Loading CSV from S3: {path}")
            df = self.wr.s3.read_csv(
                path,
                boto3_session=self.boto3_session,
                **kwargs,
            )
            logger.info(f"✓ Successfully loaded {len(df)} rows from S3")
            return df
        except Exception as e:
            logger.error(f"✗ Failed to load CSV from S3: {str(e)}")
            raise

    def load_parquet(
        self,
        path: str,
        **kwargs,
    ) -> pd.DataFrame:
        """Load Parquet from S3.

        Args:
            path (str): S3 path (e.g., 's3://bucket/key/file.parquet')
            **kwargs: Additional arguments for wr.s3.read_parquet()

        Returns:
            pd.DataFrame: Loaded data

        Example:
            >>> loader = S3Loader()
            >>> df = loader.load_parquet('s3://my-bucket/data/customers.parquet')
            >>> print(df.shape)
        """
        try:
            logger.info(f"Loading Parquet from S3: {path}")
            df = self.wr.s3.read_parquet(
                path,
                boto3_session=self.boto3_session,
                **kwargs,
            )
            logger.info(f"✓ Successfully loaded {len(df)} rows from S3")
            return df
        except Exception as e:
            logger.error(f"✗ Failed to load Parquet from S3: {str(e)}")
            raise

    def load_json(
        self,
        path: str,
        **kwargs,
    ) -> pd.DataFrame:
        """Load JSON from S3.

        Args:
            path (str): S3 path (e.g., 's3://bucket/key/file.json')
            **kwargs: Additional arguments for wr.s3.read_json()

        Returns:
            pd.DataFrame: Loaded data

        Example:
            >>> loader = S3Loader()
            >>> df = loader.load_json('s3://my-bucket/data/customers.json')
            >>> print(df.info())
        """
        try:
            logger.info(f"Loading JSON from S3: {path}")
            df = self.wr.s3.read_json(
                path,
                boto3_session=self.boto3_session,
                **kwargs,
            )
            logger.info(f"✓ Successfully loaded {len(df)} rows from S3")
            return df
        except Exception as e:
            logger.error(f"✗ Failed to load JSON from S3: {str(e)}")
            raise

    def load_excel(
        self,
        path: str,
        **kwargs,
    ) -> pd.DataFrame:
        """Load Excel from S3.

        Args:
            path (str): S3 path (e.g., 's3://bucket/key/file.xlsx')
            **kwargs: Additional arguments for wr.s3.read_excel()

        Returns:
            pd.DataFrame: Loaded data

        Example:
            >>> loader = S3Loader()
            >>> df = loader.load_excel('s3://my-bucket/data/customers.xlsx')
            >>> print(df.columns)
        """
        try:
            logger.info(f"Loading Excel from S3: {path}")
            df = self.wr.s3.read_excel(
                path,
                boto3_session=self.boto3_session,
                **kwargs,
            )
            logger.info(f"✓ Successfully loaded {len(df)} rows from S3")
            return df
        except Exception as e:
            logger.error(f"✗ Failed to load Excel from S3: {str(e)}")
            raise

    def load_glue_catalog(
        self,
        database: str,
        table: str,
        **kwargs,
    ) -> pd.DataFrame:
        """Load data from AWS Glue Catalog table.

        Args:
            database (str): Glue database name
            table (str): Glue table name
            **kwargs: Additional arguments for wr.athena.read_sql_table()

        Returns:
            pd.DataFrame: Loaded data

        Example:
            >>> loader = S3Loader()
            >>> df = loader.load_glue_catalog('my_db', 'customers')
            >>> print(df.head())
        """
        try:
            logger.info(f"Loading from Glue Catalog: {database}.{table}")
            df = self.wr.athena.read_sql_table(
                table=table,
                database=database,
                boto3_session=self.boto3_session,
                **kwargs,
            )
            logger.info(f"✓ Successfully loaded {len(df)} rows from Glue")
            return df
        except Exception as e:
            logger.error(f"✗ Failed to load from Glue: {str(e)}")
            raise


class LocalLoader:
    """Load data from local filesystem."""

    @staticmethod
    def ensure_file_path(file_path: str) -> Path:
        file_path = Path(file_path)
        if not file_path.exists():
            logger.warning(f"File not found: {file_path}")
            raise FileNotFoundError(f"File not found: {file_path}")
        return file_path

    @staticmethod
    def load_csv(file_path: str, **kwargs) -> pd.DataFrame:
        """Load CSV from local filesystem.

        Args:
            file_path (str): Path to CSV file
            **kwargs: Additional arguments for pd.read_csv()

        Returns:
            pd.DataFrame: Loaded data

        Example:
            >>> df = LocalLoader.load_csv('data/customers.csv')
            >>> print(df.head())
        """
        try:
            file_path = LocalLoader.ensure_file_path(file_path)
            logger.info(f"Loading CSV from local: {file_path}")
            df = pd.read_csv(file_path, **kwargs)
            logger.info(f"✓ Successfully loaded {len(df)} rows")
            return df
        except Exception as e:
            logger.error(f"✗ Failed to load CSV: {str(e)}")
            raise

    @staticmethod
    def load_parquet(file_path: str, **kwargs) -> pd.DataFrame:
        """Load Parquet from local filesystem.

        Args:
            file_path (str): Path to Parquet file
            **kwargs: Additional arguments for pd.read_parquet()

        Returns:
            pd.DataFrame: Loaded data

        Example:
            >>> df = LocalLoader.load_parquet('data/customers.parquet')
            >>> print(df.shape)
        """
        try:
            file_path = LocalLoader.ensure_file_path(file_path)
            logger.info(f"Loading Parquet from local: {file_path}")
            df = pd.read_parquet(file_path, **kwargs)
            logger.info(f"✓ Successfully loaded {len(df)} rows")
            return df
        except Exception as e:
            logger.error(f"✗ Failed to load Parquet: {str(e)}")
            raise

    @staticmethod
    def load_json(file_path: str, **kwargs) -> pd.DataFrame:
        """Load JSON from local filesystem.

        Args:
            file_path (str): Path to JSON file
            **kwargs: Additional arguments for pd.read_json()

        Returns:
            pd.DataFrame: Loaded data

        Example:
            >>> df = LocalLoader.load_json('data/customers.json')
            >>> print(df.info())
        """
        try:
            file_path = LocalLoader.ensure_file_path(file_path)
            logger.info(f"Loading JSON from local: {file_path}")
            df = pd.read_json(file_path, **kwargs)
            logger.info(f"✓ Successfully loaded {len(df)} rows")
            return df
        except Exception as e:
            logger.error(f"✗ Failed to load JSON: {str(e)}")
            raise


def load_data(source: str, **kwargs) -> pd.DataFrame:
    """Universal data loader that auto-detects source type.

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
        # Load from S3 using awswrangler
        file_type = source.split(".")[-1].lower()
        try:
            logger.info(f"Auto-detecting format for S3: {source}")
            if file_type == "csv":
                return S3Loader.load_csv(source, **kwargs)
            elif file_type == "parquet":
                return S3Loader.load_parquet(source, **kwargs)
            elif file_type == "json":
                return S3Loader.load_json(source, **kwargs)
            elif file_type == "xlsx" or file_type == "xls":
                return S3Loader.load_excel(source, **kwargs)
            elif file_type == "glue":
                return S3Loader.load_glue_catalog(source, **kwargs)
            else:
                raise ValueError(f"Unsupported file type: {file_type}")
        except Exception as e:
            logger.error(f"✗ Failed to load from S3: {str(e)}")
            raise
    else:
        # Load from local filesystem
        file_type = source.split(".")[-1].lower()
        try:
            logger.info(f"Auto-detecting format for local file: {source}")
            if file_type == "csv":
                return LocalLoader.load_csv(source, **kwargs)
            elif file_type == "parquet":
                return LocalLoader.load_parquet(source, **kwargs)
            elif file_type == "json":
                return LocalLoader.load_json(source, **kwargs)
            else:
                raise ValueError(f"Unsupported file type: {file_type}")
        except Exception as e:
            logger.error(f"✗ Failed to load from local: {str(e)}")
            raise
