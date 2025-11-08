from pydantic import BaseModel, Field
from typing import Optional, List, Any, Dict

class ForeignKeyParameter(BaseModel):
    """
    Foreign Key Parameter Model

    Attributes:
        child_path (Optional[str]): Description of the dependent table path
        child_column (Optional[str]): Description of the dependent column
        description (Optional[str]): Description of the foreign key
    """
    child_path: Optional[str] = Field(None, description="Description of the dependent table path")
    child_column: Optional[str] = Field(None, description="Description of the dependent column")
    description: Optional[str] = Field(None, description="Description of the foreign key")


class ColumnParameter(BaseModel):
    """
    Column Parameter Model

    Attributes:
        description (str): Description of the column
        type (str): Logical type (e.g. string, integer)
        data_type (Optional[str]): Physical database type, e.g. VARCHAR(50)
        nullable (bool): Whether column allows NULL values
        primary_keys (Optional[bool]): Whether column values must be unique
        foreign_keys (Optional[List[ForeignKeyParameter]]): List of foreign keys for this column
    """
    description: str = Field(..., description="Description of the column")
    type: str = Field(..., description="Logical type (e.g. string, integer)")
    data_type: Optional[str] = Field(None, description="Physical database type, e.g. VARCHAR(50)")
    nullable: bool = Field(True, description="Whether column allows NULL values")
    primary_keys: Optional[bool] = Field(None, description="Whether column values must be unique")
    foreign_keys: Optional[ForeignKeyParameter] = Field(None, description="Foreign keys for this column")


class RuleParameter(BaseModel):
    """
    Rule Configuration Model

    Attributes:
        enabled (bool): Whether this rule is enabled
        description (Optional[str]): Description of the rule
    """
    enabled: bool = Field(..., description="Whether this rule is enabled")
    description: Optional[str] = Field(None, description="Description of the rule")


class QualityRulesParameter(BaseModel):
    """
    Quality Rules Parameter Model

    Attributes:
        allow_record_duplicates (RuleParameter): Configuration for record duplication rule
        allow_key_duplicates (RuleParameter): Configuration for key duplication rule
        foreign_key_checks (RuleParameter): Configuration for foreign key validation
    """
    allow_record_duplicates: RuleParameter = Field(..., description="Duplicate record handling rule")
    allow_key_duplicates: RuleParameter = Field(..., description="Duplicate key handling rule")
    foreign_key_checks: Optional[RuleParameter] = Field(None, description="Foreign key check rule")


class DataValidationConfig(BaseModel):
    """
    Data Validation Schema Configuration Model

    Attributes:
        schema_version (str): Version of the schema
        columns (dict): Column configurations
        quality_rules (dict): Data quality rules
        metadata (Optional[dict]): Metadata information
    """
    schema_version: str = Field(..., description="Version of the schema")
    columns: Dict[str, ColumnParameter] = Field(..., description="Column configurations")
    quality_rules: QualityRulesParameter = Field(..., description="Data quality rules")
    metadata: Optional[dict] = Field(None, description="Metadata information")