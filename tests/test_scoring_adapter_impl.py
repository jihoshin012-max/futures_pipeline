"""Unit tests for scoring adapter factory and BinnedScoringAdapter implementation.

Tests the factory dispatch, BinnedScoringAdapter placeholder behavior,
and stub NotImplementedError preservation for SklearnScoringAdapter and ONNXScoringAdapter.
"""

import os
import pytest
import pandas as pd

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MODEL_PATH = os.path.join(REPO_ROOT, "shared/scoring_models/zone_touch_v1.json")

from shared.scoring_models.scoring_adapter import (
    load_scoring_adapter,
    BinnedScoringAdapter,
    SklearnScoringAdapter,
    ONNXScoringAdapter,
)


# --- Factory tests ---

def test_factory_binned():
    """load_scoring_adapter with 'BinnedScoringAdapter' returns BinnedScoringAdapter instance."""
    adapter = load_scoring_adapter(MODEL_PATH, "BinnedScoringAdapter")
    assert isinstance(adapter, BinnedScoringAdapter)


def test_factory_sklearn():
    """load_scoring_adapter with 'SklearnScoringAdapter' returns SklearnScoringAdapter (stub)."""
    adapter = load_scoring_adapter(MODEL_PATH, "SklearnScoringAdapter")
    assert isinstance(adapter, SklearnScoringAdapter)


def test_factory_onnx():
    """load_scoring_adapter with 'ONNXScoringAdapter' returns ONNXScoringAdapter (stub)."""
    adapter = load_scoring_adapter(MODEL_PATH, "ONNXScoringAdapter")
    assert isinstance(adapter, ONNXScoringAdapter)


def test_factory_unknown_raises_system_exit():
    """load_scoring_adapter with unknown adapter_type raises SystemExit naming the adapter."""
    with pytest.raises(SystemExit) as exc_info:
        load_scoring_adapter(MODEL_PATH, "FooAdapter")
    # SystemExit message should name the unknown adapter
    assert "FooAdapter" in str(exc_info.value)


# --- BinnedScoringAdapter tests ---

def test_binned_score_returns_series_empty_df():
    """BinnedScoringAdapter.score on empty DataFrame returns empty pd.Series."""
    adapter = load_scoring_adapter(MODEL_PATH, "BinnedScoringAdapter")
    df = pd.DataFrame(columns=["TouchType", "Reaction", "Penetration"])
    result = adapter.score(df)
    assert isinstance(result, pd.Series), f"Expected pd.Series, got {type(result)}"
    assert len(result) == 0


def test_binned_score_returns_series_aligned_to_index():
    """BinnedScoringAdapter.score returns pd.Series aligned to touch_df.index."""
    adapter = load_scoring_adapter(MODEL_PATH, "BinnedScoringAdapter")
    # Create a DataFrame with a non-default index
    df = pd.DataFrame(
        {"TouchType": ["DEMAND_EDGE", "SUPPLY_EDGE"], "Reaction": [100, 200]},
        index=[10, 20],
    )
    result = adapter.score(df)
    assert isinstance(result, pd.Series), f"Expected pd.Series, got {type(result)}"
    assert list(result.index) == [10, 20], f"Series index must align to df.index: {list(result.index)}"


def test_binned_score_returns_floats():
    """BinnedScoringAdapter.score returns float dtype (placeholder model returns zeros)."""
    adapter = load_scoring_adapter(MODEL_PATH, "BinnedScoringAdapter")
    df = pd.DataFrame({"x": [1, 2, 3]})
    result = adapter.score(df)
    assert pd.api.types.is_float_dtype(result.dtype), f"Expected float dtype, got {result.dtype}"


def test_binned_score_placeholder_all_zeros():
    """Placeholder zone_touch_v1.json has all-zero weights, so score returns all zeros."""
    adapter = load_scoring_adapter(MODEL_PATH, "BinnedScoringAdapter")
    df = pd.DataFrame({"x": [1, 2, 3]})
    result = adapter.score(df)
    assert (result == 0.0).all(), f"Placeholder model should return all zeros: {result.values}"


def test_binned_adapter_loads_json():
    """BinnedScoringAdapter.__init__ loads JSON and stores model data."""
    adapter = BinnedScoringAdapter(MODEL_PATH)
    # Should have loaded weights and bin_edges from JSON
    assert hasattr(adapter, "weights"), "BinnedScoringAdapter must store weights from JSON"
    assert hasattr(adapter, "bin_edges"), "BinnedScoringAdapter must store bin_edges from JSON"
    assert isinstance(adapter.weights, dict)
    assert isinstance(adapter.bin_edges, dict)


# --- Stub tests (NotImplementedError preserved) ---

def test_sklearn_stub_raises_not_implemented():
    """SklearnScoringAdapter.score() still raises NotImplementedError (stub)."""
    adapter = SklearnScoringAdapter(MODEL_PATH)
    with pytest.raises(NotImplementedError):
        adapter.score(pd.DataFrame())


def test_onnx_stub_raises_not_implemented():
    """ONNXScoringAdapter.score() still raises NotImplementedError (stub)."""
    adapter = ONNXScoringAdapter(MODEL_PATH)
    with pytest.raises(NotImplementedError):
        adapter.score(pd.DataFrame())
