# archetype: rotational
"""Unit tests for the frozen-anchor rotation simulator.

Tests verify:
1. Frozen anchor invariant (anchor never changes on adds)
2. Failure exit at -StepDist from anchor
3. Success exit at +ReversalTarget*StepDist from anchor
4. Priority order: SUCCESS > FAILURE > ADD
5. Successive add spacing from frozen anchor
6. MaxAdds=0 pure rotation
7. ReversalTarget < 1.0
8. progress_hwm tracking
9. cycle_day_seq tracking
10. Asymmetric PnL structure
11. Cost model
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Add parent dir to path for imports
_PARENT = str(Path(__file__).resolve().parent.parent)
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

from config_schema import FrozenAnchorConfig
from rotation_simulator import run_frozen_anchor_simulation


def _make_bars(prices: list[float], base_date: str = "2026-01-05") -> pd.DataFrame:
    """Create synthetic tick-bar DataFrame from a price list.

    All bars have O=H=L=Last (tick data format). Timestamps are synthetic
    RTH times starting at 09:30:00 on the given date (default Monday).
    """
    n = len(prices)
    base_dt = pd.Timestamp(f"{base_date} 09:30:00")
    dts = [base_dt + pd.Timedelta(seconds=i) for i in range(n)]
    return pd.DataFrame({
        "Open": prices,
        "High": prices,
        "Low": prices,
        "Last": prices,
        "datetime": dts,
    })


def _make_multiday_bars(day_prices: list[list[float]],
                        start_date: str = "2026-01-05") -> pd.DataFrame:
    """Create multi-day synthetic bars. Each inner list is one day's prices."""
    all_prices = []
    all_dts = []
    base = pd.Timestamp(start_date)
    for day_idx, prices in enumerate(day_prices):
        day_base = base + pd.Timedelta(days=day_idx)
        # Skip weekends
        while day_base.weekday() >= 5:
            day_base += pd.Timedelta(days=1)
        day_start = day_base.replace(hour=9, minute=30, second=0)
        for j, p in enumerate(prices):
            all_prices.append(p)
            all_dts.append(day_start + pd.Timedelta(seconds=j))
    return pd.DataFrame({
        "Open": all_prices,
        "High": all_prices,
        "Low": all_prices,
        "Last": all_prices,
        "datetime": all_dts,
    })


# =========================================================================
# Config validation
# =========================================================================

class TestFrozenAnchorConfigValidation:
    def test_valid_config(self):
        cfg = FrozenAnchorConfig(
            config_id="FA_TEST", step_dist=25.0, add_dist=10.0,
            max_adds=2, reversal_target=1.0
        )
        assert cfg.step_dist == 25.0
        assert cfg.add_size == 1

    def test_rejects_zero_step_dist(self):
        with pytest.raises(ValueError, match="step_dist must be > 0"):
            FrozenAnchorConfig(config_id="X", step_dist=0.0, add_dist=10.0,
                               max_adds=0, reversal_target=1.0)

    def test_rejects_zero_add_dist(self):
        with pytest.raises(ValueError, match="add_dist must be > 0"):
            FrozenAnchorConfig(config_id="X", step_dist=25.0, add_dist=0.0,
                               max_adds=0, reversal_target=1.0)

    def test_rejects_negative_max_adds(self):
        with pytest.raises(ValueError, match="max_adds must be >= 0"):
            FrozenAnchorConfig(config_id="X", step_dist=25.0, add_dist=10.0,
                               max_adds=-1, reversal_target=1.0)

    def test_rejects_reversal_target_zero(self):
        with pytest.raises(ValueError, match="reversal_target must be in"):
            FrozenAnchorConfig(config_id="X", step_dist=25.0, add_dist=10.0,
                               max_adds=0, reversal_target=0.0)

    def test_rejects_reversal_target_above_1(self):
        with pytest.raises(ValueError, match="reversal_target must be in"):
            FrozenAnchorConfig(config_id="X", step_dist=25.0, add_dist=10.0,
                               max_adds=0, reversal_target=1.5)

    def test_rejects_add_size_not_1(self):
        with pytest.raises(ValueError, match="add_size must be 1"):
            FrozenAnchorConfig(config_id="X", step_dist=25.0, add_dist=10.0,
                               max_adds=0, reversal_target=1.0, add_size=2)


