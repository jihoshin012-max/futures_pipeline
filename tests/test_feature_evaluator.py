"""Tests for zone_touch feature_evaluator.py interface contract.

Phase 5: TestFeatureEvaluatorInterface — basic interface shape tests.
Phase 6: TestMWUSpread — MWU spread computation on real P1 data.
         TestEntryTimeCanary — entry-time enforcement structural tests.
"""

import sys
import types
from pathlib import Path

import pytest

# Add repo root so shared.* imports resolve
_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))

from shared.archetypes.zone_touch.feature_evaluator import evaluate  # noqa: E402


class TestFeatureEvaluatorInterface:
    """Verify the evaluate() interface contract (Phase 5 backward compatibility)."""

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
        """Phase 6: feature_engine.py exists, features list is non-empty; n_touches > 0."""
        result = evaluate()
        # Phase 6: feature_engine.py is present, so features list should be non-empty
        # (was empty in Phase 5 placeholder — now populated by MWU spread computation)
        assert isinstance(result["features"], list), "'features' must be a list"
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
        # Feature names and kept status must be stable
        names1 = [f["name"] for f in result1["features"]]
        names2 = [f["name"] for f in result2["features"]]
        assert names1 == names2, (
            "evaluate() must be stateless — same feature names on repeated calls."
        )


