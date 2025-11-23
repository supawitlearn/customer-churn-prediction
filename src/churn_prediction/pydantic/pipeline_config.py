from pydantic import BaseModel, Field
from typing import Optional, List, Any, Dict


class IngestionParameter(BaseModel):
    """
    Ingestion Parameter Model

    Attributes:
        config_path (str): Path to ingestion configuration file
        input (Dict[str, Any]): Input data source configuration
        output (Dict[str, Any]): Output data destination configuration
    """
    config_path: str = Field(..., description="Path to data ingestion configuration file")
    input: Dict[str, Any] = Field(..., description="Input data source configuration")
    output: Dict[str, Any] = Field(..., description="Output data destination configuration")


class ValidationConfig(BaseModel):
    """
    Ingestion Parameter Model

    Attributes:
        config_path (str): Path to data validation configuration file
        input (Dict[str, Any]): Input data source configuration
        output (Dict[str, Any]): Output data destination configuration
    """
    config_path: str = Field(..., description="Path to data validation configuration file")
    input: Dict[str, Any] = Field(..., description="Input data source configuration")
    output: Dict[str, Any] = Field(..., description="Output data destination configuration")


class TransformationParameter(BaseModel):
    """
    Transformation Parameter Model

    Attributes:
        config_path (str): Path to data transformation configuration file
        input (Dict[str, Any]): Input data source configuration
        output (Dict[str, Any]): Output data destination configuration
    """
    config_path: str = Field(..., description="Path to data transformation configuration file")
    input: Dict[str, Any] = Field(..., description="Input data source configuration")
    output: Dict[str, Any] = Field(..., description="Output data destination configuration")

class FeatureEngineeringParameter(BaseModel):
    """
    Feature Engineering Parameter Model

    Attributes:
        module (str): Module name for feature engineering
        input (Dict[str, Any]): Input data source configuration
        output (Dict[str, Any]): Output data destination configuration
        resources (Dict[str, Any]): Additional resources for feature engineering
    """
    module: str = Field(..., description="Module name for feature engineering")
    input: Dict[str, Any] = Field(..., description="Input data source configuration")
    output: Dict[str, Any] = Field(..., description="Output data destination configuration")
    resources: Optional[Dict[str, Any]] = Field(None, description="Additional resources for feature engineering")

class TrainingParameter(BaseModel):
    """
    Training Parameter Model

    Attributes:
        config_path (str): Path to data training configuration file
        input (Dict[str, Any]): Input data source configuration
        output (Dict[str, Any]): Output data destination configuration
    """
    config_path: str = Field(..., description="Path to data training configuration file")
    input: Dict[str, Any] = Field(..., description="Input data source configuration")
    output: Dict[str, Any] = Field(..., description="Output data destination configuration")


class InferenceParameter(BaseModel):
    """
    Inference Parameter Model

    Attributes:
        config_path (str): Path to data inference configuration file
        input (Dict[str, Any]): Input data source configuration
        output (Dict[str, Any]): Output data destination configuration
    """
    config_path: str = Field(..., description="Path to data inference configuration file")
    input: Dict[str, Any] = Field(..., description="Input data source configuration")
    output: Dict[str, Any] = Field(..., description="Output data destination configuration")


class PipelineConfig(BaseModel):
    """
    Pipeline Configuration Model

    Attributes:
        name (str): Name of the pipeline
        version (str): Version of the pipeline
        description (str): Description of the pipeline
        owner (str): Owner of the pipeline
        ingestion (Optional[IngestionParameter]): Ingestion configuration
        validation (Optional[ValidationConfig]): Validation configuration
        transformation (Optional[TransformationParameter]): Transformation configuration
        training (Optional[TrainingParameter]): Training configuration
        inference (Optional[InferenceParameter]): Inference configuration
    """
    name: str = Field(..., description="Name of the pipeline")
    version: str = Field(..., description="Version of the pipeline")
    ingestion: Optional[IngestionParameter] = Field(None, description="Ingestion configuration")
    validation: Optional[ValidationConfig] = Field(None, description="Validation configuration")
    transformation: Optional[TransformationParameter] = Field(None, description="Transformation configuration")
    feature_engineering: Optional[FeatureEngineeringParameter] = Field(None, description="Feature engineering configuration")
    training: Optional[TrainingParameter] = Field(None, description="Training configuration")
    inference: Optional[InferenceParameter] = Field(None, description="Inference configuration")