# =========================================================================
# Test 1: Frozen anchor — anchor does not change on adds
# =========================================================================

class TestFrozenAnchor:
    def test_anchor_unchanged_after_add(self):
        """After adverse add, verify AnchorPrice unchanged in trade log.
        After success exit, verify AnchorPrice updates to new entry."""
        # Seed Long at 125, anchor=125. Drop 10 → add at 115. Anchor stays 125.
        # Then price rises to 125+25=150 (success at SD=25, RT=1.0)
        # New anchor at 150.
        prices = [100.0]
        prices += [100.0 + i * 0.5 for i in range(1, 51)]  # seed Long at 125
        prices += [125.0 - i * 0.5 for i in range(1, 21)]  # drop to 115 → add
        prices += [115.0 + i * 0.5 for i in range(1, 71)]  # up to 150 → success

        bars = _make_bars(prices)
        cfg = FrozenAnchorConfig(
            config_id="FA_ANCHOR", step_dist=25.0, add_dist=10.0,
            max_adds=2, reversal_target=1.0, cost_ticks=0.0
        )
        result = run_frozen_anchor_simulation(cfg, bars)

        # Check add trade has anchor = 125 (frozen, not 115)
        adds = result.trades[result.trades["action"] == "ADD"]
        assert len(adds) >= 1
        assert abs(adds.iloc[0]["anchor"] - 125.0) < 1.0

        # Check reversal trade has new anchor at exit price (~150)
        reversals = result.trades[result.trades["action"] == "REVERSAL"]
        if len(reversals) > 0:
            assert abs(reversals.iloc[0]["anchor"] - 150.0) < 1.0


# =========================================================================
# Test 2: Failure exit fires
# =========================================================================

class TestFailureExit:
    def test_failure_exit_at_minus_step_dist(self):
        """Price moves -StepDist from anchor → flatten + re-seed opposite.
        Verify exit_type=FAILURE."""
        # Seed Long at 125, drop 25 to 100 → failure
        prices = [100.0]
        prices += [100.0 + i * 0.5 for i in range(1, 51)]  # seed at 125
        prices += [125.0 - i * 0.5 for i in range(1, 51)]  # drop to 100

        bars = _make_bars(prices)
        cfg = FrozenAnchorConfig(
            config_id="FA_FAIL", step_dist=25.0, add_dist=10.0,
            max_adds=0, reversal_target=1.0, cost_ticks=0.0
        )
        result = run_frozen_anchor_simulation(cfg, bars)

        assert len(result.cycles) >= 1
        cycle0 = result.cycles.iloc[0]
        assert cycle0["exit_type"] == "FAILURE"
        assert cycle0["side"] == "LONG"
        assert cycle0["pnl_ticks_gross"] < 0


# =========================================================================
# Test 3: Success exit fires
# =========================================================================

class TestSuccessExit:
    def test_success_exit_at_plus_rt_sd(self):
        """Price moves +RT*SD from anchor → flatten + re-seed opposite.
        Verify exit_type=SUCCESS."""
        # Seed Long at 125, RT=1.0, SD=25 → success at 150
        prices = [100.0]
        prices += [100.0 + i * 0.5 for i in range(1, 51)]  # seed at 125
        prices += [125.0 + i * 0.5 for i in range(1, 51)]  # up to 150

        bars = _make_bars(prices)
        cfg = FrozenAnchorConfig(
            config_id="FA_SUCCESS", step_dist=25.0, add_dist=10.0,
            max_adds=0, reversal_target=1.0, cost_ticks=0.0
        )
        result = run_frozen_anchor_simulation(cfg, bars)

        assert len(result.cycles) >= 1
        cycle0 = result.cycles.iloc[0]
        assert cycle0["exit_type"] == "SUCCESS"
        assert cycle0["side"] == "LONG"
        assert cycle0["pnl_ticks_gross"] > 0


