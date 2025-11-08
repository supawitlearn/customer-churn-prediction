"""
Tests for common utility functions (common.py).

Run with:
    pytest -q
"""
import yaml
import pytest
import pandas as pd
import numpy as np
from src.churn_prediction.utils.common import load_single_config
from src.churn_prediction.utils.common import generate_sk_key

# Compatibility import for pydantic BaseModel and ValidationError across v1/v2
try:
    from pydantic import BaseModel, ValidationError
except Exception:
    # pydantic v2 exposes BaseModel in pydantic; ValidationError might come from pydantic_core
    try:
        from pydantic import BaseModel  # type: ignore
        from pydantic_core import ValidationError  # type: ignore
    except Exception:
        # As a last resort, import BaseModel from pydantic if available and fallback ValidationError to Exception
        from pydantic import BaseModel  # type: ignore
        ValidationError = Exception  # type: ignore

# ============================================================
# Test generate_sk_key
# ============================================================

def test_generate_sk_key_basic():
    df = pd.DataFrame({"a": ["x", "y", "z"]})
    returned = generate_sk_key(df)

    # function should return the same object (in-place mutation)
    assert returned is df

    # sk_key column added
    assert "sk_key" in df.columns

    # values are 1..n
    assert df["sk_key"].tolist() == ["1", "2", "3"]

    # dtype is string-like
    assert np.issubdtype(df["sk_key"].dtype, np.object_)


def test_preserves_row_order_and_index():
    # Create a dataframe with non-default index and shuffled rows
    df = pd.DataFrame({"val": [10, 20, 30]}, index=["r1", "r2", "r3"])
    df = df.loc[["r3", "r1", "r2"]].copy()  # reorder rows
    original_vals = df["val"].tolist()

    generate_sk_key(df)

    # Ensure order of rows is preserved and sk_key corresponds to row order (1-based)
    assert df["val"].tolist() == original_vals
    assert df["sk_key"].tolist() == ["1", "2", "3"]


def test_empty_dataframe_returns_empty_with_sk_key_column():
    df = pd.DataFrame(columns=["a"])
    returned = generate_sk_key(df)

    assert returned is df
    # For empty df, sk_key should be added but have length 0
    assert "sk_key" in df.columns
    assert len(df) == 0
    assert df["sk_key"].tolist() == []


def test_overwrites_existing_sk_key_column():
    df = pd.DataFrame({"a": ["p", "q", "r"], "sk_key": [999, 999, 999]})
    generate_sk_key(df)

    # sk_key should be replaced by 1..n
    assert df["sk_key"].tolist() == ["1", "2", "3"]

# ============================================================
# Test load_single_config
# ============================================================

class SampleConfig(BaseModel):
    name: str
    version: int

def test_load_single_config_success(tmp_path):
    """Test successful loading and parsing of a valid config file."""
    config_data = {
        "name": "test_config",
        "version": 1
    }
    config_file = tmp_path / "config.yaml"
    with open(config_file, 'w') as f:
        yaml.dump(config_data, f)

    config = load_single_config(SampleConfig, str(config_file))
    assert isinstance(config, SampleConfig)
    assert config.name == "test_config"
    assert config.version == 1

def test_load_single_config_validation_error(tmp_path):
    """Test that loading an invalid config file raises a ValidationError."""
    invalid_config_data = {
        "name": "test_config",
        # 'version' is missing, which is required
    }
    config_file = tmp_path / "invalid_config.yaml"
    with open(config_file, 'w') as f:
        yaml.dump(invalid_config_data, f)

    with pytest.raises(ValidationError):
        load_single_config(SampleConfig, str(config_file))