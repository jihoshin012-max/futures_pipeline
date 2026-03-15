# archetype: rotational
"""Tests for Phase 1b cross-bar-type robustness classification logic."""

import io
import json
import os
import sys
import tempfile
from pathlib import Path

import pandas as pd
import pytest

# Ensure module can be imported
_ARCHETYPE_DIR = Path(__file__).parent
sys.path.insert(0, str(_ARCHETYPE_DIR))

from run_phase1b_classification import (
    advancement_decision,
    classify_all,
    classify_hypothesis,
    load_results,
)


# ---------------------------------------------------------------------------
# classify_hypothesis tests
# ---------------------------------------------------------------------------

def test_all_three_win_is_robust():
    assert classify_hypothesis(wins={"vol": True, "tick": True, "10sec": True}, h_id="H1") == "ROBUST"


def test_vol_tick_win_10sec_fail_is_activity_dependent():
    assert classify_hypothesis(wins={"vol": True, "tick": True, "10sec": False}, h_id="H1") == "ACTIVITY_DEPENDENT"


def test_only_vol_wins_is_sampling_coupled():
    assert classify_hypothesis(wins={"vol": True, "tick": False, "10sec": False}, h_id="H1") == "SAMPLING_COUPLED"


def test_10sec_only_wins_is_time_dependent():
    assert classify_hypothesis(wins={"vol": False, "tick": False, "10sec": True}, h_id="H1") == "TIME_DEPENDENT"


def test_all_three_fail_is_no_signal():
    assert classify_hypothesis(wins={"vol": False, "tick": False, "10sec": False}, h_id="H1") == "NO_SIGNAL"


def test_h37_both_activity_sampled_win_is_robust_activity():
    assert classify_hypothesis(wins={"vol": True, "tick": True, "10sec": None}, h_id="H37") == "ROBUST_ACTIVITY"


def test_h37_one_activity_sampled_wins_is_sampling_coupled():
    assert classify_hypothesis(wins={"vol": True, "tick": False, "10sec": None}, h_id="H37") == "SAMPLING_COUPLED"


def test_h37_both_activity_sampled_fail_is_no_signal():
    assert classify_hypothesis(wins={"vol": False, "tick": False, "10sec": None}, h_id="H37") == "NO_SIGNAL"


# ---------------------------------------------------------------------------
# advancement_decision tests
# ---------------------------------------------------------------------------

def test_advance_high_for_robust():
    assert advancement_decision("ROBUST") == "ADVANCE_HIGH"


def test_advance_high_for_robust_activity():
    assert advancement_decision("ROBUST_ACTIVITY") == "ADVANCE_HIGH"


def test_advance_flagged_for_activity_dependent():
    assert advancement_decision("ACTIVITY_DEPENDENT") == "ADVANCE_FLAGGED"


def test_advance_flagged_for_time_dependent():
    assert advancement_decision("TIME_DEPENDENT") == "ADVANCE_FLAGGED"


def test_do_not_advance_for_sampling_coupled():
    assert advancement_decision("SAMPLING_COUPLED") == "DO_NOT_ADVANCE"


def test_do_not_advance_for_no_signal():
    assert advancement_decision("NO_SIGNAL") == "DO_NOT_ADVANCE"


def test_not_tested_for_skipped_reference_required():
    assert advancement_decision("SKIPPED_REFERENCE_REQUIRED") == "NOT_TESTED"


# ---------------------------------------------------------------------------
# load_results tests
# ---------------------------------------------------------------------------

def _make_sample_tsv(rows: list[dict]) -> str:
    """Create a TSV string from a list of row dicts."""
    cols = [
        "hypothesis_id", "hypothesis_name", "dimension", "source_id",
        "cycle_pf", "delta_pf", "total_pnl_ticks", "delta_pnl",
        "n_cycles", "win_rate", "sharpe", "max_drawdown_ticks",
        "avg_winner_ticks", "avg_loser_ticks", "beats_baseline",
        "feature_compute_sec", "simulator_sec", "total_sec", "classification",
    ]
    lines = ["\t".join(cols)]
    for r in rows:
        lines.append("\t".join(str(r.get(c, "")) for c in cols))
    return "\n".join(lines) + "\n"


def test_load_results_converts_beats_baseline_string_true_to_bool():
    tsv = _make_sample_tsv([
        {
            "hypothesis_id": "H1", "hypothesis_name": "ATR-scaled step",
            "dimension": "A", "source_id": "bar_data_250vol_rot",
            "cycle_pf": "0.75", "delta_pf": "0.1", "total_pnl_ticks": "100",
            "delta_pnl": "10", "n_cycles": "100", "win_rate": "0.6",
            "sharpe": "0.5", "max_drawdown_ticks": "50",
            "avg_winner_ticks": "5", "avg_loser_ticks": "-3",
            "beats_baseline": "True", "feature_compute_sec": "0.1",
            "simulator_sec": "5.0", "total_sec": "5.1", "classification": "OK",
        },
    ])
    with tempfile.NamedTemporaryFile(mode="w", suffix=".tsv", delete=False) as f:
        f.write(tsv)
        path = f.name
    try:
        df = load_results(path)
        # beats_baseline may be numpy bool (np.True_) — check truthiness and equality
        assert df["beats_baseline"].iloc[0] == True  # noqa: E712
    finally:
        os.unlink(path)