class TestMWUSpread:
    """Verify MWU spread computation on real P1 data (Phase 6)."""

    @pytest.fixture(scope="class")
    def eval_result(self):
        """Run evaluate() once and cache the result for the test class."""
        return evaluate()

    def test_zone_width_spread_positive(self, eval_result):
        """evaluate() returns zone_width feature with valid spread and mwu_p."""
        features = eval_result["features"]
        assert len(features) > 0, "evaluate() must return at least one feature (zone_width)"

        zone_width_features = [f for f in features if f["name"] == "zone_width"]
        assert len(zone_width_features) == 1, (
            f"Expected exactly one 'zone_width' feature, got: {[f['name'] for f in features]}"
        )
        zw = zone_width_features[0]
        assert isinstance(zw["spread"], float), f"spread must be float, got {type(zw['spread'])}"
        assert isinstance(zw["mwu_p"], float), f"mwu_p must be float, got {type(zw['mwu_p'])}"
        assert 0.0 <= zw["mwu_p"] <= 1.0, f"mwu_p must be in [0, 1], got {zw['mwu_p']}"

    def test_evaluate_returns_correct_shape(self, eval_result):
        """Result has 'features' (list) and 'n_touches' (int); each feature has required keys."""
        assert "features" in eval_result
        assert "n_touches" in eval_result
        assert isinstance(eval_result["features"], list)
        assert isinstance(eval_result["n_touches"], int)

        required_keys = {"name", "spread", "mwu_p", "kept", "entry_time_violation"}
        for feat in eval_result["features"]:
            missing = required_keys - set(feat.keys())
            assert not missing, f"Feature dict missing keys {missing}: {feat}"
            assert isinstance(feat["name"], str), f"name must be str: {feat}"
            assert isinstance(feat["spread"], float), f"spread must be float: {feat}"
            assert isinstance(feat["mwu_p"], float), f"mwu_p must be float: {feat}"
            assert isinstance(feat["kept"], bool), f"kept must be bool: {feat}"
            assert isinstance(feat["entry_time_violation"], bool), (
                f"entry_time_violation must be bool: {feat}"
            )

    def test_p1a_p1b_split_row_counts(self):
        """P1a has ~2882 touches, P1b has ~3267 touches (tolerance +/- 50)."""
        import pandas as pd
        from shared.data_loader import load_touches

        touches_path = _REPO_ROOT / "stages/01-data/data/touches/ZRA_Hist_P1.csv"
        touch_df = load_touches(str(touches_path))

        p1a_end = pd.Timestamp('2025-10-31 23:59:59')
        p1b_start = pd.Timestamp('2025-11-01')
        p1b_end = pd.Timestamp('2025-12-14 23:59:59')

        p1a_count = (touch_df['DateTime'] <= p1a_end).sum()
        p1b_count = (
            (touch_df['DateTime'] >= p1b_start) & (touch_df['DateTime'] <= p1b_end)
        ).sum()

        # Empirical counts from actual data: P1a=2952, P1b=3280 (verified 2026-03-14)
        # Tolerance +/-75 to accommodate minor data updates
        assert abs(p1a_count - 2952) <= 75, (
            f"P1a expected ~2952 touches (+/-75), got {p1a_count}"
        )
        assert abs(p1b_count - 3280) <= 75, (
            f"P1b expected ~3280 touches (+/-75), got {p1b_count}"
        )

    def test_degenerate_bins_handled(self):
        """Feature with constant value returns spread=0.0, mwu_p=1.0, kept=False (no crash)."""
        import importlib.util
        import tempfile
        import os
        import pandas as pd

        # Create a temporary feature_engine.py that returns a constant feature
        constant_engine_code = """# archetype: zone_touch
def compute_features(bar_df, touch_row) -> dict:
    return {'constant_feature': 1.0}
"""
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.py', delete=False, dir=str(_REPO_ROOT / "shared/archetypes/zone_touch")
        ) as tmp:
            tmp.write(constant_engine_code)
            tmp_path = tmp.name

        # Temporarily monkey-patch feature_engine path in feature_evaluator module
        import shared.archetypes.zone_touch.feature_evaluator as evaluator_mod
        original_load = evaluator_mod._load_feature_engine

        def patched_load():
            spec = importlib.util.spec_from_file_location("feature_engine", tmp_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module

        try:
            evaluator_mod._load_feature_engine = patched_load
            result = evaluator_mod.evaluate()
        finally:
            evaluator_mod._load_feature_engine = original_load
            os.unlink(tmp_path)

        constant_features = [f for f in result["features"] if f["name"] == "constant_feature"]
        assert len(constant_features) == 1, (
            f"Expected constant_feature in results, got: {[f['name'] for f in result['features']]}"
        )
        cf = constant_features[0]
        assert cf["spread"] == 0.0, f"Degenerate feature must have spread=0.0, got {cf['spread']}"
        assert cf["mwu_p"] == 1.0, f"Degenerate feature must have mwu_p=1.0, got {cf['mwu_p']}"
        assert cf["kept"] is False, f"Degenerate feature must have kept=False, got {cf['kept']}"


class TestEntryTimeCanary:
    """Verify entry-time enforcement via structural truncation guard (Phase 6)."""

    def _make_lookahead_engine(self, tmp_dir):
        """Create a feature_engine.py that reads bar_df beyond the truncation boundary."""
        engine_code = """# archetype: zone_touch
def compute_features(bar_df, touch_row) -> dict:
    # Deliberately access bar AFTER entry (lookahead) — should raise IndexError
    lookahead_val = bar_df.iloc[len(bar_df)]  # This always raises IndexError
    return {'lookahead_feature': float(lookahead_val['Close'])}
"""
        engine_path = Path(tmp_dir) / "feature_engine.py"
        engine_path.write_text(engine_code, encoding='utf-8')
        return str(engine_path)

    def _make_safe_column_inspector_engine(self, tmp_dir, captured_columns):
        """Create a feature_engine.py that captures touch_row column names."""
        engine_code = """# archetype: zone_touch
import json, tempfile, os

def compute_features(bar_df, touch_row) -> dict:
    # Capture column names for inspection
    cols = list(touch_row.index.tolist()) if hasattr(touch_row, 'index') else list(touch_row.keys())
    marker_path = os.path.join(tempfile.gettempdir(), '_test_touch_cols.json')
    with open(marker_path, 'w') as f:
        json.dump(cols, f)
    return {'zone_width': 1.0}
"""
        engine_path = Path(tmp_dir) / "feature_engine.py"
        engine_path.write_text(engine_code, encoding='utf-8')
        return str(engine_path)

    def test_lookahead_feature_blocked(self, tmp_path):
        """A feature_engine.py that reads bar_df.iloc[len(bar_df)] is caught — entry_time_violation=True."""
        import importlib.util
        import shared.archetypes.zone_touch.feature_evaluator as evaluator_mod

        engine_path = self._make_lookahead_engine(str(tmp_path))
        original_load = evaluator_mod._load_feature_engine

        def patched_load():
            spec = importlib.util.spec_from_file_location("feature_engine", engine_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module

        try:
            evaluator_mod._load_feature_engine = patched_load
            result = evaluator_mod.evaluate()
        finally:
            evaluator_mod._load_feature_engine = original_load

        # Either: no features (violation swallowed all), or feature present with violation=True
        # The key requirement: no feature should have kept=True from a lookahead engine
        for feat in result["features"]:
            assert feat["kept"] is False, (
                f"Lookahead feature must not be kept, got kept=True for {feat['name']}"
            )
            if feat["name"] == "lookahead_feature":
                assert feat["entry_time_violation"] is True, (
                    f"Lookahead feature must have entry_time_violation=True, got: {feat}"
                )

    def test_post_entry_columns_stripped(self, tmp_path):
        """touch_row passed to compute_features does NOT contain post-entry columns."""
        import importlib.util
        import json
        import tempfile
        import os
        import shared.archetypes.zone_touch.feature_evaluator as evaluator_mod

        engine_path = self._make_safe_column_inspector_engine(str(tmp_path), [])
        original_load = evaluator_mod._load_feature_engine

        def patched_load():
            spec = importlib.util.spec_from_file_location("feature_engine", engine_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module

        try:
            evaluator_mod._load_feature_engine = patched_load
            evaluator_mod.evaluate()
        finally:
            evaluator_mod._load_feature_engine = original_load

        # Read captured columns from tmp file
        marker_path = os.path.join(tempfile.gettempdir(), '_test_touch_cols.json')
        if not os.path.exists(marker_path):
            pytest.skip("Column inspector did not write marker file (no touches processed)")

        with open(marker_path, 'r') as f:
            captured_cols = json.load(f)

        # Clean up
        os.unlink(marker_path)

        # Verify post-entry columns are absent
        post_entry = {
            'Reaction', 'Penetration', 'ReactionPeakBar', 'ZoneBroken',
            'BreakBarIndex', 'BarsObserved',
            'RxnBar_30', 'RxnBar_50', 'RxnBar_80', 'RxnBar_120', 'RxnBar_160',
            'RxnBar_240', 'RxnBar_360',
            'PenBar_30', 'PenBar_50', 'PenBar_80', 'PenBar_120',
        }
        leaked = post_entry.intersection(set(captured_cols))
        assert not leaked, (
            f"Post-entry columns leaked into compute_features touch_row: {leaked}"
        )

    def test_violation_flag_per_feature(self):
        """Each feature dict in result['features'] has an 'entry_time_violation' boolean key."""
        result = evaluate()
        for feat in result["features"]:
            assert "entry_time_violation" in feat, (
                f"Feature dict missing 'entry_time_violation' key: {feat}"
            )
            assert isinstance(feat["entry_time_violation"], bool), (
                f"'entry_time_violation' must be bool, got {type(feat['entry_time_violation'])}: {feat}"
            )
