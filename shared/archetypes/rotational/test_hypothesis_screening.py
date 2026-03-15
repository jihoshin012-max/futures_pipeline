# archetype: rotational
"""Tests for run_hypothesis_screening.py.

Covers:
  - load_baselines() schema validation (best_per_source key, all 3 source IDs)
  - load_baselines() raises ValueError on missing key
  - get_base_config() has StepDist=6.0
  - H37 exclusion on 10sec (N/A_10SEC)
  - H37 NOT excluded on vol/tick
  - H19 skipped with SKIPPED_REFERENCE_REQUIRED
  - run_single_experiment returns all required fields
  - TSV column headers match expected schema
  - beats_baseline stored as string-parseable boolean
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------

_ARCHETYPE_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _ARCHETYPE_DIR.parents[3]
sys.path.insert(0, str(_ARCHETYPE_DIR))
sys.path.insert(0, str(_REPO_ROOT))

import run_hypothesis_screening as rhs  # noqa: E402

# ---------------------------------------------------------------------------
# Expected TSV columns
# ---------------------------------------------------------------------------

# Total experiment count: 41 hypotheses × 3 bar types = 123.
# H37/10sec included as N/A_10SEC placeholder (not a real run).
# H19 × 3 bar types = 3 SKIPPED rows.
# 119 OK runs + 3 H19 SKIPPED + 1 H37/10sec N/A = 123 total rows.
EXPECTED_ROW_COUNT = 123

EXPECTED_COLUMNS = [
    "hypothesis_id",
    "hypothesis_name",
    "dimension",
    "source_id",
    "cycle_pf",
    "delta_pf",
    "total_pnl_ticks",
    "delta_pnl",
    "n_cycles",
    "win_rate",
    "sharpe",
    "max_drawdown_ticks",
    "avg_winner_ticks",
    "avg_loser_ticks",
    "beats_baseline",
    "feature_compute_sec",
    "simulator_sec",
    "total_sec",
    "classification",
]

# ---------------------------------------------------------------------------
# Baseline-related tests
# ---------------------------------------------------------------------------


def test_load_baselines_returns_three_sources(tmp_path):
    """load_baselines() returns dict with all 3 source IDs and correct values."""
    baseline = {
        "best_per_source": {
            "bar_data_250vol_rot": {"cycle_pf": 0.6714, "step_dist": 6.0, "total_pnl_ticks": -100, "n_cycles": 500, "win_rate": 0.6, "sharpe": 0.1, "max_drawdown_ticks": 200},
            "bar_data_250tick_rot": {"cycle_pf": 0.7339, "step_dist": 6.0, "total_pnl_ticks": -50, "n_cycles": 480, "win_rate": 0.61, "sharpe": 0.12, "max_drawdown_ticks": 180},
            "bar_data_10sec_rot": {"cycle_pf": 0.7550, "step_dist": 6.0, "total_pnl_ticks": -30, "n_cycles": 460, "win_rate": 0.62, "sharpe": 0.14, "max_drawdown_ticks": 160},
        }
    }
    p = tmp_path / "sweep_P1a.json"
    p.write_text(json.dumps(baseline))
    result = rhs.load_baselines(str(p))

    assert set(result.keys()) == {
        "bar_data_250vol_rot",
        "bar_data_250tick_rot",
        "bar_data_10sec_rot",
    }
    assert abs(result["bar_data_250vol_rot"]["cycle_pf"] - 0.6714) < 1e-9
    assert abs(result["bar_data_250tick_rot"]["cycle_pf"] - 0.7339) < 1e-9
    assert abs(result["bar_data_10sec_rot"]["cycle_pf"] - 0.7550) < 1e-9


def test_load_baselines_raises_on_missing_best_per_source_key(tmp_path):
    """load_baselines() raises ValueError when best_per_source key is missing."""
    bad = {"results": {}, "sweep_params": {}}
    p = tmp_path / "bad.json"
    p.write_text(json.dumps(bad))
    with pytest.raises(ValueError, match="best_per_source"):
        rhs.load_baselines(str(p))


def test_load_baselines_raises_on_missing_source_id(tmp_path):
    """load_baselines() raises ValueError when one of the 3 source IDs is missing."""
    incomplete = {
        "best_per_source": {
            "bar_data_250vol_rot": {"cycle_pf": 0.6714, "step_dist": 6.0},
            "bar_data_250tick_rot": {"cycle_pf": 0.7339, "step_dist": 6.0},
            # bar_data_10sec_rot missing
        }
    }
    p = tmp_path / "incomplete.json"
    p.write_text(json.dumps(incomplete))
    with pytest.raises(ValueError, match="bar_data_10sec_rot"):
        rhs.load_baselines(str(p))


# ---------------------------------------------------------------------------
# get_base_config tests
# ---------------------------------------------------------------------------


def test_get_base_config_step_dist_is_6():
    """get_base_config() returns config with StepDist=6.0 not 2.0."""
    cfg = rhs.get_base_config()
    step_dist = cfg["hypothesis"]["trigger_params"]["step_dist"]
    assert step_dist == 6.0, f"Expected StepDist=6.0, got {step_dist}"


def test_get_base_config_period_is_p1a():
    """get_base_config() sets period='P1a'."""
    cfg = rhs.get_base_config()
    assert cfg["period"] == "P1a"


# ---------------------------------------------------------------------------
# Synthetic bar data helper
# ---------------------------------------------------------------------------


def _make_synthetic_bars(n: int = 300) -> pd.DataFrame:
    """Create minimal synthetic bar DataFrame for testing."""
    import datetime
    base = pd.Timestamp("2025-09-22 09:30:00")
    datetimes = [base + pd.Timedelta(seconds=10 * i) for i in range(n)]
    prices = 18000.0 + np.cumsum(np.random.randn(n) * 2)
    df = pd.DataFrame({
        "datetime": datetimes,
        "Date": [dt.date() for dt in datetimes],
        "Time": [dt.strftime("%H:%M:%S") for dt in datetimes],
        "Open": prices,
        "High": prices + 2,
        "Low": prices - 2,
        "Last": prices,
        "Volume": np.random.randint(100, 1000, n),
        # ATR col (col 35) — needed for some hypotheses
        "ATR": np.full(n, 5.0),
        # SD band columns for H3
        "StdDev_1_Upper": prices + 10,
        "StdDev_1_Lower": prices - 10,
        "StdDev_2_Upper": prices + 20,
        "StdDev_2_Lower": prices - 20,
        "StdDev_3_Upper": prices + 30,
        "StdDev_3_Lower": prices - 30,
        # ZZ columns
        "ZZ_reversal": np.zeros(n),
        "ZZ_oscillator": np.random.uniform(0, 1, n),
        # Bid/Ask
        "BidVolume": np.random.randint(50, 500, n),
        "AskVolume": np.random.randint(50, 500, n),
    })
    return df


def _make_baseline_metrics() -> dict:
    return {
        "bar_data_250vol_rot": {"cycle_pf": 0.6714, "step_dist": 6.0, "total_pnl_ticks": -100, "n_cycles": 500},
        "bar_data_250tick_rot": {"cycle_pf": 0.7339, "step_dist": 6.0, "total_pnl_ticks": -50, "n_cycles": 480},
        "bar_data_10sec_rot": {"cycle_pf": 0.7550, "step_dist": 6.0, "total_pnl_ticks": -30, "n_cycles": 460},
    }


def _make_instrument_info() -> dict:
    return {"tick_size": 0.25, "cost_ticks": 3, "tick_value": 5.0}


# ---------------------------------------------------------------------------
# run_single_experiment tests
# ---------------------------------------------------------------------------


def test_run_single_experiment_returns_required_fields():
    """run_single_experiment returns dict with all required output fields."""
    from hypothesis_configs import HYPOTHESIS_REGISTRY, build_experiment_config

    base_cfg = rhs.get_base_config()
    hypothesis = HYPOTHESIS_REGISTRY["H1"]
    source_id = "bar_data_250vol_rot"
    bars = _make_synthetic_bars(200)
    instrument = _make_instrument_info()
    baselines = _make_baseline_metrics()

    # Inject instrument and bar source into config
    cfg_with_source = rhs._prepare_single_source_config(base_cfg, source_id, instrument)

    result = rhs.run_single_experiment(
        base_config=cfg_with_source,
        hypothesis=hypothesis,
        source_id=source_id,
        bar_data=bars,
        instrument_info=instrument,
        baseline_metrics=baselines,
    )

    required_keys = {
        "hypothesis_id", "hypothesis_name", "dimension", "source_id",
        "cycle_pf", "delta_pf", "total_pnl_ticks", "delta_pnl",
        "n_cycles", "win_rate", "sharpe", "max_drawdown_ticks",
        "avg_winner_ticks", "avg_loser_ticks",
        "beats_baseline", "feature_compute_sec", "simulator_sec", "total_sec",
        "classification",
    }
    missing = required_keys - set(result.keys())
    assert not missing, f"Missing keys: {missing}"


def test_h37_on_10sec_returns_na_10sec():
    """H37 on bar_data_10sec_rot returns classification='N/A_10SEC' and cycle_pf=None."""
    from hypothesis_configs import HYPOTHESIS_REGISTRY

    base_cfg = rhs.get_base_config()
    hypothesis = HYPOTHESIS_REGISTRY["H37"]
    source_id = "bar_data_10sec_rot"
    bars = _make_synthetic_bars(200)
    instrument = _make_instrument_info()
    baselines = _make_baseline_metrics()

    cfg_with_source = rhs._prepare_single_source_config(base_cfg, source_id, instrument)

    result = rhs.run_single_experiment(
        base_config=cfg_with_source,
        hypothesis=hypothesis,
        source_id=source_id,
        bar_data=bars,
        instrument_info=instrument,
        baseline_metrics=baselines,
    )

    assert result["classification"] == "N/A_10SEC", f"Expected N/A_10SEC, got '{result['classification']}'"
    assert result["cycle_pf"] is None, f"Expected cycle_pf=None, got {result['cycle_pf']}"


def test_h37_on_vol_runs_normally():
    """H37 on bar_data_250vol_rot is NOT excluded — runs normally."""
    from hypothesis_configs import HYPOTHESIS_REGISTRY

    base_cfg = rhs.get_base_config()
    hypothesis = HYPOTHESIS_REGISTRY["H37"]
    source_id = "bar_data_250vol_rot"
    bars = _make_synthetic_bars(200)
    instrument = _make_instrument_info()
    baselines = _make_baseline_metrics()

    cfg_with_source = rhs._prepare_single_source_config(base_cfg, source_id, instrument)

    result = rhs.run_single_experiment(
        base_config=cfg_with_source,
        hypothesis=hypothesis,
        source_id=source_id,
        bar_data=bars,
        instrument_info=instrument,
        baseline_metrics=baselines,
    )

    # Should NOT be skipped — classification should be "OK" (ran normally)
    assert result["classification"] not in ("N/A_10SEC", "SKIPPED_REFERENCE_REQUIRED"), (
        f"H37 on vol should run normally, got classification='{result['classification']}'"
    )


def test_h19_returns_skipped_reference_required():
    """H19 on any bar type returns classification='SKIPPED_REFERENCE_REQUIRED'."""
    from hypothesis_configs import HYPOTHESIS_REGISTRY

    base_cfg = rhs.get_base_config()
    hypothesis = HYPOTHESIS_REGISTRY["H19"]
    source_id = "bar_data_250vol_rot"
    bars = _make_synthetic_bars(200)
    instrument = _make_instrument_info()
    baselines = _make_baseline_metrics()

    cfg_with_source = rhs._prepare_single_source_config(base_cfg, source_id, instrument)

    result = rhs.run_single_experiment(
        base_config=cfg_with_source,
        hypothesis=hypothesis,
        source_id=source_id,
        bar_data=bars,
        instrument_info=instrument,
        baseline_metrics=baselines,
    )

    assert result["classification"] == "SKIPPED_REFERENCE_REQUIRED", (
        f"Expected SKIPPED_REFERENCE_REQUIRED, got '{result['classification']}'"
    )
    assert result["cycle_pf"] is None, f"Expected cycle_pf=None, got {result['cycle_pf']}"


# ---------------------------------------------------------------------------
# TSV schema tests
# ---------------------------------------------------------------------------


def test_write_results_tsv_header_columns(tmp_path):
    """TSV output has expected header columns."""
    # Build a minimal fake result list
    fake_result = {
        "hypothesis_id": "H1",
        "hypothesis_name": "ATR-scaled step",
        "dimension": "A",
        "source_id": "bar_data_250vol_rot",
        "cycle_pf": 0.65,
        "delta_pf": -0.02,
        "total_pnl_ticks": -500.0,
        "delta_pnl": 10.0,
        "n_cycles": 400,
        "win_rate": 0.60,
        "sharpe": 0.08,
        "max_drawdown_ticks": 3000.0,
        "avg_winner_ticks": 30.0,
        "avg_loser_ticks": -80.0,
        "beats_baseline": False,
        "feature_compute_sec": 0.02,
        "simulator_sec": 1.5,
        "total_sec": 1.52,
        "classification": "OK",
    }

    out_path = tmp_path / "test_output.tsv"
    rhs.write_results_tsv([fake_result], str(out_path))

    df = pd.read_csv(str(out_path), sep="\t")
    for col in EXPECTED_COLUMNS:
        assert col in df.columns, f"Missing column '{col}' in TSV"


def test_beats_baseline_stored_as_string_boolean(tmp_path):
    """beats_baseline column is stored as boolean-parseable string 'True'/'False'."""
    fake_results = [
        {
            "hypothesis_id": "H1",
            "hypothesis_name": "ATR-scaled step",
            "dimension": "A",
            "source_id": "bar_data_250vol_rot",
            "cycle_pf": 0.65,
            "delta_pf": -0.02,
            "total_pnl_ticks": -500.0,
            "delta_pnl": 10.0,
            "n_cycles": 400,
            "win_rate": 0.60,
            "sharpe": 0.08,
            "max_drawdown_ticks": 3000.0,
            "avg_winner_ticks": 30.0,
            "avg_loser_ticks": -80.0,
            "beats_baseline": True,
            "feature_compute_sec": 0.02,
            "simulator_sec": 1.5,
            "total_sec": 1.52,
            "classification": "OK",
        },
        {
            "hypothesis_id": "H2",
            "hypothesis_name": "Asymmetric reversal",
            "dimension": "B",
            "source_id": "bar_data_250tick_rot",
            "cycle_pf": 0.50,
            "delta_pf": -0.20,
            "total_pnl_ticks": -1000.0,
            "delta_pnl": -50.0,
            "n_cycles": 350,
            "win_rate": 0.55,
            "sharpe": -0.05,
            "max_drawdown_ticks": 5000.0,
            "avg_winner_ticks": 25.0,
            "avg_loser_ticks": -90.0,
            "beats_baseline": False,
            "feature_compute_sec": 0.01,
            "simulator_sec": 1.2,
            "total_sec": 1.21,
            "classification": "OK",
        },
    ]

    out_path = tmp_path / "test_bb.tsv"
    rhs.write_results_tsv(fake_results, str(out_path))

    df = pd.read_csv(str(out_path), sep="\t")
    bb_vals = df["beats_baseline"].astype(str).str.strip()

    # Values must be exactly "True" or "False"
    valid = {"True", "False"}
    for v in bb_vals:
        assert v in valid, f"beats_baseline value '{v}' is not 'True' or 'False'"

    assert bb_vals.iloc[0] == "True"
    assert bb_vals.iloc[1] == "False"

    # Also verify script handles string comparison (True/False logic works after str parsing)
    bb_parsed = (bb_vals.str.lower() == "true")
    assert bb_parsed.iloc[0] is True or bool(bb_parsed.iloc[0])
    assert not (bb_parsed.iloc[1] is True or bool(bb_parsed.iloc[1]))
