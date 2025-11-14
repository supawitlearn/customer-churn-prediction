"""
Tests for data_validation_schema.py

Run with:
    pytest -q
"""
from datetime import datetime, UTC
import pytest
try:
    # Try pydantic v1 / common import
    from pydantic import ValidationError
except Exception:
    try:
        # pydantic v2 may raise pydantic_core ValidationError on model validation
        from pydantic_core import ValidationError  # type: ignore
    except Exception:
        # Fallback to a generic Exception so tests still run and assertions using
        # pytest.raises(ValidationError) won't crash on import. This will make
        # pytest.raises catch any Exception if ValidationError couldn't be resolved.
        ValidationError = Exception  # type: ignore

from src.churn_prediction.pydantic.data_validation_config import (
    DataValidationConfig,
    ColumnParameter,
    ForeignKeyParameter,
    RuleParameter,
    QualityRulesParameter,
)


def make_minimal_valid_config():
    """
    Return a minimal-but-valid configuration dict that should pass validation.
    Note: RuleParameter.enabled is required, so both allow_record_duplicates
    and allow_key_duplicates must be provided.
    """
    return {
        "schema_version": "1.0",
        "columns": {
            "id": {
                "description": "Primary identifier",
                "type": "integer",
                "nullable": False,
            },
            "name": {
                "description": "Person name",
                "type": "string",
                # omit nullable to exercise default (should be True)
            },
        },
        "quality_rules": {
            "allow_record_duplicates": {"enabled": True},
            "allow_key_duplicates": {"enabled": False},
            # foreign_key_checks is optional
        },
        "metadata": {"source": "tests"},
    }


def test_minimal_valid_config_parses():
    cfg = make_minimal_valid_config()
    obj = DataValidationConfig.model_validate(cfg)

    assert obj.schema_version == "1.0"
    # columns present
    assert "id" in obj.columns and "name" in obj.columns
    # id column fields
    id_col = obj.columns["id"]
    assert isinstance(id_col, ColumnParameter)
    assert id_col.description == "Primary identifier"
    assert id_col.type == "integer"
    assert id_col.nullable is False

    # quality rules parsed
    assert isinstance(obj.quality_rules, QualityRulesParameter)
    assert obj.quality_rules.allow_record_duplicates.enabled is True
    assert obj.quality_rules.allow_key_duplicates.enabled is False
    # metadata roundtrip
    assert obj.metadata == {"source": "tests"}


def test_column_nullable_default_true_when_omitted():
    cfg = make_minimal_valid_config()
    # 'name' column omits nullable -> default True expected
    obj = DataValidationConfig.model_validate(cfg)
    name_col = obj.columns["name"]
    assert isinstance(name_col, ColumnParameter)
    assert name_col.nullable is True


def test_foreign_key_parsing():
    cfg = make_minimal_valid_config()
    # Add a foreign key entry for the id column
    cfg["columns"]["id"]["foreign_keys"] = {
        "child_path": "ref/customers.csv",
        "child_column": "user_id",
        "description": "References customer user_id",
    }
    obj = DataValidationConfig.model_validate(cfg)
    fk = obj.columns["id"].foreign_keys
    assert isinstance(fk, ForeignKeyParameter)
    assert fk.child_path == "ref/customers.csv"
    assert fk.child_column == "user_id"
    assert fk.description == "References customer user_id"


def test_missing_required_column_fields_raises():
    cfg = make_minimal_valid_config()
    # Remove description from a column (required)
    del cfg["columns"]["id"]["description"]
    with pytest.raises(ValidationError):
        DataValidationConfig.model_validate(cfg)


def test_missing_quality_rule_required_entry_raises():
    cfg = make_minimal_valid_config()
    # Remove allow_key_duplicates (required)
    del cfg["quality_rules"]["allow_key_duplicates"]
    with pytest.raises(ValidationError):
        DataValidationConfig.model_validate(cfg)