def test_load_results_converts_beats_baseline_string_false_to_bool():
    tsv = _make_sample_tsv([
        {
            "hypothesis_id": "H1", "hypothesis_name": "ATR-scaled step",
            "dimension": "A", "source_id": "bar_data_250vol_rot",
            "cycle_pf": "0.75", "delta_pf": "0.0", "total_pnl_ticks": "100",
            "delta_pnl": "0", "n_cycles": "100", "win_rate": "0.6",
            "sharpe": "0.5", "max_drawdown_ticks": "50",
            "avg_winner_ticks": "5", "avg_loser_ticks": "-3",
            "beats_baseline": "False", "feature_compute_sec": "0.1",
            "simulator_sec": "5.0", "total_sec": "5.1", "classification": "OK",
        },
    ])
    with tempfile.NamedTemporaryFile(mode="w", suffix=".tsv", delete=False) as f:
        f.write(tsv)
        path = f.name
    try:
        df = load_results(path)
        assert df["beats_baseline"].iloc[0] is False or df["beats_baseline"].iloc[0] == False
    finally:
        os.unlink(path)


def test_load_results_aggregates_3_bar_types_per_hypothesis():
    """122 data rows (41 hypotheses x 3 bar types, minus H37/10sec skip) should produce 41 unique hypothesis_ids."""
    # Use the actual RTH results TSV
    tsv_path = _ARCHETYPE_DIR / "screening_results" / "phase1_results_rth.tsv"
    if not tsv_path.exists():
        pytest.skip("phase1_results_rth.tsv not available")
    df = load_results(str(tsv_path))
    unique_ids = df["hypothesis_id"].nunique()
    assert unique_ids == 41, f"Expected 41 unique hypothesis IDs, got {unique_ids}"


# ---------------------------------------------------------------------------
# H19 NOT_TESTED exclusion test
# ---------------------------------------------------------------------------

def test_h19_classified_as_skipped_reference_required_and_excluded_from_ranking():
    """H19 rows with classification=SKIPPED_REFERENCE_REQUIRED should produce NOT_TESTED advancement, excluded from ranking."""
    tsv = _make_sample_tsv([
        {
            "hypothesis_id": "H19", "hypothesis_name": "Bar-type divergence signal",
            "dimension": "E", "source_id": "bar_data_250vol_rot",
            "cycle_pf": "", "delta_pf": "", "total_pnl_ticks": "",
            "delta_pnl": "", "n_cycles": "", "win_rate": "",
            "sharpe": "", "max_drawdown_ticks": "",
            "avg_winner_ticks": "", "avg_loser_ticks": "",
            "beats_baseline": "", "feature_compute_sec": "0.0",
            "simulator_sec": "0.0", "total_sec": "0.0",
            "classification": "SKIPPED_REFERENCE_REQUIRED",
        },
        {
            "hypothesis_id": "H19", "hypothesis_name": "Bar-type divergence signal",
            "dimension": "E", "source_id": "bar_data_250tick_rot",
            "cycle_pf": "", "delta_pf": "", "total_pnl_ticks": "",
            "delta_pnl": "", "n_cycles": "", "win_rate": "",
            "sharpe": "", "max_drawdown_ticks": "",
            "avg_winner_ticks": "", "avg_loser_ticks": "",
            "beats_baseline": "", "feature_compute_sec": "0.0",
            "simulator_sec": "0.0", "total_sec": "0.0",
            "classification": "SKIPPED_REFERENCE_REQUIRED",
        },
        {
            "hypothesis_id": "H19", "hypothesis_name": "Bar-type divergence signal",
            "dimension": "E", "source_id": "bar_data_10sec_rot",
            "cycle_pf": "", "delta_pf": "", "total_pnl_ticks": "",
            "delta_pnl": "", "n_cycles": "", "win_rate": "",
            "sharpe": "", "max_drawdown_ticks": "",
            "avg_winner_ticks": "", "avg_loser_ticks": "",
            "beats_baseline": "", "feature_compute_sec": "0.0",
            "simulator_sec": "0.0", "total_sec": "0.0",
            "classification": "SKIPPED_REFERENCE_REQUIRED",
        },
    ])
    with tempfile.NamedTemporaryFile(mode="w", suffix=".tsv", delete=False) as f:
        f.write(tsv)
        path = f.name
    try:
        df = load_results(path)
        results = classify_all(df)
        assert len(results) == 1
        h19 = results[0]
        assert h19["hypothesis_id"] == "H19"
        assert h19["classification"] == "SKIPPED_REFERENCE_REQUIRED"
        assert h19["advancement_decision"] == "NOT_TESTED"
    finally:
        os.unlink(path)


