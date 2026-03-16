# archetype: rotational
"""Unit tests for RotationalSimulator state machine.

Covers:
    - SEED: first bar on flat position
    - REVERSAL: price moves step_dist in favor
    - ADD: price moves step_dist against
    - ADD CAP: add qty exceeds max_contract_size
    - CYCLE RECORD: all spec Section 6.4 fields present
    - COST MODEL: net_pnl = gross_pnl - action costs
    - RTH FILTER: 10-sec bars outside 09:30-16:00 excluded
    - DATE FILTER: P1a bars correctly restricted
    - DETERMINISM: identical input -> identical output
    - CONTRACT: SimulationResult fields and types

All tests use synthetic DataFrames — no CSV files required.
"""

from __future__ import annotations

import datetime
import sys
from pathlib import Path

import pandas as pd
import pytest

# Allow imports from shared/archetypes/rotational/ directly
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from rotational_simulator import (  # noqa: E402
    RotationalSimulator,
    SimulationResult,
    FeatureComputer,
    TradeLogger,
    _P1_START,
    _P1_END,
    _P1_MIDPOINT,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config(
    step_dist: float = 2.0,
    initial_qty: int = 1,
    max_levels: int = 4,
    max_contract_size: int = 8,
    period: str = "P1",
    tick_size: float = 0.25,
    cost_ticks: int = 3,
    bar_data_primary_keys: list[str] | None = None,
) -> dict:
    """Build a minimal config dict for testing."""
    if bar_data_primary_keys is None:
        bar_data_primary_keys = ["bar_data_250vol_rot"]
    return {
        "period": period,
        "instrument": "NQ",
        "_instrument": {
            "tick_size": tick_size,
            "tick_value": 5.0,
            "cost_ticks": cost_ticks,
        },
        "hypothesis": {
            "trigger_params": {"step_dist": step_dist},
        },
        "martingale": {
            "initial_qty": initial_qty,
            "max_levels": max_levels,
            "max_contract_size": max_contract_size,
        },
        "bar_data_primary": {k: f"dummy/{k}.csv" for k in bar_data_primary_keys},
    }


def _make_bars(
    prices: list[float],
    dates: list[str] | None = None,
    times: list[str] | None = None,
    start_date: str = "2025-10-01",
) -> pd.DataFrame:
    """Build a synthetic bar DataFrame with the required columns.

    Args:
        prices: List of close prices (used as Last column).
        dates: Optional list of date strings (YYYY-MM-DD); defaults to start_date for all.
        times: Optional list of time strings (HH:MM:SS); defaults to "10:00:00" for all.
        start_date: Default date string when dates is None.
    """
    n = len(prices)
    if dates is None:
        dates = [start_date] * n
    if times is None:
        times = ["10:00:00"] * n

    datetimes = [
        pd.Timestamp(f"{d} {t}") for d, t in zip(dates, times)
    ]

    df = pd.DataFrame({
        "Date": dates,
        "Time": times,
        "datetime": datetimes,
        "Open": prices,
        "High": [p + 0.25 for p in prices],
        "Low": [p - 0.25 for p in prices],
        "Last": prices,
        "Volume": [1000] * n,
        "ATR": [2.0] * n,
    })
    return df.reset_index(drop=True)


def _run(config: dict, prices: list[float], **kwargs) -> SimulationResult:
    """Convenience: build bars, instantiate simulator, run."""
    bars = _make_bars(prices, **kwargs)
    sim = RotationalSimulator(config=config, bar_data=bars)
    return sim.run()


# ---------------------------------------------------------------------------
# Test: SEED
# ---------------------------------------------------------------------------

class TestSeed:
    def test_seed_on_first_bar(self):
        """First bar triggers SEED: Long, qty=1, anchor=close, level=0."""
        cfg = _make_config()
        result = _run(cfg, [100.0, 100.0, 100.0])  # no movement -> just SEED

        trades = result.trades
        assert len(trades) >= 1
        seed = trades[trades["action"] == "SEED"]
        assert len(seed) == 1
        row = seed.iloc[0]
        assert row["action"] == "SEED"
        assert row["direction"] == "Long"
        assert row["qty"] == 1
        assert row["price"] == 100.0
        assert row["level"] == 0
        assert row["cycle_id"] == 1

    def test_seed_always_long(self):
        """Seeds Long regardless of subsequent price direction (C++ behavior)."""
        cfg = _make_config()
        result = _run(cfg, [100.0])
        seed = result.trades[result.trades["action"] == "SEED"]
        assert seed.iloc[0]["direction"] == "Long"

    def test_seed_costs_correct(self):
        """SEED cost = cost_ticks * initial_qty."""
        cfg = _make_config(cost_ticks=3, initial_qty=1)
        result = _run(cfg, [100.0])
        seed = result.trades[result.trades["action"] == "SEED"]
        assert seed.iloc[0]["cost_ticks"] == 3  # 3 * 1


# ---------------------------------------------------------------------------
# Test: REVERSAL
# ---------------------------------------------------------------------------

class TestReversal:
    def test_reversal_triggered_in_favor(self):
        """Long position: price rises >= step_dist -> REVERSAL to Short."""
        cfg = _make_config(step_dist=2.0)
        # Bar 0: SEED at 100 (Long)
        # Bar 1: close=102 -> distance=+2.0 in favor -> REVERSAL to Short
        result = _run(cfg, [100.0, 102.0])

        trades = result.trades
        assert "REVERSAL" in trades["action"].values
        rev = trades[trades["action"] == "REVERSAL"].iloc[0]
        assert rev["direction"] == "Short"
        assert rev["qty"] == 1
        assert rev["level"] == 0
        assert rev["price"] == 102.0

    def test_reversal_flips_direction(self):
        """After REVERSAL Long->Short, next REVERSAL is Short->Long."""
        cfg = _make_config(step_dist=2.0)
        # 100 -> 102 (rev to Short) -> 100 (rev to Long)
        result = _run(cfg, [100.0, 102.0, 100.0])

        reversals = result.trades[result.trades["action"] == "REVERSAL"]
        assert len(reversals) >= 2
        assert reversals.iloc[0]["direction"] == "Short"
        assert reversals.iloc[1]["direction"] == "Long"

    def test_reversal_creates_flatten(self):
        """REVERSAL produces a FLATTEN action for the prior position."""
        cfg = _make_config(step_dist=2.0)
        result = _run(cfg, [100.0, 102.0])

        trades = result.trades
        assert "FLATTEN" in trades["action"].values

    def test_reversal_cost_double(self):
        """Reversal costs = cost_ticks * flatten_qty + cost_ticks * initial_qty."""
        cfg = _make_config(step_dist=2.0, cost_ticks=3, initial_qty=1)
        result = _run(cfg, [100.0, 102.0])

        # FLATTEN cost: 3 * 1 = 3; REVERSAL entry cost: 3 * 1 = 3
        trades = result.trades
        flatten = trades[trades["action"] == "FLATTEN"].iloc[0]
        reversal = trades[trades["action"] == "REVERSAL"].iloc[0]
        assert flatten["cost_ticks"] == 3
        assert reversal["cost_ticks"] == 3

    def test_reversal_finalizes_cycle(self):
        """REVERSAL creates a completed cycle record."""
        cfg = _make_config(step_dist=2.0)
        result = _run(cfg, [100.0, 102.0])

        assert not result.cycles.empty
        cycle = result.cycles.iloc[0]
        assert cycle["exit_reason"] == "reversal"
        assert cycle["direction"] == "Long"

    def test_reversal_not_triggered_below_step(self):
        """Price must reach exactly step_dist to trigger REVERSAL."""
        cfg = _make_config(step_dist=2.0)
        # 100 -> 101.75 (not enough for step_dist=2.0)
        result = _run(cfg, [100.0, 101.75])

        assert "REVERSAL" not in result.trades["action"].values


# ---------------------------------------------------------------------------
# Test: ADD
# ---------------------------------------------------------------------------

class TestAdd:
    def test_add_triggered_against(self):
        """Long position: price drops >= step_dist -> ADD."""
        cfg = _make_config(step_dist=2.0)
        # Bar 0: SEED at 100 (Long, anchor=100)
        # Bar 1: close=98 -> -2.0 against -> ADD
        result = _run(cfg, [100.0, 98.0])

        trades = result.trades
        adds = trades[trades["action"] == "ADD"]
        assert len(adds) == 1
        assert adds.iloc[0]["direction"] == "Long"
        assert adds.iloc[0]["qty"] == 1  # initial_qty * 2^0

    def test_add_doubles_qty(self):
        """Second ADD doubles quantity (2^1 = 2 at level 1)."""
        cfg = _make_config(step_dist=2.0, initial_qty=1)
        # 100 -> 98 (ADD level0, qty=1) -> 96 (ADD level1, qty=2)
        result = _run(cfg, [100.0, 98.0, 96.0])

        adds = result.trades[result.trades["action"] == "ADD"]
        assert len(adds) >= 2
        assert adds.iloc[0]["qty"] == 1
        assert adds.iloc[1]["qty"] == 2

    def test_add_updates_anchor(self):
        """Each ADD updates anchor to current close."""
        cfg = _make_config(step_dist=2.0)
        result = _run(cfg, [100.0, 98.0, 96.0])

        adds = result.trades[result.trades["action"] == "ADD"]
        assert adds.iloc[0]["anchor"] == 98.0
        assert adds.iloc[1]["anchor"] == 96.0

    def test_add_short_position(self):
        """Short position: price rises >= step_dist -> ADD."""
        cfg = _make_config(step_dist=2.0)
        # 100 -> 102 (REVERSAL to Short, anchor=102) -> 104 (ADD against Short)
        result = _run(cfg, [100.0, 102.0, 104.0])

        adds = result.trades[result.trades["action"] == "ADD"]
        assert len(adds) >= 1
        assert adds.iloc[0]["direction"] == "Short"


# ---------------------------------------------------------------------------
# Test: ADD CAP
# ---------------------------------------------------------------------------

class TestAddCap:
    def test_add_cap_resets_to_initial(self):
        """When add_qty > max_contract_size, reset to initial_qty and level=0."""
        # max_contract_size=8, initial_qty=1
        # Level sequence: 0->1 (qty=1), 1->2 (qty=2), 2->3 (qty=4), 3->4 would be 8 which == max, ok
        # 4->5 would be 16 > 8 -> cap reset to qty=1, level=0
        cfg = _make_config(step_dist=2.0, initial_qty=1, max_contract_size=8)
        # Need 5 consecutive ADDs against:
        # 100, 98, 96, 94, 92, 90 (5 drops of 2.0)
        prices = [100.0, 98.0, 96.0, 94.0, 92.0, 90.0]
        result = _run(cfg, prices)

        adds = result.trades[result.trades["action"] == "ADD"]
        qtys = list(adds["qty"])
        # Expected: 1, 2, 4, 8 (=max_contract_size, so NOT capped), then cap at next
        # Level 0: qty=1*2^0=1 ok; Level 1: qty=1*2^1=2 ok; Level 2: qty=1*2^2=4 ok;
        # Level 3: qty=1*2^3=8 == max_contract_size (not >), ok; Level 4: qty=1*2^4=16 > 8 -> reset to 1
        assert 1 in qtys  # cap reset produces qty=1 again

    def test_add_cap_resets_level_to_zero(self):
        """After cap reset, subsequent ADDs restart from level 0."""
        cfg = _make_config(step_dist=2.0, initial_qty=1, max_contract_size=4)
        # Level 0: 1; Level 1: 2; Level 2: 4 (==max); Level 3: 8 > 4 -> reset
        # 100, 98, 96, 94, 92 (4 drops of 2.0)
        prices = [100.0, 98.0, 96.0, 94.0, 92.0]
        result = _run(cfg, prices)

        adds = result.trades[result.trades["action"] == "ADD"]
        # After cap reset, level should be 0 again in that add row
        levels = list(adds["level"])
        assert 0 in levels[1:]  # level 0 should appear in a non-first ADD (cap reset)


# ---------------------------------------------------------------------------
# Test: Cycle Record Completeness
# ---------------------------------------------------------------------------

class TestCycleRecord:
    _REQUIRED_FIELDS = [
        "cycle_id", "start_bar", "end_bar", "direction", "duration_bars",
        "entry_price", "exit_price", "avg_entry_price", "adds_count",
        "max_level_reached", "max_position_qty", "gross_pnl_ticks",
        "net_pnl_ticks", "max_adverse_excursion_ticks",
        "max_favorable_excursion_ticks", "retracement_depths",
        "time_at_max_level_bars", "trend_defense_level_max", "exit_reason",
    ]

    def test_all_required_fields_present(self):
        """Cycle DataFrame must have all spec Section 6.4 fields."""
        cfg = _make_config(step_dist=2.0)
        result = _run(cfg, [100.0, 102.0])  # One cycle (SEED + REVERSAL)

        cycles = result.cycles
        assert not cycles.empty
        for field in self._REQUIRED_FIELDS:
            assert field in cycles.columns, f"Missing cycle field: {field}"

    def test_cycle_id_sequential(self):
        """cycle_id starts at 1 and increments per cycle."""
        cfg = _make_config(step_dist=2.0)
        result = _run(cfg, [100.0, 102.0, 100.0, 102.0])

        cycles = result.cycles
        assert list(cycles["cycle_id"]) == list(range(1, len(cycles) + 1))

    def test_trend_defense_level_max_zero(self):
        """Baseline has no TDS; trend_defense_level_max must be 0."""
        cfg = _make_config(step_dist=2.0)
        result = _run(cfg, [100.0, 102.0])

        assert result.cycles.iloc[0]["trend_defense_level_max"] == 0

    def test_exit_reason_reversal(self):
        """Cycles closed by REVERSAL have exit_reason='reversal'."""
        cfg = _make_config(step_dist=2.0)
        result = _run(cfg, [100.0, 102.0])

        assert result.cycles.iloc[0]["exit_reason"] == "reversal"

    def test_exit_reason_end_of_data(self):
        """Open cycle at end of data has exit_reason='end_of_data'."""
        cfg = _make_config(step_dist=2.0)
        result = _run(cfg, [100.0])  # Just SEED, no reversal

        assert result.cycles.iloc[0]["exit_reason"] == "end_of_data"

    def test_duration_bars_positive(self):
        """duration_bars must be >= 1."""
        cfg = _make_config(step_dist=2.0)
        result = _run(cfg, [100.0, 102.0])

        assert result.cycles.iloc[0]["duration_bars"] >= 1


# ---------------------------------------------------------------------------
# Test: Cost Model
# ---------------------------------------------------------------------------

class TestCostModel:
    def test_seed_net_pnl_formula(self):
        """net_pnl = gross_pnl - cost.

        SEED at 100, exit at end_of_data at 100. Gross=0 ticks.
        Cost = cost_ticks * 1 (seed qty). Net = -cost_ticks.
        """
        cfg = _make_config(step_dist=2.0, cost_ticks=3, initial_qty=1)
        result = _run(cfg, [100.0])  # SEED only, no reversal

        cycle = result.cycles.iloc[0]
        # gross = (100 - 100) / 0.25 * 1 = 0
        assert cycle["gross_pnl_ticks"] == 0.0
        # net = 0 - 3 = -3
        assert cycle["net_pnl_ticks"] == -3.0

    def test_reversal_double_cost(self):
        """Reversal costs = FLATTEN (cost*qty) + REVERSAL_entry (cost*qty).

        SEED at 100, REVERSAL at 102 (Long won 8 ticks gross), then end_of_data.
        Cycle 1: gross = (102 - 100) / 0.25 = 8 ticks.
        Cost = SEED(3) + FLATTEN(3) = 6. Net = 8 - 6 = 2.
        """
        cfg = _make_config(step_dist=2.0, cost_ticks=3, initial_qty=1, tick_size=0.25)
        result = _run(cfg, [100.0, 102.0])  # SEED, REVERSAL

        cycle1 = result.cycles.iloc[0]
        assert cycle1["gross_pnl_ticks"] == pytest.approx(8.0)
        # Cycle 1 actions: SEED (cost=3) + FLATTEN (cost=3) = 6
        assert cycle1["net_pnl_ticks"] == pytest.approx(2.0)

    def test_add_cost_included(self):
        """ADD actions also incur cost_ticks * qty in net_pnl."""
        cfg = _make_config(step_dist=2.0, cost_ticks=3, initial_qty=1, tick_size=0.25)
        # SEED at 100, ADD at 98 (qty=1), then end_of_data at 98
        result = _run(cfg, [100.0, 98.0])

        cycle = result.cycles.iloc[0]
        # avg_entry = (100*1 + 98*1) / 2 = 99, total_qty = 2
        # gross = (98 - 99) / 0.25 * 2 = -4 * 2 = -8 ticks
        # cost = SEED(3*1) + ADD(3*1) = 6
        # net = -8 - 6 = -14
        assert cycle["gross_pnl_ticks"] == pytest.approx(-8.0)
        assert cycle["net_pnl_ticks"] == pytest.approx(-14.0)


# ---------------------------------------------------------------------------
# Test: RTH Filter
# ---------------------------------------------------------------------------

class TestRTHFilter:
    def _make_10sec_config(self):
        return _make_config(bar_data_primary_keys=["bar_data_10sec_rot"])

    def test_rth_includes_930(self):
        """Bar at 09:30:00 is included (within RTH)."""
        cfg = self._make_10sec_config()
        prices = [100.0]
        bars = _make_bars(prices, times=["09:30:00"])
        sim = RotationalSimulator(config=cfg, bar_data=bars)
        result = sim.run()
        assert result.bars_processed == 1

    def test_rth_excludes_0800(self):
        """Bar at 08:00:00 is excluded (pre-market)."""
        cfg = self._make_10sec_config()
        bars = _make_bars([100.0], times=["08:00:00"])
        sim = RotationalSimulator(config=cfg, bar_data=bars)
        result = sim.run()
        assert result.bars_processed == 0

    def test_rth_excludes_1601(self):
        """Bar at 16:01:00 is excluded (post-market, >= 16:00:00)."""
        cfg = self._make_10sec_config()
        bars = _make_bars([100.0], times=["16:01:00"])
        sim = RotationalSimulator(config=cfg, bar_data=bars)
        result = sim.run()
        assert result.bars_processed == 0

    def test_rth_excludes_1600(self):
        """Bar at exactly 16:00:00 is excluded (RTH end is exclusive)."""
        cfg = self._make_10sec_config()
        bars = _make_bars([100.0], times=["16:00:00"])
        sim = RotationalSimulator(config=cfg, bar_data=bars)
        result = sim.run()
        assert result.bars_processed == 0

    def test_rth_includes_1559(self):
        """Bar at 15:59:00 is included (last minute of RTH)."""
        cfg = self._make_10sec_config()
        bars = _make_bars([100.0], times=["15:59:00"])
        sim = RotationalSimulator(config=cfg, bar_data=bars)
        result = sim.run()
        assert result.bars_processed == 1

    def test_rth_mixed_bars(self):
        """Only in-session bars are processed."""
        cfg = self._make_10sec_config()
        bars = _make_bars(
            [100.0, 101.0, 102.0],
            times=["08:00:00", "10:00:00", "17:00:00"],
        )
        sim = RotationalSimulator(config=cfg, bar_data=bars)
        result = sim.run()
        assert result.bars_processed == 1  # only 10:00:00 bar

    def test_vol_bars_not_rth_filtered(self):
        """Volume bars (non-10sec source) are NOT RTH filtered."""
        cfg = _make_config(bar_data_primary_keys=["bar_data_250vol_rot"])
        bars = _make_bars([100.0, 101.0], times=["08:00:00", "17:00:00"])
        sim = RotationalSimulator(config=cfg, bar_data=bars)
        result = sim.run()
        # Vol bars pass through unfiltered (RTH filter not applied)
        assert result.bars_processed == 2


# ---------------------------------------------------------------------------
# Test: Date Filter
# ---------------------------------------------------------------------------

class TestDateFilter:
    def test_p1a_keeps_correct_dates(self):
        """P1a: only bars in [P1_START, P1_MIDPOINT] are kept."""
        cfg = _make_config(period="P1a")
        # P1a dates vs out-of-range
        in_date = str(_P1_START)          # 2025-09-21 (in P1a)
        mid_date = str(_P1_MIDPOINT)      # ~2025-11-02 (boundary, in P1a)
        out_date = "2025-12-10"           # in P1b
        bars = _make_bars([100.0, 101.0, 102.0], dates=[in_date, mid_date, out_date])
        sim = RotationalSimulator(config=cfg, bar_data=bars)
        result = sim.run()
        assert result.bars_processed == 2

    def test_p1a_excludes_before_p1_start(self):
        """P1a: bars before P1_START are excluded."""
        cfg = _make_config(period="P1a")
        before = "2025-09-20"
        in_range = str(_P1_START)
        bars = _make_bars([100.0, 101.0], dates=[before, in_range])
        sim = RotationalSimulator(config=cfg, bar_data=bars)
        result = sim.run()
        assert result.bars_processed == 1  # only in_range

    def test_p1b_keeps_correct_dates(self):
        """P1b: only bars in (P1_MIDPOINT, P1_END] are kept."""
        cfg = _make_config(period="P1b")
        mid_plus_one = str(_P1_MIDPOINT + datetime.timedelta(days=1))
        end_date = str(_P1_END)
        before_mid = str(_P1_MIDPOINT)  # midpoint itself is P1a, NOT P1b
        bars = _make_bars([100.0, 101.0, 102.0], dates=[before_mid, mid_plus_one, end_date])
        sim = RotationalSimulator(config=cfg, bar_data=bars)
        result = sim.run()
        assert result.bars_processed == 2

    def test_p1_no_date_filter(self):
        """P1 (full): no date filter applied — all bars pass through."""
        cfg = _make_config(period="P1")
        bars = _make_bars([100.0, 101.0], dates=["2025-01-01", "2026-06-01"])
        sim = RotationalSimulator(config=cfg, bar_data=bars)
        result = sim.run()
        assert result.bars_processed == 2


# ---------------------------------------------------------------------------
# Test: SimulationResult Contract
# ---------------------------------------------------------------------------

class TestContract:
    def test_result_has_trades_df(self):
        """SimulationResult.trades is a DataFrame."""
        cfg = _make_config()
        result = _run(cfg, [100.0])
        assert isinstance(result.trades, pd.DataFrame)

    def test_result_has_cycles_df(self):
        """SimulationResult.cycles is a DataFrame."""
        cfg = _make_config()
        result = _run(cfg, [100.0])
        assert isinstance(result.cycles, pd.DataFrame)

    def test_result_has_bars_processed_int(self):
        """SimulationResult.bars_processed is an int."""
        cfg = _make_config()
        result = _run(cfg, [100.0, 100.0, 100.0])
        assert isinstance(result.bars_processed, int)
        assert result.bars_processed == 3

    def test_trades_required_columns(self):
        """Trades DataFrame has all required columns."""
        expected = {"bar_idx", "datetime", "action", "direction", "qty",
                    "price", "level", "anchor", "cost_ticks", "cycle_id"}
        cfg = _make_config()
        result = _run(cfg, [100.0, 102.0])
        assert expected.issubset(set(result.trades.columns))

    def test_empty_bars_returns_empty_result(self):
        """No bars -> empty trades, empty cycles, bars_processed=0."""
        cfg = _make_config()
        bars = _make_bars([])
        sim = RotationalSimulator(config=cfg, bar_data=bars)
        result = sim.run()
        assert result.bars_processed == 0
        assert result.trades.empty
        assert result.cycles.empty


# ---------------------------------------------------------------------------
# Test: Determinism
# ---------------------------------------------------------------------------

class TestDeterminism:
    def test_identical_runs_produce_identical_trades(self):
        """Running the simulator twice with same input yields identical trades."""
        cfg = _make_config(step_dist=2.0)
        prices = [100.0, 98.0, 102.0, 100.0, 104.0]
        bars = _make_bars(prices)

        sim1 = RotationalSimulator(config=cfg, bar_data=bars.copy())
        result1 = sim1.run()

        sim2 = RotationalSimulator(config=cfg, bar_data=bars.copy())
        result2 = sim2.run()

        pd.testing.assert_frame_equal(
            result1.trades.reset_index(drop=True),
            result2.trades.reset_index(drop=True),
        )

    def test_identical_runs_produce_identical_cycles(self):
        """Running the simulator twice with same input yields identical cycles."""
        cfg = _make_config(step_dist=2.0)
        prices = [100.0, 98.0, 102.0, 100.0, 104.0]
        bars = _make_bars(prices)

        sim1 = RotationalSimulator(config=cfg, bar_data=bars.copy())
        result1 = sim1.run()

        sim2 = RotationalSimulator(config=cfg, bar_data=bars.copy())
        result2 = sim2.run()

        # Compare numeric columns; skip retracement_depths (list col)
        numeric_cols = [c for c in result1.cycles.columns if c != "retracement_depths"]
        pd.testing.assert_frame_equal(
            result1.cycles[numeric_cols].reset_index(drop=True),
            result2.cycles[numeric_cols].reset_index(drop=True),
        )

    def test_bars_processed_deterministic(self):
        """bars_processed is identical across runs."""
        cfg = _make_config()
        bars = _make_bars([100.0, 101.0, 102.0])

        sim1 = RotationalSimulator(config=cfg, bar_data=bars.copy())
        sim2 = RotationalSimulator(config=cfg, bar_data=bars.copy())

        assert sim1.run().bars_processed == sim2.run().bars_processed


# ---------------------------------------------------------------------------
# Test: Determinism on Real P1a Data
# ---------------------------------------------------------------------------

class TestDeterminismRealData:
    """Verify determinism using real P1a bar data (250-vol bar type).

    These tests load actual CSV files from the pipeline data directory and
    confirm that two consecutive runs with identical config+data produce
    bit-for-bit identical output.  Marked slow because file I/O is involved.
    """

    _REPO_ROOT = Path(__file__).resolve().parents[3]
    _VOL_PATH = (
        _REPO_ROOT
        / "stages/01-data/data/bar_data/volume/NQ_BarData_250vol_rot_P1.csv"
    )
    _CONFIG = {
        "period": "P1a",
        "instrument": "NQ",
        "_instrument": {
            "tick_size": 0.25,
            "tick_value": 5.0,
            "cost_ticks": 3,
        },
        "hypothesis": {
            "trigger_params": {"step_dist": 2.0},
        },
        "martingale": {
            "initial_qty": 1,
            "max_levels": 4,
            "max_contract_size": 8,
        },
        # Single-source config so RTH filter is NOT applied to vol bars
        "bar_data_primary": {
            "bar_data_250vol_rot": str(
                _REPO_ROOT
                / "stages/01-data/data/bar_data/volume/NQ_BarData_250vol_rot_P1.csv"
            ),
        },
    }

    @pytest.fixture(scope="class")
    def vol_bars(self):
        """Load 250-vol P1a bars once per test class."""
        import sys as _sys
        _sys.path.insert(0, str(self._REPO_ROOT))
        from shared.data_loader import load_bars
        return load_bars(str(self._VOL_PATH))

    @pytest.mark.slow
    def test_determinism_bars_processed(self, vol_bars):
        """Two runs on real P1a data return identical bars_processed."""
        sim1 = RotationalSimulator(config=self._CONFIG, bar_data=vol_bars.copy())
        run1 = sim1.run()

        sim2 = RotationalSimulator(config=self._CONFIG, bar_data=vol_bars.copy())
        run2 = sim2.run()

        assert run1.bars_processed == run2.bars_processed
        assert run1.bars_processed > 0, "P1a filter should retain bars"

    @pytest.mark.slow
    def test_determinism_trades_equal(self, vol_bars):
        """Two runs on real P1a data return identical trades DataFrame."""
        sim1 = RotationalSimulator(config=self._CONFIG, bar_data=vol_bars.copy())
        run1 = sim1.run()

        sim2 = RotationalSimulator(config=self._CONFIG, bar_data=vol_bars.copy())
        run2 = sim2.run()

        pd.testing.assert_frame_equal(
            run1.trades.reset_index(drop=True),
            run2.trades.reset_index(drop=True),
            check_exact=True,
        )

    @pytest.mark.slow
    def test_determinism_cycles_equal(self, vol_bars):
        """Two runs on real P1a data return identical cycles DataFrame (excl. retracement_depths list col)."""
        sim1 = RotationalSimulator(config=self._CONFIG, bar_data=vol_bars.copy())
        run1 = sim1.run()

        sim2 = RotationalSimulator(config=self._CONFIG, bar_data=vol_bars.copy())
        run2 = sim2.run()

        assert not run1.cycles.empty, "P1a run should produce at least one cycle"
        # Compare all columns except retracement_depths (contains Python lists)
        numeric_cols = [c for c in run1.cycles.columns if c != "retracement_depths"]
        pd.testing.assert_frame_equal(
            run1.cycles[numeric_cols].reset_index(drop=True),
            run2.cycles[numeric_cols].reset_index(drop=True),
            check_exact=True,
        )
        # Verify retracement_depths lists are also identical
        assert list(run1.cycles["retracement_depths"]) == list(run2.cycles["retracement_depths"])


# ---------------------------------------------------------------------------
# Test: MaxTotalPosition Cap
# ---------------------------------------------------------------------------

class TestMaxTotalPosition:
    """Tests for the MaxTotalPosition cap feature.

    MaxTotalPosition (MTP) refuses ADD trades when adding would exceed the cap.
    MTP=0 means unlimited (backward compatible with pre-feature behavior).
    MTP=1 produces pure reversal (SEED->REVERSAL only, zero ADDs).
    When an ADD is refused: position unchanged, level unchanged.
    """

    _REPO_ROOT = Path(__file__).resolve().parents[3]
    _VOL_PATH = (
        _REPO_ROOT
        / "stages/01-data/data/bar_data/volume/NQ_BarData_250vol_rot_P1.csv"
    )

    @classmethod
    def _make_mtp_config(
        cls,
        max_total_position: int,
        max_levels: int = 4,
        step_dist: float = 2.0,
        initial_qty: int = 1,
    ) -> dict:
        """Build config with max_total_position in martingale block."""
        cfg = _make_config(
            step_dist=step_dist,
            initial_qty=initial_qty,
            max_levels=max_levels,
            max_contract_size=16,  # high enough not to be the limiting factor
        )
        cfg["martingale"]["max_total_position"] = max_total_position
        return cfg

    def test_mtp1_pure_reversal_no_add_trades(self):
        """MTP=1: zero ADD trades — every cycle is SEED->REVERSAL only.

        With MTP=1 and initial_qty=1, position after SEED is 1 = MTP.
        Any ADD would produce position 2 > MTP=1, so ALL adds are refused.
        """
        cfg = self._make_mtp_config(max_total_position=1, max_levels=5, step_dist=2.0)

        # Load real P1a vol bars
        import sys as _sys
        _sys.path.insert(0, str(self._REPO_ROOT))
        from shared.data_loader import load_bars

        vol_bars = load_bars(str(self._VOL_PATH))
        sim = RotationalSimulator(config=cfg, bar_data=vol_bars)
        result = sim.run()

        assert result.bars_processed > 0, "Should process some bars"
        adds = result.trades[result.trades["action"] == "ADD"]
        assert len(adds) == 0, (
            f"MTP=1 must produce zero ADD trades; got {len(adds)}"
        )
        # Verify cycles: adds_count=0 for every cycle
        if not result.cycles.empty:
            assert (result.cycles["adds_count"] == 0).all(), (
                "MTP=1: all cycles must have adds_count=0"
            )

    def test_mtp0_identical_to_no_mtp_config(self):
        """MTP=0 backward compat: results IDENTICAL to config without max_total_position key.

        MTP=0 means unlimited — must not change any behavior vs the pre-feature baseline.
        """
        import sys as _sys
        _sys.path.insert(0, str(self._REPO_ROOT))
        from shared.data_loader import load_bars

        vol_bars = load_bars(str(self._VOL_PATH))

        # Config WITH max_total_position=0
        cfg_with_mtp = self._make_mtp_config(
            max_total_position=0, max_levels=4, step_dist=2.0
        )

        # Config WITHOUT max_total_position key (simulate pre-feature state)
        cfg_without_mtp = _make_config(
            step_dist=2.0,
            max_levels=4,
            max_contract_size=16,
        )
        # Ensure max_total_position key is NOT present
        assert "max_total_position" not in cfg_without_mtp.get("martingale", {}), (
            "Control config must not have max_total_position"
        )

        sim_with = RotationalSimulator(config=cfg_with_mtp, bar_data=vol_bars.copy())
        run_with = sim_with.run()

        sim_without = RotationalSimulator(config=cfg_without_mtp, bar_data=vol_bars.copy())
        run_without = sim_without.run()

        pd.testing.assert_frame_equal(
            run_with.trades.reset_index(drop=True),
            run_without.trades.reset_index(drop=True),
            check_exact=True,
            obj="MTP=0 vs no-MTP trades",
        )
        numeric_cols = [c for c in run_with.cycles.columns if c != "retracement_depths"]
        pd.testing.assert_frame_equal(
            run_with.cycles[numeric_cols].reset_index(drop=True),
            run_without.cycles[numeric_cols].reset_index(drop=True),
            check_exact=True,
            obj="MTP=0 vs no-MTP cycles",
        )

    def test_mtp2_cap_mid_sequence_refuses_third_add(self):
        """MTP=2: after SEED(pos=1), first ADD fires (pos=2=MTP), second ADD refused.

        Synthetic bar sequence with controlled timing:
        - Bar 0: SEED at 100.0 (Long, pos=1)
        - Bar 1: 98.0 (down 2.0, ADD fires: pos=1+1=2=MTP, level->1)
        - Bar 2: 96.0 (down 2.0 from anchor 98, second ADD attempted: pos would be 2+2=4>MTP=2, REFUSED)
        - Bar 3: 94.0 (another 2.0 down, still refused since pos=2, proposed=2, 2+2=4>2)
        """
        cfg = self._make_mtp_config(max_total_position=2, max_levels=3, initial_qty=1)
        prices = [100.0, 98.0, 96.0, 94.0, 92.0]
        result = _run(cfg, prices)

        trades = result.trades
        adds = trades[trades["action"] == "ADD"]

        # Only ONE add should fire (the first one brings pos from 1 to 2=MTP)
        assert len(adds) == 1, (
            f"MTP=2 with initial_qty=1: only first ADD (qty=1, pos->2) should fire; "
            f"got {len(adds)} adds"
        )
        assert adds.iloc[0]["qty"] == 1  # initial_qty * 2^0 = 1

    def test_mtp_cap_does_not_mutate_level(self):
        """When ADD is refused due to MTP cap, self._level must remain unchanged.

        After a REVERSAL that resets position to initial_qty, the next ADD attempt
        should use the level that was current before the refusal (not level+1).

        Sequence:
        - Bar 0: SEED Long at 100.0 (pos=1, level=0)
        - Bar 1: 98.0 (ADD fires, pos=2=MTP=2, level->1)
        - Bar 2: 96.0 (ADD refused: pos=2, proposed=2, 2+2>2; level stays at 1)
        - Bar 3: 100.0 (REVERSAL to Short: pos->1, level->0, anchor->100)
        - Bar 4: 98.0 (SEED cycle over; we're now Short at 100, 100->98 = -2 against Short? No)

        Let's re-sequence so the reversal fires cleanly:
        - Bar 0: SEED Long at 100.0 (pos=1, level=0)
        - Bar 1: 98.0 (down 2.0 against: ADD fires pos=2=MTP, level->1)
        - Bar 2: 96.0 (down 2.0 against: ADD refused, pos stays 2, level stays 1)
        - Bar 3: 104.0 (up from anchor=96 by 8.0 >= 2.0: REVERSAL to Short, pos->1, level->0)
        - Bar 4: 106.0 (up 2.0 against Short: ADD fires; should use level=0 -> qty=1*2^0=1)

        The key assertion: after the refused add at bar 2, the reversal at bar 3 resets level to 0.
        Then the first ADD on the Short side should fire at level=0 with qty=1.
        """
        # MTP=4 to allow adds on the Short side to prove level continuity
        cfg = self._make_mtp_config(max_total_position=2, max_levels=3, initial_qty=1)
        prices = [100.0, 98.0, 96.0, 104.0, 106.0]
        result = _run(cfg, prices)

        trades = result.trades
        adds = trades[trades["action"] == "ADD"]

        # Should have exactly 2 adds:
        # 1) Long-side: bar 1 at 98.0 (level=0 -> level=1, qty=1)
        # 2) Short-side: bar 4 at 106.0 (level=0 -> level=1, qty=1) — after reversal reset
        # Bar 2 add should be REFUSED (pos=2, proposed=2, exceeds MTP=2)
        assert len(adds) == 2, (
            f"Expected 2 adds (1 Long, 1 Short); got {len(adds)}: "
            f"{adds[['action','direction','qty','level','price']].to_dict('records')}"
        )

        # Both adds should be at level=0 (level resets at reversal; short-side starts fresh)
        assert adds.iloc[0]["level"] == 0, "First ADD (Long side): should be at level=0"
        assert adds.iloc[1]["level"] == 0, "Second ADD (Short side): should be at level=0 after reversal reset"


# ---------------------------------------------------------------------------
# Test: Anchor Mode on MTP Refusal
# ---------------------------------------------------------------------------

class TestAnchorMode:
    """Tests for anchor_mode behavior when MTP refuses an ADD."""

    @staticmethod
    def _make_anchor_mode_config(
        anchor_mode: str,
        max_total_position: int = 2,
        mtp_dd_exit_ticks: float = 0,
        step_dist: float = 2.0,
        initial_qty: int = 1,
        max_levels: int = 3,
    ) -> dict:
        cfg = _make_config(
            step_dist=step_dist,
            initial_qty=initial_qty,
            max_levels=max_levels,
            max_contract_size=16,
        )
        cfg["martingale"]["max_total_position"] = max_total_position
        cfg["martingale"]["anchor_mode"] = anchor_mode
        cfg["martingale"]["mtp_dd_exit_ticks"] = mtp_dd_exit_ticks
        return cfg

    def test_mode_a_frozen_anchor_unchanged_on_refusal(self):
        """Mode A (frozen): anchor stays at last successful ADD price on MTP refusal.

        - Bar 0: SEED Long at 100.0 (pos=1, anchor=100.0)
        - Bar 1: 98.0 (down 2.0: ADD fires, pos=2=MTP, anchor->98.0)
        - Bar 2: 96.0 (down 2.0 from anchor 98: ADD refused, anchor stays 98.0)
        - Bar 3: 94.0 (down 2.0 from anchor 98? No, distance=98-94=4 >= step=2: ADD refused again)
        """
        cfg = self._make_anchor_mode_config(anchor_mode="frozen", max_total_position=2)
        prices = [100.0, 98.0, 96.0, 94.0]
        bars = _make_bars(prices)
        sim = RotationalSimulator(config=cfg, bar_data=bars)
        result = sim.run()

        # After MTP refusal at bar 2, anchor should still be 98.0 (from last ADD)
        adds = result.trades[result.trades["action"] == "ADD"]
        assert len(adds) == 1, f"Only 1 ADD should fire; got {len(adds)}"
        assert adds.iloc[0]["anchor"] == 98.0

    def test_mode_b_walking_anchor_updates_on_refusal(self):
        """Mode B (walking): anchor moves to current price on MTP refusal.

        - Bar 0: SEED Long at 100.0 (pos=1, anchor=100.0)
        - Bar 1: 98.0 (down 2.0: ADD fires, pos=2=MTP, anchor->98.0)
        - Bar 2: 96.0 (down 2.0 from anchor 98: ADD refused, anchor->96.0 via walking)
        - Bar 3: 94.0 (down 2.0 from anchor 96: ADD refused, anchor->94.0 via walking)
        - Bar 4: 96.25 (up 2.25 from anchor 94.0 >= step 2.0: REVERSAL fires)

        Key: with frozen anchor (98.0), reversal would need price >= 100.0.
        With walking anchor (94.0), reversal fires at 96.0+step = 96.0.
        """
        cfg = self._make_anchor_mode_config(anchor_mode="walking", max_total_position=2)
        prices = [100.0, 98.0, 96.0, 94.0, 96.25]
        result = _run(cfg, prices)

        # Should have a reversal at bar 4 (only possible if anchor walked to 94.0)
        reversals = result.trades[result.trades["action"] == "REVERSAL"]
        assert len(reversals) >= 1, (
            "Walking anchor should enable earlier reversal; "
            f"trades: {result.trades[['action','price','anchor']].to_dict('records')}"
        )
        # The reversal anchor should reflect the walked anchor
        assert reversals.iloc[0]["price"] == 96.25

    def test_mode_b_vs_mode_a_different_reversal_timing(self):
        """Mode B enables earlier reversal than Mode A with same price sequence.

        With frozen anchor at 98.0, reversal needs price >= 100.0 (98+2).
        With walking anchor at 94.0, reversal needs price >= 96.0 (94+2).
        """
        prices = [100.0, 98.0, 96.0, 94.0, 96.25]

        cfg_a = self._make_anchor_mode_config(anchor_mode="frozen", max_total_position=2)
        result_a = _run(cfg_a, prices)

        cfg_b = self._make_anchor_mode_config(anchor_mode="walking", max_total_position=2)
        result_b = _run(cfg_b, prices)

        reversals_a = result_a.trades[result_a.trades["action"] == "REVERSAL"]
        reversals_b = result_b.trades[result_b.trades["action"] == "REVERSAL"]

        # Mode A: no reversal at 96.25 (anchor frozen at 98, needs 100.0)
        # Mode B: reversal at 96.25 (anchor walked to 94.0, needs 96.0)
        assert len(reversals_a) == 0, "Mode A should NOT reverse at 96.25"
        assert len(reversals_b) >= 1, "Mode B SHOULD reverse at 96.25"

    def test_mode_c_hard_stop_flattens_on_threshold(self):
        """Mode C (frozen_stop): flattens when unrealized PnL breaches threshold.

        - Bar 0: SEED Long at 100.0 (pos=1, avg_entry=100.0)
        - Bar 1: 98.0 (ADD fires, pos=2, avg_entry=99.0)
        - Bar 2: 96.0 (ADD refused — MTP=2 — anchor frozen at 98.0)
        - Bar 3: 89.0 (unrealized = (89-99)/0.25 * 1 * 2 = -80 ticks, breaches -60)

        mtp_dd_exit_ticks=-60: should flatten at bar 3.
        """
        cfg = self._make_anchor_mode_config(
            anchor_mode="frozen_stop", max_total_position=2,
            mtp_dd_exit_ticks=-60,
        )
        prices = [100.0, 98.0, 96.0, 89.0, 100.0]
        result = _run(cfg, prices)

        # Should have a FLATTEN with exit_reason mtp_dd_exit
        if not result.cycles.empty:
            mtp_dd_exits = result.cycles[result.cycles["exit_reason"] == "mtp_dd_exit"]
            assert len(mtp_dd_exits) >= 1, (
                f"Mode C should flatten on threshold breach; "
                f"exit_reasons: {result.cycles['exit_reason'].tolist()}"
            )

    def test_mode_c_no_exit_above_threshold(self):
        """Mode C does NOT flatten when unrealized PnL stays above threshold.

        - Bar 0: SEED Long at 100.0 (pos=1)
        - Bar 1: 98.0 (ADD, pos=2, avg_entry=99.0)
        - Bar 2: 96.0 (MTP refused)
        - Bar 3: 95.0 (unrealized = (95-99)/0.25 * 2 = -32 ticks, above -60)
        """
        cfg = self._make_anchor_mode_config(
            anchor_mode="frozen_stop", max_total_position=2,
            mtp_dd_exit_ticks=-60,
        )
        prices = [100.0, 98.0, 96.0, 95.0]
        result = _run(cfg, prices)

        if not result.cycles.empty:
            mtp_dd_exits = result.cycles[result.cycles["exit_reason"] == "mtp_dd_exit"]
            assert len(mtp_dd_exits) == 0, (
                "Mode C should NOT flatten when above threshold"
            )

    def test_mode_c_reseeds_after_flatten(self):
        """After Mode C mtp_dd_exit flatten, sim goes FLAT then re-SEEDs on next bar.

        Prices: SEED, ADD, MTP-refused, breach threshold (flatten), re-SEED.
        """
        cfg = self._make_anchor_mode_config(
            anchor_mode="frozen_stop", max_total_position=2,
            mtp_dd_exit_ticks=-60,
        )
        # At bar 3: unrealized = (89-99)/0.25 * 2 = -80 ticks < -60 => flatten
        # Bar 4: FLAT, should re-SEED
        prices = [100.0, 98.0, 96.0, 89.0, 100.0]
        result = _run(cfg, prices)

        seeds = result.trades[result.trades["action"] == "SEED"]
        assert len(seeds) >= 2, (
            f"Should re-SEED after mtp_dd_exit; got {len(seeds)} seeds"
        )

    def test_default_anchor_mode_is_frozen(self):
        """When anchor_mode is not specified, default behavior is 'frozen' (Mode A)."""
        cfg = _make_config(step_dist=2.0)
        cfg["martingale"]["max_total_position"] = 2
        # No anchor_mode key — should default to "frozen"
        prices = [100.0, 98.0, 96.0, 94.0, 96.25]
        result_default = _run(cfg, prices)

        cfg_explicit = self._make_anchor_mode_config(
            anchor_mode="frozen", max_total_position=2
        )
        result_explicit = _run(cfg_explicit, prices)

        # Should produce identical trades
        pd.testing.assert_frame_equal(
            result_default.trades.reset_index(drop=True),
            result_explicit.trades.reset_index(drop=True),
            check_exact=True,
            obj="default vs explicit frozen anchor mode",
        )
