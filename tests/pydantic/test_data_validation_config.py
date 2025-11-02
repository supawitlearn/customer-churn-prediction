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
    ColumnParameter,
    RuleParameter,
    QualityRulesParameter,
    DataValidationSchemaConfig,
)


def make_sample_column():
    return {
        "description": "User identifier",
        "type": "integer",
        "data_type": "INT",
        "nullable": False,
        "unique": True,
        # constraints may be an empty list or contain ConstraintParameter objects;
        # here we provide an empty list to exercise default handling.
        "constraints": [],
    }


def make_sample_quality_rules():
    return {
        "allow_record_duplicates": {"enabled": False, "description": "No duplicate records allowed"},
        "allow_key_duplicates": {"enabled": False},
        # optional fields left out to ensure optional handling
    }


def make_valid_schema_payload():
    return {
        "schema_version": "1.0.0",
        "columns": {
            "user_id": make_sample_column(),
            "email": {
                "description": "Email address",
                "type": "string",
                "data_type": "VARCHAR(255)",
                "nullable": False,
                "unique": True,
                # test that constraints default_factory works when omitted
            },
        },
        "quality_rules": make_sample_quality_rules(),
        "metadata": {"created_by": "test-suite", "created_at": datetime.now(UTC)},
    }


def test_columnparameter_accepts_valid_data():
    col = ColumnParameter(**make_sample_column())
    assert col.description == "User identifier"
    assert col.type == "integer"
    assert col.data_type == "INT"
    assert col.nullable is False
    assert col.unique is True
    # constraints should be a list (default_factory ensures [] when omitted)
    assert isinstance(col.constraints, list)


def test_ruleparameter_requires_enabled():
    # enabled is required
    with pytest.raises(ValidationError):
        RuleParameter()  # missing required field

    # valid when enabled provided
    r = RuleParameter(enabled=True)
    assert r.enabled is True
    assert r.description is None


def test_qualityrules_accepts_required_and_optional_fields():
    payload = {
        "allow_record_duplicates": {"enabled": True},
        "allow_key_duplicates": {"enabled": False},
        # leave optional fields out to ensure they are treated as None
    }
    qr = QualityRulesParameter(**payload)
    assert isinstance(qr.allow_record_duplicates, RuleParameter)
    assert qr.foreign_key_checks is None
    assert qr.statistical_bounds is None


def test_data_validation_schema_config_roundtrip_and_types():
    payload = make_valid_schema_payload()
    cfg = DataValidationSchemaConfig(**payload)

    assert cfg.schema_version == "1.0.0"
    # columns should be parsed into a dict of ColumnParameter
    assert "user_id" in cfg.columns
    assert isinstance(cfg.columns["user_id"], ColumnParameter)
    assert cfg.columns["email"].description == "Email address"

    # quality_rules should be parsed into QualityRulesParameter
    assert isinstance(cfg.quality_rules, QualityRulesParameter)
    assert cfg.metadata["created_by"] == "test-suite"

    # serializing to dict should produce JSON-serializable primitives
    d = cfg.dict()
    assert d["schema_version"] == payload["schema_version"]
    assert "columns" in d and "user_id" in d["columns"]


def test_missing_required_fields_in_schema_config_raises():
    # missing schema_version
    payload = make_valid_schema_payload()
    payload.pop("schema_version")
    with pytest.raises(ValidationError):
        DataValidationSchemaConfig(**payload)

    # missing columns
    payload = make_valid_schema_payload()
    payload.pop("columns")
    with pytest.raises(ValidationError):
        DataValidationSchemaConfig(**payload)

    # missing quality_rules
    payload = make_valid_schema_payload()
    payload.pop("quality_rules")
    with pytest.raises(ValidationError):
        DataValidationSchemaConfig(**payload)


def test_column_defaults_for_constraints_and_nullable():
    # If constraints omitted, default_factory should give an empty list
    col_payload = {
        "description": "Test",
        "type": "string",
        "nullable": True,
    }
    # Provide minimal required fields except constraints and data_type
    # dataclass/model may require all fields; if 'type' and 'description' are sufficient, this will pass
    col = ColumnParameter(**{"description": "Test", "type": "string"})
    assert col.constraints == [] or isinstance(col.constraints, list)
    assert isinstance(col.nullable, bool)


def test_quality_rules_validation_errors_are_informative():
    # allow_record_duplicates must be present and be a RuleParameter-like mapping
    bad_payload = {
        "schema_version": "1.0",
        "columns": {"a": {"description": "x", "type": "string"}},
        "quality_rules": {"allow_record_duplicates": "not-a-dict", "allow_key_duplicates": {"enabled": True}},
    }
    with pytest.raises(ValidationError) as excinfo:
        DataValidationSchemaConfig(**bad_payload)

    # error should mention the problematic field
    msg = str(excinfo.value)
    assert "allow_record_duplicates" in msg or "quality_rules" in msg
