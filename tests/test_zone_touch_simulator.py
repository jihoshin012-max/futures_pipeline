# tests/test_zone_touch_simulator.py
"""Unit tests for zone_touch_simulator.run() pure function.

All tests use synthetic bar data with known OHLC progressions.
No I/O — simulator must be a pure function (no file reads, no prints, no global state).
"""

import sys
from pathlib import Path
import pandas as pd
import pytest

# Add repo root to sys.path so imports resolve
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
# Add archetype dir so the simulator module is importable
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "shared/archetypes/zone_touch"))

from zone_touch_simulator import run, SimResult  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_config(stop_ticks=100, leg_targets=None, trail_steps=None, time_cap_bars=20,
                tick_size=0.25, mode="M1", active_modes=None):
    """Build a minimal config dict for tests."""
    if leg_targets is None:
        leg_targets = [50]
    if trail_steps is None:
        trail_steps = []
    if active_modes is None:
        active_modes = [mode]
    return {
        "instrument": "NQ",
        "active_modes": active_modes,
        "tick_size": tick_size,
        mode: {
            "stop_ticks": stop_ticks,
            "leg_targets": leg_targets,
            "trail_steps": trail_steps,
            "time_cap_bars": time_cap_bars,
        },
    }


def make_touch(entry_price=16000.0, direction=1, mode="M1"):
    """Build a synthetic touch row (pd.Series) with required columns."""
    return pd.Series({
        "TouchPrice": entry_price,
        "ApproachDir": direction,   # 1 = Long, -1 = Short
        "mode": mode,
    })


def make_bars_move_against(entry_price=16000.0, direction=1, n_bars=5, tick_size=0.25,
                            adverse_ticks=120):
    """Bars that steadily move against the entry — triggers stop."""
    rows = []
    for i in range(n_bars):
        # For LONG: bars move down (High near entry, Low drops)
        # For SHORT: bars move up (Low near entry, High rises)
        if direction == 1:  # Long
            low = entry_price - (i + 1) * adverse_ticks / n_bars * tick_size
            rows.append({
                "Open": entry_price,
                "High": entry_price + 1 * tick_size,
                "Low": low,
                "Last": low + 1 * tick_size,
            })
        else:  # Short
            high = entry_price + (i + 1) * adverse_ticks / n_bars * tick_size
            rows.append({
                "Open": entry_price,
                "High": high,
                "Low": entry_price - 1 * tick_size,
                "Last": high - 1 * tick_size,
            })
    return pd.DataFrame(rows)


def make_bars_move_favorable(entry_price=16000.0, direction=1, n_bars=5, tick_size=0.25,
                              favorable_ticks=60):
    """Bars that steadily move in the favorable direction — hits target."""
    rows = []
    for i in range(n_bars):
        if direction == 1:  # Long: price rises
            high = entry_price + (i + 1) * favorable_ticks / n_bars * tick_size
            rows.append({
                "Open": entry_price,
                "High": high,
                "Low": entry_price - 1 * tick_size,
                "Last": high - 1 * tick_size,
            })
        else:  # Short: price falls
            low = entry_price - (i + 1) * favorable_ticks / n_bars * tick_size
            rows.append({
                "Open": entry_price,
                "High": entry_price + 1 * tick_size,
                "Low": low,
                "Last": low + 1 * tick_size,
            })
    return pd.DataFrame(rows)


