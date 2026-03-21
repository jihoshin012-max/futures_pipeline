# archetype: rotational
"""Unit tests for multi-approach rotation simulator.

Uses synthetic price sequences to test state machine logic in isolation.
Tests verify approach-specific add behavior, anchor rules, position sizes,
and priority rules.
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

from config_schema import RotationConfig
from rotation_simulator import run_simulation


def _make_bars(prices: list[float]) -> pd.DataFrame:
    """Create a synthetic tick-bar DataFrame from a price list.

    All bars have O=H=L=Last (tick data format). Timestamps are synthetic
    RTH times starting at 09:30:00 on 2026-01-05 (a Monday).
    """
    n = len(prices)
    base_dt = pd.Timestamp("2026-01-05 09:30:00")
    dts = [base_dt + pd.Timedelta(seconds=i) for i in range(n)]
    return pd.DataFrame({
        "Open": prices,
        "High": prices,
        "Low": prices,
        "Last": prices,
        "datetime": dts,
    })


# =========================================================================
# Config validation tests
# =========================================================================

class TestConfigValidation:
    def test_approach_a_valid(self):
        cfg = RotationConfig(config_id="A1", approach="A", step_dist=25.0)
        assert cfg.approach == "A"
        assert cfg.max_adds == 0

    def test_approach_a_rejects_max_adds(self):
        with pytest.raises(ValueError, match="max_adds must be 0"):
            RotationConfig(config_id="A1", approach="A", step_dist=25.0, max_adds=1)

    def test_approach_a_rejects_add_dist(self):
        with pytest.raises(ValueError, match="add_dist must be 0"):
            RotationConfig(config_id="A1", approach="A", step_dist=25.0, add_dist=5.0)

    def test_approach_b_valid(self):
        cfg = RotationConfig(config_id="B1", approach="B", step_dist=25.0,
                             add_dist=10.0, max_adds=2)
        assert cfg.approach == "B"
        assert cfg.add_dist == 10.0

    def test_approach_b_rejects_zero_add_dist(self):
        with pytest.raises(ValueError, match="add_dist must be > 0"):
            RotationConfig(config_id="B1", approach="B", step_dist=25.0,
                           add_dist=0.0, max_adds=2)

    def test_approach_c_valid(self):
        cfg = RotationConfig(config_id="C1", approach="C", step_dist=25.0,
                             confirm_dist=10.0, max_adds=2)
        assert cfg.approach == "C"
        assert cfg.add_size == 1

    def test_approach_c_rejects_add_size(self):
        with pytest.raises(ValueError, match="add_size must be 1"):
            RotationConfig(config_id="C1", approach="C", step_dist=25.0,
                           confirm_dist=10.0, max_adds=2, add_size=2)

    def test_approach_d_valid(self):
        cfg = RotationConfig(config_id="D1", approach="D", step_dist=25.0,
                             confirm_dist=10.0, max_adds=2, add_size=3)
        assert cfg.approach == "D"
        assert cfg.add_size == 3

    def test_rejects_zero_step_dist(self):
        with pytest.raises(ValueError, match="step_dist must be > 0"):
            RotationConfig(config_id="X", approach="A", step_dist=0.0)

    def test_rejects_unknown_approach(self):
        with pytest.raises(ValueError, match="Unknown approach"):
            RotationConfig(config_id="X", approach="E", step_dist=25.0)


# =========================================================================
# Approach A: Pure rotation
# =========================================================================

class TestApproachA:
    """Approach A: both in-favor and against moves of >= StepDist trigger reversals.
    Position is always exactly 1 contract. No adds ever fire.
    """

    def test_favor_reversal(self):
        """Price moves +SD → reversal to Short."""
        # Start at 100, move up to seed Long, then move up another SD to reverse
        prices = [100.0]
        # Move up 25 pts to seed Long at 125
        prices += [100.0 + i * 0.5 for i in range(1, 51)]  # 100.5..125.0
        # Move up another 25 pts to trigger reversal at 150
        prices += [125.0 + i * 0.5 for i in range(1, 51)]  # 125.5..150.0

        bars = _make_bars(prices)
        cfg = RotationConfig(config_id="A_test", approach="A", step_dist=25.0,
                             cost_ticks=0.0)
        result = run_simulation(cfg, bars)

        assert len(result.cycles) >= 1
        cycle0 = result.cycles.iloc[0]
        assert cycle0["side"] == "LONG"
        assert cycle0["add_count"] == 0
        assert cycle0["exit_position"] == 1

    def test_against_fires_reversal_not_add(self):
        """Price moves -SD from anchor → fires reversal (not add). Position stays 1."""
        # Seed Long at 125, then move down 25 to 100 → should reverse to Short
        prices = [100.0]
        prices += [100.0 + i * 0.5 for i in range(1, 51)]  # seed Long at 125
        prices += [125.0 - i * 0.5 for i in range(1, 51)]  # drop to 100

        bars = _make_bars(prices)
        cfg = RotationConfig(config_id="A_test", approach="A", step_dist=25.0,
                             cost_ticks=0.0)
        result = run_simulation(cfg, bars)

        assert len(result.cycles) >= 1
        cycle0 = result.cycles.iloc[0]
        assert cycle0["side"] == "LONG"
        assert cycle0["add_count"] == 0
        assert cycle0["exit_position"] == 1
        # The cycle ended by against-reversal, and a new Short cycle started

    def test_position_never_exceeds_1(self):
        """Multiple reversals — position stays at 1 throughout."""
        # Zigzag: up 25, down 25, up 25, down 25
        prices = [100.0]
        for cycle in range(4):
            base = 100.0 if cycle % 2 == 0 else 125.0
            target = 125.0 if cycle % 2 == 0 else 100.0
            step = 0.5 if target > base else -0.5
            prices += [base + i * step for i in range(1, 51)]

        bars = _make_bars(prices)
        cfg = RotationConfig(config_id="A_test", approach="A", step_dist=25.0,
                             cost_ticks=0.0)
        result = run_simulation(cfg, bars)

        for _, cycle in result.cycles.iterrows():
            assert cycle["exit_position"] == 1
            assert cycle["add_count"] == 0


# =========================================================================
# Approach B: Traditional martingale
# =========================================================================

class TestApproachB:
    """Approach B: adds fire against at AddDist, anchor walks on add."""

    def test_add_fires_on_against(self):
        """Price moves -AddDist → add fires, add_count increments."""
        # Seed Long at 125, then drop AddDist (10 pts) to 115 → add fires
        prices = [100.0]
        prices += [100.0 + i * 0.5 for i in range(1, 51)]  # seed Long at 125
        prices += [125.0 - i * 0.5 for i in range(1, 21)]  # drop 10 to 115

        bars = _make_bars(prices)
        cfg = RotationConfig(config_id="B_test", approach="B", step_dist=25.0,
                             add_dist=10.0, max_adds=2, cost_ticks=0.0)
        result = run_simulation(cfg, bars)

        # Check trades for an ADD action
        adds = result.trades[result.trades["action"] == "ADD"]
        assert len(adds) >= 1
        assert adds.iloc[0]["qty"] == 1

    def test_anchor_resets_on_add(self):
        """After add, anchor moves to add price (walking anchor)."""
        # Seed Long at 125, drop 10 to 115 (add), then drop 10 more to 105 (2nd add)
        prices = [100.0]
        prices += [100.0 + i * 0.5 for i in range(1, 51)]  # seed at 125
        prices += [125.0 - i * 0.5 for i in range(1, 21)]  # drop to 115 → add
        prices += [115.0 - i * 0.5 for i in range(1, 21)]  # drop to 105 → 2nd add

        bars = _make_bars(prices)
        cfg = RotationConfig(config_id="B_test", approach="B", step_dist=25.0,
                             add_dist=10.0, max_adds=3, cost_ticks=0.0)
        result = run_simulation(cfg, bars)

        adds = result.trades[result.trades["action"] == "ADD"]
        assert len(adds) >= 2
        # First add at ~115, anchor should be ~115
        # Second add at ~105, anchor should be ~105
        assert abs(adds.iloc[0]["price"] - 115.0) < 1.0
        assert abs(adds.iloc[1]["price"] - 105.0) < 1.0

    def test_adds_suppressed_at_max(self):
        """When max_adds reached, further against moves do not add."""
        # Seed Long at 125, drop by 10 three times (but max_adds=2)
        prices = [100.0]
        prices += [100.0 + i * 0.5 for i in range(1, 51)]  # seed at 125
        prices += [125.0 - i * 0.5 for i in range(1, 21)]  # 115 → add 1
        prices += [115.0 - i * 0.5 for i in range(1, 21)]  # 105 → add 2
        prices += [105.0 - i * 0.5 for i in range(1, 21)]  # 95 → should NOT add

        bars = _make_bars(prices)
        cfg = RotationConfig(config_id="B_test", approach="B", step_dist=25.0,
                             add_dist=10.0, max_adds=2, cost_ticks=0.0)
        result = run_simulation(cfg, bars)

        adds = result.trades[result.trades["action"] == "ADD"]
        assert len(adds) == 2  # only 2 adds, not 3

    def test_frozen_position_holds_until_reversal(self):
        """After max_adds, position holds until price reverses StepDist in favor."""
        # Seed Long at 125, two adds (max), then price recovers +25 from last anchor
        prices = [100.0]
        prices += [100.0 + i * 0.5 for i in range(1, 51)]  # seed at 125
        prices += [125.0 - i * 0.5 for i in range(1, 21)]  # 115 → add
        prices += [115.0 - i * 0.5 for i in range(1, 21)]  # 105 → add (max)
        # Now anchor is at 105. Price needs to go to 130 (105+25) to reverse
        prices += [105.0 + i * 0.5 for i in range(1, 51)]  # up to 130

        bars = _make_bars(prices)
        cfg = RotationConfig(config_id="B_test", approach="B", step_dist=25.0,
                             add_dist=10.0, max_adds=2, cost_ticks=0.0)
        result = run_simulation(cfg, bars)

        assert len(result.cycles) >= 1
        cycle0 = result.cycles.iloc[0]
        assert cycle0["add_count"] == 2


# =========================================================================
# Approach C: Anti-martingale
# =========================================================================

class TestApproachC:
    """Approach C: adds in-favor at successive multiples of ConfirmDist.
    Anchor does NOT reset on add. Reversal from original anchor.
    """

    def test_first_add_fires_at_confirm_dist(self):
        """Price moves +ConfirmDist in favor → first add fires."""
        # Seed Long at 125, then move up 10 (ConfirmDist) to 135 → add
        prices = [100.0]
        prices += [100.0 + i * 0.5 for i in range(1, 51)]  # seed at 125
        prices += [125.0 + i * 0.5 for i in range(1, 21)]  # up to 135 → add

        bars = _make_bars(prices)
        cfg = RotationConfig(config_id="C_test", approach="C", step_dist=25.0,
                             confirm_dist=10.0, max_adds=2, cost_ticks=0.0)
        result = run_simulation(cfg, bars)

        adds = result.trades[result.trades["action"] == "ADD"]
        assert len(adds) >= 1

    def test_second_add_at_2x_confirm_dist(self):
        """Second add fires at 2×ConfirmDist from anchor, not at 1×ConfirmDist from first add."""
        # Seed Long at 125, ConfirmDist=10
        # First add at 135 (125+10), second at 145 (125+20)
        prices = [100.0]
        prices += [100.0 + i * 0.5 for i in range(1, 51)]  # seed at 125
        prices += [125.0 + i * 0.5 for i in range(1, 41)]  # up to 145

        bars = _make_bars(prices)
        cfg = RotationConfig(config_id="C_test", approach="C", step_dist=25.0,
                             confirm_dist=10.0, max_adds=2, cost_ticks=0.0)
        result = run_simulation(cfg, bars)

        adds = result.trades[result.trades["action"] == "ADD"]
        assert len(adds) == 2
        # First add near 135, second near 145
        assert abs(adds.iloc[0]["price"] - 135.0) < 1.0
        assert abs(adds.iloc[1]["price"] - 145.0) < 1.0

    def test_anchor_does_not_reset_on_add(self):
        """Reversal triggers at StepDist from ORIGINAL anchor, not from add price."""
        # Seed Long at 125, ConfirmDist=10, StepDist=25
        # Add at 135 — anchor stays at 125
        # Reversal at 150 (125+25), NOT at 160 (135+25)
        prices = [100.0]
        prices += [100.0 + i * 0.5 for i in range(1, 51)]  # seed at 125
        prices += [125.0 + i * 0.5 for i in range(1, 51)]  # up to 150

        bars = _make_bars(prices)
        cfg = RotationConfig(config_id="C_test", approach="C", step_dist=25.0,
                             confirm_dist=10.0, max_adds=2, cost_ticks=0.0)
        result = run_simulation(cfg, bars)

        assert len(result.cycles) >= 1
        cycle0 = result.cycles.iloc[0]
        assert cycle0["side"] == "LONG"
        # Reversal should happen at 150 (125 + 25), not later

    def test_against_move_no_add(self):
        """Price moves against — no add fires in Approach C."""
        # Seed Long at 125, then drop 20 — no add should fire
        prices = [100.0]
        prices += [100.0 + i * 0.5 for i in range(1, 51)]  # seed at 125
        prices += [125.0 - i * 0.5 for i in range(1, 41)]  # drop to 105

        bars = _make_bars(prices)
        cfg = RotationConfig(config_id="C_test", approach="C", step_dist=25.0,
                             confirm_dist=10.0, max_adds=2, cost_ticks=0.0)
        result = run_simulation(cfg, bars)

        adds = result.trades[result.trades["action"] == "ADD"]
        assert len(adds) == 0

    def test_reversal_priority_over_add(self):
        """With ConfirmDist=0.5×SD and MaxAdds=2, reversal fires at SD,
        preventing the second add (which would also fire at 2×0.5×SD = SD).
        """
        # Seed Long at 125, StepDist=20, ConfirmDist=10 (0.5×SD)
        # First add at 135 (125+10)
        # At 145 (125+20): both reversal (at SD=20) and 2nd add (at 2×10=20) qualify
        # Reversal takes priority → second add does NOT fire
        prices = [100.0]
        prices += [100.0 + i * 0.5 for i in range(1, 51)]  # seed at ~125
        prices += [125.0 + i * 0.5 for i in range(1, 41)]  # up to 145

        bars = _make_bars(prices)
        cfg = RotationConfig(config_id="C_prio", approach="C", step_dist=20.0,
                             confirm_dist=10.0, max_adds=2, cost_ticks=0.0)
        result = run_simulation(cfg, bars)

        adds = result.trades[result.trades["action"] == "ADD"]
        assert len(adds) == 1  # only one add, not two (reversal won priority)


# =========================================================================
# Approach D: Scaled entry
# =========================================================================

class TestApproachD:
    """Approach D: same as C but add_size can be > 1."""

    def test_add_qty_equals_add_size(self):
        """Each add in Approach D uses add_size contracts."""
        prices = [100.0]
        prices += [100.0 + i * 0.5 for i in range(1, 51)]  # seed at 125
        prices += [125.0 + i * 0.5 for i in range(1, 21)]  # up to 135 → add

        bars = _make_bars(prices)
        cfg = RotationConfig(config_id="D_test", approach="D", step_dist=25.0,
                             confirm_dist=10.0, max_adds=2, add_size=3,
                             cost_ticks=0.0)
        result = run_simulation(cfg, bars)

        adds = result.trades[result.trades["action"] == "ADD"]
        assert len(adds) >= 1
        assert adds.iloc[0]["qty"] == 3

    def test_successive_add_spacing_same_as_c(self):
        """Adds fire at N×ConfirmDist, same spacing as C."""
        prices = [100.0]
        prices += [100.0 + i * 0.5 for i in range(1, 51)]  # seed at 125
        prices += [125.0 + i * 0.5 for i in range(1, 41)]  # up to 145

        bars = _make_bars(prices)
        cfg = RotationConfig(config_id="D_test", approach="D", step_dist=25.0,
                             confirm_dist=10.0, max_adds=2, add_size=2,
                             cost_ticks=0.0)
        result = run_simulation(cfg, bars)

        adds = result.trades[result.trades["action"] == "ADD"]
        assert len(adds) == 2
        # Each add has qty=2
        assert all(adds["qty"] == 2)


# =========================================================================
# Cost model tests
# =========================================================================

class TestCostModel:
    def test_seed_cost(self):
        """SEED costs cost_ticks × 1 contract."""
        prices = [100.0]
        prices += [100.0 + i * 0.5 for i in range(1, 51)]  # seed at 125
        prices += [125.0 + i * 0.5 for i in range(1, 51)]  # reversal at 150

        bars = _make_bars(prices)
        cfg = RotationConfig(config_id="cost_test", approach="A", step_dist=25.0,
                             cost_ticks=2.0)
        result = run_simulation(cfg, bars)

        seeds = result.trades[result.trades["action"] == "SEED"]
        assert len(seeds) >= 1
        assert seeds.iloc[0]["cost"] == 2.0

    def test_reversal_cost(self):
        """REVERSAL costs: flatten (exit_qty × cost) + entry (1 × cost)."""
        prices = [100.0]
        prices += [100.0 + i * 0.5 for i in range(1, 51)]  # seed at 125
        # Add at 115 (approach B)
        prices += [125.0 - i * 0.5 for i in range(1, 21)]  # drop to 115
        # Reversal: need to go up 25 from anchor=115 → 140
        prices += [115.0 + i * 0.5 for i in range(1, 51)]  # up to 140

        bars = _make_bars(prices)
        cfg = RotationConfig(config_id="cost_test", approach="B", step_dist=25.0,
                             add_dist=10.0, max_adds=1, cost_ticks=2.0)
        result = run_simulation(cfg, bars)

        assert len(result.cycles) >= 1
        cycle0 = result.cycles.iloc[0]
        # Position at exit: 2 contracts (1 seed + 1 add)
        # Total cost: seed(2) + add(2) + flatten(2×2) + reversal_entry(2) = 10
        # net = gross - 10
        assert cycle0["pnl_ticks_net"] < cycle0["pnl_ticks_gross"]


# =========================================================================
# Shadow metrics tests
# =========================================================================

class TestShadowMetrics:
    def test_would_flatten_reseed_b_only(self):
        """would_flatten_reseed is only evaluated for Approach B."""
        # Approach A cycle
        prices = [100.0]
        prices += [100.0 + i * 0.5 for i in range(1, 51)]
        prices += [125.0 + i * 0.5 for i in range(1, 51)]

        bars = _make_bars(prices)
        cfg = RotationConfig(config_id="shadow_A", approach="A", step_dist=25.0,
                             cost_ticks=0.0)
        result = run_simulation(cfg, bars)

        if len(result.cycles) > 0:
            assert result.cycles.iloc[0]["would_flatten_reseed"] == False  # noqa: E712

    def test_half_block_profit_captured(self):
        """half_block_profit is captured when price reaches 0.5×SD in favor."""
        # Seed Long at 125, SD=20. Half block at 125+10=135. Reversal at 145.
        prices = [100.0]
        prices += [100.0 + i * 0.5 for i in range(1, 51)]  # seed at 125
        prices += [125.0 + i * 0.5 for i in range(1, 41)]  # up to 145

        bars = _make_bars(prices)
        cfg = RotationConfig(config_id="hbp_test", approach="A", step_dist=20.0,
                             cost_ticks=0.0)
        result = run_simulation(cfg, bars)

        if len(result.cycles) > 0:
            hbp = result.cycles.iloc[0]["half_block_profit"]
            assert hbp is not None
            assert hbp > 0  # should be positive since we're in profit at 0.5×SD


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
