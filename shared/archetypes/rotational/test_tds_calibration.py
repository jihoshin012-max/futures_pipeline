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
