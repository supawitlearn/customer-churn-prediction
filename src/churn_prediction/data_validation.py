"""
Data Validation Module

This module loads schema configurations and applies validation rules to data
using pandas DataFrames. It ensures data quality before ingestion into the DWH.

Example:
    >>> from src.churn_prediction.data_validation import DataValidator
    >>> validator = DataValidator("config/data_sources/schemas/customer_profile.schema.yaml")
    >>> validation_results = validator.validate(df)
    >>> print(validation_results.report())
"""

import yaml
import pandas as pd
from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional
from dataclasses import dataclass
import re
from datetime import datetime
from src.churn_prediction.logger import logger


@dataclass
class ValidationResult:
    """Stores validation results for a dataset."""
    is_valid: bool
    total_records: int
    valid_records: int
    invalid_records: int
    errors: List[Dict[str, Any]]
    warnings: List[Dict[str, Any]]
    quality_score: float
    
    def report(self) -> str:
        """Generate human-readable validation report."""
        report = f"""
{'='*70}
DATA VALIDATION REPORT
{'='*70}
Valid: {self.is_valid}
Quality Score: {self.quality_score:.2%}
Total Records: {self.total_records}
Valid Records: {self.valid_records}
Invalid Records: {self.invalid_records}

ERRORS ({len(self.errors)}):
{self._format_issues(self.errors)}

WARNINGS ({len(self.warnings)}):
{self._format_issues(self.warnings)}
{'='*70}
        """
        return report
    
    def _format_issues(self, issues: List[Dict]) -> str:
        """Format error/warning list."""
        if not issues:
            return "  None"
        return "\n".join([f"  - {issue['message']}" for issue in issues[:10]])


