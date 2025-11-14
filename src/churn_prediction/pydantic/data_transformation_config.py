from pydantic import BaseModel, Field
from typing import Optional, List, Any, Dict

class ColumnParameter(BaseModel):
    """
    Column Parameter Model

    Attributes:
        description (str): Description of the column
        type (str): Data type of the column
    """
    description: str = Field(..., description="Description of the column")
    type: str = Field(..., description="Data type of the column")


class TransformationParameter(BaseModel):
    """
    Transformation Parameter Model

    Attributes:
        description (str): Description of the transformation
        kind (str): Kind of transformation
        parameters (Dict[str, Any]): Parameters for the transformation operations
    """
    description: str = Field(..., description="Description of the transformation")
    kind: str = Field(..., description="Kind of transformation")
    parameters: Dict[str, Any] = Field(..., description="Parameters for the transformation operations")


class DataTransformationConfig(BaseModel):
    """
    Data Transformation Schema Configuration Model

    Attributes:
        schema_version (str): Version of the schema
        schema_type (str): Type of the schema
        columns (Dict[str, ColumnParameter]): Column configurations
        transformation (Optional[Dict[str, TransformationParameter]]): Transformation configurations
        metadata (Optional[dict]): Metadata information
    """
    schema_version: str = Field(..., description="Version of the schema")
    schema_type: str = Field(..., description="Type of the schema")
    columns: Dict[str, ColumnParameter] = Field(..., description="Column configurations")
    transformation: Optional[Dict[str, TransformationParameter]] = Field(None, description="Transformation configurations")
    metadata: Optional[dict] = Field(None, description="Metadata information")
