"""Tests for AWS Wrangler loaders."""

import pytest
import pandas as pd
from pathlib import Path
from src.churn_prediction.utils.loaders import LocalLoader, load_data


class TestLocalLoader:
    """Test local file loading with LocalLoader."""

    def test_load_csv_success(self, tmp_path):
        """Test successful CSV loading."""
        # Create test CSV
        df_original = pd.DataFrame({
            "id": [1, 2, 3],
            "name": ["Alice", "Bob", "Charlie"],
            "value": [10.5, 20.3, 15.7],
        })

        csv_file = tmp_path / "test.csv"
        df_original.to_csv(csv_file, index=False)

        # Load and verify
        df_loaded = LocalLoader.load_csv(str(csv_file))

        assert len(df_loaded) == 3
        assert list(df_loaded.columns) == ["id", "name", "value"]
        assert df_loaded["id"].tolist() == [1, 2, 3]

    def test_load_parquet_success(self, tmp_path):
        """Test successful Parquet loading."""
        # Create test Parquet
        df_original = pd.DataFrame({
            "id": [1, 2, 3],
            "category": ["A", "B", "A"],
        })

        parquet_file = tmp_path / "test.parquet"
        df_original.to_parquet(parquet_file, index=False)

        # Load and verify
        df_loaded = LocalLoader.load_parquet(str(parquet_file))

        assert len(df_loaded) == 3
        assert list(df_loaded.columns) == ["id", "category"]

    def test_load_json_success(self, tmp_path):
        """Test successful JSON loading."""
        # Create test JSON
        df_original = pd.DataFrame({
            "id": [1, 2, 3],
            "value": [10, 20, 30],
        })

        json_file = tmp_path / "test.json"
        df_original.to_json(json_file)

        # Load and verify
        df_loaded = LocalLoader.load_json(str(json_file))

        assert len(df_loaded) == 3
        assert set(df_loaded.columns) == {"id", "value"}

    def test_save_csv(self, tmp_path):
        """Test saving CSV."""
        df = pd.DataFrame({
            "col1": [1, 2, 3],
            "col2": ["a", "b", "c"],
        })

        csv_file = tmp_path / "output" / "test.csv"
        LocalLoader.save_csv(df, str(csv_file))

        assert csv_file.exists()
        df_loaded = pd.read_csv(csv_file)
        assert len(df_loaded) == 3
        assert list(df_loaded.columns) == ["col1", "col2"]

    def test_save_parquet(self, tmp_path):
        """Test saving Parquet."""
        df = pd.DataFrame({
            "col1": [1, 2, 3],
            "col2": ["x", "y", "z"],
        })

        parquet_file = tmp_path / "output" / "test.parquet"
        LocalLoader.save_parquet(df, str(parquet_file))

        assert parquet_file.exists()
        df_loaded = pd.read_parquet(parquet_file)
        assert len(df_loaded) == 3

    def test_creates_directories(self, tmp_path):
        """Test that save creates parent directories."""
        df = pd.DataFrame({"x": [1, 2, 3]})

        deep_path = tmp_path / "a" / "b" / "c" / "test.csv"
        LocalLoader.save_csv(df, str(deep_path))

        assert deep_path.exists()
        assert deep_path.parent.exists()


class TestLoadDataFunction:
    """Test universal load_data function."""

    def test_load_local_csv(self, tmp_path):
        """Test loading local CSV via universal loader."""
        df_original = pd.DataFrame({"x": [1, 2, 3], "y": [4, 5, 6]})
        csv_file = tmp_path / "data.csv"
        df_original.to_csv(csv_file, index=False)

        df = load_data(str(csv_file))
        assert len(df) == 3
        assert "x" in df.columns
        assert "y" in df.columns

    def test_load_local_parquet(self, tmp_path):
        """Test loading local Parquet via universal loader."""
        df_original = pd.DataFrame({"a": [10, 20, 30], "b": [40, 50, 60]})
        parquet_file = tmp_path / "data.parquet"
        df_original.to_parquet(parquet_file, index=False)

        df = load_data(str(parquet_file))
        assert len(df) == 3
        assert "a" in df.columns

    def test_load_local_json(self, tmp_path):
        """Test loading local JSON via universal loader."""
        df_original = pd.DataFrame({"p": [1, 2, 3], "q": [4, 5, 6]})
        json_file = tmp_path / "data.json"
        df_original.to_json(json_file)

        df = load_data(str(json_file))
        assert len(df) == 3

    def test_unsupported_local_format(self):
        """Test error handling for unsupported local formats."""
        with pytest.raises(ValueError, match="Unsupported file type"):
            load_data("data.txt")

    def test_unsupported_s3_format(self):
        """Test error handling for unsupported S3 formats."""
        # This will fail during awswrangler import, but tests the path
        with pytest.raises((ValueError, ImportError)):
            load_data("s3://bucket/data.txt")


class TestLoaderEdgeCases:
    """Test edge cases and error handling."""

    def test_load_nonexistent_file(self):
        """Test loading nonexistent file."""
        with pytest.raises(FileNotFoundError):
            LocalLoader.load_csv("nonexistent_file.csv")

    def test_save_with_index(self, tmp_path):
        """Test saving with index included."""
        df = pd.DataFrame(
            {"col1": [1, 2, 3], "col2": ["a", "b", "c"]},
            index=pd.Index([10, 20, 30], name="idx"),
        )

        csv_file = tmp_path / "with_index.csv"
        LocalLoader.save_csv(df, str(csv_file), index=True)

        df_loaded = pd.read_csv(csv_file, index_col="idx")
        assert df_loaded.index.name == "idx"

    def test_empty_dataframe(self, tmp_path):
        """Test handling of empty DataFrame."""
        df = pd.DataFrame({"col1": [], "col2": []})

        csv_file = tmp_path / "empty.csv"
        LocalLoader.save_csv(df, str(csv_file))

        df_loaded = LocalLoader.load_csv(str(csv_file))
        assert len(df_loaded) == 0

    def test_large_dataframe(self, tmp_path):
        """Test handling large DataFrame."""
        import numpy as np

        df = pd.DataFrame({
            "id": np.arange(10000),
            "value": np.random.randn(10000),
            "category": np.random.choice(["A", "B", "C"], 10000),
        })

        csv_file = tmp_path / "large.csv"
        LocalLoader.save_csv(df, str(csv_file))

        df_loaded = LocalLoader.load_csv(str(csv_file))
        assert len(df_loaded) == 10000

    def test_special_characters(self, tmp_path):
        """Test handling special characters in data."""
        df = pd.DataFrame({
            "text": ["Hello, World!", "Special: @#$%", "Unicode: 你好"],
            "value": [1, 2, 3],
        })

        csv_file = tmp_path / "special.csv"
        LocalLoader.save_csv(df, str(csv_file))

        df_loaded = LocalLoader.load_csv(str(csv_file))
        assert df_loaded.iloc[2, 0] == "Unicode: 你好"