class DataValidator:
    """
    Validates data against schema configurations.
    
    Loads YAML schema files and applies comprehensive validation rules
    to pandas DataFrames including type checking, constraint validation,
    and data quality checks.
    """
    
    def __init__(self, schema_path: str):
        """
        Initialize validator with schema file.
        
        Args:
            schema_path (str): Path to schema YAML file
        """
        self.schema_path = Path(schema_path)
        self.schema = self._load_schema()
        self.columns_config = self.schema.get('columns', {})
        self.table_constraints = self.schema.get('table_constraints', {})
        self.quality_rules = self.schema.get('quality_rules', {})
        self.transformations = self.schema.get('transformations', [])
        
        logger.info(f"Schema loaded from {schema_path}")
    
    def _load_schema(self) -> Dict:
        """Load and parse YAML schema file."""
        try:
            with open(self.schema_path, 'r', encoding='utf-8') as f:
                schema = yaml.safe_load(f)
            logger.info(f"Successfully loaded schema: {self.schema_path}")
            return schema
        except FileNotFoundError:
            logger.error(f"Schema file not found: {self.schema_path}")
            raise
        except yaml.YAMLError as e:
            logger.error(f"Error parsing YAML schema: {e}")
            raise
    
    def validate(self, df: pd.DataFrame) -> ValidationResult:
        """
        Run all validation checks on DataFrame.
        
        Args:
            df (pd.DataFrame): Data to validate
        
        Returns:
            ValidationResult: Comprehensive validation results
        """
        errors = []
        warnings = []
        
        logger.info(f"Starting validation for {len(df)} records")
        
        # 1. Check required columns exist
        errors.extend(self._validate_columns_exist(df))
        
        # 2. Validate data types
        errors.extend(self._validate_data_types(df))
        
        # 3. Validate null/missing values
        warnings.extend(self._validate_nullability(df))
        
        # 4. Validate constraints (unique, foreign keys, etc.)
        errors.extend(self._validate_constraints(df))
        
        # 5. Validate business rules (enums, patterns, ranges)
        errors.extend(self._validate_business_rules(df))
        
        # 6. Detect anomalies
        warnings.extend(self._detect_anomalies(df))
        
        # Calculate quality score
        valid_records = len(df) - len([e for e in errors if 'row' in str(e)])
        quality_score = valid_records / len(df) if len(df) > 0 else 0
        
        is_valid = len(errors) == 0
        
        result = ValidationResult(
            is_valid=is_valid,
            total_records=len(df),
            valid_records=valid_records,
            invalid_records=len([e for e in errors if 'row' in str(e)]),
            errors=errors,
            warnings=warnings,
            quality_score=quality_score
        )
        
        logger.info(f"Validation complete. Quality Score: {quality_score:.2%}")
        return result
    
    def _validate_columns_exist(self, df: pd.DataFrame) -> List[Dict]:
        """Check all required columns exist in DataFrame."""
        errors = []
        required_columns = set(self.columns_config.keys())
        df_columns = set(df.columns)
        
        missing_columns = required_columns - df_columns
        if missing_columns:
            error = {
                'type': 'MissingColumn',
                'columns': list(missing_columns),
                'message': f"Missing required columns: {missing_columns}"
            }
            errors.append(error)
            logger.warning(f"Missing columns: {missing_columns}")
        
        extra_columns = df_columns - required_columns
        if extra_columns:
            logger.info(f"Extra columns found (will be ignored): {extra_columns}")
        
        return errors
    
    def _validate_data_types(self, df: pd.DataFrame) -> List[Dict]:
        """Validate column data types."""
        errors = []
        
        for column, config in self.columns_config.items():
            if column not in df.columns:
                continue
            
            expected_type = config.get('type')
            
            try:
                if expected_type == 'date':
                    # Try to parse as date
                    pd.to_datetime(df[column], errors='coerce')
                    null_count = df[column].isna().sum()
                    if null_count > 0 and not config.get('nullable', False):
                        errors.append({
                            'column': column,
                            'type': 'InvalidDateFormat',
                            'message': f"Column '{column}' has {null_count} invalid dates"
                        })
                
                elif expected_type == 'datetime':
                    pd.to_datetime(df[column], errors='coerce')
                    null_count = df[column].isna().sum()
                    if null_count > 0 and not config.get('nullable', False):
                        errors.append({
                            'column': column,
                            'type': 'InvalidDatetimeFormat',
                            'message': f"Column '{column}' has {null_count} invalid datetimes"
                        })
                
                elif expected_type == 'numeric':
                    pd.to_numeric(df[column], errors='coerce')
                    null_count = df[column].isna().sum()
                    if null_count > 0 and not config.get('nullable', False):
                        errors.append({
                            'column': column,
                            'type': 'InvalidNumeric',
                            'message': f"Column '{column}' has {null_count} non-numeric values"
                        })
            
            except Exception as e:
                logger.error(f"Error validating type for column '{column}': {e}")
        
        return errors
    
    def _validate_nullability(self, df: pd.DataFrame) -> List[Dict]:
        """Validate null/missing values against schema."""
        warnings = []
        null_tolerance = self.quality_rules.get('null_tolerance', {})
        
        for column, config in self.columns_config.items():
            if column not in df.columns:
                continue
            
            null_count = df[column].isna().sum()
            total_count = len(df)
            null_percentage = (null_count / total_count * 100) if total_count > 0 else 0
            
            is_nullable = config.get('nullable', False)
            tolerance = null_tolerance.get(column, 0)
            
            # Check if nulls exceed tolerance
            if null_percentage > tolerance:
                if not is_nullable and null_count > 0:
                    warnings.append({
                        'column': column,
                        'type': 'NullableViolation',
                        'null_percentage': null_percentage,
                        'message': f"Column '{column}' has {null_percentage:.2f}% null values "
                                   f"(tolerance: {tolerance}%)"
                    })
            
            logger.info(f"Column '{column}': {null_percentage:.2f}% null values")
        
        return warnings
    
    def _validate_constraints(self, df: pd.DataFrame) -> List[Dict]:
        """Validate primary key, unique, and foreign key constraints."""
        errors = []
        
        # Check unique constraints
        primary_keys = self.table_constraints.get('primary_keys', [])
        for column in primary_keys:
            if column not in df.columns:
                continue
            
            duplicate_count = df[column].duplicated().sum()
            if duplicate_count > 0:
                errors.append({
                    'column': column,
                    'type': 'DuplicateKeyViolation',
                    'duplicate_count': duplicate_count,
                    'message': f"Column '{column}' has {duplicate_count} duplicate values"
                })
                logger.error(f"Duplicate values found in '{column}'")
        
        # Check primary key
        primary_key = self.table_constraints.get('primary_key')
        if primary_key and primary_key in df.columns:
            duplicate_count = df[primary_key].duplicated().sum()
            null_count = df[primary_key].isna().sum()
            
            if duplicate_count > 0:
                errors.append({
                    'column': primary_key,
                    'type': 'PrimaryKeyDuplicate',
                    'duplicate_count': duplicate_count,
                    'message': f"Primary key '{primary_key}' has {duplicate_count} duplicates"
                })
            
            if null_count > 0:
                errors.append({
                    'column': primary_key,
                    'type': 'PrimaryKeyNull',
                    'null_count': null_count,
                    'message': f"Primary key '{primary_key}' has {null_count} null values"
                })
        
        return errors
    
    def _validate_business_rules(self, df: pd.DataFrame) -> List[Dict]:
        """Validate business rules (enums, patterns, ranges)."""
        errors = []
        
        for column, config in self.columns_config.items():
            if column not in df.columns:
                continue
            
            constraints = config.get('constraints', [])
            
            for constraint in constraints:
                constraint_type = constraint.get('type')
                
                # Enum constraint
                if constraint_type == 'enum':
                    allowed_values = constraint.get('values', [])
                    invalid_rows = ~df[column].isin(allowed_values) & df[column].notna()
                    invalid_count = invalid_rows.sum()
                    
                    if invalid_count > 0:
                        errors.append({
                            'column': column,
                            'type': 'EnumViolation',
                            'allowed_values': allowed_values,
                            'invalid_count': invalid_count,
                            'message': f"Column '{column}' has {invalid_count} values outside "
                                       f"allowed enum: {allowed_values}"
                        })
                        logger.warning(f"Enum violation in '{column}'")
                
                # Pattern constraint (regex)
                elif constraint_type == 'pattern':
                    pattern = constraint.get('value')
                    invalid_rows = df[column].astype(str).str.match(pattern) == False
                    invalid_count = invalid_rows.sum()
                    
                    if invalid_count > 0:
                        errors.append({
                            'column': column,
                            'type': 'PatternViolation',
                            'pattern': pattern,
                            'invalid_count': invalid_count,
                            'message': f"Column '{column}' has {invalid_count} values not matching "
                                       f"pattern: {pattern}"
                        })
                        logger.warning(f"Pattern violation in '{column}'")
                
                # Date range constraint
                elif constraint_type == 'date_range':
                    min_date = constraint.get('min')
                    max_date = constraint.get('max')
                    
                    try:
                        df_dates = pd.to_datetime(df[column], errors='coerce')
                        if min_date:
                            before_min = (df_dates < pd.to_datetime(min_date)).sum()
                            if before_min > 0:
                                errors.append({
                                    'column': column,
                                    'type': 'DateRangeViolation',
                                    'min_date': min_date,
                                    'violation_count': before_min,
                                    'message': f"Column '{column}' has {before_min} dates before {min_date}"
                                })
                        
                        if max_date:
                            after_max = (df_dates > pd.to_datetime(max_date)).sum()
                            if after_max > 0:
                                errors.append({
                                    'column': column,
                                    'type': 'DateRangeViolation',
                                    'max_date': max_date,
                                    'violation_count': after_max,
                                    'message': f"Column '{column}' has {after_max} dates after {max_date}"
                                })
                    except Exception as e:
                        logger.error(f"Error validating date range for '{column}': {e}")
        
        return errors
    
    def _detect_anomalies(self, df: pd.DataFrame) -> List[Dict]:
        """Detect statistical anomalies."""
        warnings = []
        statistical_bounds = self.quality_rules.get('statistical_bounds', {})
        
        if not statistical_bounds.get('enabled', False):
            return warnings
        
        for column, config in self.columns_config.items():
            if column not in df.columns:
                continue
            
            # Check for not_future constraint on dates
            constraints = config.get('constraints', [])
            for constraint in constraints:
                if constraint.get('type') == 'not_future':
                    try:
                        df_dates = pd.to_datetime(df[column], errors='coerce')
                        future_count = (df_dates > datetime.now()).sum()
                        
                        if future_count > 0:
                            warnings.append({
                                'column': column,
                                'type': 'FutureDate',
                                'anomaly_count': future_count,
                                'message': f"Column '{column}' has {future_count} future dates"
                            })
                            logger.warning(f"Future dates detected in '{column}'")
                    except Exception as e:
                        logger.error(f"Error checking future dates in '{column}': {e}")
        
        return warnings


# Example usage
if __name__ == "__main__":
    # Load schema
    schema_path = "src/churn_prediction/config/data_sources/schemas/customer_profile.schema.yaml"
    validator = DataValidator(schema_path)
    
    # Create sample data
    sample_data = {
        'user_id': ['user_001', 'user_002', 'user_003'],
        'first_name': ['John', 'Jane', 'Bob'],
        'last_name': ['Doe', 'Smith', 'Johnson'],
        'activated': ['yes', 'yes', 'no'],
        'admin_id': ['admin_001', 'admin_002', 'admin_003'],
        'sex': ['M', 'F', 'M'],
        'foreigner': ['no', 'yes', 'no'],
        'birthdate': ['1990-01-15', '1985-03-22', '1992-07-10'],
        'registed_time': ['2023-01-01 10:30:00', '2023-01-05 14:20:00', '2023-01-10 09:15:00']
    }
    
    df = pd.DataFrame(sample_data)
    
    # Validate data
    results = validator.validate(df)
    print(results.report())
    
    # Apply transformations
    df_clean = validator.apply_transformations(df)
    print("\nTransformed Data:")
    print(df_clean)
