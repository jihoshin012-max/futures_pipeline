# archetype: rotational
"""Unit tests for run_tds_calibration.py — TDD RED phase.

Tests:
    - test_build_isolated_detector_configs
    - test_build_drawdown_sweep_configs
    - test_build_combined_config
    - test_build_run_config
    - test_compute_survival_metrics
    - test_n_td_flatten_cycles
    - test_dry_run_smoke
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Path setup so we can import run_tds_calibration
# ---------------------------------------------------------------------------
_ARCHETYPE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_ARCHETYPE_DIR))

import run_tds_calibration as rc  # noqa: E402


# ---------------------------------------------------------------------------
# test_build_isolated_detector_configs
# ---------------------------------------------------------------------------

class TestBuildIsolatedDetectorConfigs:
    def setup_method(self):
        self.configs = rc.build_isolated_detector_configs()

    def test_returns_exactly_4_configs(self):
        assert len(self.configs) == 4

    def test_config_names_correct(self):
        names = [c["_name"] for c in self.configs]
        assert names == ["retracement", "velocity", "consecutive_adds", "drawdown_budget"]

    def test_retracement_config_disables_velocity(self):
        cfg = self.configs[0]  # retracement
        tds = cfg["trend_defense"]
        # velocity disabled: velocity_threshold_sec very small
        assert tds["level_2"]["velocity_threshold_sec"] == pytest.approx(0.001)

    def test_retracement_config_disables_consecutive_adds(self):
        cfg = self.configs[0]
        tds = cfg["trend_defense"]
        assert tds["level_2"]["consecutive_adds_threshold"] == 999

    def test_retracement_config_disables_drawdown(self):
        cfg = self.configs[0]
        tds = cfg["trend_defense"]
        assert tds["level_3"]["drawdown_budget_ticks"] == 999999

    def test_retracement_config_disables_precursor(self):
        cfg = self.configs[0]
        tds = cfg["trend_defense"]
        assert tds["precursor"]["precursor_min_signals"] == 99

    def test_velocity_config_normal_velocity_threshold(self):
        cfg = self.configs[1]  # velocity
        tds = cfg["trend_defense"]
        # velocity at spec default (60 sec)
        assert tds["level_2"]["velocity_threshold_sec"] == pytest.approx(60.0)

    def test_velocity_config_disables_consecutive_adds(self):
        cfg = self.configs[1]
        tds = cfg["trend_defense"]
        assert tds["level_2"]["consecutive_adds_threshold"] == 999

    def test_velocity_config_disables_drawdown(self):
        cfg = self.configs[1]
        tds = cfg["trend_defense"]
        assert tds["level_3"]["drawdown_budget_ticks"] == 999999

    def test_velocity_config_disables_precursor(self):
        cfg = self.configs[1]
        tds = cfg["trend_defense"]
        assert tds["precursor"]["precursor_min_signals"] == 99

    def test_consecutive_adds_config_normal_threshold(self):
        cfg = self.configs[2]  # consecutive_adds
        tds = cfg["trend_defense"]
        assert tds["level_2"]["consecutive_adds_threshold"] == 3

    def test_consecutive_adds_config_disables_velocity(self):
        cfg = self.configs[2]
        tds = cfg["trend_defense"]
        assert tds["level_2"]["velocity_threshold_sec"] == pytest.approx(0.001)

    def test_consecutive_adds_config_disables_drawdown(self):
        cfg = self.configs[2]
        tds = cfg["trend_defense"]
        assert tds["level_3"]["drawdown_budget_ticks"] == 999999

    def test_drawdown_budget_config_normal_threshold(self):
        cfg = self.configs[3]  # drawdown_budget
        tds = cfg["trend_defense"]
        assert tds["level_3"]["drawdown_budget_ticks"] == pytest.approx(50.0)

    def test_drawdown_budget_config_disables_velocity(self):
        cfg = self.configs[3]
        tds = cfg["trend_defense"]
        assert tds["level_2"]["velocity_threshold_sec"] == pytest.approx(0.001)

    def test_drawdown_budget_config_disables_consecutive_adds(self):
        cfg = self.configs[3]
        tds = cfg["trend_defense"]
        assert tds["level_2"]["consecutive_adds_threshold"] == 999

    def test_all_configs_have_tds_enabled(self):
        for cfg in self.configs:
            assert cfg["trend_defense"]["enabled"] is True

    def test_all_configs_have_retracement_reset_pct(self):
        for cfg in self.configs:
            assert cfg["trend_defense"]["level_2"]["retracement_reset_pct"] == pytest.approx(0.3)

    def test_all_configs_have_cooldown_sec(self):
        for cfg in self.configs:
            assert cfg["trend_defense"]["level_3"]["cooldown_sec"] == pytest.approx(300.0)


# ---------------------------------------------------------------------------
# test_build_drawdown_sweep_configs
# ---------------------------------------------------------------------------

class TestBuildDrawdownSweepConfigs:
    def setup_method(self):
        self.configs = rc.build_drawdown_sweep_configs()
        self._default_thresholds = [30, 40, 50, 60, 80, 100]

    def test_returns_exactly_6_configs(self):
        assert len(self.configs) == 6

    def test_drawdown_thresholds_correct(self):
        actual = [c["trend_defense"]["level_3"]["drawdown_budget_ticks"] for c in self.configs]
        assert actual == self._default_thresholds

    def test_all_configs_disable_velocity(self):
        for cfg in self.configs:
            assert cfg["trend_defense"]["level_2"]["velocity_threshold_sec"] == pytest.approx(0.001)

    def test_all_configs_disable_consecutive_adds(self):
        for cfg in self.configs:
            assert cfg["trend_defense"]["level_2"]["consecutive_adds_threshold"] == 999

    def test_all_configs_disable_precursor(self):
        for cfg in self.configs:
            assert cfg["trend_defense"]["precursor"]["precursor_min_signals"] == 99

    def test_all_configs_have_tds_enabled(self):
        for cfg in self.configs:
            assert cfg["trend_defense"]["enabled"] is True

    def test_custom_thresholds_accepted(self):
        custom = [25, 75, 150]
        configs = rc.build_drawdown_sweep_configs(thresholds=custom)
        assert len(configs) == 3
        actual = [c["trend_defense"]["level_3"]["drawdown_budget_ticks"] for c in configs]
        assert actual == custom

    def test_each_config_has_name(self):
        for cfg in self.configs:
            assert "_name" in cfg


# ---------------------------------------------------------------------------
# test_build_combined_config
# ---------------------------------------------------------------------------

class TestBuildCombinedConfig:
    def test_velocity_winner_with_l3_threshold(self):
        cfg = rc.build_combined_config(best_l1_detector="velocity", best_l3_threshold=100)
        tds = cfg["trend_defense"]
        # velocity should be at spec default
        assert tds["level_2"]["velocity_threshold_sec"] == pytest.approx(60.0)
        # drawdown budget at the best L3 threshold
        assert tds["level_3"]["drawdown_budget_ticks"] == pytest.approx(100.0)
        # non-winning detectors disabled
        assert tds["level_2"]["consecutive_adds_threshold"] == 999
        assert tds["precursor"]["precursor_min_signals"] == 99

    def test_consecutive_adds_winner(self):
        cfg = rc.build_combined_config(best_l1_detector="consecutive_adds", best_l3_threshold=50)
        tds = cfg["trend_defense"]
        assert tds["level_2"]["consecutive_adds_threshold"] == 3
        assert tds["level_2"]["velocity_threshold_sec"] == pytest.approx(0.001)
        assert tds["level_3"]["drawdown_budget_ticks"] == pytest.approx(50.0)

    def test_retracement_winner(self):
        cfg = rc.build_combined_config(best_l1_detector="retracement", best_l3_threshold=80)
        tds = cfg["trend_defense"]
        # retracement has no tunable threshold; other detectors disabled
        assert tds["level_2"]["velocity_threshold_sec"] == pytest.approx(0.001)
        assert tds["level_2"]["consecutive_adds_threshold"] == 999
        assert tds["level_3"]["drawdown_budget_ticks"] == pytest.approx(80.0)

    def test_drawdown_budget_winner_degenerates(self):
        # If drawdown_budget won Exp 1, Exp 3 is drawdown at best threshold
        cfg = rc.build_combined_config(best_l1_detector="drawdown_budget", best_l3_threshold=60)
        tds = cfg["trend_defense"]
        assert tds["level_3"]["drawdown_budget_ticks"] == pytest.approx(60.0)

    def test_combined_config_has_tds_enabled(self):
        cfg = rc.build_combined_config(best_l1_detector="velocity", best_l3_threshold=100)
        assert cfg["trend_defense"]["enabled"] is True

    def test_combined_config_has_name(self):
        cfg = rc.build_combined_config(best_l1_detector="velocity", best_l3_threshold=100)
        assert "_name" in cfg


# ---------------------------------------------------------------------------
# test_build_run_config
# ---------------------------------------------------------------------------

class TestBuildRunConfig:
    def setup_method(self):
        # Minimal profile data (mirrors profiles/max_profit.json bar_types entry)
        self.profile_data = {
            "step_dist": 7.0,
            "max_levels": 1,
            "max_total_position": 2,
        }
        self.source_id = "bar_data_250vol_rot"
        self.tds_config = {
            "enabled": True,
            "level_1": {"step_widen_factor": 1.5, "max_levels_reduction": 1},
            "level_2": {
                "velocity_threshold_sec": 60.0,
                "consecutive_adds_threshold": 3,
                "retracement_reset_pct": 0.3,
            },
            "level_3": {"drawdown_budget_ticks": 50.0, "cooldown_sec": 300.0},
            "precursor": {
                "precursor_min_signals": 2,
                "speed_threshold": 1.0,
                "regime_accel_threshold": 1.0,
                "adverse_speed_threshold": 1.0,
            },
        }
        # Minimal base_params matching rotational_params.json
        self.base_params = {
            "version": "v1",
            "instrument": "NQ",
            "archetype": {
                "name": "rotational",
                "simulator_module": "rotational_simulator",
            },
            "period": "P1a",
            "bar_data_primary": {
                "bar_data_250vol_rot": "stages/01-data/data/bar_data/volume/NQ_BarData_250vol_rot_P1.csv",
                "bar_data_250tick_rot": "stages/01-data/data/bar_data/tick/NQ_BarData_250tick_rot_P1.csv",
                "bar_data_10sec_rot": "stages/01-data/data/bar_data/time/NQ_BarData_10sec_rot_P1.csv",
            },
            "bar_data_reference": {},
            "_instrument": {"tick_size": 0.25, "cost_ticks": 3},
        }

    def test_returns_dict(self):
        cfg = rc.build_run_config(
            self.profile_data, self.source_id, self.tds_config, self.base_params
        )
        assert isinstance(cfg, dict)

    def test_trend_defense_enabled(self):
        cfg = rc.build_run_config(
            self.profile_data, self.source_id, self.tds_config, self.base_params
        )
        assert cfg["trend_defense"]["enabled"] is True

    def test_martingale_uses_profile_step_dist(self):
        cfg = rc.build_run_config(
            self.profile_data, self.source_id, self.tds_config, self.base_params
        )
        assert cfg["hypothesis"]["trigger_params"]["step_dist"] == pytest.approx(7.0)

    def test_martingale_uses_profile_max_levels(self):
        cfg = rc.build_run_config(
            self.profile_data, self.source_id, self.tds_config, self.base_params
        )
        assert cfg["martingale"]["max_levels"] == 1

    def test_martingale_uses_profile_max_total_position(self):
        cfg = rc.build_run_config(
            self.profile_data, self.source_id, self.tds_config, self.base_params
        )
        assert cfg["martingale"]["max_total_position"] == 2

    def test_max_contract_size_fixed_16(self):
        cfg = rc.build_run_config(
            self.profile_data, self.source_id, self.tds_config, self.base_params
        )
        assert cfg["martingale"]["max_contract_size"] == 16

    def test_period_is_p1a(self):
        cfg = rc.build_run_config(
            self.profile_data, self.source_id, self.tds_config, self.base_params
        )
        assert cfg["period"].lower() == "p1a"

    def test_bar_data_primary_has_only_this_source(self):
        cfg = rc.build_run_config(
            self.profile_data, self.source_id, self.tds_config, self.base_params
        )
        assert list(cfg["bar_data_primary"].keys()) == [self.source_id]

    def test_instrument_constants_present(self):
        cfg = rc.build_run_config(
            self.profile_data, self.source_id, self.tds_config, self.base_params
        )
        assert "_instrument" in cfg
        assert "tick_size" in cfg["_instrument"]
        assert "cost_ticks" in cfg["_instrument"]


# ---------------------------------------------------------------------------
# test_compute_survival_metrics
# ---------------------------------------------------------------------------

class TestComputeSurvivalMetrics:
    """Tests survival metric computation with synthetic data."""

    def _make_cycles_df(self, n_td_flatten: int = 2, total: int = 10) -> pd.DataFrame:
        """Create minimal synthetic cycles DataFrame."""
        rows = []
        for i in range(total):
            exit_reason = "td_flatten" if i < n_td_flatten else "reversal"
            rows.append({
                "exit_reason": exit_reason,
                "duration_bars": 10 + i,
                "pnl_ticks": 5.0 if exit_reason == "reversal" else -3.0,
            })
        return pd.DataFrame(rows)

    def _make_mock_result(self, cycles_df: pd.DataFrame):
        result = MagicMock()
        result.cycles = cycles_df
        return result

    def _make_mock_tds(self):
        tds = MagicMock()
        tds.get_summary.return_value = {
            "l1_triggers": 5,
            "l2_triggers": 2,
            "l3_triggers": 3,
        }
        return tds

    def _make_baseline_metrics(self):
        return {
            "worst_cycle_dd": 1000.0,
            "max_level_exposure_pct": 20.0,
            "total_pnl_ticks": 5000.0,
            "tail_ratio": 0.5,
        }

    def test_returns_dict(self):
        cycles = self._make_cycles_df()
        result = self._make_mock_result(cycles)
        tds = self._make_mock_tds()
        baseline = self._make_baseline_metrics()
        bars_df = pd.DataFrame({"datetime": pd.date_range("2025-10-01", periods=100, freq="10s")})

        with _patch_compute_extended(return_val={
            "worst_cycle_dd": 800.0,
            "max_level_exposure_pct": 15.0,
            "total_pnl_ticks": 4800.0,
            "tail_ratio": 0.6,
            "cycle_pf": 1.5,
            "n_cycles": 10,
        }):
            out = rc.compute_survival_metrics(result, tds, baseline, bars_df, max_levels=1, cost_ticks=3)
        assert isinstance(out, dict)

    def test_worst_dd_reduction_positive_when_improved(self):
        cycles = self._make_cycles_df()
        result = self._make_mock_result(cycles)
        tds = self._make_mock_tds()
        baseline = self._make_baseline_metrics()
        bars_df = pd.DataFrame({"datetime": pd.date_range("2025-10-01", periods=100, freq="10s")})

        extended = {
            "worst_cycle_dd": 800.0,  # improved: 1000 -> 800
            "max_level_exposure_pct": 15.0,
            "total_pnl_ticks": 4800.0,
            "tail_ratio": 0.6,
            "cycle_pf": 1.5,
            "n_cycles": 10,
        }
        with _patch_compute_extended(return_val=extended):
            out = rc.compute_survival_metrics(result, tds, baseline, bars_df, max_levels=1, cost_ticks=3)

        # worst_dd_reduction = baseline_worst_dd - run_worst_dd (positive = improvement)
        assert out["worst_dd_reduction"] == pytest.approx(1000.0 - 800.0)

    def test_pnl_impact_is_delta_from_baseline(self):
        cycles = self._make_cycles_df()
        result = self._make_mock_result(cycles)
        tds = self._make_mock_tds()
        baseline = self._make_baseline_metrics()
        bars_df = pd.DataFrame({"datetime": pd.date_range("2025-10-01", periods=100, freq="10s")})

        extended = {
            "worst_cycle_dd": 800.0,
            "max_level_exposure_pct": 15.0,
            "total_pnl_ticks": 4700.0,  # worse by 300
            "tail_ratio": 0.6,
            "cycle_pf": 1.5,
            "n_cycles": 10,
        }
        with _patch_compute_extended(return_val=extended):
            out = rc.compute_survival_metrics(result, tds, baseline, bars_df, max_levels=1, cost_ticks=3)

        # pnl_impact_ticks = extended_pnl - baseline_pnl = 4700 - 5000 = -300
        assert out["pnl_impact_ticks"] == pytest.approx(4700.0 - 5000.0)

    def test_n_td_flatten_cycles_counted_correctly(self):
        cycles = self._make_cycles_df(n_td_flatten=3, total=10)
        result = self._make_mock_result(cycles)
        tds = self._make_mock_tds()
        baseline = self._make_baseline_metrics()
        bars_df = pd.DataFrame({"datetime": pd.date_range("2025-10-01", periods=100, freq="10s")})

        extended = {
            "worst_cycle_dd": 800.0,
            "max_level_exposure_pct": 15.0,
            "total_pnl_ticks": 4800.0,
            "tail_ratio": 0.6,
            "cycle_pf": 1.5,
            "n_cycles": 10,
        }
        with _patch_compute_extended(return_val=extended):
            out = rc.compute_survival_metrics(result, tds, baseline, bars_df, max_levels=1, cost_ticks=3)

        assert out["n_td_flatten_cycles"] == 3

    def test_l3_recovery_bars_avg_computed(self):
        cycles = self._make_cycles_df(n_td_flatten=2, total=10)
        result = self._make_mock_result(cycles)
        tds = self._make_mock_tds()
        baseline = self._make_baseline_metrics()
        bars_df = pd.DataFrame({"datetime": pd.date_range("2025-10-01", periods=100, freq="10s")})

        extended = {
            "worst_cycle_dd": 800.0,
            "max_level_exposure_pct": 15.0,
            "total_pnl_ticks": 4800.0,
            "tail_ratio": 0.6,
            "cycle_pf": 1.5,
            "n_cycles": 10,
        }
        with _patch_compute_extended(return_val=extended):
            out = rc.compute_survival_metrics(result, tds, baseline, bars_df, max_levels=1, cost_ticks=3)

        # td_flatten cycles have duration_bars of 10, 11 -> avg = 10.5
        assert out["l3_recovery_bars_avg"] == pytest.approx(10.5)

    def test_tds_triggers_included_in_output(self):
        cycles = self._make_cycles_df()
        result = self._make_mock_result(cycles)
        tds = self._make_mock_tds()
        baseline = self._make_baseline_metrics()
        bars_df = pd.DataFrame({"datetime": pd.date_range("2025-10-01", periods=100, freq="10s")})

        extended = {
            "worst_cycle_dd": 800.0,
            "max_level_exposure_pct": 15.0,
            "total_pnl_ticks": 4800.0,
            "tail_ratio": 0.6,
            "cycle_pf": 1.5,
            "n_cycles": 10,
        }
        with _patch_compute_extended(return_val=extended):
            out = rc.compute_survival_metrics(result, tds, baseline, bars_df, max_levels=1, cost_ticks=3)

        assert out["l1_triggers"] == 5
        assert out["l2_triggers"] == 2
        assert out["l3_triggers"] == 3


# ---------------------------------------------------------------------------
# test_n_td_flatten_cycles
# ---------------------------------------------------------------------------

class TestNTdFlattenCycles:
    def test_counts_correctly_with_mixed_exit_reasons(self):
        cycles = pd.DataFrame({
            "exit_reason": ["reversal", "td_flatten", "reversal", "td_flatten", "td_flatten"],
            "duration_bars": [5, 8, 3, 12, 7],
        })
        assert rc.count_td_flatten_cycles(cycles) == 3

    def test_zero_when_no_td_flatten(self):
        cycles = pd.DataFrame({
            "exit_reason": ["reversal", "reversal", "reversal"],
            "duration_bars": [5, 8, 3],
        })
        assert rc.count_td_flatten_cycles(cycles) == 0

    def test_all_td_flatten(self):
        cycles = pd.DataFrame({
            "exit_reason": ["td_flatten", "td_flatten"],
            "duration_bars": [5, 8],
        })
        assert rc.count_td_flatten_cycles(cycles) == 2

    def test_empty_dataframe(self):
        cycles = pd.DataFrame({"exit_reason": [], "duration_bars": []})
        assert rc.count_td_flatten_cycles(cycles) == 0


# ---------------------------------------------------------------------------
# test_dry_run_smoke
# ---------------------------------------------------------------------------

class TestDryRunSmoke:
    def _run_dry(self, experiment: str) -> subprocess.CompletedProcess:
        script = _ARCHETYPE_DIR / "run_tds_calibration.py"
        return subprocess.run(
            [sys.executable, str(script), "--dry-run", "--experiment", experiment],
            capture_output=True,
            text=True,
            cwd=str(_ARCHETYPE_DIR),
        )

    def test_experiment_1_exits_0(self):
        proc = self._run_dry("1")
        assert proc.returncode == 0, f"stderr: {proc.stderr}"

    def test_experiment_1_prints_4_configs(self):
        proc = self._run_dry("1")
        # Output should mention 4 isolated configs
        assert "4" in proc.stdout

    def test_experiment_2_exits_0(self):
        proc = self._run_dry("2")
        assert proc.returncode == 0, f"stderr: {proc.stderr}"

    def test_experiment_2_prints_6_configs(self):
        proc = self._run_dry("2")
        assert "6" in proc.stdout

    def test_experiment_3_exits_0(self):
        proc = self._run_dry("3")
        assert proc.returncode == 0, f"stderr: {proc.stderr}"

    def test_experiment_all_exits_0(self):
        proc = self._run_dry("all")
        assert proc.returncode == 0, f"stderr: {proc.stderr}"


# ---------------------------------------------------------------------------
# Helper: context manager to patch compute_extended_metrics
# ---------------------------------------------------------------------------

from contextlib import contextmanager
from unittest.mock import patch


@contextmanager
def _patch_compute_extended(return_val: dict):
    with patch("run_tds_calibration.compute_extended_metrics", return_value=return_val):
        yield


# ---------------------------------------------------------------------------
# test_select_best_configs — selection logic with guard tests
# ---------------------------------------------------------------------------

def _make_exp_row(
    experiment: int,
    detector_name: str,
    profile: str,
    source_id: str,
    worst_dd_reduction: float,
    max_level_pct_reduction: float,
    pnl_impact_ticks: float,
    n_td_flatten_cycles: int,
    n_cycles: int,
    drawdown_budget_ticks: float = 999999.0,
) -> dict:
    """Helper to build a synthetic experiment row dict."""
    return {
        "experiment": experiment,
        "detector_name": detector_name,
        "profile": profile,
        "source_id": source_id,
        "worst_dd_reduction": worst_dd_reduction,
        "max_level_pct_reduction": max_level_pct_reduction,
        "pnl_impact_ticks": pnl_impact_ticks,
        "n_td_flatten_cycles": n_td_flatten_cycles,
        "n_cycles": n_cycles,
        "drawdown_budget_ticks": drawdown_budget_ticks,
        # Required columns with defaults
        "l1_triggers": 0,
        "l2_triggers": 0,
        "l3_triggers": 0,
        "tail_ratio_delta": 0.0,
        "l3_recovery_bars_avg": 0.0,
        "velocity_threshold_sec": 0.001,
        "consecutive_adds_threshold": 999,
        "cooldown_sec": 300.0,
        "step_widen_factor": 1.5,
        "max_levels_reduction": 1,
        "retracement_reset_pct": 0.3,
        "precursor_min_signals": 99,
    }


class TestSelectBestConfigs:
    """Tests for select_best_configs() selection logic."""

    _PROFILE = "MAX_PROFIT"
    _SOURCE = "bar_data_250vol_rot"
    _BASELINE_PNL = 10000.0
    _BASELINE_N = 500

    def _make_baselines(self, pnl=None, n=None):
        return {
            (self._PROFILE, self._SOURCE): {
                "total_pnl_ticks": pnl or self._BASELINE_PNL,
                "n_cycles": n or self._BASELINE_N,
                "worst_cycle_dd": 8000.0,
                "max_level_exposure_pct": 0.0,
                "tail_ratio": 0.1,
            }
        }

    def _make_dfs(self, exp1_rows, exp2_rows, exp3_rows):
        return (
            pd.DataFrame(exp1_rows),
            pd.DataFrame(exp2_rows),
            pd.DataFrame(exp3_rows),
        )

    def test_select_best_prefers_combined(self):
        """When Exp 3 combined has higher composite score, it is selected."""
        exp1 = [_make_exp_row(1, "velocity", self._PROFILE, self._SOURCE,
                              worst_dd_reduction=100, max_level_pct_reduction=0,
                              pnl_impact_ticks=-100, n_td_flatten_cycles=1, n_cycles=500)]
        exp2 = [_make_exp_row(2, "drawdown_sweep_80", self._PROFILE, self._SOURCE,
                              worst_dd_reduction=200, max_level_pct_reduction=0,
                              pnl_impact_ticks=-500, n_td_flatten_cycles=5, n_cycles=500,
                              drawdown_budget_ticks=80)]
        exp3 = [_make_exp_row(3, "combined_velocity_dd80", self._PROFILE, self._SOURCE,
                              worst_dd_reduction=350, max_level_pct_reduction=5,
                              pnl_impact_ticks=-200, n_td_flatten_cycles=5, n_cycles=505)]
        baselines = self._make_baselines()
        e1, e2, e3 = self._make_dfs(exp1, exp2, exp3)
        result = rc.select_best_configs(e1, e2, e3, baselines)
        assert len(result) == 1
        key = (self._PROFILE, self._SOURCE)
        selected = result[key]["selected"]
        # Exp 3 has composite=355, Exp 1 has composite=100, Exp 2 has composite=200
        assert selected["_experiment_source"] == "exp3_combined"

    def test_pnl_guard_excludes_high_impact_configs(self):
        """Configs exceeding -20% PnL impact are excluded even if survival improvement is high."""
        # Exp 1 has great dd reduction but catastrophic PnL: -3000 vs baseline 10000 -> fails guard (>-2000)
        exp1_bad = [_make_exp_row(1, "velocity", self._PROFILE, self._SOURCE,
                                  worst_dd_reduction=5000, max_level_pct_reduction=10,
                                  pnl_impact_ticks=-3000, n_td_flatten_cycles=1, n_cycles=500)]
        # Exp 3 has lower dd reduction but passes guard: -1000 < -2000 threshold
        exp3_good = [_make_exp_row(3, "combined_velocity_dd80", self._PROFILE, self._SOURCE,
                                   worst_dd_reduction=50, max_level_pct_reduction=0,
                                   pnl_impact_ticks=-500, n_td_flatten_cycles=2, n_cycles=502)]
        baselines = self._make_baselines(pnl=10000.0)  # guard threshold = -2000
        e1 = pd.DataFrame(exp1_bad)
        e2 = pd.DataFrame([_make_exp_row(2, "drawdown_sweep_80", self._PROFILE, self._SOURCE,
                                         worst_dd_reduction=100, max_level_pct_reduction=0,
                                         pnl_impact_ticks=-3500, n_td_flatten_cycles=10, n_cycles=500,
                                         drawdown_budget_ticks=80)])
        e3 = pd.DataFrame(exp3_good)
        result = rc.select_best_configs(e1, e2, e3, baselines)
        key = (self._PROFILE, self._SOURCE)
        selected = result[key]["selected"]
        # Only exp3 passes guard — must be selected despite lower dd_reduction
        assert selected["_pnl_guard_passed"] is True
        assert selected["_experiment_source"] == "exp3_combined"

    def test_over_trigger_flag(self):
        """Configs with n_td_flatten_cycles > 5% of n_cycles are flagged over_trigger."""
        # baseline n_cycles = 500, 5% = 25 — flag if >25 td_flatten cycles
        exp1 = [_make_exp_row(1, "velocity", self._PROFILE, self._SOURCE,
                              worst_dd_reduction=100, max_level_pct_reduction=0,
                              pnl_impact_ticks=-100, n_td_flatten_cycles=30, n_cycles=530)]
        exp2 = [_make_exp_row(2, "drawdown_sweep_80", self._PROFILE, self._SOURCE,
                              worst_dd_reduction=200, max_level_pct_reduction=0,
                              pnl_impact_ticks=-500, n_td_flatten_cycles=5, n_cycles=505,
                              drawdown_budget_ticks=80)]
        exp3 = [_make_exp_row(3, "combined_velocity_dd80", self._PROFILE, self._SOURCE,
                              worst_dd_reduction=250, max_level_pct_reduction=0,
                              pnl_impact_ticks=-200, n_td_flatten_cycles=28, n_cycles=528)]
        baselines = self._make_baselines()
        e1, e2, e3 = self._make_dfs(exp1, exp2, exp3)
        result = rc.select_best_configs(e1, e2, e3, baselines)
        key = (self._PROFILE, self._SOURCE)
        # The best config by composite score is exp3 (250 vs 200 vs 100) — but it has >25 td_flatten
        # over_trigger flag should be set
        selected = result[key]["selected"]
        # Check _over_trigger on the selected entry (may or may not select exp3)
        # Just verify that the flag is computed correctly for the config with 28 td_flatten cycles
        # (baseline n=500, 5%=25, 28>25 => over_trigger=True)
        exp3_candidate = [c for c in result[key]["all_candidates"] if "combined" in c.get("_experiment_source", "")]
        assert len(exp3_candidate) == 1
        assert exp3_candidate[0]["_over_trigger"] is True

    def test_output_json_schema(self):
        """best_tds_configs.json has all 9 profile x bar_type entries + baselines."""
        import json
        from pathlib import Path
        output_path = Path(__file__).parent / "tds_profiles" / "best_tds_configs.json"
        if not output_path.exists():
            pytest.skip("best_tds_configs.json not yet generated (run experiments first)")

        with open(output_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Must have all 3 profiles
        assert "MAX_PROFIT" in data, "Missing MAX_PROFIT profile"
        assert "SAFEST" in data, "Missing SAFEST profile"
        assert "MOST_CONSISTENT" in data, "Missing MOST_CONSISTENT profile"

        # Each profile must have all 3 bar types
        bar_types = ["bar_data_250vol_rot", "bar_data_250tick_rot", "bar_data_10sec_rot"]
        for profile in ["MAX_PROFIT", "SAFEST", "MOST_CONSISTENT"]:
            for bt in bar_types:
                assert bt in data[profile], f"Missing {profile}/{bt}"
                entry = data[profile][bt]
                assert "trend_defense" in entry
                assert entry["trend_defense"]["enabled"] is True
                assert "survival_deltas" in entry
                assert "worst_dd_reduction" in entry["survival_deltas"]
                assert "metadata" in entry

        # Must have baselines
        assert "no_tds_baselines" in data
        assert "calibration_method" in data

    def test_check_pnl_guard_pass(self):
        """PnL guard passes when impact is within -20% of baseline."""
        # baseline=10000, guard_threshold=-2000
        assert rc._check_pnl_guard(-1999, 10000) is True   # just passes
        assert rc._check_pnl_guard(-2000, 10000) is True   # exactly at threshold passes
        assert rc._check_pnl_guard(-2001, 10000) is False  # just fails

    def test_check_pnl_guard_fail(self):
        """PnL guard fails when impact exceeds -20% threshold."""
        assert rc._check_pnl_guard(-5000, 10000) is False  # -50% fails
        assert rc._check_pnl_guard(-30000, 3000) is False  # catastrophic fails

    def test_check_over_trigger_flag(self):
        """Over-trigger flag is True when n_td_flatten > 5% of baseline n_cycles."""
        assert rc._check_over_trigger(26, 500) is True   # 26 > 25 (5% of 500)
        assert rc._check_over_trigger(25, 500) is False  # exactly 25 = not over
        assert rc._check_over_trigger(0, 500) is False   # none = fine

    def test_determine_exp3_winners_prefers_guard_passing(self):
        """_determine_exp3_winners selects guard-passing L1 detector over guard-failing one."""
        # velocity: pnl_impact=-100 (passes guard on 10000 baseline)
        # consecutive_adds: pnl_impact=-3000 (fails guard), but higher dd_reduction
        exp1 = pd.DataFrame([
            _make_exp_row(1, "velocity", self._PROFILE, self._SOURCE,
                          worst_dd_reduction=100, max_level_pct_reduction=0,
                          pnl_impact_ticks=-100, n_td_flatten_cycles=0, n_cycles=500),
            _make_exp_row(1, "consecutive_adds", self._PROFILE, self._SOURCE,
                          worst_dd_reduction=500, max_level_pct_reduction=0,
                          pnl_impact_ticks=-3000, n_td_flatten_cycles=0, n_cycles=500),
            _make_exp_row(1, "retracement", self._PROFILE, self._SOURCE,
                          worst_dd_reduction=0, max_level_pct_reduction=0,
                          pnl_impact_ticks=0, n_td_flatten_cycles=0, n_cycles=500),
        ])
        exp2 = pd.DataFrame([
            _make_exp_row(2, "drawdown_sweep_100", self._PROFILE, self._SOURCE,
                          worst_dd_reduction=200, max_level_pct_reduction=0,
                          pnl_impact_ticks=-100, n_td_flatten_cycles=1, n_cycles=501,
                          drawdown_budget_ticks=100),
        ])
        baselines = self._make_baselines()
        winners = rc._determine_exp3_winners(exp1, exp2, baselines)
        key = (self._PROFILE, self._SOURCE)
        assert key in winners
        # velocity (dd=100, pnl=-100) should win over consecutive_adds (dd=500, pnl=-3000)
        assert winners[key]["best_l1"] == "velocity"

    def test_select_best_fallback_when_all_fail_guard(self):
        """When no config passes PnL guard, select least-bad by pnl_impact_ticks."""
        # All options fail guard (baseline=1000, threshold=-200)
        exp1 = [_make_exp_row(1, "velocity", self._PROFILE, self._SOURCE,
                              worst_dd_reduction=500, max_level_pct_reduction=0,
                              pnl_impact_ticks=-5000, n_td_flatten_cycles=5, n_cycles=500)]
        exp2 = [_make_exp_row(2, "drawdown_sweep_80", self._PROFILE, self._SOURCE,
                              worst_dd_reduction=300, max_level_pct_reduction=0,
                              pnl_impact_ticks=-3000, n_td_flatten_cycles=5, n_cycles=500,
                              drawdown_budget_ticks=80)]
        exp3 = [_make_exp_row(3, "combined_velocity_dd80", self._PROFILE, self._SOURCE,
                              worst_dd_reduction=400, max_level_pct_reduction=0,
                              pnl_impact_ticks=-4000, n_td_flatten_cycles=5, n_cycles=505)]
        baselines = self._make_baselines(pnl=1000.0)  # threshold = -200
        e1, e2, e3 = self._make_dfs(exp1, exp2, exp3)
        result = rc.select_best_configs(e1, e2, e3, baselines)
        key = (self._PROFILE, self._SOURCE)
        selected = result[key]["selected"]
        # _no_guard_pass should be set (no config passed)
        assert selected.get("_no_guard_pass", False) is True
        # Least-bad by pnl_impact: exp2 has -3000 (closest to 0 of the 3 options)
        assert selected["_pnl_guard_passed"] is False
