# archetype: rotational
"""Rotational simulator — continuous state machine for the rotational archetype.

Implements:
    - RotationalSimulator: bar-by-bar state machine (FLAT/POSITIONED, SEED/REVERSAL/ADD)
    - FeatureComputer: static feature pass-through (Phase B: baseline uses CSV columns only)
    - TradeLogger: cycle-level record accumulator per spec Section 6.4
    - RTH session filter for 10-sec bars (09:30-16:00 ET)
    - P1a / P1b date filtering (first/second half of the P1 window)

Usage (engine calls):
    simulator = RotationalSimulator(config=config, bar_data=bars, reference_data=None)
    result = simulator.run()
    # result.trades: pd.DataFrame of individual actions
    # result.cycles: pd.DataFrame of cycle summaries
    # result.bars_processed: int
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

try:
    from trend_defense import TrendDefenseSystem  # noqa: F401
    _TDS_AVAILABLE = True
except ImportError:
    _TDS_AVAILABLE = False

# ---------------------------------------------------------------------------
# P1 rotational date boundaries (frozen per spec)
# ---------------------------------------------------------------------------

_P1_START = datetime.date(2025, 9, 21)
_P1_END = datetime.date(2025, 12, 14)
_P1_MIDPOINT: datetime.date = _P1_START + (_P1_END - _P1_START) / 2  # ~2025-11-02

# RTH session limits for 10-sec bars (per simulation_rules.md)
_RTH_START = datetime.time(9, 30, 0)
_RTH_END = datetime.time(16, 0, 0)  # exclusive


# ---------------------------------------------------------------------------
# SimulationResult contract (must match rotational_engine.py load_simulator)
# ---------------------------------------------------------------------------

@dataclass
class SimulationResult:
    """Output of RotationalSimulator.run().

    Attributes:
        trades: DataFrame of individual trade actions (one row per action).
        cycles: DataFrame of cycle-level summaries (one row per reversal cycle).
        bars_processed: Number of bars fed to the simulation loop.
    """
    trades: pd.DataFrame
    cycles: pd.DataFrame
    bars_processed: int


# ---------------------------------------------------------------------------
# FeatureComputer
# ---------------------------------------------------------------------------

class FeatureComputer:
    """Compute features for each bar before simulation.

    Phase B (baseline): ATR and SD bands are already present in the CSV columns;
    no additional computation is required. The method is a no-op pass-through so
    that Phase C can add computed features by overriding or extending this class.

    Args:
        config: Full config dict (for future parameterisation).
    """

    def __init__(self, config: dict) -> None:
        self._config = config

    def compute_static_features(self, bar_df: pd.DataFrame) -> pd.DataFrame:
        """Return bar_df with any additional feature columns appended.

        For the baseline (trigger_mechanism="fixed", no active_filters, no
        structural_mods), returns bar_df unchanged — all needed columns
        (ATR, SD bands, etc.) are already present in the CSV.

        For hypothesis configs that require computed features, dispatches to
        feature_engine.compute_hypothesis_features() which returns a new
        DataFrame with feature columns appended (vectorized, entry-time safe).
        """
        hyp = self._config.get("hypothesis", {})
        trigger = hyp.get("trigger_mechanism", "fixed")
        active_filters = hyp.get("active_filters", [])
        structural_mods = hyp.get("structural_mods", [])

        needs_features = (
            trigger != "fixed"
            or bool(active_filters)
            or bool(structural_mods)
        )

        if not needs_features:
            return bar_df

        # Import feature_engine dynamically to avoid circular imports
        # and to keep the simulator self-contained.
        try:
            from feature_engine import compute_hypothesis_features  # noqa: PLC0415
            return compute_hypothesis_features(bar_df, hyp)
        except Exception:
            # If feature engine unavailable (e.g., missing module), return unchanged
            return bar_df


# ---------------------------------------------------------------------------
# TradeLogger
# ---------------------------------------------------------------------------

class TradeLogger:
    """Accumulate individual trade actions and finalize cycle records.

    Args:
        tick_size: Instrument tick size (e.g. 0.25 for NQ).
        cost_ticks: Per-action round-trip cost in ticks (e.g. 3 for NQ).
    """

    def __init__(self, tick_size: float, cost_ticks: int) -> None:
        self._tick_size = tick_size
        self._cost_ticks = cost_ticks
        self._trades: list[dict] = []
        self._cycles: list[dict] = []

    # -- Trade logging -------------------------------------------------------

    def log_action(
        self,
        bar_idx: int,
        dt: object,
        action: str,
        direction: str,
        qty: int,
        price: float,
        level: int,
        anchor: float,
        cycle_id: int,
        price_source: str = "close",
    ) -> None:
        """Append a single trade action row."""
        self._trades.append({
            "bar_idx": bar_idx,
            "datetime": dt,
            "action": action,
            "direction": direction,
            "qty": qty,
            "price": price,
            "level": level,
            "anchor": anchor,
            "cost_ticks": self._cost_ticks * qty,
            "cycle_id": cycle_id,
            "price_source": price_source,
        })

    # -- Cycle finalization --------------------------------------------------

    def finalize_cycle(
        self,
        cycle_id: int,
        start_bar: int,
        end_bar: int,
        direction: str,
        trades_in_cycle: list[dict],
        bars_df: pd.DataFrame,
        exit_price: float,
        exit_reason: str,
        trend_defense_level_max: int = 0,
    ) -> None:
        """Compute and store a cycle record with all spec Section 6.4 fields.

        Args:
            cycle_id: Unique cycle identifier.
            start_bar: First bar index of this cycle (in filtered bar_df index).
            end_bar: Last bar index (inclusive) of this cycle.
            direction: "Long" or "Short".
            trades_in_cycle: List of trade dicts for this cycle (from log_action).
            bars_df: Full filtered bar DataFrame (used for bar-by-bar MAE/MFE).
            exit_price: Price at which the cycle is closed (reversal close or end-of-data close).
            exit_reason: "reversal" or "end_of_data".
        """
        tick_size = self._tick_size
        cost_ticks = self._cost_ticks

        # Separate entry trades from FLATTEN (FLATTEN belongs to exiting, not entering)
        entry_trades = [t for t in trades_in_cycle if t["action"] in ("SEED", "REVERSAL", "ADD")]
        flatten_trades = [t for t in trades_in_cycle if t["action"] == "FLATTEN"]

        # Weighted average entry price
        total_qty = sum(t["qty"] for t in entry_trades)
        if total_qty > 0:
            avg_entry = sum(t["price"] * t["qty"] for t in entry_trades) / total_qty
        else:
            avg_entry = exit_price

        # Gross PnL in ticks
        # Long: exit higher = profit; Short: exit lower = profit
        if direction == "Long":
            gross_pnl_ticks = (exit_price - avg_entry) / tick_size * total_qty
        else:
            gross_pnl_ticks = (avg_entry - exit_price) / tick_size * total_qty

        # Net PnL: subtract cost_ticks * qty for every action (including FLATTEN)
        total_cost = sum(t["cost_ticks"] for t in trades_in_cycle)
        net_pnl_ticks = gross_pnl_ticks - total_cost

        # Adds count and levels
        adds = [t for t in entry_trades if t["action"] == "ADD"]
        adds_count = len(adds)
        max_level = max((t["level"] for t in entry_trades), default=0)

        # Maximum position size during cycle
        # Reconstruct running position qty
        max_position_qty = 0
        running_qty = 0
        for t in trades_in_cycle:
            if t["action"] == "FLATTEN":
                running_qty = 0
            elif t["action"] in ("SEED", "REVERSAL", "ADD"):
                running_qty += t["qty"]
                max_position_qty = max(max_position_qty, running_qty)

        # Duration
        duration_bars = end_bar - start_bar + 1

        # MAE / MFE — bar-level unrealized PnL during cycle
        cycle_bars = bars_df.iloc[start_bar: end_bar + 1]
        mae_ticks = 0.0
        mfe_ticks = 0.0
        retracement_depths: list[float] = []
        time_at_max_level_bars = 0

        if not cycle_bars.empty and "Last" in cycle_bars.columns:
            running_qty_for_excursion = 0
            entry_idx = 0  # which entry_trades we've processed
            peak_mfe = 0.0  # track MFE for retracement calculation
            current_max_level = 0

            for row_offset, (_, row) in enumerate(cycle_bars.iterrows()):
                bar_abs = start_bar + row_offset
                # Apply any entries that happen at or before this bar
                while entry_idx < len(entry_trades) and entry_trades[entry_idx]["bar_idx"] <= bar_abs:
                    t = entry_trades[entry_idx]
                    running_qty_for_excursion += t["qty"]
                    if t["action"] == "ADD":
                        current_max_level = max(current_max_level, t["level"])
                    entry_idx += 1

                if running_qty_for_excursion == 0:
                    continue

                close = row["Last"]
                if direction == "Long":
                    unrealized = (close - avg_entry) / tick_size * running_qty_for_excursion
                else:
                    unrealized = (avg_entry - close) / tick_size * running_qty_for_excursion

                mfe_ticks = max(mfe_ticks, unrealized)
                mae_ticks = min(mae_ticks, unrealized)

                # Retracement: if price pulls back from MFE peak
                if unrealized > peak_mfe:
                    peak_mfe = unrealized
                elif peak_mfe > 0 and unrealized < peak_mfe:
                    ratio = (peak_mfe - unrealized) / peak_mfe
                    if retracement_depths and abs(ratio - retracement_depths[-1]) < 0.001:
                        pass  # avoid duplicate samples at same bar
                    else:
                        retracement_depths.append(round(ratio, 4))

                # time_at_max_level_bars: count bars where level == max_level_reached
                if current_max_level == max_level and max_level > 0:
                    time_at_max_level_bars += 1

        # Entry price for cycle = price at SEED or REVERSAL (first entry trade)
        entry_price = entry_trades[0]["price"] if entry_trades else avg_entry

        self._cycles.append({
            "cycle_id": cycle_id,
            "start_bar": start_bar,
            "end_bar": end_bar,
            "direction": direction,
            "duration_bars": duration_bars,
            "entry_price": round(entry_price, 4),
            "exit_price": round(exit_price, 4),
            "avg_entry_price": round(avg_entry, 4),
            "adds_count": adds_count,
            "max_level_reached": max_level,
            "max_position_qty": max_position_qty,
            "gross_pnl_ticks": round(gross_pnl_ticks, 4),
            "net_pnl_ticks": round(net_pnl_ticks, 4),
            "max_adverse_excursion_ticks": round(mae_ticks, 4),
            "max_favorable_excursion_ticks": round(mfe_ticks, 4),
            "retracement_depths": retracement_depths,
            "time_at_max_level_bars": time_at_max_level_bars,
            "trend_defense_level_max": trend_defense_level_max,
            "exit_reason": exit_reason,
        })

    # -- Accessors -----------------------------------------------------------

    def get_trades_df(self) -> pd.DataFrame:
        """Return accumulated trade actions as a DataFrame."""
        if not self._trades:
            return pd.DataFrame(columns=[
                "bar_idx", "datetime", "action", "direction", "qty",
                "price", "level", "anchor", "cost_ticks", "cycle_id",
                "price_source",
            ])
        return pd.DataFrame(self._trades)

    def get_cycles_df(self) -> pd.DataFrame:
        """Return accumulated cycle records as a DataFrame."""
        if not self._cycles:
            return pd.DataFrame(columns=[
                "cycle_id", "start_bar", "end_bar", "direction", "duration_bars",
                "entry_price", "exit_price", "avg_entry_price", "adds_count",
                "max_level_reached", "max_position_qty", "gross_pnl_ticks",
                "net_pnl_ticks", "max_adverse_excursion_ticks",
                "max_favorable_excursion_ticks", "retracement_depths",
                "time_at_max_level_bars", "trend_defense_level_max", "exit_reason",
            ])
        return pd.DataFrame(self._cycles)


# ---------------------------------------------------------------------------
# RotationalSimulator
# ---------------------------------------------------------------------------

class RotationalSimulator:
    """Core rotational state machine simulator.

    Processes bar data sequentially, maintaining FLAT/POSITIONED state and
    executing SEED/REVERSAL/ADD actions based on price movement relative to
    the current anchor.

    Engine contract (see rotational_engine.py load_simulator):
        simulator = RotationalSimulator(config=config, bar_data=bars, reference_data=None)
        result = simulator.run()
        # result.trades, result.cycles, result.bars_processed

    Args:
        config: Full config dict (injected by engine; must contain _instrument,
                hypothesis.trigger_params.step_dist, martingale, period).
        bar_data: pd.DataFrame from load_bars() — pre-loaded by engine.
        reference_data: Optional dict of reference bar DataFrames (unused in baseline).
    """

    def __init__(
        self,
        config: dict,
        bar_data: pd.DataFrame,
        reference_data: Optional[dict] = None,
    ) -> None:
        self._config = config
        self._bar_data = bar_data
        self._reference_data = reference_data

        # -- Extract parameters from config ----------------------------------
        hyp = config.get("hypothesis", {})
        trigger = hyp.get("trigger_params", {})
        self._step_dist: float = float(trigger.get("step_dist", 2.0))

        mart = config.get("martingale", {})
        self._initial_qty: int = int(mart.get("initial_qty", 1))
        self._max_levels: int = int(mart.get("max_levels", 4))
        self._max_contract_size: int = int(mart.get("max_contract_size", 8))
        self._max_total_position: int = int(mart.get("max_total_position", 0))  # 0=unlimited
        self._anchor_mode: str = mart.get("anchor_mode", "walking")  # "walking" (B) | "frozen" (A) | "frozen_stop" (C)
        self._mtp_dd_exit_ticks: float = float(mart.get("mtp_dd_exit_ticks", 0))  # Mode C only: negative threshold

        instr = config.get("_instrument", {})
        self._tick_size: float = float(instr.get("tick_size", 0.25))
        self._cost_ticks: int = int(instr.get("cost_ticks", 3))

        self._period: str = config.get("period", "P1")

        # -- State machine variables -----------------------------------------
        self._state: str = "FLAT"       # "FLAT" | "POSITIONED"
        self._direction: Optional[str] = None   # "Long" | "Short"
        self._level: int = 0
        self._anchor: Optional[float] = None
        self._position_qty: int = 0
        self._cycle_id: int = 0

        # -- Track bar index range for active cycle --------------------------
        self._cycle_start_bar: int = 0
        self._cycle_trades: list[dict] = []

        # -- Running avg entry price (for TDS sim_state) --------------------
        self._avg_entry_price: float = 0.0

        # -- TDS integration state ------------------------------------------
        self._tds = None  # TrendDefenseSystem or None
        self._tds_level_max: int = 0  # max TDS level in current cycle

        # -- Dynamic feature tracking (for H36/H39 computation) -------------
        self._prev_close: Optional[float] = None   # previous bar close
        self._prev_bar_ts: Optional[float] = None  # previous bar timestamp (epoch seconds)
        # Cumulative weighted distances for H39 (adverse_velocity_ratio)
        self._cycle_favorable_weighted: float = 0.0
        self._cycle_adverse_weighted: float = 0.0

    # -----------------------------------------------------------------------
    # Bar filtering
    # -----------------------------------------------------------------------

    def _filter_bars(self, bars: pd.DataFrame) -> pd.DataFrame:
        """Apply date and RTH filters, return filtered+reset-index DataFrame.

        Date filter:
            P1a: _P1_START <= bar.date <= _P1_MIDPOINT
            P1b: _P1_MIDPOINT < bar.date <= _P1_END
            P1 or P2: no date filter (use full file)

        RTH filter (only for 10-sec bars identified via bar_data_primary keys):
            Keep bars where 09:30:00 <= Time < 16:00:00
            Vol/tick bars are already session-filtered by their construction.
        """
        mask = pd.Series(True, index=bars.index)

        # Date filter
        period = self._period.lower()
        if period in ("p1a", "p1b"):
            dates = bars["datetime"].dt.date
            if period == "p1a":
                mask &= (dates >= _P1_START) & (dates <= _P1_MIDPOINT)
            else:  # p1b
                mask &= (dates > _P1_MIDPOINT) & (dates <= _P1_END)

        # RTH filter: applied when the bar source is the 10-sec type
        # Detect by checking bar_data_primary keys for "10sec"
        source_ids = list(self._config.get("bar_data_primary", {}).keys())
        is_10sec_source = any("10sec" in sid for sid in source_ids)

        # Also detect if only a single bar type is being run with a 10sec source
        # When engine calls us, bar_data is already a single-source DataFrame.
        # We check the config's primary sources — if any 10sec key exists AND
        # the bar data has a Time column with sub-minute granularity, apply RTH.
        if is_10sec_source and "Time" in bars.columns:
            def _parse_time(t_str: str) -> datetime.time:
                parts = str(t_str).strip().split(":")
                h = int(parts[0])
                m = int(parts[1])
                # Strip fractional seconds (e.g. "00.000000" -> 0)
                s = int(float(parts[2])) if len(parts) > 2 else 0
                return datetime.time(h, m, s)

            times = bars["Time"].apply(_parse_time)
            mask &= (times >= _RTH_START) & (times < _RTH_END)

        filtered = bars[mask].reset_index(drop=True)
        return filtered

    # -----------------------------------------------------------------------
    # Action helpers
    # -----------------------------------------------------------------------

    def _seed(
        self,
        bar_idx: int,
        dt: object,
        close: float,
        logger: TradeLogger,
        price_source: str = "close",
    ) -> None:
        """Execute SEED: enter Long at initial_qty."""
        self._cycle_id += 1
        self._state = "POSITIONED"
        self._direction = "Long"
        self._level = 0
        self._anchor = close
        self._position_qty = self._initial_qty
        self._avg_entry_price = close
        self._cycle_start_bar = bar_idx
        self._cycle_trades = []
        # Reset dynamic feature tracking for new cycle
        self._cycle_favorable_weighted = 0.0
        self._cycle_adverse_weighted = 0.0

        trade = {
            "bar_idx": bar_idx,
            "datetime": dt,
            "action": "SEED",
            "direction": "Long",
            "qty": self._initial_qty,
            "price": close,
            "level": 0,
            "anchor": close,
            "cost_ticks": self._cost_ticks * self._initial_qty,
            "cycle_id": self._cycle_id,
            "price_source": price_source,
        }
        self._cycle_trades.append(trade)
        logger.log_action(bar_idx, dt, "SEED", "Long", self._initial_qty, close, 0, close, self._cycle_id, price_source)

    def _reversal(
        self,
        bar_idx: int,
        dt: object,
        close: float,
        logger: TradeLogger,
        bars_df: pd.DataFrame,
        price_source: str = "close",
    ) -> None:
        """Execute REVERSAL: finalize current cycle, flatten, enter opposite."""
        # 1. Add FLATTEN to current cycle's trades before finalizing
        flatten_trade = {
            "bar_idx": bar_idx,
            "datetime": dt,
            "action": "FLATTEN",
            "direction": self._direction,
            "qty": self._position_qty,
            "price": close,
            "level": self._level,
            "anchor": self._anchor,
            "cost_ticks": self._cost_ticks * self._position_qty,
            "cycle_id": self._cycle_id,
            "price_source": price_source,
        }
        self._cycle_trades.append(flatten_trade)
        logger.log_action(bar_idx, dt, "FLATTEN", self._direction, self._position_qty, close,
                          self._level, self._anchor, self._cycle_id, price_source)

        # 2. Finalize current cycle
        logger.finalize_cycle(
            cycle_id=self._cycle_id,
            start_bar=self._cycle_start_bar,
            end_bar=bar_idx,
            direction=self._direction,
            trades_in_cycle=list(self._cycle_trades),
            bars_df=bars_df,
            exit_price=close,
            exit_reason="reversal",
        )

        # 3. Flip direction and enter new cycle
        new_direction = "Short" if self._direction == "Long" else "Long"
        self._cycle_id += 1
        self._direction = new_direction
        self._level = 0
        self._anchor = close
        self._position_qty = self._initial_qty
        self._avg_entry_price = close
        self._cycle_start_bar = bar_idx
        self._cycle_trades = []
        # Reset dynamic feature tracking for new cycle
        self._cycle_favorable_weighted = 0.0
        self._cycle_adverse_weighted = 0.0

        trade = {
            "bar_idx": bar_idx,
            "datetime": dt,
            "action": "REVERSAL",
            "direction": new_direction,
            "qty": self._initial_qty,
            "price": close,
            "level": 0,
            "anchor": close,
            "cost_ticks": self._cost_ticks * self._initial_qty,
            "cycle_id": self._cycle_id,
            "price_source": price_source,
        }
        self._cycle_trades.append(trade)
        logger.log_action(bar_idx, dt, "REVERSAL", new_direction, self._initial_qty, close, 0, close, self._cycle_id, price_source)

    def _add(
        self,
        bar_idx: int,
        dt: object,
        close: float,
        logger: TradeLogger,
        price_source: str = "close",
    ) -> None:
        """Execute ADD: add to position (with cap reset logic).

        Level recorded in the trade row reflects the level AT WHICH the ADD occurs
        (before incrementing). On cap reset, qty resets to initial_qty and level -> 0.

        MaxTotalPosition gate: if self._max_total_position > 0 and adding
        proposed_qty would exceed the cap, the ADD is refused entirely.
        No state is mutated (position unchanged, level unchanged).
        """
        # 1. Compute proposed qty and next level as local variables — no state mutation yet
        proposed_qty = self._initial_qty * (2 ** self._level)
        if proposed_qty > self._max_contract_size:
            # Cap reset: qty resets to initial_qty and level resets to 0
            proposed_qty = self._initial_qty
            next_level = 0
            level_at_add = 0  # level recorded in trade row is post-reset level
        else:
            next_level = self._level + 1
            level_at_add = self._level  # level recorded is the level before incrementing

        # 2. MaxTotalPosition gate — refuse add, anchor behavior depends on anchor_mode
        if self._max_total_position > 0:
            if self._position_qty + proposed_qty > self._max_total_position:
                if self._anchor_mode == "walking":
                    # Mode B: update anchor to current price on MTP refusal
                    self._anchor = close
                # Mode A ("frozen") and Mode C ("frozen_stop"): anchor stays frozen
                return  # skip: position unchanged, level unchanged

        # 3. Commit state changes
        self._level = next_level
        self._anchor = close
        old_qty = self._position_qty
        self._position_qty += proposed_qty
        # Update running avg entry price
        if self._position_qty > 0:
            self._avg_entry_price = (
                self._avg_entry_price * old_qty + close * proposed_qty
            ) / self._position_qty

        trade = {
            "bar_idx": bar_idx,
            "datetime": dt,
            "action": "ADD",
            "direction": self._direction,
            "qty": proposed_qty,
            "price": close,
            "level": level_at_add,
            "anchor": close,
            "cost_ticks": self._cost_ticks * proposed_qty,
            "cycle_id": self._cycle_id,
            "price_source": price_source,
        }
        self._cycle_trades.append(trade)
        logger.log_action(bar_idx, dt, "ADD", self._direction, proposed_qty, close,
                          level_at_add, close, self._cycle_id, price_source)

    # -----------------------------------------------------------------------
    # TDS helper methods
    # -----------------------------------------------------------------------

    def _get_sim_state(self, bar_idx: int) -> dict:
        """Return the sim_state dict expected by TrendDefenseSystem.evaluate()."""
        return {
            "direction": self._direction,
            "level": self._level,
            "anchor": self._anchor,
            "position_qty": self._position_qty,
            "cycle_start_bar": self._cycle_start_bar,
            "bar_idx": bar_idx,
            "avg_entry_price": self._avg_entry_price,
            "step_dist_ticks": self._step_dist / self._tick_size,
            "tick_size": self._tick_size,
        }

    def _compute_dynamic_features(self, bar_idx: int, row: "pd.Series") -> dict:
        """Compute per-bar dynamic features H36 (adverse_speed) and H39 (adverse_velocity_ratio).

        H36 adverse_speed: absolute adverse price delta per second since last bar.
        H39 adverse_velocity_ratio: cumulative adverse weighted distance / cumulative
            favorable weighted distance within current cycle.

        Returns 0.0 for both when FLAT, no prior bar, or when the delta is zero.
        """
        result = {"adverse_speed": 0.0, "adverse_velocity_ratio": 0.0}

        if self._state != "POSITIONED" or self._direction is None:
            # Update prev for next bar
            try:
                self._prev_close = float(row["Last"])
                ts = row["datetime"]
                self._prev_bar_ts = ts.timestamp() if hasattr(ts, "timestamp") else None
            except Exception:
                pass
            return result

        try:
            close = float(row["Last"])
            ts = row["datetime"]
            cur_ts = ts.timestamp() if hasattr(ts, "timestamp") else None
        except Exception:
            return result

        # Compute bar duration in seconds
        bar_dur_sec: float = 10.0  # default fallback
        if cur_ts is not None and self._prev_bar_ts is not None:
            delta_sec = cur_ts - self._prev_bar_ts
            if delta_sec > 0:
                bar_dur_sec = delta_sec

        # Compute H36: adverse price delta since last bar
        if self._prev_close is not None:
            price_delta = close - self._prev_close
            if self._direction == "Long":
                adverse_delta = -price_delta  # adverse for Long = price falling
            else:
                adverse_delta = price_delta   # adverse for Short = price rising

            h36 = max(0.0, adverse_delta) / bar_dur_sec
            result["adverse_speed"] = h36

            # Accumulate for H39
            if adverse_delta > 0:
                self._cycle_adverse_weighted += adverse_delta * bar_dur_sec
            else:
                fav_delta = -adverse_delta
                self._cycle_favorable_weighted += fav_delta * bar_dur_sec

        # Compute H39: adverse_velocity_ratio
        if self._cycle_favorable_weighted > 0:
            result["adverse_velocity_ratio"] = (
                self._cycle_adverse_weighted / self._cycle_favorable_weighted
            )

        # Update prev for next bar
        self._prev_close = close
        self._prev_bar_ts = cur_ts

        return result

    def _finalize_current_cycle_as_tds_exit(
        self,
        bar_idx: int,
        dt: object,
        close: float,
        logger: TradeLogger,
        bars_df: "pd.DataFrame",
        price_source: str = "close",
    ) -> None:
        """Flatten current position due to TDS Level 3 forced exit.

        Finalizes the cycle with exit_reason='td_flatten', resets simulator
        state to FLAT, and sets TDS forced_flat=True to enter cooldown.
        """
        # Add FLATTEN trade to cycle
        flatten_trade = {
            "bar_idx": bar_idx,
            "datetime": dt,
            "action": "FLATTEN",
            "direction": self._direction,
            "qty": self._position_qty,
            "price": close,
            "level": self._level,
            "anchor": self._anchor,
            "cost_ticks": self._cost_ticks * self._position_qty,
            "cycle_id": self._cycle_id,
            "price_source": price_source,
        }
        self._cycle_trades.append(flatten_trade)
        logger.log_action(
            bar_idx, dt, "FLATTEN", self._direction, self._position_qty,
            close, self._level, self._anchor, self._cycle_id, price_source,
        )

        # Finalize cycle record with td_flatten exit reason
        logger.finalize_cycle(
            cycle_id=self._cycle_id,
            start_bar=self._cycle_start_bar,
            end_bar=bar_idx,
            direction=self._direction,
            trades_in_cycle=list(self._cycle_trades),
            bars_df=bars_df,
            exit_price=close,
            exit_reason="td_flatten",
            trend_defense_level_max=self._tds_level_max,
        )

        # Reset simulator to FLAT
        self._state = "FLAT"
        self._direction = None
        self._level = 0
        self._anchor = None
        self._position_qty = 0
        self._avg_entry_price = 0.0
        self._cycle_trades = []
        self._tds_level_max = 0
        self._cycle_favorable_weighted = 0.0
        self._cycle_adverse_weighted = 0.0

        # Enter TDS cooldown
        self._tds.state.forced_flat = True

    def _check_mtp_dd_exit(
        self,
        bar_idx: int,
        dt: object,
        close: float,
        logger: TradeLogger,
        bars_df: "pd.DataFrame",
        price_source: str = "close",
    ) -> bool:
        """Mode C: check if unrealized PnL breaches mtp_dd_exit_ticks threshold.

        Returns True if position was flattened (caller should skip further processing).
        Only active when anchor_mode='frozen_stop' and mtp_dd_exit_ticks < 0.
        """
        if self._anchor_mode != "frozen_stop" or self._mtp_dd_exit_ticks >= 0:
            return False
        if self._state != "POSITIONED" or self._position_qty == 0:
            return False

        # Unrealized PnL in ticks: (close - avg_entry) / tick_size * qty * direction_sign
        direction_sign = 1.0 if self._direction == "Long" else -1.0
        unrealized_ticks = (
            (close - self._avg_entry_price) / self._tick_size
        ) * direction_sign * self._position_qty

        if unrealized_ticks <= self._mtp_dd_exit_ticks:
            # Flatten and reset to FLAT
            flatten_trade = {
                "bar_idx": bar_idx,
                "datetime": dt,
                "action": "FLATTEN",
                "direction": self._direction,
                "qty": self._position_qty,
                "price": close,
                "level": self._level,
                "anchor": self._anchor,
                "cost_ticks": self._cost_ticks * self._position_qty,
                "cycle_id": self._cycle_id,
                "price_source": price_source,
            }
            self._cycle_trades.append(flatten_trade)
            logger.log_action(
                bar_idx, dt, "FLATTEN", self._direction, self._position_qty,
                close, self._level, self._anchor, self._cycle_id, price_source,
            )

            logger.finalize_cycle(
                cycle_id=self._cycle_id,
                start_bar=self._cycle_start_bar,
                end_bar=bar_idx,
                direction=self._direction,
                trades_in_cycle=list(self._cycle_trades),
                bars_df=bars_df,
                exit_price=close,
                exit_reason="mtp_dd_exit",
                trend_defense_level_max=self._tds_level_max,
            )

            # Reset to FLAT
            self._state = "FLAT"
            self._direction = None
            self._level = 0
            self._anchor = None
            self._position_qty = 0
            self._avg_entry_price = 0.0
            self._cycle_trades = []
            self._tds_level_max = 0
            self._cycle_favorable_weighted = 0.0
            self._cycle_adverse_weighted = 0.0
            return True

        return False

    # -----------------------------------------------------------------------
    # Tick-mode fast path
    # -----------------------------------------------------------------------

    def _is_tick_data(self, bars: pd.DataFrame) -> bool:
        """Detect tick data: O=H=L=Last on all rows (single price per row)."""
        if len(bars) < 2:
            return False
        sample = bars.head(min(100, len(bars)))
        return bool(
            (sample["Open"] == sample["Last"]).all()
            and (sample["High"] == sample["Last"]).all()
            and (sample["Low"] == sample["Last"]).all()
        )

    def _run_tick_fast(self, bars: pd.DataFrame) -> SimulationResult:
        """Tick-mode fast path: one price per row, one action per tick max.

        Operates on numpy arrays directly for speed (~10-50x faster than iterrows).
        No OHLC threshold-crossing loop — each tick is one price evaluation.
        Executes at tick price (with gap slippage), not at trigger price.
        One action per tick maximum, matching C++ behavior.
        """
        prices = bars["Last"].values.astype(np.float64)
        n = len(prices)

        # Asymmetric step support: separate reversal and add distances
        trigger_params = self._config.get("hypothesis", {}).get("trigger_params", {})
        step_rev = float(trigger_params.get("step_dist_reversal", self._step_dist))
        step_add = float(trigger_params.get("step_dist_add", self._step_dist))
        step = self._step_dist  # used for directional seed watch distance
        mtp = self._max_total_position
        max_cs = self._max_contract_size
        max_levels = self._max_levels
        init_qty = self._initial_qty
        cost_ticks = self._cost_ticks
        tick_size = self._tick_size
        walking = self._anchor_mode == "walking"

        # ATR-normalized mode: distances = multiple × ATR per tick
        atr_rev_mult = float(trigger_params.get("atr_rev_mult", 0))
        atr_add_mult = float(trigger_params.get("atr_add_mult", 0))
        atr_normalized = atr_rev_mult > 0 and atr_add_mult > 0
        atr_array = self._config.get("_tick_atr_array", None)

        # Flatten-and-reseed cap: flatten when position reaches cap, re-enter via
        # directional seed. Config key: martingale.flatten_reseed_cap (0 = disabled).
        mart = self._config.get("martingale", {})
        flatten_reseed_cap = int(mart.get("flatten_reseed_cap", 0))

        # Pre-extract datetimes for trade records (only accessed on actions)
        dts = bars["datetime"].values

        # State variables
        state = -1  # -1=WATCHING, 0=FLAT_RESEEDING, 1=LONG, 2=SHORT
        watch_price = 0.0  # price recorded when entering WATCHING state
        anchor = 0.0
        level = 0
        position_qty = 0
        avg_entry = 0.0
        cycle_id = 0
        cycle_start = 0

        # Accumulate trade and cycle records as lists (fast append)
        trade_records = []
        cycle_records = []
        cycle_trades = []

        for i in range(n):
            price = prices[i]

            if state == -1:
                # WATCHING: wait for first StepDist directional move
                if watch_price == 0.0:
                    watch_price = price
                    continue
                # Seed watch distance: use ATR-normalized reversal distance if enabled
                seed_step = step
                if atr_normalized and atr_array is not None and i < len(atr_array):
                    cur_atr = atr_array[i]
                    if not np.isnan(cur_atr) and cur_atr > 0:
                        seed_step = atr_rev_mult * cur_atr
                up_dist = price - watch_price
                down_dist = watch_price - price
                if up_dist >= seed_step:
                    # First move is UP -> seed Long
                    cycle_id += 1
                    state = 1
                    anchor = price
                    level = 0
                    position_qty = init_qty
                    avg_entry = price
                    cycle_start = i
                    trade = {
                        "bar_idx": i, "datetime": dts[i], "action": "SEED",
                        "direction": "Long", "qty": init_qty, "price": price,
                        "level": 0, "anchor": price,
                        "cost_ticks": cost_ticks * init_qty,
                        "cycle_id": cycle_id, "price_source": "tick",
                    }
                    trade_records.append(trade)
                    cycle_trades = [trade]
                elif down_dist >= seed_step:
                    # First move is DOWN -> seed Short
                    cycle_id += 1
                    state = 2
                    anchor = price
                    level = 0
                    position_qty = init_qty
                    avg_entry = price
                    cycle_start = i
                    trade = {
                        "bar_idx": i, "datetime": dts[i], "action": "SEED",
                        "direction": "Short", "qty": init_qty, "price": price,
                        "level": 0, "anchor": price,
                        "cost_ticks": cost_ticks * init_qty,
                        "cycle_id": cycle_id, "price_source": "tick",
                    }
                    trade_records.append(trade)
                    cycle_trades = [trade]
                continue

            if state == 0:
                # FLAT after a cycle ended (e.g., end_of_data or TDS exit)
                # Re-enter WATCHING state
                state = -1
                watch_price = price
                continue

            # POSITIONED: compute effective distances (ATR-normalized or fixed)
            eff_rev = step_rev
            eff_add = step_add
            if atr_normalized and atr_array is not None and i < len(atr_array):
                cur_atr = atr_array[i]
                if not np.isnan(cur_atr) and cur_atr > 0:
                    eff_rev = atr_rev_mult * cur_atr
                    eff_add = atr_add_mult * cur_atr

            distance = price - anchor
            if state == 1:  # Long
                in_favor = distance >= eff_rev
                against = (-distance) >= eff_add
            else:  # Short
                in_favor = (-distance) >= eff_rev
                against = distance >= eff_add

            if in_favor:
                # REVERSAL: flatten current + enter opposite at tick price
                direction = "Long" if state == 1 else "Short"
                new_direction = "Short" if state == 1 else "Long"

                # FLATTEN trade (belongs to current cycle)
                flatten_trade = {
                    "bar_idx": i, "datetime": dts[i], "action": "FLATTEN",
                    "direction": direction, "qty": position_qty, "price": price,
                    "level": level, "anchor": anchor,
                    "cost_ticks": cost_ticks * position_qty,
                    "cycle_id": cycle_id, "price_source": "tick",
                }
                trade_records.append(flatten_trade)
                cycle_trades.append(flatten_trade)

                # Finalize cycle
                entry_trades = [t for t in cycle_trades if t["action"] in ("SEED", "REVERSAL", "ADD")]
                total_qty = sum(t["qty"] for t in entry_trades)
                if total_qty > 0:
                    wavg = sum(t["price"] * t["qty"] for t in entry_trades) / total_qty
                else:
                    wavg = price
                if direction == "Long":
                    gross = (price - wavg) / tick_size * total_qty
                else:
                    gross = (wavg - price) / tick_size * total_qty
                total_cost = sum(t["cost_ticks"] for t in cycle_trades)
                net = gross - total_cost
                adds = [t for t in entry_trades if t["action"] == "ADD"]
                max_pos = 0
                rq = 0
                for t in cycle_trades:
                    if t["action"] == "FLATTEN":
                        rq = 0
                    elif t["action"] in ("SEED", "REVERSAL", "ADD"):
                        rq += t["qty"]
                        max_pos = max(max_pos, rq)
                max_level = max((t["level"] for t in entry_trades), default=0)

                cycle_records.append({
                    "cycle_id": cycle_id,
                    "start_bar": cycle_start,
                    "end_bar": i,
                    "direction": direction,
                    "duration_bars": i - cycle_start + 1,
                    "entry_price": round(entry_trades[0]["price"], 4) if entry_trades else price,
                    "exit_price": round(price, 4),
                    "avg_entry_price": round(wavg, 4),
                    "adds_count": len(adds),
                    "max_level_reached": max_level,
                    "max_position_qty": max_pos,
                    "gross_pnl_ticks": round(gross, 4),
                    "net_pnl_ticks": round(net, 4),
                    "max_adverse_excursion_ticks": 0.0,
                    "max_favorable_excursion_ticks": 0.0,
                    "retracement_depths": [],
                    "time_at_max_level_bars": 0,
                    "trend_defense_level_max": 0,
                    "exit_reason": "reversal",
                })

                # Enter new cycle in opposite direction
                cycle_id += 1
                state = 2 if direction == "Long" else 1
                anchor = price
                level = 0
                position_qty = init_qty
                avg_entry = price
                cycle_start = i
                rev_trade = {
                    "bar_idx": i, "datetime": dts[i], "action": "REVERSAL",
                    "direction": new_direction, "qty": init_qty, "price": price,
                    "level": 0, "anchor": price,
                    "cost_ticks": cost_ticks * init_qty,
                    "cycle_id": cycle_id, "price_source": "tick",
                }
                trade_records.append(rev_trade)
                cycle_trades = [rev_trade]

            elif against:
                # Flatten-reseed cap: if position at cap, flatten all and re-enter WATCHING
                if flatten_reseed_cap > 0 and position_qty >= flatten_reseed_cap:
                    direction = "Long" if state == 1 else "Short"
                    flatten_trade = {
                        "bar_idx": i, "datetime": dts[i], "action": "FLATTEN",
                        "direction": direction, "qty": position_qty, "price": price,
                        "level": level, "anchor": anchor,
                        "cost_ticks": cost_ticks * position_qty,
                        "cycle_id": cycle_id, "price_source": "tick",
                    }
                    trade_records.append(flatten_trade)
                    cycle_trades.append(flatten_trade)
                    # Finalize cycle with exit_reason="flatten_reseed"
                    entry_trades = [t for t in cycle_trades if t["action"] in ("SEED", "REVERSAL", "ADD")]
                    total_qty = sum(t["qty"] for t in entry_trades)
                    wavg = sum(t["price"] * t["qty"] for t in entry_trades) / total_qty if total_qty else price
                    if direction == "Long":
                        gross = (price - wavg) / tick_size * total_qty
                    else:
                        gross = (wavg - price) / tick_size * total_qty
                    total_cost_cycle = sum(t["cost_ticks"] for t in cycle_trades)
                    net = gross - total_cost_cycle
                    adds_list = [t for t in entry_trades if t["action"] == "ADD"]
                    max_pos = 0
                    rq = 0
                    for t in cycle_trades:
                        if t["action"] == "FLATTEN":
                            rq = 0
                        elif t["action"] in ("SEED", "REVERSAL", "ADD"):
                            rq += t["qty"]
                            max_pos = max(max_pos, rq)
                    max_level_r = max((t["level"] for t in entry_trades), default=0)
                    cycle_records.append({
                        "cycle_id": cycle_id, "start_bar": cycle_start, "end_bar": i,
                        "direction": direction, "duration_bars": i - cycle_start + 1,
                        "entry_price": round(entry_trades[0]["price"], 4) if entry_trades else price,
                        "exit_price": round(price, 4), "avg_entry_price": round(wavg, 4),
                        "adds_count": len(adds_list), "max_level_reached": max_level_r,
                        "max_position_qty": max_pos,
                        "gross_pnl_ticks": round(gross, 4), "net_pnl_ticks": round(net, 4),
                        "max_adverse_excursion_ticks": 0.0, "max_favorable_excursion_ticks": 0.0,
                        "retracement_depths": [], "time_at_max_level_bars": 0,
                        "trend_defense_level_max": 0, "exit_reason": "flatten_reseed",
                    })
                    # Re-enter WATCHING state
                    state = -1
                    watch_price = price
                    position_qty = 0
                    continue

                # ADD (or MTP refusal)
                proposed_qty = init_qty * (2 ** level)
                if proposed_qty > max_cs or level >= max_levels:
                    # Cap reset: qty resets to initial, level resets to 0
                    proposed_qty = init_qty
                    next_level = 0
                    level_at_add = 0
                else:
                    next_level = level + 1
                    level_at_add = level

                if mtp > 0 and position_qty + proposed_qty > mtp:
                    # MTP refusal
                    if walking:
                        anchor = price  # Mode B: walk anchor to tick price
                    continue  # no action this tick

                # Commit ADD
                level = next_level
                anchor = price
                old_qty = position_qty
                position_qty += proposed_qty
                if position_qty > 0:
                    avg_entry = (avg_entry * old_qty + price * proposed_qty) / position_qty

                direction = "Long" if state == 1 else "Short"
                add_trade = {
                    "bar_idx": i, "datetime": dts[i], "action": "ADD",
                    "direction": direction, "qty": proposed_qty, "price": price,
                    "level": level_at_add, "anchor": price,
                    "cost_ticks": cost_ticks * proposed_qty,
                    "cycle_id": cycle_id, "price_source": "tick",
                }
                trade_records.append(add_trade)
                cycle_trades.append(add_trade)

        # Finalize any open cycle at end of data
        if state in (1, 2) and cycle_trades:
            last_price = prices[-1]
            direction = "Long" if state == 1 else "Short"
            entry_trades = [t for t in cycle_trades if t["action"] in ("SEED", "REVERSAL", "ADD")]
            total_qty = sum(t["qty"] for t in entry_trades)
            wavg = sum(t["price"] * t["qty"] for t in entry_trades) / total_qty if total_qty else last_price
            if direction == "Long":
                gross = (last_price - wavg) / tick_size * total_qty
            else:
                gross = (wavg - last_price) / tick_size * total_qty
            total_cost = sum(t["cost_ticks"] for t in cycle_trades)
            net = gross - total_cost
            adds = [t for t in entry_trades if t["action"] == "ADD"]
            max_pos = 0
            rq = 0
            for t in cycle_trades:
                if t["action"] == "FLATTEN":
                    rq = 0
                elif t["action"] in ("SEED", "REVERSAL", "ADD"):
                    rq += t["qty"]
                    max_pos = max(max_pos, rq)
            max_level = max((t["level"] for t in entry_trades), default=0)

            cycle_records.append({
                "cycle_id": cycle_id,
                "start_bar": cycle_start,
                "end_bar": n - 1,
                "direction": direction,
                "duration_bars": n - 1 - cycle_start + 1,
                "entry_price": round(entry_trades[0]["price"], 4) if entry_trades else last_price,
                "exit_price": round(last_price, 4),
                "avg_entry_price": round(wavg, 4),
                "adds_count": len(adds),
                "max_level_reached": max_level,
                "max_position_qty": max_pos,
                "gross_pnl_ticks": round(gross, 4),
                "net_pnl_ticks": round(net, 4),
                "max_adverse_excursion_ticks": 0.0,
                "max_favorable_excursion_ticks": 0.0,
                "retracement_depths": [],
                "time_at_max_level_bars": 0,
                "trend_defense_level_max": 0,
                "exit_reason": "end_of_data",
            })

        trades_df = pd.DataFrame(trade_records) if trade_records else pd.DataFrame(columns=[
            "bar_idx", "datetime", "action", "direction", "qty",
            "price", "level", "anchor", "cost_ticks", "cycle_id", "price_source",
        ])
        cycles_df = pd.DataFrame(cycle_records) if cycle_records else pd.DataFrame(columns=[
            "cycle_id", "start_bar", "end_bar", "direction", "duration_bars",
            "entry_price", "exit_price", "avg_entry_price", "adds_count",
            "max_level_reached", "max_position_qty", "gross_pnl_ticks",
            "net_pnl_ticks", "max_adverse_excursion_ticks",
            "max_favorable_excursion_ticks", "retracement_depths",
            "time_at_max_level_bars", "trend_defense_level_max", "exit_reason",
        ])

        return SimulationResult(
            trades=trades_df,
            cycles=cycles_df,
            bars_processed=n,
        )

    # -----------------------------------------------------------------------
    # Main simulation loop
    # -----------------------------------------------------------------------

    def run(self) -> SimulationResult:
        """Execute the full simulation over all (filtered) bars.

        Auto-detects tick data (O=H=L=Last) and uses optimized tick-mode
        fast path when TDS is disabled. Falls back to OHLC threshold-crossing
        loop for aggregated bar data.

        Returns:
            SimulationResult with trades, cycles, and bars_processed.
        """
        bars = self._filter_bars(self._bar_data)

        # Tick-mode fast path: skip feature computation and OHLC logic
        tds_cfg = self._config.get("trend_defense", {})
        tds_enabled = _TDS_AVAILABLE and tds_cfg.get("enabled", False)
        if self._is_tick_data(bars) and not tds_enabled:
            return self._run_tick_fast(bars)

        feature_computer = FeatureComputer(self._config)
        bars = feature_computer.compute_static_features(bars)

        logger = TradeLogger(tick_size=self._tick_size, cost_ticks=self._cost_ticks)

        # Reset state for each run (supports calling run() multiple times for testing)
        self._state = "FLAT"
        self._direction = None
        self._level = 0
        self._anchor = None
        self._position_qty = 0
        self._avg_entry_price = 0.0
        self._cycle_id = 0
        self._cycle_start_bar = 0
        self._cycle_trades = []
        self._prev_close = None
        self._prev_bar_ts = None
        self._cycle_favorable_weighted = 0.0
        self._cycle_adverse_weighted = 0.0
        self._tds_level_max = 0

        # -- TDS initialization -------------------------------------------
        tds_cfg = self._config.get("trend_defense", {})
        if _TDS_AVAILABLE and tds_cfg.get("enabled", False):
            # Compute bar duration stats from the actual bar DataFrame
            bar_duration_stats = {"median_sec": 10.0}  # safe fallback
            if "datetime" in bars.columns and len(bars) > 1:
                ts_series = bars["datetime"]
                if hasattr(ts_series.iloc[0], "timestamp"):
                    diffs = [
                        ts_series.iloc[i + 1].timestamp() - ts_series.iloc[i].timestamp()
                        for i in range(min(len(bars) - 1, 1000))
                        if ts_series.iloc[i + 1].timestamp() > ts_series.iloc[i].timestamp()
                    ]
                    if diffs:
                        bar_duration_stats["median_sec"] = float(np.median(diffs))
            self._tds = TrendDefenseSystem(tds_cfg, bar_duration_stats)
        else:
            self._tds = None

        action_modifiers: dict = {
            "step_widen_factor": 1.0,
            "max_levels_reduction": 0,
            "refuse_adds": False,
            "force_flatten": False,
            "reduced_reversal_threshold": None,
        }

        for bar_idx, row in bars.iterrows():
            close = float(row["Last"])
            dt = row["datetime"]
            open_price = float(row["Open"])
            high = float(row["High"])
            low = float(row["Low"])

            # -- TDS evaluation (bar-level, once per bar, using close) ---------
            tds_flattened = False
            if self._tds is not None:
                # Handle cooldown period (forced_flat=True after Level 3)
                if self._tds.state.forced_flat:
                    self._tds.state.cooldown_remaining = max(
                        0, self._tds.state.cooldown_remaining - 1
                    )
                    if self._tds.can_reengage({}):
                        self._tds.state.forced_flat = False
                        # Allow normal FLAT->SEED on next iteration
                    else:
                        # Still in cooldown: skip entire bar
                        self._prev_close = close
                        ts = row["datetime"]
                        self._prev_bar_ts = ts.timestamp() if hasattr(ts, "timestamp") else None
                        continue

                if self._state == "POSITIONED":
                    dyn_features = self._compute_dynamic_features(bar_idx, row)
                    sim_state = self._get_sim_state(bar_idx)
                    threat = self._tds.evaluate(row, dyn_features, sim_state)
                    action_modifiers = self._tds.apply_response(sim_state, threat)
                    self._tds_level_max = max(self._tds_level_max, threat)

                    # Level 3 forced flatten: exit position immediately at close
                    if action_modifiers.get("force_flatten", False):
                        self._finalize_current_cycle_as_tds_exit(
                            bar_idx, dt, close, logger, bars
                        )
                        action_modifiers = {
                            "step_widen_factor": 1.0,
                            "max_levels_reduction": 0,
                            "refuse_adds": False,
                            "force_flatten": False,
                            "reduced_reversal_threshold": None,
                        }
                        tds_flattened = True
                else:
                    # FLAT state: update prev tracking but don't compute H36/H39
                    self._prev_close = close
                    ts_val = row["datetime"]
                    self._prev_bar_ts = ts_val.timestamp() if hasattr(ts_val, "timestamp") else None
                    # Reset action modifiers when flat
                    action_modifiers = {
                        "step_widen_factor": 1.0,
                        "max_levels_reduction": 0,
                        "refuse_adds": False,
                        "force_flatten": False,
                        "reduced_reversal_threshold": None,
                    }

            if tds_flattened:
                continue  # skip intra-bar processing for this bar

            # -- FLAT: seed at open price --------------------------------------
            if self._state == "FLAT":
                self._seed(bar_idx, dt, open_price, logger, "open")

            # -- POSITIONED: threshold-crossing loop within bar ----------------
            # Deterministic trigger levels are computed from anchor + step_dist.
            # High/Low tell us with certainty whether each threshold was crossed.
            # Loop until no more triggers fire within this bar's H-L range.
            if self._state == "POSITIONED":
                effective_step = self._step_dist * action_modifiers.get("step_widen_factor", 1.0)
                # Safety limit: max actions per bar = floor(bar_range / step) + 2
                bar_range = high - low
                max_actions = int(bar_range / effective_step) + 2 if effective_step > 0 else 1
                actions_this_bar = 0

                while actions_this_bar <= max_actions:
                    # Recompute effective step (may change after TDS interactions)
                    effective_step = self._step_dist * action_modifiers.get("step_widen_factor", 1.0)

                    if self._direction == "Long":
                        reversal_trigger = self._anchor + effective_step
                        add_trigger = self._anchor - effective_step
                        reversal_hit = high >= reversal_trigger
                        add_hit = low <= add_trigger
                    else:  # Short
                        reversal_trigger = self._anchor - effective_step
                        add_trigger = self._anchor + effective_step
                        reversal_hit = low <= reversal_trigger
                        add_hit = high >= add_trigger

                    if not reversal_hit and not add_hit:
                        break  # no triggers within this bar

                    # Determine which fires first when both hit
                    if reversal_hit and add_hit:
                        # Use Open proximity to determine sequence
                        rev_dist = abs(open_price - reversal_trigger)
                        add_dist = abs(open_price - add_trigger)
                        reversal_first = rev_dist <= add_dist
                    elif reversal_hit:
                        reversal_first = True
                    else:
                        reversal_first = False

                    if reversal_first:
                        # Execute reversal at the exact trigger price
                        if self._tds is not None:
                            self._tds.on_reversal()
                        tds_level_for_cycle = self._tds_level_max
                        self._tds_level_max = 0

                        self._reversal(bar_idx, dt, reversal_trigger, logger, bars, "intrabar")

                        if logger._cycles:
                            logger._cycles[-1]["trend_defense_level_max"] = tds_level_for_cycle
                    else:
                        # Execute add at the exact trigger price
                        if action_modifiers.get("refuse_adds", False):
                            break  # TDS blocks adds — no further triggers to check
                        pos_before = self._position_qty
                        anchor_before = self._anchor
                        self._add(bar_idx, dt, add_trigger, logger, "intrabar")
                        if self._tds is not None and self._position_qty != pos_before:
                            self._tds.on_add(price=add_trigger)
                        # If add was refused and no state changed, break to avoid
                        # infinite loop (Mode A/C: frozen anchor, same trigger repeats).
                        # Mode B: anchor walks on refusal, so anchor_before != self._anchor.
                        if self._position_qty == pos_before and self._anchor == anchor_before:
                            break

                    actions_this_bar += 1

                    # Mode C: check drawdown exit after each action
                    if self._state == "POSITIONED" and self._check_mtp_dd_exit(
                        bar_idx, dt, add_trigger if not reversal_first else reversal_trigger,
                        logger, bars, "intrabar"
                    ):
                        break

                    # If we went FLAT (shouldn't happen mid-loop, but guard)
                    if self._state != "POSITIONED":
                        break

                # Post-loop: Mode C dd_exit check at bar's most adverse price.
                # The threshold loop only checks at trigger prices; the actual
                # bar extreme may breach the dd threshold even if no trigger fired.
                if self._state == "POSITIONED":
                    adverse_price = low if self._direction == "Long" else high
                    if self._check_mtp_dd_exit(
                        bar_idx, dt, adverse_price, logger, bars, "intrabar"
                    ):
                        pass  # flattened — state is now FLAT

            # End of bar: update TDS cycle metrics
            if self._tds is not None and self._state == "POSITIONED":
                self._tds.update_cycle_metrics(row, self._get_sim_state(bar_idx))

        # Finalize any open cycle at end of data
        if self._state == "POSITIONED" and self._cycle_trades:
            last_row = bars.iloc[-1] if not bars.empty else None
            if last_row is not None:
                last_close = float(last_row["Last"])
                last_dt = last_row["datetime"]
                last_bar_idx = bars.index[-1]

                logger.finalize_cycle(
                    cycle_id=self._cycle_id,
                    start_bar=self._cycle_start_bar,
                    end_bar=last_bar_idx,
                    direction=self._direction,
                    trades_in_cycle=list(self._cycle_trades),
                    bars_df=bars,
                    exit_price=last_close,
                    exit_reason="end_of_data",
                    trend_defense_level_max=self._tds_level_max,
                )

        return SimulationResult(
            trades=logger.get_trades_df(),
            cycles=logger.get_cycles_df(),
            bars_processed=len(bars),
        )