# ---------------------------------------------------------------------------
# classify_all synthetic integration test
# ---------------------------------------------------------------------------

def test_classify_all_with_synthetic_results():
    """Verify classify_all correctly handles a multi-hypothesis synthetic DataFrame."""
    tsv = _make_sample_tsv([
        # H1: all 3 win -> ROBUST
        {"hypothesis_id": "H1", "hypothesis_name": "Test A", "dimension": "A",
         "source_id": "bar_data_250vol_rot", "cycle_pf": "0.8", "delta_pf": "0.1",
         "total_pnl_ticks": "100", "delta_pnl": "10", "n_cycles": "100",
         "win_rate": "0.6", "sharpe": "0.5", "max_drawdown_ticks": "50",
         "avg_winner_ticks": "5", "avg_loser_ticks": "-3",
         "beats_baseline": "True", "feature_compute_sec": "0.1",
         "simulator_sec": "5.0", "total_sec": "5.1", "classification": "OK"},
        {"hypothesis_id": "H1", "hypothesis_name": "Test A", "dimension": "A",
         "source_id": "bar_data_250tick_rot", "cycle_pf": "0.8", "delta_pf": "0.1",
         "total_pnl_ticks": "100", "delta_pnl": "10", "n_cycles": "100",
         "win_rate": "0.6", "sharpe": "0.5", "max_drawdown_ticks": "50",
         "avg_winner_ticks": "5", "avg_loser_ticks": "-3",
         "beats_baseline": "True", "feature_compute_sec": "0.1",
         "simulator_sec": "5.0", "total_sec": "5.1", "classification": "OK"},
        {"hypothesis_id": "H1", "hypothesis_name": "Test A", "dimension": "A",
         "source_id": "bar_data_10sec_rot", "cycle_pf": "0.8", "delta_pf": "0.1",
         "total_pnl_ticks": "100", "delta_pnl": "10", "n_cycles": "100",
         "win_rate": "0.6", "sharpe": "0.5", "max_drawdown_ticks": "50",
         "avg_winner_ticks": "5", "avg_loser_ticks": "-3",
         "beats_baseline": "True", "feature_compute_sec": "0.1",
         "simulator_sec": "5.0", "total_sec": "5.1", "classification": "OK"},
        # H2: vol+tick win, 10sec fail -> ACTIVITY_DEPENDENT
        {"hypothesis_id": "H2", "hypothesis_name": "Test B", "dimension": "B",
         "source_id": "bar_data_250vol_rot", "cycle_pf": "0.8", "delta_pf": "0.1",
         "total_pnl_ticks": "100", "delta_pnl": "10", "n_cycles": "100",
         "win_rate": "0.6", "sharpe": "0.5", "max_drawdown_ticks": "50",
         "avg_winner_ticks": "5", "avg_loser_ticks": "-3",
         "beats_baseline": "True", "feature_compute_sec": "0.1",
         "simulator_sec": "5.0", "total_sec": "5.1", "classification": "OK"},
        {"hypothesis_id": "H2", "hypothesis_name": "Test B", "dimension": "B",
         "source_id": "bar_data_250tick_rot", "cycle_pf": "0.8", "delta_pf": "0.1",
         "total_pnl_ticks": "100", "delta_pnl": "10", "n_cycles": "100",
         "win_rate": "0.6", "sharpe": "0.5", "max_drawdown_ticks": "50",
         "avg_winner_ticks": "5", "avg_loser_ticks": "-3",
         "beats_baseline": "True", "feature_compute_sec": "0.1",
         "simulator_sec": "5.0", "total_sec": "5.1", "classification": "OK"},
        {"hypothesis_id": "H2", "hypothesis_name": "Test B", "dimension": "B",
         "source_id": "bar_data_10sec_rot", "cycle_pf": "0.8", "delta_pf": "0.0",
         "total_pnl_ticks": "100", "delta_pnl": "0", "n_cycles": "100",
         "win_rate": "0.6", "sharpe": "0.5", "max_drawdown_ticks": "50",
         "avg_winner_ticks": "5", "avg_loser_ticks": "-3",
         "beats_baseline": "False", "feature_compute_sec": "0.1",
         "simulator_sec": "5.0", "total_sec": "5.1", "classification": "OK"},
    ])
    with tempfile.NamedTemporaryFile(mode="w", suffix=".tsv", delete=False) as f:
        f.write(tsv)
        path = f.name
    try:
        df = load_results(path)
        results = classify_all(df)
        by_id = {r["hypothesis_id"]: r for r in results}
        assert by_id["H1"]["classification"] == "ROBUST"
        assert by_id["H1"]["advancement_decision"] == "ADVANCE_HIGH"
        assert by_id["H2"]["classification"] == "ACTIVITY_DEPENDENT"
        assert by_id["H2"]["advancement_decision"] == "ADVANCE_FLAGGED"
    finally:
        os.unlink(path)