# =========================================================================
# Test 4: Priority order — failure beats add
# =========================================================================

class TestPriorityOrder:
    def test_failure_beats_add_on_same_bar(self):
        """Price crosses both add threshold AND failure threshold → FAILURE fires.

        With SD=40, AD=10, MaxAdds=3: adds at -10, -20, -30 from anchor.
        Failure at -40. If price jumps from -9 to -42 in one bar, both
        add1 (-10) and failure (-40) qualify. Failure wins."""
        # Seed Long at 140, then jump to 98 (drop of 42 > SD=40)
        prices = [100.0]
        prices += [100.0 + i * 0.5 for i in range(1, 81)]  # seed at 140
        prices.append(98.0)  # single bar drop past failure

        bars = _make_bars(prices)
        cfg = FrozenAnchorConfig(
            config_id="FA_PRIO", step_dist=40.0, add_dist=10.0,
            max_adds=3, reversal_target=1.0, cost_ticks=0.0
        )
        result = run_frozen_anchor_simulation(cfg, bars)

        assert len(result.cycles) >= 1
        cycle0 = result.cycles.iloc[0]
        assert cycle0["exit_type"] == "FAILURE"
        assert cycle0["add_count"] == 0  # no adds fired — failure took priority


# =========================================================================
# Test 5: Successive add spacing from frozen anchor
# =========================================================================

class TestAddSpacing:
    def test_adds_at_multiples_from_frozen_anchor(self):
        """With SD=40, AD=10, MaxAdds=3: adds fire at -10, -20, -30 from anchor.
        Not at -10 from last add. Failure at -40."""
        # Seed Long at 140. Adds at 130, 120, 110. Failure at 100.
        prices = [100.0]
        prices += [100.0 + i * 0.5 for i in range(1, 81)]  # seed at 140
        # Gradual drop to trigger adds one by one
        prices += [140.0 - i * 0.25 for i in range(1, 161)]  # drop 40 pts over 160 bars

        bars = _make_bars(prices)
        cfg = FrozenAnchorConfig(
            config_id="FA_ADDS", step_dist=40.0, add_dist=10.0,
            max_adds=3, reversal_target=1.0, cost_ticks=0.0
        )
        result = run_frozen_anchor_simulation(cfg, bars)

        # Should have 3 adds before failure
        assert len(result.cycles) >= 1
        cycle0 = result.cycles.iloc[0]
        assert cycle0["exit_type"] == "FAILURE"
        assert cycle0["add_count"] == 3

        # Check add prices are at -10, -20, -30 from anchor (140)
        adds = result.trades[
            (result.trades["action"] == "ADD") &
            (result.trades["cycle_id"] == cycle0["cycle_id"])
        ]
        assert len(adds) == 3
        assert abs(adds.iloc[0]["price"] - 130.0) < 0.5
        assert abs(adds.iloc[1]["price"] - 120.0) < 0.5
        assert abs(adds.iloc[2]["price"] - 110.0) < 0.5

        # All adds should have anchor=140 (frozen)
        for _, add_row in adds.iterrows():
            assert abs(add_row["anchor"] - 140.0) < 0.5


# =========================================================================
# Test 6: MaxAdds=0 — pure rotation with symmetric exits
# =========================================================================

class TestMaxAddsZero:
    def test_no_adds_only_exits(self):
        """MaxAdds=0: no adds, just success/failure exits. Position always 1."""
        # Seed Long at 125, success at 150.
        # Re-seed Short at 150, price goes UP to 175 → FAILURE for Short
        # (price moved +25 against Short position = -StepDist from anchor)
        prices = [100.0]
        prices += [100.0 + i * 0.5 for i in range(1, 51)]  # seed Long at 125
        prices += [125.0 + i * 0.5 for i in range(1, 51)]  # up to 150 → SUCCESS (Long)
        prices += [150.0 + i * 0.5 for i in range(1, 51)]  # up to 175 → FAILURE (Short)

        bars = _make_bars(prices)
        cfg = FrozenAnchorConfig(
            config_id="FA_MA0", step_dist=25.0, add_dist=10.0,
            max_adds=0, reversal_target=1.0, cost_ticks=0.0
        )
        result = run_frozen_anchor_simulation(cfg, bars)

        # Should have at least 2 cycles
        assert len(result.cycles) >= 2

        # All cycles: position always 1, no adds
        for _, cycle in result.cycles.iterrows():
            assert cycle["exit_position"] == 1
            assert cycle["add_count"] == 0

        # First cycle SUCCESS (Long up), second FAILURE (Short, price kept going up)
        assert result.cycles.iloc[0]["exit_type"] == "SUCCESS"
        assert result.cycles.iloc[1]["exit_type"] == "FAILURE"

        adds = result.trades[result.trades["action"] == "ADD"]
        assert len(adds) == 0


