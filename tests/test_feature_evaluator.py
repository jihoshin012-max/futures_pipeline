"""Tests for zone_touch feature_evaluator.py interface contract.

These tests verify the standard evaluate() interface shape for Phase 5.
evaluate() returns empty features list (no feature_engine.py yet — Phase 6 work).
The key assertion is the interface contract: correct dict keys and types.
"""

import sys
from pathlib import Path

import pytest

# Add repo root so shared.* imports resolve
_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

from shared.archetypes.zone_touch.feature_evaluator import evaluate  # noqa: E402


class TestFeatureEvaluatorInterface:
    """Verify the evaluate() interface contract."""

    def test_evaluate_is_callable(self):
        """feature_evaluator module has a callable evaluate() at module level."""
        import shared.archetypes.zone_touch.feature_evaluator as mod
        assert callable(getattr(mod, "evaluate", None)), (
            "feature_evaluator module must export a callable 'evaluate' function"
        )

    def test_evaluate_returns_dict(self):
        """evaluate() returns a dict with 'features' (list) and 'n_touches' (int) keys."""
        result = evaluate()
        assert isinstance(result, dict), f"evaluate() must return dict, got {type(result)}"
        assert "features" in result, "Result dict must have 'features' key"
        assert "n_touches" in result, "Result dict must have 'n_touches' key"
        assert isinstance(result["features"], list), "'features' must be a list"
        assert isinstance(result["n_touches"], int), "'n_touches' must be an int"

    def test_evaluate_features_list_schema(self):
        """Each item in 'features' list has 'name', 'spread', 'mwu_p', 'kept' keys."""
        result = evaluate()
        for item in result["features"]:
            assert "name" in item, f"Feature item missing 'name': {item}"
            assert "spread" in item, f"Feature item missing 'spread': {item}"
            assert "mwu_p" in item, f"Feature item missing 'mwu_p': {item}"
            assert "kept" in item, f"Feature item missing 'kept': {item}"
            # Type checks
            assert isinstance(item["name"], str), "'name' must be str"
            assert isinstance(item["spread"], float), "'spread' must be float"
            assert isinstance(item["mwu_p"], float), "'mwu_p' must be float"
            assert isinstance(item["kept"], bool), "'kept' must be bool"

    def test_evaluate_empty_features(self):
        """Phase 5: no features registered, returns empty list; n_touches > 0 (data loads)."""
        result = evaluate()
        # Phase 5 placeholder — no features registered yet (Phase 6 adds feature_engine.py)
        assert result["features"] == [], (
            "Phase 5 placeholder must return empty features list. "
            "Real features are added in Phase 6."
        )
        # Data must load successfully — n_touches > 0
        assert result["n_touches"] > 0, (
            f"n_touches must be > 0 (P1 touch data must load). Got: {result['n_touches']}"
        )

    def test_evaluate_stateless(self):
        """evaluate() is stateless — two consecutive calls return consistent n_touches."""
        result1 = evaluate()
        result2 = evaluate()
        assert result1["n_touches"] == result2["n_touches"], (
            "evaluate() must be stateless — same result on repeated calls. "
            f"Got {result1['n_touches']} vs {result2['n_touches']}"
        )
        assert result1["features"] == result2["features"], (
            "evaluate() must be stateless — same features on repeated calls."
        )
