from pydantic import BaseModel, Field
from typing import Optional, List, Any, Dict

class ColumnParameter(BaseModel):
    """
    Column Parameter Model

    Attributes:
        description (str): Description of the column
        target_column (str): Target column name in source data
    """
    description: str = Field(..., description="Description of the column")
    target_column: str = Field(..., description="Target column name in source data")


class DataIngestionConfig(BaseModel):
    """
    Data Ingestion Schema Configuration Model

    Attributes:
        schema_version (str): Version of the schema
        columns (dict): Column configurations
        metadata (Optional[dict]): Metadata information
    """
    schema_version: str = Field(..., description="Version of the schema")
    columns: Dict[str, ColumnParameter] = Field(..., description="Column configurations")
    metadata: Optional[dict] = Field(None, description="Metadata information")