# =========================================================================
# Test 7: ReversalTarget < 1.0
# =========================================================================

class TestReversalTargetFractional:
    def test_success_at_rt_times_sd(self):
        """With RT=0.7 and SD=40, success fires at +28 from anchor (not +40)."""
        # Seed Long at 140, success at 168 (140 + 0.7*40 = 168)
        prices = [100.0]
        prices += [100.0 + i * 0.5 for i in range(1, 81)]  # seed at 140
        prices += [140.0 + i * 0.5 for i in range(1, 57)]  # up to 168

        bars = _make_bars(prices)
        cfg = FrozenAnchorConfig(
            config_id="FA_RT07", step_dist=40.0, add_dist=10.0,
            max_adds=0, reversal_target=0.7, cost_ticks=0.0
        )
        result = run_frozen_anchor_simulation(cfg, bars)

        assert len(result.cycles) >= 1
        cycle0 = result.cycles.iloc[0]
        assert cycle0["exit_type"] == "SUCCESS"
        # PnL should be ~28pts = 112 ticks (28/0.25)
        assert abs(cycle0["pnl_ticks_gross"] - 112.0) < 4.0


# =========================================================================
# Test 8: progress_hwm tracking
# =========================================================================

class TestProgressHwm:
    def test_progress_hwm_on_failure(self):
        """Cycle reaches 80% of target then fails. Verify progress_hwm ~ 80."""
        # Seed Long at 125, SD=25, RT=1.0. Target = 150.
        # Price goes up 20 (80% of 25) to 145, then drops back to 100 (failure)
        prices = [100.0]
        prices += [100.0 + i * 0.5 for i in range(1, 51)]  # seed at 125
        prices += [125.0 + i * 0.5 for i in range(1, 41)]  # up to 145 (80% of 25 = 20pts)
        prices += [145.0 - i * 0.5 for i in range(1, 91)]  # down to 100 → failure

        bars = _make_bars(prices)
        cfg = FrozenAnchorConfig(
            config_id="FA_HWM", step_dist=25.0, add_dist=10.0,
            max_adds=0, reversal_target=1.0, cost_ticks=0.0
        )
        result = run_frozen_anchor_simulation(cfg, bars)

        assert len(result.cycles) >= 1
        cycle0 = result.cycles.iloc[0]
        assert cycle0["exit_type"] == "FAILURE"
        assert abs(cycle0["progress_hwm"] - 80.0) < 2.0


# =========================================================================
# Test 9: cycle_day_seq tracking
# =========================================================================

class TestCycleDaySeq:
    def test_day_seq_resets_each_day(self):
        """Run 2 days. First cycle each day has seq=1, subsequent increment."""
        # Day 1: 3 cycles (seed, success, failure)
        day1 = [100.0]
        day1 += [100.0 + i * 0.5 for i in range(1, 51)]   # seed at 125
        day1 += [125.0 + i * 0.5 for i in range(1, 51)]   # up to 150 → SUCCESS
        day1 += [150.0 - i * 0.5 for i in range(1, 51)]   # down to 125 → FAILURE

        # Day 2: 2 cycles
        day2 = [200.0]
        day2 += [200.0 + i * 0.5 for i in range(1, 51)]   # seed at 225
        day2 += [225.0 + i * 0.5 for i in range(1, 51)]   # up to 250 → SUCCESS

        bars = _make_multiday_bars([day1, day2])
        cfg = FrozenAnchorConfig(
            config_id="FA_SEQ", step_dist=25.0, add_dist=10.0,
            max_adds=0, reversal_target=1.0, cost_ticks=0.0
        )
        result = run_frozen_anchor_simulation(cfg, bars)

        # Day 1 cycles should have seq 1, 2
        # Day 2 cycles should have seq 1
        day1_cycles = result.cycles[result.cycles["cycle_day_seq"] <= 2]
        assert len(day1_cycles) >= 1
        assert day1_cycles.iloc[0]["cycle_day_seq"] == 1

        # Check that day 2 resets to 1
        all_seqs = result.cycles["cycle_day_seq"].tolist()
        # There should be at least one cycle with seq=1 after the first
        assert all_seqs.count(1) >= 2  # at least one per day


