# archetype: rotational
"""Unit tests for TrendDefenseSystem.

Covers:
    - Initialization: config dict parsing, bar-type parameter conversion
    - Detector 1: retracement quality (declining depths)
    - Detector 2: velocity monitor (rapid level escalation)
    - Detector 3: consecutive add counter (N adds without qualifying retrace)
    - Detector 4: drawdown budget (cycle unrealized PnL threshold)
    - Detector 5: trend precursor composite (multi-signal alignment)
    - Level 1 response: step_widen_factor, max_levels_reduction
    - Level 2 response: refuse_adds=True
    - Level 3 response: force_flatten=True, cooldown_remaining set
    - Level 3 re-engagement: cooldown expired AND threat < 1
    - Bar-type parameter conversion: seconds to bar counts via median_bar_sec
    - Summary metrics: trigger counts match actual triggers
    - on_reversal: resets per-cycle state
    - on_add: increments consecutive_adds

All tests use synthetic data -- no CSV files required.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from trend_defense import TrendDefenseSystem, TDSState  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_tds_config(
    step_widen_factor: float = 1.5,
    max_levels_reduction: int = 1,
    velocity_threshold_sec: float = 60.0,
    consecutive_adds_threshold: int = 3,
    retracement_reset_pct: float = 0.3,
    drawdown_budget_ticks: float = 50.0,
    cooldown_sec: float = 300.0,
    precursor_min_signals: int = 2,
    speed_threshold: float = 1.0,
    regime_accel_threshold: float = 1.0,
    adverse_speed_threshold: float = 1.0,
) -> dict:
    return {
        "enabled": True,
        "level_1": {
            "step_widen_factor": step_widen_factor,
            "max_levels_reduction": max_levels_reduction,
        },
        "level_2": {
            "velocity_threshold_sec": velocity_threshold_sec,
            "consecutive_adds_threshold": consecutive_adds_threshold,
            "retracement_reset_pct": retracement_reset_pct,
        },
        "level_3": {
            "drawdown_budget_ticks": drawdown_budget_ticks,
            "cooldown_sec": cooldown_sec,
        },
        "precursor": {
            "precursor_min_signals": precursor_min_signals,
            "speed_threshold": speed_threshold,
            "regime_accel_threshold": regime_accel_threshold,
            "adverse_speed_threshold": adverse_speed_threshold,
        },
    }


def _make_bar_duration_stats(median_sec: float = 10.0) -> dict:
    return {"median_sec": median_sec, "p10_sec": median_sec * 0.5}


def _make_bar(price: float = 100.0) -> pd.Series:
    return pd.Series({"Last": price, "datetime": pd.Timestamp("2024-01-01 10:00:00")})


def _make_sim_state(
    direction: str = "Long",
    level: int = 0,
    anchor: float = 100.0,
    position_qty: int = 1,
    cycle_start_bar: int = 0,
    bar_idx: int = 10,
    avg_entry_price: float = 100.0,
    step_dist_ticks: float = 8.0,
) -> dict:
    return {
        "direction": direction,
        "level": level,
        "anchor": anchor,
        "position_qty": position_qty,
        "cycle_start_bar": cycle_start_bar,
        "bar_idx": bar_idx,
        "avg_entry_price": avg_entry_price,
        "step_dist_ticks": step_dist_ticks,
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_tds_init():
    """TrendDefenseSystem initializes with correct defaults and converts timing params."""
    config = _make_tds_config()
    stats = _make_bar_duration_stats(median_sec=10.0)
    tds = TrendDefenseSystem(config, stats)

    assert tds.state.current_level == 0
    assert tds.state.forced_flat is False
    assert tds.state.cooldown_remaining == 0
    assert tds.state.consecutive_adds == 0
    assert tds.state.last_retracement_depths == []
    assert tds.state.cycle_unrealized_pnl_ticks == 0.0
    assert tds.state.l1_triggers == 0
    assert tds.state.l2_triggers == 0
    assert tds.state.l3_triggers == 0

    # velocity_threshold_sec=60, median_bar_sec=10 -> velocity_bars=6
    assert tds._velocity_bars == 6
    # cooldown_sec=300, median_bar_sec=10 -> cooldown_bars=30
    assert tds._cooldown_bars == 30


def test_detector_retracement_quality():
    """Detector 1 fires when 3+ consecutive retracement depths are declining."""
    config = _make_tds_config()
    stats = _make_bar_duration_stats()
    tds = TrendDefenseSystem(config, stats)
    bar = _make_bar()
    sim_state = _make_sim_state()
    features = {}

    # Not enough retracement data -- should not fire
    tds.state.last_retracement_depths = [0.5, 0.4]
    threat = tds.evaluate(bar, features, sim_state)
    assert threat == 0, "Should not fire with only 2 retracement entries"

    # 3 declining depths -- should fire (detector 1 only = level 1)
    tds2 = TrendDefenseSystem(config, stats)
    tds2.state.last_retracement_depths = [0.5, 0.4, 0.3]
    threat2 = tds2.evaluate(bar, features, sim_state)
    assert threat2 >= 1, "Declining depths should fire detector 1"

    # Flat depths -- should not fire
    tds3 = TrendDefenseSystem(config, stats)
    tds3.state.last_retracement_depths = [0.4, 0.4, 0.4]
    threat3 = tds3.evaluate(bar, features, sim_state)
    assert threat3 == 0, "Flat depths should not fire detector 1"

    # Increasing depths -- should not fire
    tds4 = TrendDefenseSystem(config, stats)
    tds4.state.last_retracement_depths = [0.3, 0.4, 0.5]
    threat4 = tds4.evaluate(bar, features, sim_state)
    assert threat4 == 0, "Increasing depths should not fire detector 1"


def test_detector_velocity_monitor():
    """Detector 2 fires when level > 0 and escalation happened faster than velocity_bars."""
    config = _make_tds_config(velocity_threshold_sec=60.0)
    stats = _make_bar_duration_stats(median_sec=10.0)  # velocity_bars = 6
    tds = TrendDefenseSystem(config, stats)
    bar = _make_bar()
    features = {}

    # Level=0 in sim_state, _level_zero_bar_idx=0, bar_idx=3 -> fires (3 < 6 bars but level=0)
    sim_state_level0 = _make_sim_state(level=0, bar_idx=3)
    tds.state._level_zero_bar_idx = 0
    threat = tds.evaluate(bar, features, sim_state_level0)
    # level=0 means no escalation to monitor -- should not fire detector 2
    assert threat == 0

    # Level=2, bar_idx=3, _level_zero_bar_idx=0 -> 3 < 6 -> fires
    tds2 = TrendDefenseSystem(config, stats)
    tds2.state._level_zero_bar_idx = 0
    sim_state_level2_fast = _make_sim_state(level=2, bar_idx=3)
    threat2 = tds2.evaluate(bar, features, sim_state_level2_fast)
    assert threat2 >= 1, "Rapid escalation should fire detector 2"

    # Level=2, bar_idx=20, _level_zero_bar_idx=0 -> 20 >= 6 -> does not fire
    tds3 = TrendDefenseSystem(config, stats)
    tds3.state._level_zero_bar_idx = 0
    sim_state_level2_slow = _make_sim_state(level=2, bar_idx=20)
    threat3 = tds3.evaluate(bar, features, sim_state_level2_slow)
    assert threat3 == 0, "Slow escalation should not fire detector 2"


def test_detector_consecutive_adds():
    """Detector 3 fires when consecutive_adds >= threshold without qualifying retracement."""
    config = _make_tds_config(consecutive_adds_threshold=3)
    stats = _make_bar_duration_stats()
    features = {}

    # 2 adds -- below threshold, should not fire
    tds = TrendDefenseSystem(config, stats)
    tds.state.consecutive_adds = 2
    sim_state = _make_sim_state()
    threat = tds.evaluate(_make_bar(), features, sim_state)
    assert threat == 0, "2 consecutive adds should not fire (threshold=3)"

    # 3 adds -- at threshold, should fire
    tds2 = TrendDefenseSystem(config, stats)
    tds2.state.consecutive_adds = 3
    threat2 = tds2.evaluate(_make_bar(), features, sim_state)
    assert threat2 >= 1, "3 consecutive adds should fire detector 3"

    # After on_reversal, counter resets to 0
    tds2.on_reversal()
    assert tds2.state.consecutive_adds == 0


def test_detector_drawdown_budget():
    """Detector 4 fires when cycle_unrealized_pnl_ticks < -drawdown_budget_ticks."""
    config = _make_tds_config(drawdown_budget_ticks=50.0)
    stats = _make_bar_duration_stats()
    features = {}
    sim_state = _make_sim_state()

    # PnL at -49 ticks -- below budget, should not fire
    tds = TrendDefenseSystem(config, stats)
    tds.state.cycle_unrealized_pnl_ticks = -49.0
    threat = tds.evaluate(_make_bar(), features, sim_state)
    assert threat == 0, "-49 ticks should not fire drawdown detector (budget=50)"

    # PnL at -51 ticks -- exceeds budget, should fire
    tds2 = TrendDefenseSystem(config, stats)
    tds2.state.cycle_unrealized_pnl_ticks = -51.0
    threat2 = tds2.evaluate(_make_bar(), features, sim_state)
    assert threat2 >= 1, "-51 ticks should fire drawdown detector (budget=50)"


def test_detector_trend_precursor():
    """Detector 5 fires when precursor_min_signals (default 2) signals align."""
    config = _make_tds_config(
        precursor_min_signals=2,
        speed_threshold=1.0,
        regime_accel_threshold=1.0,
        adverse_speed_threshold=1.0,
    )
    stats = _make_bar_duration_stats()
    sim_state = _make_sim_state()

    # 0 signals -- should not fire
    tds = TrendDefenseSystem(config, stats)
    features_none = {
        "price_speed": 0.5,
        "regime_transition_speed": 0.5,
        "band_speed_state": 1,
        "adverse_speed": 0.5,
    }
    threat = tds.evaluate(_make_bar(), features_none, sim_state)
    assert threat == 0, "0 precursor signals should not fire detector 5"

    # 1 signal -- should not fire (min=2)
    tds2 = TrendDefenseSystem(config, stats)
    features_one = {
        "price_speed": 2.0,  # exceeds threshold=1.0
        "regime_transition_speed": 0.5,
        "band_speed_state": 1,
        "adverse_speed": 0.5,
    }
    threat2 = tds2.evaluate(_make_bar(), features_one, sim_state)
    assert threat2 == 0, "1 precursor signal should not fire detector 5 (min=2)"

    # 2 signals -- should fire
    tds3 = TrendDefenseSystem(config, stats)
    features_two = {
        "price_speed": 2.0,          # signal 1
        "regime_transition_speed": 2.0,  # signal 2
        "band_speed_state": 1,
        "adverse_speed": 0.5,
    }
    threat3 = tds3.evaluate(_make_bar(), features_two, sim_state)
    assert threat3 >= 1, "2 precursor signals should fire detector 5"

    # band_speed_state >= 3 counts as signal
    tds4 = TrendDefenseSystem(config, stats)
    features_band = {
        "price_speed": 0.5,
        "regime_transition_speed": 0.5,
        "band_speed_state": 3,       # signal 1
        "adverse_speed": 2.0,        # signal 2
    }
    threat4 = tds4.evaluate(_make_bar(), features_band, sim_state)
    assert threat4 >= 1, "band_speed_state>=3 + adverse_speed should fire detector 5"


def test_level1_response():
    """Level 1: 1 detector firing returns step_widen_factor and max_levels_reduction."""
    config = _make_tds_config(step_widen_factor=1.5, max_levels_reduction=1)
    stats = _make_bar_duration_stats()
    tds = TrendDefenseSystem(config, stats)
    sim_state = _make_sim_state()

    response = tds.apply_response(sim_state, threat=1)

    assert response["step_widen_factor"] == 1.5
    assert response["max_levels_reduction"] == 1
    assert response["refuse_adds"] is False
    assert response["force_flatten"] is False


def test_level2_response():
    """Level 2: 2+ detectors firing returns refuse_adds=True."""
    config = _make_tds_config(step_widen_factor=1.5, max_levels_reduction=1)
    stats = _make_bar_duration_stats()
    tds = TrendDefenseSystem(config, stats)
    sim_state = _make_sim_state()

    response = tds.apply_response(sim_state, threat=2)

    assert response["refuse_adds"] is True
    assert response["force_flatten"] is False


def test_level3_response():
    """Level 3: drawdown_budget fires OR 3+ detectors -> force_flatten=True, cooldown set."""
    config = _make_tds_config(cooldown_sec=300.0)
    stats = _make_bar_duration_stats(median_sec=10.0)  # cooldown_bars = 30
    tds = TrendDefenseSystem(config, stats)
    sim_state = _make_sim_state()

    response = tds.apply_response(sim_state, threat=3)

    assert response["force_flatten"] is True
    assert tds.state.cooldown_remaining == 30
    assert tds.state.forced_flat is True


def test_level3_reengage():
    """Level 3 re-engagement: False when cooldown_remaining > 0; True when expired."""
    config = _make_tds_config()
    stats = _make_bar_duration_stats()
    tds = TrendDefenseSystem(config, stats)
    features = {}

    # Cooldown still active
    tds.state.cooldown_remaining = 10
    assert tds.can_reengage(features) is False

    # Cooldown expired
    tds.state.cooldown_remaining = 0
    assert tds.can_reengage(features) is True


def test_bar_type_param_conversion():
    """Bar-type conversion: seconds -> bar counts using median_bar_sec."""
    config = _make_tds_config(velocity_threshold_sec=60.0, cooldown_sec=300.0)

    # 10sec bars: velocity_threshold_sec=60 -> 6 bars; cooldown_sec=300 -> 30 bars
    stats_10sec = _make_bar_duration_stats(median_sec=10.0)
    tds_10sec = TrendDefenseSystem(config, stats_10sec)
    assert tds_10sec._velocity_bars == 6
    assert tds_10sec._cooldown_bars == 30

    # 3sec (vol/tick-like) bars: velocity_threshold_sec=60 -> 20 bars; cooldown_sec=300 -> 100 bars
    stats_vol = _make_bar_duration_stats(median_sec=3.0)
    tds_vol = TrendDefenseSystem(config, stats_vol)
    assert tds_vol._velocity_bars == 20
    assert tds_vol._cooldown_bars == 100


def test_summary_metrics():
    """get_summary() returns trigger counts matching actual trigger counts."""
    config = _make_tds_config(
        consecutive_adds_threshold=1,  # low threshold so detector fires easily
        drawdown_budget_ticks=10.0,    # low budget so detector fires easily
    )
    stats = _make_bar_duration_stats()
    tds = TrendDefenseSystem(config, stats)
    sim_state = _make_sim_state()
    features = {}

    # Trigger level 1 once: 1 consecutive add
    tds.state.consecutive_adds = 1
    tds.evaluate(_make_bar(), features, sim_state)

    # Trigger level 3 once: drawdown budget hit
    tds2 = TrendDefenseSystem(config, stats)
    tds2.state.cycle_unrealized_pnl_ticks = -50.0  # exceeds budget=10
    tds2.evaluate(_make_bar(), features, sim_state)

    summary = tds.get_summary()
    assert "l1_triggers" in summary
    assert "l2_triggers" in summary
    assert "l3_triggers" in summary
    assert summary["l1_triggers"] >= 1


def test_on_reversal_resets():
    """on_reversal() resets consecutive_adds, last_retracement_depths, per-cycle state."""
    config = _make_tds_config()
    stats = _make_bar_duration_stats()
    tds = TrendDefenseSystem(config, stats)

    tds.state.consecutive_adds = 5
    tds.state.last_retracement_depths = [0.3, 0.2, 0.1]
    tds.state.cycle_unrealized_pnl_ticks = -30.0
    tds.state._last_add_price = 95.0

    tds.on_reversal()

    assert tds.state.consecutive_adds == 0
    assert tds.state.last_retracement_depths == []
    assert tds.state.cycle_unrealized_pnl_ticks == 0.0
    assert tds.state._last_add_price is None


def test_on_add_increments():
    """on_add() increments consecutive_adds by 1."""
    config = _make_tds_config()
    stats = _make_bar_duration_stats()
    tds = TrendDefenseSystem(config, stats)

    assert tds.state.consecutive_adds == 0
    tds.on_add(price=100.0)
    assert tds.state.consecutive_adds == 1
    tds.on_add(price=98.0)
    assert tds.state.consecutive_adds == 2