def make_bars_mfe_then_adverse(entry_price=16000.0, direction=1, tick_size=0.25,
                                mfe_ticks=35, then_adverse_ticks=110):
    """
    Bars: first bar reaches mfe_ticks favorable, then second bar goes adverse.
    Used to test BE trigger and subsequent stop hit.
    """
    if direction == 1:
        # Bar 0: MFE bar — goes up to mfe_ticks then comes back
        bar0 = {
            "Open": entry_price,
            "High": entry_price + mfe_ticks * tick_size,
            "Low": entry_price - 2 * tick_size,
            "Last": entry_price,
        }
        # Bar 1: Adverse — drops to adverse_ticks below entry (hits BE stop if triggered)
        bar1 = {
            "Open": entry_price,
            "High": entry_price + 2 * tick_size,
            "Low": entry_price - then_adverse_ticks * tick_size,
            "Last": entry_price - then_adverse_ticks * tick_size,
        }
    else:
        bar0 = {
            "Open": entry_price,
            "High": entry_price + 2 * tick_size,
            "Low": entry_price - mfe_ticks * tick_size,
            "Last": entry_price,
        }
        bar1 = {
            "Open": entry_price,
            "High": entry_price + then_adverse_ticks * tick_size,
            "Low": entry_price - 2 * tick_size,
            "Last": entry_price + then_adverse_ticks * tick_size,
        }
    return pd.DataFrame([bar0, bar1])


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestStopHit:
    """Test that bars moving adversely trigger the stop."""

    def test_stop_hit_long(self):
        """Long trade: bars drop 100 ticks — stop at 100 ticks fires."""
        tick_size = 0.25
        stop_ticks = 100
        entry = 16000.0
        config = make_config(stop_ticks=stop_ticks, leg_targets=[200], trail_steps=[],
                             time_cap_bars=20, tick_size=tick_size)
        touch = make_touch(entry_price=entry, direction=1)
        bar_df = make_bars_move_against(entry_price=entry, direction=1, n_bars=5,
                                        tick_size=tick_size, adverse_ticks=stop_ticks)
        result = run(bar_df, touch, config, bar_offset=0)

        assert isinstance(result, SimResult)
        assert result.win is False
        assert result.exit_reason == "stop"
        assert result.pnl_ticks == pytest.approx(-stop_ticks, abs=1)
        assert result.bars_held >= 1

    def test_stop_hit_short(self):
        """Short trade: bars rise 100 ticks — stop at 100 ticks fires."""
        tick_size = 0.25
        stop_ticks = 100
        entry = 16000.0
        config = make_config(stop_ticks=stop_ticks, leg_targets=[200], trail_steps=[],
                             time_cap_bars=20, tick_size=tick_size)
        touch = make_touch(entry_price=entry, direction=-1)
        bar_df = make_bars_move_against(entry_price=entry, direction=-1, n_bars=5,
                                        tick_size=tick_size, adverse_ticks=stop_ticks)
        result = run(bar_df, touch, config, bar_offset=0)

        assert result.win is False
        assert result.exit_reason == "stop"
        assert result.pnl_ticks == pytest.approx(-stop_ticks, abs=1)


class TestTargetHit:
    """Test that bars moving favorably hit the first leg_target."""

    def test_target_1_hit_long(self):
        """Long trade: bars rise 50 ticks — hits first target at 50 ticks."""
        tick_size = 0.25
        target_ticks = 50
        entry = 16000.0
        config = make_config(stop_ticks=100, leg_targets=[target_ticks], trail_steps=[],
                             time_cap_bars=20, tick_size=tick_size)
        touch = make_touch(entry_price=entry, direction=1)
        bar_df = make_bars_move_favorable(entry_price=entry, direction=1, n_bars=5,
                                          tick_size=tick_size, favorable_ticks=target_ticks)
        result = run(bar_df, touch, config, bar_offset=0)

        assert result.win is True
        assert result.exit_reason == "target_1"
        assert result.pnl_ticks == pytest.approx(target_ticks, abs=1)
        assert result.bars_held >= 1

    def test_target_1_hit_short(self):
        """Short trade: bars fall 50 ticks — hits first target at 50 ticks."""
        tick_size = 0.25
        target_ticks = 50
        entry = 16000.0
        config = make_config(stop_ticks=100, leg_targets=[target_ticks], trail_steps=[],
                             time_cap_bars=20, tick_size=tick_size)
        touch = make_touch(entry_price=entry, direction=-1)
        bar_df = make_bars_move_favorable(entry_price=entry, direction=-1, n_bars=5,
                                          tick_size=tick_size, favorable_ticks=target_ticks)
        result = run(bar_df, touch, config, bar_offset=0)

        assert result.win is True
        assert result.exit_reason == "target_1"
        assert result.pnl_ticks == pytest.approx(target_ticks, abs=1)