# =========================================================================
# Test 10: Asymmetric PnL structure
# =========================================================================

class TestAsymmetricPnL:
    def test_success_pnl_with_adds(self):
        """With SD=40, AD=16, MA=2, RT=1.0: SUCCESS should yield +672 ticks gross."""
        # Seed Long at 140. Add1 at 124 (-16). Add2 at 108 (-32).
        # Then price rises to 180 (anchor + 40 = success).
        # Contract 1 (140): +40pts = 160 ticks
        # Contract 2 (124): +56pts = 224 ticks
        # Contract 3 (108): +72pts = 288 ticks
        # Total: 672 ticks
        prices = [100.0]
        prices += [100.0 + i * 0.5 for i in range(1, 81)]    # seed at 140
        prices += [140.0 - i * 0.25 for i in range(1, 65)]   # drop to 124 → add1
        prices += [124.0 - i * 0.25 for i in range(1, 65)]   # drop to 108 → add2
        prices += [108.0 + i * 0.5 for i in range(1, 145)]   # up to 180 → success

        bars = _make_bars(prices)
        cfg = FrozenAnchorConfig(
            config_id="FA_ASYM_S", step_dist=40.0, add_dist=16.0,
            max_adds=2, reversal_target=1.0, cost_ticks=0.0
        )
        result = run_frozen_anchor_simulation(cfg, bars)

        # Find the cycle with 2 adds and SUCCESS
        success_cycles = result.cycles[
            (result.cycles["exit_type"] == "SUCCESS") &
            (result.cycles["add_count"] == 2)
        ]
        assert len(success_cycles) >= 1
        gross = success_cycles.iloc[0]["pnl_ticks_gross"]
        assert abs(gross - 672.0) < 8.0  # tolerance for tick rounding

    def test_failure_pnl_with_adds(self):
        """With SD=40, AD=16, MA=2, RT=1.0: FAILURE should yield -288 ticks gross."""
        # Seed Long at 140. Add1 at 124 (-16). Add2 at 108 (-32).
        # Price drops to 100 (anchor - 40 = failure).
        # Contract 1 (140): -40pts = -160 ticks
        # Contract 2 (124): -24pts = -96 ticks
        # Contract 3 (108): -8pts = -32 ticks
        # Total: -288 ticks
        prices = [100.0]
        prices += [100.0 + i * 0.5 for i in range(1, 81)]    # seed at 140
        prices += [140.0 - i * 0.25 for i in range(1, 65)]   # drop to 124 → add1
        prices += [124.0 - i * 0.25 for i in range(1, 65)]   # drop to 108 → add2
        prices += [108.0 - i * 0.25 for i in range(1, 33)]   # drop to 100 → failure

        bars = _make_bars(prices)
        cfg = FrozenAnchorConfig(
            config_id="FA_ASYM_F", step_dist=40.0, add_dist=16.0,
            max_adds=2, reversal_target=1.0, cost_ticks=0.0
        )
        result = run_frozen_anchor_simulation(cfg, bars)

        # Find the cycle with 2 adds and FAILURE
        fail_cycles = result.cycles[
            (result.cycles["exit_type"] == "FAILURE") &
            (result.cycles["add_count"] == 2)
        ]
        assert len(fail_cycles) >= 1
        gross = fail_cycles.iloc[0]["pnl_ticks_gross"]
        assert abs(gross - (-288.0)) < 8.0

    def test_asymmetry_success_greater_than_failure(self):
        """Win PnL should exceed abs(loss PnL) when adds are present."""
        # Use the exact same setup for both
        # SUCCESS scenario
        prices_s = [100.0]
        prices_s += [100.0 + i * 0.5 for i in range(1, 81)]
        prices_s += [140.0 - i * 0.25 for i in range(1, 65)]
        prices_s += [124.0 - i * 0.25 for i in range(1, 65)]
        prices_s += [108.0 + i * 0.5 for i in range(1, 145)]

        bars_s = _make_bars(prices_s)
        cfg = FrozenAnchorConfig(
            config_id="FA_ASYM", step_dist=40.0, add_dist=16.0,
            max_adds=2, reversal_target=1.0, cost_ticks=0.0
        )
        result_s = run_frozen_anchor_simulation(cfg, bars_s)
        success_2add = result_s.cycles[
            (result_s.cycles["exit_type"] == "SUCCESS") &
            (result_s.cycles["add_count"] == 2)
        ]

        # FAILURE scenario
        prices_f = [100.0]
        prices_f += [100.0 + i * 0.5 for i in range(1, 81)]
        prices_f += [140.0 - i * 0.25 for i in range(1, 65)]
        prices_f += [124.0 - i * 0.25 for i in range(1, 65)]
        prices_f += [108.0 - i * 0.25 for i in range(1, 33)]

        bars_f = _make_bars(prices_f)
        result_f = run_frozen_anchor_simulation(cfg, bars_f)
        fail_2add = result_f.cycles[
            (result_f.cycles["exit_type"] == "FAILURE") &
            (result_f.cycles["add_count"] == 2)
        ]

        assert len(success_2add) >= 1
        assert len(fail_2add) >= 1
        win = success_2add.iloc[0]["pnl_ticks_gross"]
        loss = fail_2add.iloc[0]["pnl_ticks_gross"]
        assert win > abs(loss)  # asymmetric: wins > losses


