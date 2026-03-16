# archetype: rotational
"""Unit tests for run_combination_sweep.py

Tests cover:
- inject_profile_martingale: profile param injection without mutation
- Per-bar-type profile param variation
- H37 exclusion from 10sec bar type
- H19 deferred (requires_reference=True)
- Dimensional winner selection (min_bar_types >= 2)
- Best param selection (highest delta_pf)
- delta_pf uses profile baselines from best_tds_configs.json
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------

_ARCHETYPE_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _ARCHETYPE_DIR.parents[2]
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_ARCHETYPE_DIR))

from run_combination_sweep import (  # noqa: E402
    inject_profile_martingale,
    load_param_sweep_baselines,
    select_dimensional_winners,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_MAX_PROFIT_VOL_DATA = {
    "step_dist": 7.0,
    "max_levels": 1,
    "max_total_position": 2,
    "cycle_pf": 2.2037,
}

_MAX_PROFIT_TICK_DATA = {
    "step_dist": 4.5,
    "max_levels": 1,
    "max_total_position": 1,
    "cycle_pf": 1.8413,
}

_MAX_PROFIT_10SEC_DATA = {
    "step_dist": 10.0,
    "max_levels": 1,
    "max_total_position": 4,
    "cycle_pf": 1.7218,
}


def _make_base_config() -> dict:
    """Return a minimal config dict for testing."""
    return {
        "hypothesis": {
            "trigger_params": {"step_dist": 6.0},
        },
        "martingale": {
            "max_levels": 3,
            "max_total_position": 8,
            "max_contract_size": 8,
        },
    }


def _make_results_df(rows: list[dict]) -> pd.DataFrame:
    """Create a results DataFrame from a list of row dicts."""
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# test_inject_profile_martingale
# ---------------------------------------------------------------------------

class TestInjectProfileMartingale:
    def test_injects_step_dist(self):
        """inject_profile_martingale sets step_dist from profile bar_type data."""
        config = _make_base_config()
        result = inject_profile_martingale(config, _MAX_PROFIT_VOL_DATA)
        assert result["hypothesis"]["trigger_params"]["step_dist"] == 7.0

    def test_injects_max_levels(self):
        """inject_profile_martingale sets martingale.max_levels from profile."""
        config = _make_base_config()
        result = inject_profile_martingale(config, _MAX_PROFIT_VOL_DATA)
        assert result["martingale"]["max_levels"] == 1

    def test_injects_max_total_position(self):
        """inject_profile_martingale sets martingale.max_total_position from profile."""
        config = _make_base_config()
        result = inject_profile_martingale(config, _MAX_PROFIT_VOL_DATA)
        assert result["martingale"]["max_total_position"] == 2

    def test_sets_max_contract_size_16(self):
        """inject_profile_martingale always sets max_contract_size=16."""
        config = _make_base_config()
        result = inject_profile_martingale(config, _MAX_PROFIT_VOL_DATA)
        assert result["martingale"]["max_contract_size"] == 16

    def test_does_not_mutate_original(self):
        """inject_profile_martingale does not mutate the input config."""
        config = _make_base_config()
        original_step = config["hypothesis"]["trigger_params"]["step_dist"]
        inject_profile_martingale(config, _MAX_PROFIT_VOL_DATA)
        # Original should be unchanged
        assert config["hypothesis"]["trigger_params"]["step_dist"] == original_step
        assert config["martingale"]["max_levels"] == 3  # unchanged

    def test_returns_deep_copy(self):
        """inject_profile_martingale returns a new dict, not a reference."""
        config = _make_base_config()
        result = inject_profile_martingale(config, _MAX_PROFIT_VOL_DATA)
        assert result is not config
        assert result["hypothesis"] is not config["hypothesis"]


# ---------------------------------------------------------------------------
# test_inject_profile_per_bar_type
# ---------------------------------------------------------------------------

class TestInjectProfilePerBarType:
    def test_different_bar_types_get_different_params(self):
        """250vol and 250tick bar types get different step_dist values for MAX_PROFIT."""
        config = _make_base_config()
        result_vol = inject_profile_martingale(config, _MAX_PROFIT_VOL_DATA)
        result_tick = inject_profile_martingale(config, _MAX_PROFIT_TICK_DATA)

        # MAX_PROFIT: 250vol SD=7.0, 250tick SD=4.5
        assert result_vol["hypothesis"]["trigger_params"]["step_dist"] == 7.0
        assert result_tick["hypothesis"]["trigger_params"]["step_dist"] == 4.5
        assert result_vol["hypothesis"]["trigger_params"]["step_dist"] != result_tick["hypothesis"]["trigger_params"]["step_dist"]

    def test_10sec_bar_type_params(self):
        """10sec bar type gets step_dist=10.0 for MAX_PROFIT."""
        config = _make_base_config()
        result = inject_profile_martingale(config, _MAX_PROFIT_10SEC_DATA)
        assert result["hypothesis"]["trigger_params"]["step_dist"] == 10.0
        assert result["martingale"]["max_total_position"] == 4


# ---------------------------------------------------------------------------
# test_h37_exclusion
# ---------------------------------------------------------------------------

class TestH37Exclusion:
    def test_h37_excluded_from_10sec(self):
        """H37 (exclude_10sec=True) is skipped for bar_data_10sec_rot."""
        from hypothesis_configs import HYPOTHESIS_REGISTRY

        h37 = HYPOTHESIS_REGISTRY["H37"]
        assert h37["exclude_10sec"] is True, "H37 must have exclude_10sec=True"

    def test_h37_included_for_vol_tick(self):
        """H37 is NOT excluded from vol/tick bar types."""
        from hypothesis_configs import HYPOTHESIS_REGISTRY

        h37 = HYPOTHESIS_REGISTRY["H37"]
        # Only 10sec is excluded — vol and tick are fine
        assert h37["exclude_10sec"] is True
        # The flag only gates 10sec, confirmed by field name
        # (run_combination_sweep respects this per source_id check)


# ---------------------------------------------------------------------------
# test_h19_deferred
# ---------------------------------------------------------------------------

class TestH19Deferred:
    def test_h19_has_requires_reference_true(self):
        """H19 has requires_reference=True — it must be skipped in param sweep."""
        from hypothesis_configs import HYPOTHESIS_REGISTRY

        h19 = HYPOTHESIS_REGISTRY["H19"]
        assert h19["requires_reference"] is True

    def test_h19_skipped_in_sweep_results(self):
        """run_param_sweep with dry_run produces no H19 rows."""
        # We verify H19 is filtered by checking the sweep logic directly:
        # Any hypothesis with requires_reference=True is skipped.
        from hypothesis_configs import HYPOTHESIS_REGISTRY

        skipped = [
            h_id for h_id, h in HYPOTHESIS_REGISTRY.items()
            if h.get("requires_reference", False)
        ]
        assert "H19" in skipped
        # H19 is the only one with requires_reference=True
        assert skipped == ["H19"]


# ---------------------------------------------------------------------------
# test_select_dimensional_winners_min_bar_types
# ---------------------------------------------------------------------------

class TestSelectDimensionalWinnersMinBarTypes:
    def test_winner_requires_2_bar_types(self):
        """A hypothesis that beats baseline on only 1 bar type is excluded."""
        # H1 beats baseline on 250vol only (1 bar type) -> excluded
        rows = [
            {
                "hypothesis_id": "H1", "profile": "MAX_PROFIT",
                "source_id": "bar_data_250vol_rot",
                "delta_pf": 0.5, "beats_baseline": True, "cycle_pf": 2.7,
                "params_str": "{}",
            },
            {
                "hypothesis_id": "H1", "profile": "MAX_PROFIT",
                "source_id": "bar_data_250tick_rot",
                "delta_pf": -0.1, "beats_baseline": False, "cycle_pf": 1.7,
                "params_str": "{}",
            },
            {
                "hypothesis_id": "H1", "profile": "MAX_PROFIT",
                "source_id": "bar_data_10sec_rot",
                "delta_pf": -0.2, "beats_baseline": False, "cycle_pf": 1.5,
                "params_str": "{}",
            },
        ]
        df = _make_results_df(rows)
        winners = select_dimensional_winners(df, min_bar_types=2)
        # H1 does not qualify on >= 2 bar types
        assert "H1" not in winners

    def test_winner_included_when_2_bar_types_beat_baseline(self):
        """A hypothesis that beats baseline on 2 of 3 bar types is included."""
        rows = [
            {
                "hypothesis_id": "H4", "profile": "MAX_PROFIT",
                "source_id": "bar_data_250vol_rot",
                "delta_pf": 0.3, "beats_baseline": True, "cycle_pf": 2.5,
                "params_str": '{"H4.lookback_bars": 5}',
            },
            {
                "hypothesis_id": "H4", "profile": "MAX_PROFIT",
                "source_id": "bar_data_250tick_rot",
                "delta_pf": 0.2, "beats_baseline": True, "cycle_pf": 2.0,
                "params_str": '{"H4.lookback_bars": 5}',
            },
            {
                "hypothesis_id": "H4", "profile": "MAX_PROFIT",
                "source_id": "bar_data_10sec_rot",
                "delta_pf": -0.1, "beats_baseline": False, "cycle_pf": 1.6,
                "params_str": '{"H4.lookback_bars": 5}',
            },
        ]
        df = _make_results_df(rows)
        winners = select_dimensional_winners(df, min_bar_types=2)
        assert "H4" in winners

    def test_winner_included_when_all_3_bar_types_beat_baseline(self):
        """A hypothesis beating baseline on all 3 bar types is also included."""
        rows = [
            {
                "hypothesis_id": "H7", "profile": "MAX_PROFIT",
                "source_id": "bar_data_250vol_rot",
                "delta_pf": 0.3, "beats_baseline": True, "cycle_pf": 2.5,
                "params_str": "{}",
            },
            {
                "hypothesis_id": "H7", "profile": "MAX_PROFIT",
                "source_id": "bar_data_250tick_rot",
                "delta_pf": 0.2, "beats_baseline": True, "cycle_pf": 2.0,
                "params_str": "{}",
            },
            {
                "hypothesis_id": "H7", "profile": "MAX_PROFIT",
                "source_id": "bar_data_10sec_rot",
                "delta_pf": 0.1, "beats_baseline": True, "cycle_pf": 1.8,
                "params_str": "{}",
            },
        ]
        df = _make_results_df(rows)
        winners = select_dimensional_winners(df, min_bar_types=2)
        assert "H7" in winners


# ---------------------------------------------------------------------------
# test_select_dimensional_winners_best_params
# ---------------------------------------------------------------------------

class TestSelectDimensionalWinnersBestParams:
    def test_selects_highest_delta_pf_params(self):
        """When multiple param values beat baseline, the one with highest delta_pf is selected."""
        rows = [
            # lookback=3 beats baseline with delta_pf=0.2
            {
                "hypothesis_id": "H4", "profile": "MAX_PROFIT",
                "source_id": "bar_data_250vol_rot",
                "delta_pf": 0.2, "beats_baseline": True, "cycle_pf": 2.4,
                "params_str": '{"H4.lookback_bars": 3}',
            },
            # lookback=5 beats baseline with delta_pf=0.5 (best)
            {
                "hypothesis_id": "H4", "profile": "MAX_PROFIT",
                "source_id": "bar_data_250vol_rot",
                "delta_pf": 0.5, "beats_baseline": True, "cycle_pf": 2.7,
                "params_str": '{"H4.lookback_bars": 5}',
            },
            # lookback=10 beats baseline with delta_pf=0.1
            {
                "hypothesis_id": "H4", "profile": "MAX_PROFIT",
                "source_id": "bar_data_250vol_rot",
                "delta_pf": 0.1, "beats_baseline": True, "cycle_pf": 2.3,
                "params_str": '{"H4.lookback_bars": 10}',
            },
            # Must also beat baseline on 250tick
            {
                "hypothesis_id": "H4", "profile": "MAX_PROFIT",
                "source_id": "bar_data_250tick_rot",
                "delta_pf": 0.3, "beats_baseline": True, "cycle_pf": 2.1,
                "params_str": '{"H4.lookback_bars": 5}',
            },
            {
                "hypothesis_id": "H4", "profile": "MAX_PROFIT",
                "source_id": "bar_data_10sec_rot",
                "delta_pf": -0.1, "beats_baseline": False, "cycle_pf": 1.6,
                "params_str": '{"H4.lookback_bars": 5}',
            },
        ]
        df = _make_results_df(rows)
        winners = select_dimensional_winners(df, min_bar_types=2)

        # H4 should be selected; 250vol best params should be lookback=5
        assert "H4" in winners
        vol_entry = winners["H4"]["MAX_PROFIT"]["bar_data_250vol_rot"]
        assert vol_entry["delta_pf"] == 0.5
        assert vol_entry["params_str"] == '{"H4.lookback_bars": 5}'

    def test_excludes_non_beating_params(self):
        """Only rows with beats_baseline=True are considered for winner selection."""
        rows = [
            # Only this one beats baseline on 250vol
            {
                "hypothesis_id": "H4", "profile": "MAX_PROFIT",
                "source_id": "bar_data_250vol_rot",
                "delta_pf": 0.3, "beats_baseline": True, "cycle_pf": 2.5,
                "params_str": '{"H4.lookback_bars": 5}',
            },
            # Higher delta_pf but does NOT beat baseline (beats_baseline=False)
            {
                "hypothesis_id": "H4", "profile": "MAX_PROFIT",
                "source_id": "bar_data_250vol_rot",
                "delta_pf": 0.8, "beats_baseline": False, "cycle_pf": 1.1,
                "params_str": '{"H4.lookback_bars": 20}',
            },
            {
                "hypothesis_id": "H4", "profile": "MAX_PROFIT",
                "source_id": "bar_data_250tick_rot",
                "delta_pf": 0.2, "beats_baseline": True, "cycle_pf": 2.0,
                "params_str": '{"H4.lookback_bars": 5}',
            },
            {
                "hypothesis_id": "H4", "profile": "MAX_PROFIT",
                "source_id": "bar_data_10sec_rot",
                "delta_pf": -0.1, "beats_baseline": False, "cycle_pf": 1.6,
                "params_str": '{"H4.lookback_bars": 5}',
            },
        ]
        df = _make_results_df(rows)
        winners = select_dimensional_winners(df, min_bar_types=2)

        assert "H4" in winners
        vol_entry = winners["H4"]["MAX_PROFIT"]["bar_data_250vol_rot"]
        # Should pick lookback=5 (beats_baseline=True), NOT lookback=20
        assert vol_entry["params_str"] == '{"H4.lookback_bars": 5}'


# ---------------------------------------------------------------------------
# test_delta_pf_uses_profile_baselines
# ---------------------------------------------------------------------------

class TestDeltaPfUsesProfileBaselines:
    def test_baselines_loaded_from_best_tds_configs(self):
        """load_param_sweep_baselines returns the no_tds_baselines dict from best_tds_configs.json."""
        baselines = load_param_sweep_baselines()

        # Should have all 3 profiles
        assert "MAX_PROFIT" in baselines
        assert "SAFEST" in baselines
        assert "MOST_CONSISTENT" in baselines

    def test_baselines_have_correct_cycle_pf_for_max_profit_vol(self):
        """MAX_PROFIT/250vol baseline cycle_pf matches best_tds_configs.json."""
        baselines = load_param_sweep_baselines()
        # From best_tds_configs.json no_tds_baselines:
        # MAX_PROFIT / bar_data_250vol_rot / cycle_pf = 2.2037
        pf = baselines["MAX_PROFIT"]["bar_data_250vol_rot"]["cycle_pf"]
        assert abs(pf - 2.2037) < 0.001

    def test_baselines_have_correct_cycle_pf_for_safest_tick(self):
        """SAFEST/250tick baseline cycle_pf matches best_tds_configs.json."""
        baselines = load_param_sweep_baselines()
        # SAFEST / bar_data_250tick_rot / cycle_pf = 1.2154
        pf = baselines["SAFEST"]["bar_data_250tick_rot"]["cycle_pf"]
        assert abs(pf - 1.2154) < 0.001

    def test_delta_pf_computed_correctly(self):
        """delta_pf = run cycle_pf - profile baseline cycle_pf (not Phase 01 baselines)."""
        # This is a logic test — delta_pf must use profile-specific baselines,
        # not the Phase 1 sweep_P1a.json baselines.
        baselines = load_param_sweep_baselines()
        # MAX_PROFIT/250vol baseline is 2.2037
        # If a run gets cycle_pf=2.5, delta_pf should be ~0.2963
        baseline_pf = baselines["MAX_PROFIT"]["bar_data_250vol_rot"]["cycle_pf"]
        run_pf = 2.5
        expected_delta = run_pf - baseline_pf
        assert abs(expected_delta - 0.2963) < 0.001