class TestBETrigger:
    """Test breakeven trigger: trail_steps[0] with new_stop_ticks=0."""

    def test_be_trigger_long_then_stop_at_entry(self):
        """
        Long: MFE reaches 35 (>= trigger 30), BE fires (stop moves to entry=0 risk).
        Then price drops past entry — exits at 0 pnl (breakeven).
        """
        tick_size = 0.25
        entry = 16000.0
        trail_steps = [{"trigger_ticks": 30, "new_stop_ticks": 0}]
        config = make_config(stop_ticks=100, leg_targets=[200], trail_steps=trail_steps,
                             time_cap_bars=20, tick_size=tick_size)
        touch = make_touch(entry_price=entry, direction=1)
        # Bar 0: MFE goes to 35 ticks. Bar 1: drops 110 ticks below entry (triggers BE stop at 0)
        bar_df = make_bars_mfe_then_adverse(entry_price=entry, direction=1, tick_size=tick_size,
                                             mfe_ticks=35, then_adverse_ticks=110)
        result = run(bar_df, touch, config, bar_offset=0)

        assert result.exit_reason == "stop"
        assert result.pnl_ticks == pytest.approx(0.0, abs=1)  # stopped at breakeven
        assert result.bars_held >= 1

    def test_be_trigger_short_then_stop_at_entry(self):
        """
        Short: MFE reaches 35 (>= trigger 30), BE fires, then price rises past entry.
        """
        tick_size = 0.25
        entry = 16000.0
        trail_steps = [{"trigger_ticks": 30, "new_stop_ticks": 0}]
        config = make_config(stop_ticks=100, leg_targets=[200], trail_steps=trail_steps,
                             time_cap_bars=20, tick_size=tick_size)
        touch = make_touch(entry_price=entry, direction=-1)
        bar_df = make_bars_mfe_then_adverse(entry_price=entry, direction=-1, tick_size=tick_size,
                                             mfe_ticks=35, then_adverse_ticks=110)
        result = run(bar_df, touch, config, bar_offset=0)

        assert result.exit_reason == "stop"
        assert result.pnl_ticks == pytest.approx(0.0, abs=1)


class TestTrailRatchet:
    """Test that multi-step trail ratchets stop progressively."""

    def test_trail_ratchet_long(self):
        """
        Long: MFE reaches 70 ticks (triggers trail_steps[1] at 60, new_stop=20).
        Then price drops back to 15 ticks favorable — stop at 20 fires.
        Exit pnl should be approximately +20 ticks (stopped at ratcheted stop).
        """
        tick_size = 0.25
        entry = 16000.0
        trail_steps = [
            {"trigger_ticks": 30, "new_stop_ticks": 0},
            {"trigger_ticks": 60, "new_stop_ticks": 20},
        ]
        config = make_config(stop_ticks=100, leg_targets=[200], trail_steps=trail_steps,
                             time_cap_bars=20, tick_size=tick_size)
        touch = make_touch(entry_price=entry, direction=1)

        # Bar 0: High goes to entry + 70 ticks (triggers both trail steps)
        # Bar 1: Low drops to entry + 15 ticks (below new_stop of 20, above entry)
        bar0 = {
            "Open": entry,
            "High": entry + 70 * tick_size,
            "Low": entry - 1 * tick_size,
            "Last": entry + 5 * tick_size,
        }
        bar1 = {
            "Open": entry + 5 * tick_size,
            "High": entry + 22 * tick_size,
            "Low": entry + 15 * tick_size,  # 15 ticks above entry, below new_stop=20
            "Last": entry + 16 * tick_size,
        }
        bar_df = pd.DataFrame([bar0, bar1])
        result = run(bar_df, touch, config, bar_offset=0)

        assert result.exit_reason == "stop"
        assert result.pnl_ticks == pytest.approx(20.0, abs=2)  # ratcheted stop fires at +20