# =========================================================================
# Test 11: Cost model
# =========================================================================

class TestFACostModel:
    def test_failure_exit_cost(self):
        """FAILURE with 3 contracts: flatten(3) + reseed(1) = 4 sides charged to cycle."""
        # Seed Long at 140, 2 adds → 3 contracts. Failure at 100.
        # Cost: seed(2) + add1(2) + add2(2) + flatten(3×2) + reseed(2) = 14
        prices = [100.0]
        prices += [100.0 + i * 0.5 for i in range(1, 81)]
        prices += [140.0 - i * 0.25 for i in range(1, 65)]
        prices += [124.0 - i * 0.25 for i in range(1, 65)]
        prices += [108.0 - i * 0.25 for i in range(1, 33)]

        bars = _make_bars(prices)
        cfg = FrozenAnchorConfig(
            config_id="FA_COST", step_dist=40.0, add_dist=16.0,
            max_adds=2, reversal_target=1.0, cost_ticks=2.0
        )
        result = run_frozen_anchor_simulation(cfg, bars)

        fail_cycles = result.cycles[
            (result.cycles["exit_type"] == "FAILURE") &
            (result.cycles["add_count"] == 2)
        ]
        assert len(fail_cycles) >= 1
        cycle = fail_cycles.iloc[0]
        # seed(2) + add1(2) + add2(2) + flatten(6) + reseed(2) = 14
        expected_cost = 14.0
        actual_cost = cycle["pnl_ticks_gross"] - cycle["pnl_ticks_net"]
        assert abs(actual_cost - expected_cost) < 0.1

    def test_success_exit_cost_no_adds(self):
        """SUCCESS with 1 contract: seed(1) + flatten(1) + reseed(1) = 3 sides."""
        prices = [100.0]
        prices += [100.0 + i * 0.5 for i in range(1, 51)]
        prices += [125.0 + i * 0.5 for i in range(1, 51)]

        bars = _make_bars(prices)
        cfg = FrozenAnchorConfig(
            config_id="FA_COST0", step_dist=25.0, add_dist=10.0,
            max_adds=0, reversal_target=1.0, cost_ticks=2.0
        )
        result = run_frozen_anchor_simulation(cfg, bars)

        assert len(result.cycles) >= 1
        cycle = result.cycles.iloc[0]
        # seed(2) + flatten(2) + reseed(2) = 6
        expected_cost = 6.0
        actual_cost = cycle["pnl_ticks_gross"] - cycle["pnl_ticks_net"]
        assert abs(actual_cost - expected_cost) < 0.1


