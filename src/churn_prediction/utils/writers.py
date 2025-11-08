"""Data writers for S3 and local sources using AWS Wrangler."""

from typing import Optional, List
from pathlib import Path
import pandas as pd

from src.churn_prediction.logger import logger


class S3Writer:
    """Save data to AWS S3 using AWS Wrangler.
    
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
        logger.info(f"S3Writer initialized for region: {region_name}")

    def save_csv(
        self,
        df: pd.DataFrame,
        path: str,
        index: bool = False,
        **kwargs,
    ) -> None:
        """Save DataFrame as CSV to S3.

        Args:
            df (pd.DataFrame): DataFrame to save
            path (str): S3 path (e.g., 's3://bucket/key/file.csv')
            index (bool): Whether to save index. Defaults to False.
            **kwargs: Additional arguments for wr.s3.to_csv()

        Example:
            >>> loader = S3Loader()
            >>> loader.save_csv(df, 's3://my-bucket/output/result.csv')
        """
        try:
            logger.info(f"Saving CSV to S3: {path}")
            self.wr.s3.to_csv(
                df,
                path,
                index=index,
                boto3_session=self.boto3_session,
                **kwargs,
            )
            logger.info(f"✓ Successfully saved {len(df)} rows to S3")
        except Exception as e:
            logger.error(f"✗ Failed to save CSV to S3: {str(e)}")
            raise

    def save_parquet(
        self,
        df: pd.DataFrame,
        path: str,
        index: bool = False,
        **kwargs,
    ) -> None:
        """Save DataFrame as Parquet to S3.

        Args:
            df (pd.DataFrame): DataFrame to save
            path (str): S3 path (e.g., 's3://bucket/key/file.parquet')
            index (bool): Whether to save index. Defaults to False.
            **kwargs: Additional arguments for wr.s3.to_parquet()

        Example:
            >>> loader = S3Loader()
            >>> loader.save_parquet(df, 's3://my-bucket/output/result.parquet')
        """
        try:
            logger.info(f"Saving Parquet to S3: {path}")
            self.wr.s3.to_parquet(
                df,
                path,
                index=index,
                boto3_session=self.boto3_session,
                **kwargs,
            )
            logger.info(f"✓ Successfully saved {len(df)} rows to S3")
        except Exception as e:
            logger.error(f"✗ Failed to save Parquet to S3: {str(e)}")
            raise

    def save_json(
        self,
        df: pd.DataFrame,
        path: str,
        **kwargs,
    ) -> None:
        """Save DataFrame as JSON to S3.

        Args:
            df (pd.DataFrame): DataFrame to save
            path (str): S3 path (e.g., 's3://bucket/key/file.json')
            **kwargs: Additional arguments for wr.s3.to_json()

        Example:
            >>> loader = S3Loader()
            >>> loader.save_json(df, 's3://my-bucket/output/result.json')
        """
        try:
            logger.info(f"Saving JSON to S3: {path}")
            self.wr.s3.to_json(
                df,
                path,
                boto3_session=self.boto3_session,
                **kwargs,
            )
            logger.info(f"✓ Successfully saved {len(df)} rows to S3")
        except Exception as e:
            logger.error(f"✗ Failed to save JSON to S3: {str(e)}")
            raise

    def list_objects(
        self,
        path: str,
        recursive: bool = True,
        suffix: Optional[str] = None,
    ) -> List[str]:
        """List objects in S3 path.

        Args:
            path (str): S3 path (e.g., 's3://bucket/prefix/')
            recursive (bool): List recursively. Defaults to True.
            suffix (Optional[str]): Filter by file extension (e.g., '.csv')

        Returns:
            List[str]: List of S3 paths

        Example:
            >>> loader = S3Loader()
            >>> files = loader.list_objects('s3://my-bucket/data/', suffix='.csv')
            >>> print(files)
        """
        try:
            logger.info(f"Listing objects in S3: {path}")
            objects = self.wr.s3.list_objects(
                path,
                recursive=recursive,
                boto3_session=self.boto3_session,
            )

            if suffix:
                objects = [obj for obj in objects if obj.endswith(suffix)]

            logger.info(f"✓ Found {len(objects)} objects")
            return objects
        except Exception as e:
            logger.error(f"✗ Failed to list S3 objects: {str(e)}")
            raise

    def delete_object(self, path: str) -> None:
        """Delete object from S3.

        Args:
            path (str): S3 path (e.g., 's3://bucket/key/file.csv')

        Example:
            >>> loader = S3Loader()
            >>> loader.delete_object('s3://my-bucket/data/old_file.csv')
        """
        try:
            logger.info(f"Deleting object from S3: {path}")
            self.wr.s3.delete_objects(
                path,
                boto3_session=self.boto3_session,
            )
            logger.info(f"✓ Successfully deleted object from S3")
        except Exception as e:
            logger.error(f"✗ Failed to delete object from S3: {str(e)}")
            raise

    def copy_object(
        self,
        source: str,
        dest: str,
    ) -> None:
        """Copy object from source to destination in S3.

        Args:
            source (str): Source S3 path
            dest (str): Destination S3 path

        Example:
            >>> loader = S3Loader()
            >>> loader.copy_object('s3://bucket/old.csv', 's3://bucket/new.csv')
        """
        try:
            logger.info(f"Copying from {source} to {dest}")
            self.wr.s3.copy_objects(
                source,
                dest,
                boto3_session=self.boto3_session,
            )
            logger.info(f"✓ Successfully copied object")
        except Exception as e:
            logger.error(f"✗ Failed to copy object: {str(e)}")
            raise


class LocalWriter:
    """Save data to local filesystem."""

    @staticmethod
    def ensure_file_path(file_path: str) -> Path:
        """
        Ensure the directory for the given file path exists.
        
        Args:
            file_path (str): The file path (including file name).
        
        Returns:
            Path: A Path object of the file path.
        """
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def save_csv(
        df: pd.DataFrame,
        file_path: str,
        index: bool = False,
        **kwargs,
    ) -> None:
        """Save DataFrame as CSV to local filesystem.

        Args:
            df (pd.DataFrame): DataFrame to save
            file_path (str): Path to save the CSV file
            index (bool): Whether to save index. Defaults to False.
            **kwargs: Additional arguments for df.to_csv()

        Example:
            >>> LocalLoader.save_csv(df, 'output/result.csv')
        """
        try:
            file_path = LocalWriter.ensure_file_path(file_path)
            logger.info(f"Saving CSV to local: {file_path}")
            df.to_csv(file_path, index=index, **kwargs)
            logger.info(f"✓ Successfully saved {len(df)} rows")
        except Exception as e:
            logger.error(f"✗ Failed to save CSV: {str(e)}")
            raise

    @staticmethod
    def save_parquet(
        df: pd.DataFrame,
        file_path: str,
        index: bool = False,
        **kwargs,
    ) -> None:
        """Save DataFrame as Parquet to local filesystem.

        Args:
            df (pd.DataFrame): DataFrame to save
            file_path (str): Path to save the Parquet file
            index (bool): Whether to save index. Defaults to False.
            **kwargs: Additional arguments for df.to_parquet()

        Example:
            >>> LocalLoader.save_parquet(df, 'output/result.parquet')
        """
        try:
            logger.info(f"Saving Parquet to local: {file_path}")
            file_path = LocalWriter.ensure_file_path(file_path)
            df.to_parquet(file_path, index=index, **kwargs)
            logger.info(f"✓ Successfully saved {len(df)} rows")
        except Exception as e:
            logger.error(f"✗ Failed to save Parquet: {str(e)}")
            raise

def save_data(
    df: pd.DataFrame,
    file_path: str,
    index: bool = False,
    **kwargs,
) -> None:
    """Save DataFrame to a file.

    Args:
        df (pd.DataFrame): DataFrame to save
        file_path (str): Path to save the file
        index (bool): Whether to save index. Defaults to False.
        **kwargs: Additional arguments for file saving functions

    Example:
        >>> save_data(df, 'output/result.csv')
    """
    if file_path.endswith('.csv'):
        LocalWriter.save_csv(df, file_path=file_path, index=index, **kwargs)
    elif file_path.endswith('.parquet'):
        LocalWriter.save_parquet(df, file_path=file_path, index=index, **kwargs)
    else:
        raise ValueError(f"Unsupported file format for path: {file_path}")