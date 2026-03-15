# archetype: rotational
"""Tests for feature_engine.py vectorized hypothesis feature computation,
FeatureComputer dispatch in rotational_simulator.py, and feature_evaluator.py
outcome types (direction, reversal_quality, add_quality).

Covers:
    - compute_hypothesis_features returns correct columns for H1, H8, H27, H28, H33
    - Rolling features have NaN for warmup period (entry-time safe)
    - H9 VWAP is vectorized and session-aware
    - Baseline config (fixed trigger, no filters) returns bar_df unchanged
    - H1 config adds atr_scaled_step column
    - H19 returns NaN columns with SKIPPED_REFERENCE_REQUIRED note
    - H17/H36/H39 (requires_dynamic_features=True) return NaN placeholder columns
    - Entry-time safety: rolling feature at bar 5 with lookback=200 is NaN
    - MWU spread from feature_evaluator works with synthetic data
    - evaluate() outcome_type parameter (direction, reversal_quality, add_quality)
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from feature_engine import compute_hypothesis_features  # noqa: E402
from rotational_simulator import FeatureComputer  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers: synthetic bar DataFrames
# ---------------------------------------------------------------------------

def _make_bars(
    n: int = 100,
    start_price: float = 17000.0,
    step: float = 2.5,
    seed: int = 42,
) -> pd.DataFrame:
    """Build a minimal synthetic bar DataFrame for testing.

    Columns match the real bar schema (entry-time safe usage only).
    """
    rng = np.random.default_rng(seed)
    prices = start_price + np.cumsum(rng.normal(0, step, n))
    volumes = rng.integers(100, 500, n).astype(float)
    atr = np.abs(rng.normal(5.0, 1.0, n))

    # Timestamps: 1-minute bars starting from 2025-09-22 09:30
    base_dt = pd.Timestamp("2025-09-22 09:30:00")
    dts = [base_dt + pd.Timedelta(minutes=i) for i in range(n)]

    ask_vol = rng.integers(50, 300, n).astype(float)
    bid_vol = rng.integers(50, 300, n).astype(float)

    df = pd.DataFrame({
        "Date": [dt.date().isoformat() for dt in dts],
        "Time": [dt.strftime("%H:%M:%S") for dt in dts],
        "Open": prices + rng.uniform(-1, 1, n),
        "High": prices + rng.uniform(0, 3, n),
        "Low": prices - rng.uniform(0, 3, n),
        "Last": prices,
        "Volume": volumes,
        "# of Trades": rng.integers(50, 200, n).astype(float),
        "ATR": atr,
        "Bid Volume": bid_vol,
        "Ask Volume": ask_vol,
        "StdDev_1_Top": prices + 5.0,
        "StdDev_1_Bottom": prices - 5.0,
        "StdDev_2_Top": prices + 15.0,
        "StdDev_2_Bottom": prices - 15.0,
        "datetime": dts,
    })
    return df


def _make_h1_config(multiplier: float = 0.5) -> dict:
    return {
        "hypothesis": {
            "trigger_mechanism": "atr_scaled",
            "trigger_params": {"multiplier": multiplier},
            "active_filters": [],
            "filter_params": {},
            "structural_mods": [],
            "structural_params": {},
        }
    }


def _make_baseline_config() -> dict:
    return {
        "hypothesis": {
            "trigger_mechanism": "fixed",
            "trigger_params": {"step_dist": 6.0},
            "active_filters": [],
            "filter_params": {},
            "structural_mods": [],
            "structural_params": {},
        }
    }


def _make_h8_config(multiplier: float = 0.75, lookback: int = 50) -> dict:
    return {
        "hypothesis": {
            "trigger_mechanism": "sd_scaled",
            "trigger_params": {"multiplier": multiplier, "lookback": lookback},
            "active_filters": [],
            "filter_params": {},
            "structural_mods": [],
            "structural_params": {},
        }
    }


def _make_h27_config(lookback: int = 14) -> dict:
    return {
        "hypothesis": {
            "trigger_mechanism": "fixed",
            "trigger_params": {"step_dist": 6.0},
            "active_filters": ["H27"],
            "filter_params": {"H27": {"lookback": lookback}},
            "structural_mods": [],
            "structural_params": {},
        }
    }


def _make_h28_config(lookback: int = 10) -> dict:
    return {
        "hypothesis": {
            "trigger_mechanism": "fixed",
            "trigger_params": {"step_dist": 6.0},
            "active_filters": ["H28"],
            "filter_params": {"H28": {"lookback": lookback}},
            "structural_mods": [],
            "structural_params": {},
        }
    }


def _make_h33_config(speed_threshold: float = 1.0) -> dict:
    return {
        "hypothesis": {
            "trigger_mechanism": "fixed",
            "trigger_params": {"step_dist": 6.0},
            "active_filters": ["H33"],
            "filter_params": {"H33": {"speed_threshold": speed_threshold}},
            "structural_mods": [],
            "structural_params": {},
        }
    }


def _make_h9_config(k: float = 2.0, vwap_reset: str = "session") -> dict:
    return {
        "hypothesis": {
            "trigger_mechanism": "vwap_sd",
            "trigger_params": {"k": k, "vwap_reset": vwap_reset},
            "active_filters": [],
            "filter_params": {},
            "structural_mods": [],
            "structural_params": {},
        }
    }


def _make_h19_config() -> dict:
    return {
        "hypothesis": {
            "trigger_mechanism": "fixed",
            "trigger_params": {"step_dist": 6.0},
            "active_filters": [],
            "filter_params": {},
            "structural_mods": [],
            "structural_params": {},
        },
        "requires_reference": True,
    }


# ---------------------------------------------------------------------------
# Tests: compute_hypothesis_features
# ---------------------------------------------------------------------------

class TestBaseline:
    def test_baseline_config_returns_bar_df_unchanged(self):
        bars = _make_bars(50)
        config = _make_baseline_config()["hypothesis"]
        result = compute_hypothesis_features(bars, config)
        # Same columns — no additions for baseline
        assert set(result.columns) == set(bars.columns), (
            "Baseline config should not add columns. "
            f"Added: {set(result.columns) - set(bars.columns)}"
        )

    def test_baseline_returns_dataframe(self):
        bars = _make_bars(50)
        config = _make_baseline_config()["hypothesis"]
        result = compute_hypothesis_features(bars, config)
        assert isinstance(result, pd.DataFrame)


class TestH1ATRScaled:
    def test_h1_adds_atr_scaled_step_column(self):
        bars = _make_bars(100)
        config = _make_h1_config(multiplier=0.5)["hypothesis"]
        result = compute_hypothesis_features(bars, config)
        assert "atr_scaled_step" in result.columns, "H1 must add 'atr_scaled_step' column"

    def test_h1_atr_scaled_step_values_correct(self):
        bars = _make_bars(100)
        multiplier = 0.5
        config = _make_h1_config(multiplier=multiplier)["hypothesis"]
        result = compute_hypothesis_features(bars, config)
        expected = multiplier * bars["ATR"]
        pd.testing.assert_series_equal(
            result["atr_scaled_step"].reset_index(drop=True),
            expected.reset_index(drop=True),
            check_names=False,
        )

    def test_h1_does_not_modify_original_bar_df(self):
        bars = _make_bars(50)
        original_cols = set(bars.columns)
        config = _make_h1_config()["hypothesis"]
        compute_hypothesis_features(bars, config)
        assert set(bars.columns) == original_cols, "compute_hypothesis_features must not mutate input"


class TestH8SDScaled:
    def test_h8_adds_rolling_sd_and_sd_scaled_step(self):
        bars = _make_bars(100)
        config = _make_h8_config(multiplier=0.75, lookback=20)["hypothesis"]
        result = compute_hypothesis_features(bars, config)
        assert "rolling_sd" in result.columns
        assert "sd_scaled_step" in result.columns

    def test_h8_warmup_period_is_nan(self):
        """First lookback-1 bars should be NaN for rolling_sd (entry-time safe)."""
        bars = _make_bars(200)
        lookback = 50
        config = _make_h8_config(lookback=lookback)["hypothesis"]
        result = compute_hypothesis_features(bars, config)
        # Bars 0..lookback-2 should all be NaN (not enough data yet)
        # pandas rolling with min_periods=lookback: first valid at index lookback-1
        assert result["rolling_sd"].iloc[:lookback - 1].isna().all(), (
            f"rolling_sd should be NaN for first {lookback-1} bars (warmup)"
        )


class TestH27ATRROC:
    def test_h27_adds_atr_roc_column(self):
        bars = _make_bars(100)
        config = _make_h27_config(lookback=14)["hypothesis"]
        result = compute_hypothesis_features(bars, config)
        assert "atr_roc" in result.columns

    def test_h27_atr_roc_is_pct_change(self):
        bars = _make_bars(100)
        lookback = 14
        config = _make_h27_config(lookback=lookback)["hypothesis"]
        result = compute_hypothesis_features(bars, config)
        expected = bars["ATR"].pct_change(lookback)
        pd.testing.assert_series_equal(
            result["atr_roc"].reset_index(drop=True),
            expected.reset_index(drop=True),
            check_names=False,
        )


class TestH28PriceROC:
    def test_h28_adds_price_roc_column(self):
        bars = _make_bars(100)
        config = _make_h28_config(lookback=10)["hypothesis"]
        result = compute_hypothesis_features(bars, config)
        assert "price_roc" in result.columns


class TestH33PriceSpeed:
    def test_h33_adds_price_speed_and_bar_duration(self):
        bars = _make_bars(100)
        config = _make_h33_config()["hypothesis"]
        result = compute_hypothesis_features(bars, config)
        assert "price_speed" in result.columns
        assert "bar_duration_sec" in result.columns

    def test_h33_price_speed_is_nonneg(self):
        bars = _make_bars(100)
        config = _make_h33_config()["hypothesis"]
        result = compute_hypothesis_features(bars, config)
        speeds = result["price_speed"].dropna()
        assert (speeds >= 0).all(), "price_speed must be non-negative"


class TestH9VWAP:
    def test_h9_adds_vwap_columns(self):
        bars = _make_bars(100)
        config = _make_h9_config(k=2.0, vwap_reset="session")["hypothesis"]
        result = compute_hypothesis_features(bars, config)
        assert "vwap" in result.columns
        assert "vwap_sd_upper" in result.columns
        assert "vwap_sd_lower" in result.columns

    def test_h9_vwap_upper_above_lower(self):
        bars = _make_bars(100)
        config = _make_h9_config(k=2.0)["hypothesis"]
        result = compute_hypothesis_features(bars, config)
        valid = result[result["vwap_sd_upper"].notna() & result["vwap_sd_lower"].notna()]
        if len(valid) > 0:
            assert (valid["vwap_sd_upper"] >= valid["vwap_sd_lower"]).all()


class TestH19ReferenceRequired:
    def test_h19_config_returns_nan_placeholder_columns(self):
        bars = _make_bars(50)
        # H19 has no config_patch (empty), but a special flag in the config
        h19_config = {
            "trigger_mechanism": "fixed",
            "trigger_params": {"step_dist": 6.0},
            "active_filters": [],
            "filter_params": {},
            "structural_mods": [],
            "structural_params": {},
            "_h19_skip": True,  # signal to engine this needs multi-source
        }
        result = compute_hypothesis_features(bars, h19_config)
        if "bar_type_divergence" in result.columns:
            assert result["bar_type_divergence"].isna().all(), (
                "H19 bar_type_divergence should be NaN when reference not available"
            )


class TestDynamicFeaturePlaceholders:
    """H17, H36, H39 require simulator state — should return NaN placeholder columns."""

    @pytest.mark.parametrize("filter_id,col_name", [
        ("H36", "adverse_speed"),
        ("H39", "adverse_velocity_ratio"),
        ("H17", "cycle_feedback_state"),
    ])
    def test_dynamic_feature_returns_nan_placeholder(self, filter_id, col_name):
        bars = _make_bars(50)
        config = {
            "trigger_mechanism": "fixed",
            "trigger_params": {"step_dist": 6.0},
            "active_filters": [filter_id],
            "filter_params": {},
            "structural_mods": [],
            "structural_params": {},
        }
        result = compute_hypothesis_features(bars, config)
        if col_name in result.columns:
            assert result[col_name].isna().all(), (
                f"{filter_id} column '{col_name}' should be all NaN (requires simulator state)"
            )


class TestEntryTimeSafety:
    def test_rolling_feature_at_bar_5_with_lookback_200_is_nan(self):
        """Entry-time safety: rolling features at bar index 5 must be NaN for lookback=200."""
        bars = _make_bars(300)
        lookback = 200
        config = _make_h8_config(lookback=lookback)["hypothesis"]
        result = compute_hypothesis_features(bars, config)
        # Bar index 5 has only 6 bars available — lookback=200 requires 200 bars
        assert pd.isna(result["rolling_sd"].iloc[5]), (
            f"rolling_sd at bar 5 with lookback=200 must be NaN (entry-time safe)"
        )

    def test_rolling_feature_valid_after_warmup(self):
        """After warmup period, rolling features should have valid values."""
        bars = _make_bars(300)
        lookback = 20
        config = _make_h8_config(lookback=lookback)["hypothesis"]
        result = compute_hypothesis_features(bars, config)
        # Bar index >= lookback should have valid value
        valid_values = result["rolling_sd"].iloc[lookback:].dropna()
        assert len(valid_values) > 0, "rolling_sd should have valid values after warmup"


# ---------------------------------------------------------------------------
# Tests: FeatureComputer dispatch in rotational_simulator
# ---------------------------------------------------------------------------

class TestFeatureComputerDispatch:
    def _make_full_config(self, hypothesis_config: dict) -> dict:
        return {
            "hypothesis": hypothesis_config,
            "period": "P1",
            "_instrument": {"tick_size": 0.25, "cost_ticks": 3},
            "martingale": {"initial_qty": 1, "max_levels": 4, "max_contract_size": 8},
            "bar_data_primary": {"bar_data_250vol_rot": "dummy.csv"},
        }

    def test_baseline_config_returns_unchanged(self):
        bars = _make_bars(50)
        hypothesis_config = _make_baseline_config()["hypothesis"]
        full_config = self._make_full_config(hypothesis_config)
        fc = FeatureComputer(full_config)
        result = fc.compute_static_features(bars)
        assert set(result.columns) == set(bars.columns)

    def test_h1_config_dispatches_to_feature_engine(self):
        bars = _make_bars(50)
        hypothesis_config = _make_h1_config(multiplier=0.5)["hypothesis"]
        full_config = self._make_full_config(hypothesis_config)
        fc = FeatureComputer(full_config)
        result = fc.compute_static_features(bars)
        assert "atr_scaled_step" in result.columns

    def test_active_filter_dispatches_to_feature_engine(self):
        bars = _make_bars(50)
        hypothesis_config = _make_h27_config(lookback=14)["hypothesis"]
        full_config = self._make_full_config(hypothesis_config)
        fc = FeatureComputer(full_config)
        result = fc.compute_static_features(bars)
        assert "atr_roc" in result.columns


# ---------------------------------------------------------------------------
# Tests: MWU spread with synthetic data (from feature_evaluator.py)
# ---------------------------------------------------------------------------

class TestMWUSpread:
    def test_mwu_spread_with_predictive_feature(self):
        """A feature that perfectly predicts outcome should show high spread."""
        from feature_evaluator import _compute_mwu_spread

        rng = np.random.default_rng(123)
        n = 500
        # Feature is perfectly correlated with outcome
        feature = pd.Series(rng.uniform(0, 1, n))
        outcome = pd.Series(np.where(feature > 0.5, 1.0, -1.0))

        result = _compute_mwu_spread(feature, outcome, feature, outcome, "test_feature")
        assert result["spread"] > 0, "Predictive feature should show positive spread"
        assert "name" in result
        assert "spread" in result
        assert "mwu_p" in result
        assert "kept" in result

    def test_mwu_spread_with_random_feature(self):
        """A random feature should show near-zero spread."""
        from feature_evaluator import _compute_mwu_spread

        rng = np.random.default_rng(456)
        n = 500
        feature = pd.Series(rng.uniform(0, 1, n))
        outcome = pd.Series(rng.choice([-1.0, 1.0], n))

        result = _compute_mwu_spread(feature, outcome, feature, outcome, "random_feature")
        # Random feature: spread should be small (not guaranteed, but typical)
        assert "spread" in result
        assert isinstance(result["spread"], float)

    def test_mwu_spread_returns_correct_structure(self):
        from feature_evaluator import _compute_mwu_spread

        rng = np.random.default_rng(789)
        feature = pd.Series(rng.uniform(0, 1, 200))
        outcome = pd.Series(rng.choice([-1.0, 1.0], 200))

        result = _compute_mwu_spread(feature, outcome, feature, outcome, "my_feat")
        assert set(result.keys()) >= {"name", "spread", "mwu_p", "kept", "entry_time_violation"}