# =========================================================================
# Test: prev_cycle_exit_type
# =========================================================================

class TestPrevCycleExitType:
    def test_first_cycle_is_session_start(self):
        """First cycle of day has prev_cycle_exit_type=SESSION_START."""
        prices = [100.0]
        prices += [100.0 + i * 0.5 for i in range(1, 51)]
        prices += [125.0 + i * 0.5 for i in range(1, 51)]

        bars = _make_bars(prices)
        cfg = FrozenAnchorConfig(
            config_id="FA_PREV", step_dist=25.0, add_dist=10.0,
            max_adds=0, reversal_target=1.0, cost_ticks=0.0
        )
        result = run_frozen_anchor_simulation(cfg, bars)

        assert len(result.cycles) >= 1
        assert result.cycles.iloc[0]["prev_cycle_exit_type"] == "SESSION_START"

    def test_second_cycle_inherits_prev(self):
        """Second cycle's prev_cycle_exit_type matches first cycle's exit_type."""
        prices = [100.0]
        prices += [100.0 + i * 0.5 for i in range(1, 51)]
        prices += [125.0 + i * 0.5 for i in range(1, 51)]  # SUCCESS
        prices += [150.0 - i * 0.5 for i in range(1, 51)]  # FAILURE (Short)

        bars = _make_bars(prices)
        cfg = FrozenAnchorConfig(
            config_id="FA_PREV2", step_dist=25.0, add_dist=10.0,
            max_adds=0, reversal_target=1.0, cost_ticks=0.0
        )
        result = run_frozen_anchor_simulation(cfg, bars)

        if len(result.cycles) >= 2:
            assert result.cycles.iloc[1]["prev_cycle_exit_type"] == result.cycles.iloc[0]["exit_type"]


# =========================================================================
# Test: cycle_start_hour
# =========================================================================

class TestCycleStartHour:
    def test_start_hour_captured(self):
        """cycle_start_hour is the integer hour of cycle start."""
        prices = [100.0]
        prices += [100.0 + i * 0.5 for i in range(1, 51)]  # seed at 09:30 + 50s
        prices += [125.0 + i * 0.5 for i in range(1, 51)]

        bars = _make_bars(prices)
        cfg = FrozenAnchorConfig(
            config_id="FA_HOUR", step_dist=25.0, add_dist=10.0,
            max_adds=0, reversal_target=1.0, cost_ticks=0.0
        )
        result = run_frozen_anchor_simulation(cfg, bars)

        assert len(result.cycles) >= 1
        assert result.cycles.iloc[0]["cycle_start_hour"] == 9


# =========================================================================
# Test: incomplete cycles have SESSION_END
# =========================================================================

class TestIncompleteCycles:
    def test_session_end_incomplete(self):
        """Cycle still open at session end is logged as SESSION_END."""
        # Seed Long at 125, but session ends before success or failure
        prices = [100.0]
        prices += [100.0 + i * 0.5 for i in range(1, 51)]  # seed at 125
        prices += [125.0 + i * 0.1 for i in range(1, 21)]  # drift up slightly

        bars = _make_bars(prices)
        cfg = FrozenAnchorConfig(
            config_id="FA_INC", step_dist=25.0, add_dist=10.0,
            max_adds=0, reversal_target=1.0, cost_ticks=0.0
        )
        result = run_frozen_anchor_simulation(cfg, bars)

        # No completed cycles (price didn't move enough)
        assert len(result.cycles) == 0
        # But there should be an incomplete cycle
        assert len(result.incomplete_cycles) >= 1
        assert result.incomplete_cycles.iloc[0]["exit_type"] == "SESSION_END"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