class TestTimeCap:
    """Test that trades exiting at time_cap use last bar's close price."""

    def test_time_cap_exit(self):
        """
        No target or stop reached within time_cap_bars — exit at market (Last price).
        """
        tick_size = 0.25
        entry = 16000.0
        last_price = entry + 10 * tick_size  # 10 ticks favorable at close
        config = make_config(stop_ticks=500, leg_targets=[2000], trail_steps=[],
                             time_cap_bars=3, tick_size=tick_size)
        touch = make_touch(entry_price=entry, direction=1)

        # 3 bars all well within stop, none reach target
        bars = []
        for _ in range(3):
            bars.append({
                "Open": entry,
                "High": entry + 20 * tick_size,
                "Low": entry - 20 * tick_size,
                "Last": last_price,
            })
        bar_df = pd.DataFrame(bars)
        result = run(bar_df, touch, config, bar_offset=0)

        assert result.exit_reason == "time_cap"
        assert result.bars_held == 3
        assert result.pnl_ticks == pytest.approx(10.0, abs=1)

    def test_time_cap_exit_short(self):
        """Short: time cap with price below entry — should be a win."""
        tick_size = 0.25
        entry = 16000.0
        last_price = entry - 10 * tick_size  # 10 ticks favorable for short
        config = make_config(stop_ticks=500, leg_targets=[2000], trail_steps=[],
                             time_cap_bars=3, tick_size=tick_size)
        touch = make_touch(entry_price=entry, direction=-1)

        bars = []
        for _ in range(3):
            bars.append({
                "Open": entry,
                "High": entry + 20 * tick_size,
                "Low": entry - 20 * tick_size,
                "Last": last_price,
            })
        bar_df = pd.DataFrame(bars)
        result = run(bar_df, touch, config, bar_offset=0)

        assert result.exit_reason == "time_cap"
        assert result.pnl_ticks == pytest.approx(10.0, abs=1)


class TestDeterminism:
    """Simulator must be deterministic — same inputs produce identical output."""

    def test_determinism(self):
        """Run same inputs twice, compare all SimResult fields."""
        tick_size = 0.25
        entry = 16000.0
        trail_steps = [
            {"trigger_ticks": 30, "new_stop_ticks": 0},
            {"trigger_ticks": 60, "new_stop_ticks": 20},
        ]
        config = make_config(stop_ticks=100, leg_targets=[50, 120], trail_steps=trail_steps,
                             time_cap_bars=10, tick_size=tick_size)
        touch = make_touch(entry_price=entry, direction=1)
        bar_df = make_bars_move_favorable(entry_price=entry, direction=1, n_bars=10,
                                          tick_size=tick_size, favorable_ticks=55)

        result1 = run(bar_df, touch, config, bar_offset=0)
        result2 = run(bar_df, touch, config, bar_offset=0)

        assert result1.pnl_ticks == result2.pnl_ticks
        assert result1.win == result2.win
        assert result1.exit_reason == result2.exit_reason
        assert result1.bars_held == result2.bars_held


class TestPureFunction:
    """Simulator must not mutate inputs or have side effects."""

    def test_does_not_mutate_touch(self):
        """touch_row should be unchanged after run()."""
        config = make_config()
        touch = make_touch()
        original_price = touch["TouchPrice"]
        bar_df = make_bars_move_against()
        run(bar_df, touch, config, bar_offset=0)
        assert touch["TouchPrice"] == original_price

    def test_does_not_mutate_bar_df(self):
        """bar_df should be unchanged after run()."""
        config = make_config()
        touch = make_touch()
        bar_df = make_bars_move_against()
        original_cols = list(bar_df.columns)
        original_len = len(bar_df)
        run(bar_df, touch, config, bar_offset=0)
        assert list(bar_df.columns) == original_cols
        assert len(bar_df) == original_len

    def test_returns_simresult_type(self):
        """run() must return a SimResult instance."""
        config = make_config()
        touch = make_touch()
        bar_df = make_bars_move_against()
        result = run(bar_df, touch, config, bar_offset=0)
        assert isinstance(result, SimResult)
