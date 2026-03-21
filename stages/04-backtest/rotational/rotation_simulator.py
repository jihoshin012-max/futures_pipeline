# archetype: rotational
"""Rotation simulator — unified multi-approach state machine for the rotational archetype.

Extends the Phase 0 calibrated tick-fast simulator to support four approach
variants (A-D) via RotationConfig. Preserves exact Phase 0 logic for
Approach B verification.

Approach behavior (only ADD logic differs; SEED and REVERSAL are shared):
    A: Pure rotation — against move fires reversal, not add. Position always 1.
    B: Traditional martingale — adds against at AddDist, anchor walks on add.
    C: Anti-martingale — adds in-favor at N×ConfirmDist, anchor frozen on add.
    D: Scaled entry — same as C but add_size can be > 1.

Usage:
    from config_schema import RotationConfig
    from rotation_simulator import run_simulation

    config = RotationConfig(config_id="B_SD25_AD10_MA2", approach="B",
                            step_dist=25.0, add_dist=10.0, max_adds=2)
    result = run_simulation(config, bars_df)
    # result.cycles: pd.DataFrame with enriched cycle log
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

from config_schema import FrozenAnchorConfig, RotationConfig
from cycle_logger import (
    CycleLog, CycleRecord, FACycleLog, FACycleRecord,
    FAMissedLog, FAMissedRecord,
)


# ---------------------------------------------------------------------------
# RTH session constants
# ---------------------------------------------------------------------------
_RTH_START_SECONDS = 9 * 3600 + 30 * 60   # 09:30 ET
_RTH_END_SECONDS = 16 * 3600 + 15 * 60    # 16:15 ET


# ---------------------------------------------------------------------------
# SimulationResult
# ---------------------------------------------------------------------------

@dataclass
class SimulationResult:
    """Output of run_simulation()."""
    cycles: pd.DataFrame
    trades: pd.DataFrame
    bars_processed: int
    incomplete_cycles: pd.DataFrame = None  # Cycles discarded at session end
    missed_entries: pd.DataFrame = None     # Pullback mode: direction detected but never entered

    def __post_init__(self) -> None:
        if self.incomplete_cycles is None:
            self.incomplete_cycles = pd.DataFrame(columns=[
                "config_id", "cycle_id", "start_time", "end_time", "side",
                "position_size", "add_count", "avg_entry", "last_price",
                "unrealized_pnl_ticks",
            ])
        if self.missed_entries is None:
            self.missed_entries = pd.DataFrame(columns=[
                "config_id", "date", "direction_detect_time", "direction",
                "hwm_reached", "exit_reason", "hypothetical_immediate_pnl",
            ])


# ---------------------------------------------------------------------------
# Session filtering
# ---------------------------------------------------------------------------

def filter_rth_sessions(bars: pd.DataFrame) -> list[tuple[int, int]]:
    """Return list of (start_idx, end_idx) tuples for each RTH session.

    Each tuple marks a contiguous RTH session in the bar DataFrame.
    The simulator resets state at the start of each session.
    """
    if "datetime" not in bars.columns:
        return [(0, len(bars) - 1)]

    dt = pd.to_datetime(bars["datetime"])
    time_seconds = dt.dt.hour * 3600 + dt.dt.minute * 60 + dt.dt.second
    dates = dt.dt.date

    rth_mask = (time_seconds >= _RTH_START_SECONDS) & (time_seconds < _RTH_END_SECONDS)

    sessions: list[tuple[int, int]] = []
    in_session = False
    session_start = 0
    prev_date = None

    for i in range(len(bars)):
        if not rth_mask.iloc[i]:
            if in_session:
                sessions.append((session_start, i - 1))
                in_session = False
            continue

        cur_date = dates.iloc[i]
        if not in_session:
            session_start = i
            in_session = True
            prev_date = cur_date
        elif cur_date != prev_date:
            # New date within RTH — close previous session, start new
            sessions.append((session_start, i - 1))
            session_start = i
            prev_date = cur_date

    if in_session:
        sessions.append((session_start, len(bars) - 1))

    return sessions


# ---------------------------------------------------------------------------
# Core simulation loop
# ---------------------------------------------------------------------------

def run_simulation(
    config: RotationConfig,
    bars: pd.DataFrame,
    *,
    context_bars: Optional[pd.DataFrame] = None,
    tick_size: float = 0.25,
    rth_filter: bool = True,
    strict_trigger: bool = False,
    initial_watch_price: float = 0.0,
) -> SimulationResult:
    """Run the rotation simulator with the given config on bar data.

    Args:
        config: RotationConfig defining the approach and parameters.
        bars: DataFrame with columns: Last, High, Low, Open, datetime.
              For tick data, O=H=L=Last.
        context_bars: Optional pre-tagged DataFrame (from context_tagger.tag_context)
                      with regime context columns. If None, context columns are NaN.
        tick_size: Instrument tick size (default 0.25 for NQ).
        rth_filter: If True (default), apply RTH session filtering and reset
                    state at session boundaries. If False, treat all data as
                    one continuous session (for calibration/verification).
        strict_trigger: If True, use strict > (not >=) for positioned-state
                        triggers. Matches Phase 0 calibration behavior where
                        tick-batching offsets are modeled with strict comparison.
        initial_watch_price: Pre-set watch price for first session (0.0 = use
                             first tick). Used for calibration verification.

    Returns:
        SimulationResult with enriched cycle log.
    """
    prices = bars["Last"].values.astype(np.float64)
    dts = bars["datetime"].values if "datetime" in bars.columns else np.arange(len(bars))
    n = len(prices)

    # Config params
    approach = config.approach
    step_dist = config.step_dist
    add_dist = config.add_dist
    confirm_dist = config.confirm_dist
    max_adds = config.max_adds
    add_size = config.add_size
    cost_ticks = config.cost_ticks

    # Determine RTH sessions
    if rth_filter:
        sessions = filter_rth_sessions(bars)
        if not sessions:
            sessions = [(0, n - 1)]
    else:
        # No RTH filter — treat entire dataset as one continuous session
        sessions = [(0, n - 1)]

    # Accumulators
    cycle_log = CycleLog()
    trade_records: list[dict] = []
    incomplete_records: list[dict] = []
    global_cycle_id = 0

    for sess_start, sess_end in sessions:
        # --- Reset state at session start ---
        state = -1  # -1=WATCHING, 1=LONG, 2=SHORT
        watch_price = initial_watch_price if (sess_start == sessions[0][0]) else 0.0
        anchor = 0.0
        original_entry_price = 0.0  # For half_block_profit (tracks seed/reversal price)
        add_count = 0
        position_qty = 0
        avg_entry = 0.0
        cycle_start_bar = sess_start
        cycle_trades: list[dict] = []
        cumulative_cost = 0.0

        # MFE/MAE tracking (in points from avg entry)
        mfe_points = 0.0
        mae_points = 0.0

        # Shadow: half_block_profit tracking
        half_block_captured = False
        half_block_profit: Optional[float] = None

        # Shadow: would_flatten_reseed (Approach B only)
        max_adverse_from_entry = 0.0

        # Approach C/D: track next add threshold index
        # next_add_number = add_count + 1 (the Nth add fires at N×ConfirmDist)
        # Threshold computed as: anchor + next_add_number × confirm_dist × direction_sign

        for i in range(sess_start, sess_end + 1):
            price = prices[i]

            # ----- WATCHING state -----
            if state == -1:
                if watch_price == 0.0:
                    watch_price = price
                    continue

                up_dist = price - watch_price
                down_dist = watch_price - price

                if up_dist >= step_dist:
                    # Seed LONG
                    global_cycle_id += 1
                    state = 1
                    anchor = price
                    original_entry_price = price
                    position_qty = 1
                    avg_entry = price
                    add_count = 0
                    cycle_start_bar = i
                    cumulative_cost = cost_ticks * 1
                    mfe_points = 0.0
                    mae_points = 0.0
                    half_block_captured = False
                    half_block_profit = None
                    max_adverse_from_entry = 0.0

                    trade = {
                        "bar_idx": i, "datetime": dts[i], "action": "SEED",
                        "direction": "Long", "qty": 1, "price": price,
                        "anchor": price, "cost": cost_ticks,
                        "cycle_id": global_cycle_id,
                    }
                    trade_records.append(trade)
                    cycle_trades = [trade]

                elif down_dist >= step_dist:
                    # Seed SHORT
                    global_cycle_id += 1
                    state = 2
                    anchor = price
                    original_entry_price = price
                    position_qty = 1
                    avg_entry = price
                    add_count = 0
                    cycle_start_bar = i
                    cumulative_cost = cost_ticks * 1
                    mfe_points = 0.0
                    mae_points = 0.0
                    half_block_captured = False
                    half_block_profit = None
                    max_adverse_from_entry = 0.0

                    trade = {
                        "bar_idx": i, "datetime": dts[i], "action": "SEED",
                        "direction": "Short", "qty": 1, "price": price,
                        "anchor": price, "cost": cost_ticks,
                        "cycle_id": global_cycle_id,
                    }
                    trade_records.append(trade)
                    cycle_trades = [trade]

                continue

            # ----- POSITIONED state -----
            direction_sign = 1.0 if state == 1 else -1.0  # +1 Long, -1 Short
            direction_str = "Long" if state == 1 else "Short"
            favor_move = (price - anchor) * direction_sign
            against_move = -favor_move

            # Track MFE/MAE (from avg entry, in points)
            unrealized_points = (price - avg_entry) * direction_sign
            if unrealized_points > mfe_points:
                mfe_points = unrealized_points
            if unrealized_points < mae_points:
                mae_points = unrealized_points

            # Track max adverse from original entry (for would_flatten_reseed)
            adverse_from_entry = -(price - original_entry_price) * direction_sign
            if adverse_from_entry > max_adverse_from_entry:
                max_adverse_from_entry = adverse_from_entry

            # Shadow: half_block_profit
            if not half_block_captured:
                favor_from_original = (price - original_entry_price) * direction_sign
                if favor_from_original >= 0.5 * step_dist:
                    # Snapshot PnL at this point
                    gross_at_snap = (price - avg_entry) * direction_sign / tick_size * position_qty
                    half_block_profit = gross_at_snap - cumulative_cost
                    half_block_captured = True

            # --- Determine triggers ---
            # strict_trigger: use > for positioned triggers (calibration mode)
            # normal: use >= (production sweep mode)
            if strict_trigger:
                reversal_triggered = favor_move > step_dist
            else:
                reversal_triggered = favor_move >= step_dist

            # Add trigger depends on approach
            add_triggered = False
            add_is_reversal = False  # Approach A: against fires reversal

            if approach == "A":
                # Against move >= StepDist fires a REVERSAL (not add)
                cond = against_move > step_dist if strict_trigger else against_move >= step_dist
                if cond:
                    add_is_reversal = True
                    add_triggered = True

            elif approach == "B":
                # Against move >= AddDist fires an ADD
                cond = against_move > add_dist if strict_trigger else against_move >= add_dist
                if cond:
                    if add_count < max_adds:
                        add_triggered = True
                    # else: frozen — hold, ignore against trigger

            elif approach in ("C", "D"):
                # Favorable adds at successive multiples of ConfirmDist
                # Next add fires at (add_count + 1) × ConfirmDist in favor from ORIGINAL anchor
                # Note: anchor does NOT move on favorable adds for C/D
                if add_count < max_adds and confirm_dist > 0:
                    next_threshold = (add_count + 1) * confirm_dist
                    favor_from_anchor = (price - anchor) * direction_sign
                    cond = favor_from_anchor > next_threshold if strict_trigger else favor_from_anchor >= next_threshold
                    if cond:
                        add_triggered = True

            # --- PRIORITY RULE: reversal always takes priority over add ---
            if reversal_triggered and add_triggered:
                add_triggered = False

            # --- Approach A special: against-reversal ---
            if add_is_reversal and not reversal_triggered:
                # Against-trigger fires reversal in Approach A
                reversal_triggered = True

            # --- Execute REVERSAL ---
            if reversal_triggered:
                # Flatten current position
                flatten_cost = cost_ticks * position_qty
                cumulative_cost += flatten_cost

                flatten_trade = {
                    "bar_idx": i, "datetime": dts[i], "action": "FLATTEN",
                    "direction": direction_str, "qty": position_qty, "price": price,
                    "anchor": anchor, "cost": flatten_cost,
                    "cycle_id": global_cycle_id,
                }
                trade_records.append(flatten_trade)
                cycle_trades.append(flatten_trade)

                # Compute cycle PnL
                entry_trades = [t for t in cycle_trades if t["action"] in ("SEED", "REVERSAL", "ADD")]
                total_qty = sum(t["qty"] for t in entry_trades)
                if total_qty > 0:
                    wavg = sum(t["price"] * t["qty"] for t in entry_trades) / total_qty
                else:
                    wavg = price
                if state == 1:  # Long
                    gross = (price - wavg) / tick_size * total_qty
                    per_unit = (price - wavg) / tick_size
                else:  # Short
                    gross = (wavg - price) / tick_size * total_qty
                    per_unit = (wavg - price) / tick_size
                net = gross - cumulative_cost

                # Shadow: would_flatten_reseed
                wfr = False
                if approach == "B" and add_dist > 0:
                    wfr = max_adverse_from_entry >= 3.0 * add_dist

                # Build cycle record
                rec = CycleRecord(
                    config_id=config.config_id,
                    approach=config.approach,
                    step_dist=config.step_dist,
                    add_dist=config.add_dist,
                    confirm_dist=config.confirm_dist,
                    cycle_id=global_cycle_id,
                    start_time=dts[cycle_start_bar],
                    end_time=dts[i],
                    duration_bars=i - cycle_start_bar + 1,
                    duration_minutes=(i - cycle_start_bar + 1) * 0.0,  # placeholder; real time below
                    start_bar_idx=cycle_start_bar,
                    end_bar_idx=i,
                    side="LONG" if state == 1 else "SHORT",
                    add_count=add_count,
                    exit_position=position_qty,
                    pnl_ticks_gross=round(gross, 4),
                    pnl_ticks_net=round(net, 4),
                    pnl_ticks_per_unit=round(per_unit, 4),
                    mfe_points=round(mfe_points, 4),
                    mae_points=round(mae_points, 4),
                    would_flatten_reseed=wfr,
                    half_block_profit=round(half_block_profit, 4) if half_block_profit is not None else None,
                )

                # Duration in minutes (from datetime if available)
                try:
                    t_start = pd.Timestamp(dts[cycle_start_bar])
                    t_end = pd.Timestamp(dts[i])
                    rec.duration_minutes = round((t_end - t_start).total_seconds() / 60.0, 2)
                except Exception:
                    pass

                # Look up regime context from pre-computed bars
                if context_bars is not None and cycle_start_bar < len(context_bars):
                    ctx_row = context_bars.iloc[cycle_start_bar]
                    rec.atr_20bar = _safe_float(ctx_row, "atr_20")
                    rec.atr_percentile = _safe_float(ctx_row, "atr_pct")
                    rec.swing_median_20 = _safe_float(ctx_row, "swing_median_20")
                    rec.swing_p90_20 = _safe_float(ctx_row, "swing_p90_20")
                    rec.directional_persistence = _safe_int(ctx_row, "directional_persistence")
                    rec.bar_range_median_20 = _safe_float(ctx_row, "bar_range_median_20")

                cycle_log.append(rec)

                # Enter new cycle in opposite direction
                new_direction = 2 if state == 1 else 1
                new_dir_str = "Short" if state == 1 else "Long"
                global_cycle_id += 1
                state = new_direction
                anchor = price
                original_entry_price = price
                position_qty = 1
                avg_entry = price
                add_count = 0
                cycle_start_bar = i
                cumulative_cost = cost_ticks * 1
                mfe_points = 0.0
                mae_points = 0.0
                half_block_captured = False
                half_block_profit = None
                max_adverse_from_entry = 0.0

                rev_trade = {
                    "bar_idx": i, "datetime": dts[i], "action": "REVERSAL",
                    "direction": new_dir_str, "qty": 1, "price": price,
                    "anchor": price, "cost": cost_ticks,
                    "cycle_id": global_cycle_id,
                }
                trade_records.append(rev_trade)
                cycle_trades = [rev_trade]
                continue

            # --- Execute ADD ---
            if add_triggered:
                qty = 1 if approach in ("A", "B", "C") else add_size
                add_cost = cost_ticks * qty
                cumulative_cost += add_cost

                old_qty = position_qty
                position_qty += qty
                avg_entry = (avg_entry * old_qty + price * qty) / position_qty
                add_count += 1

                # Anchor behavior:
                # B: anchor walks to add price
                # C/D: anchor does NOT reset on favorable add
                if approach == "B":
                    anchor = price

                add_trade = {
                    "bar_idx": i, "datetime": dts[i], "action": "ADD",
                    "direction": direction_str, "qty": qty, "price": price,
                    "anchor": anchor, "cost": add_cost,
                    "cycle_id": global_cycle_id,
                }
                trade_records.append(add_trade)
                cycle_trades.append(add_trade)

        # End of session: capture incomplete cycle before discarding
        # (state != -1 means a cycle was in progress)
        if state != -1:
            last_price = prices[sess_end]
            last_dt = dts[sess_end]
            direction_sign_inc = 1.0 if state == 1 else -1.0
            unrealized_pnl = (last_price - avg_entry) * direction_sign_inc / tick_size * position_qty
            incomplete_records.append({
                "config_id": config.config_id,
                "cycle_id": global_cycle_id,
                "start_time": dts[cycle_start_bar],
                "end_time": last_dt,
                "side": "LONG" if state == 1 else "SHORT",
                "position_size": position_qty,
                "add_count": add_count,
                "avg_entry": round(avg_entry, 4),
                "last_price": last_price,
                "unrealized_pnl_ticks": round(unrealized_pnl, 4),
            })

    # Build output DataFrames
    trades_df = pd.DataFrame(trade_records) if trade_records else pd.DataFrame(
        columns=["bar_idx", "datetime", "action", "direction", "qty", "price",
                 "anchor", "cost", "cycle_id"]
    )
    cycles_df = cycle_log.to_dataframe()

    incomplete_df = pd.DataFrame(incomplete_records) if incomplete_records else pd.DataFrame(
        columns=["config_id", "cycle_id", "start_time", "end_time", "side",
                 "position_size", "add_count", "avg_entry", "last_price",
                 "unrealized_pnl_ticks"]
    )

    return SimulationResult(
        cycles=cycles_df,
        trades=trades_df,
        bars_processed=n,
        incomplete_cycles=incomplete_df,
    )


# ---------------------------------------------------------------------------
# Frozen-anchor simulation
# ---------------------------------------------------------------------------

def run_frozen_anchor_simulation(
    config: FrozenAnchorConfig,
    bars: pd.DataFrame,
    *,
    context_bars: Optional[pd.DataFrame] = None,
    tick_size: float = 0.25,
    rth_filter: bool = True,
) -> SimulationResult:
    """Run the frozen-anchor rotation simulator.

    The frozen anchor sets AnchorPrice once at seed/re-seed and never moves
    it on adverse adds.  Three triggers are checked on every bar in priority
    order: SUCCESS > FAILURE > ADD.

    Args:
        config: FrozenAnchorConfig with frozen-anchor parameters.
        bars: DataFrame with columns: Last, High, Low, Open, datetime.
        context_bars: Optional pre-tagged DataFrame for regime context.
        tick_size: Instrument tick size (default 0.25 for NQ).
        rth_filter: If True, apply RTH session filtering.

    Returns:
        SimulationResult with enriched cycle log including exit_type,
        progress_hwm, and other frozen-anchor diagnostic columns.
    """
    prices = bars["Last"].values.astype(np.float64)
    dts = bars["datetime"].values if "datetime" in bars.columns else np.arange(len(bars))
    n = len(prices)

    # Config params
    step_dist = config.step_dist
    add_dist = config.add_dist
    max_adds = config.max_adds
    reversal_target = config.reversal_target
    cost_ticks = config.cost_ticks
    success_dist = reversal_target * step_dist

    # Determine RTH sessions
    if rth_filter:
        sessions = filter_rth_sessions(bars)
        if not sessions:
            sessions = [(0, n - 1)]
    else:
        sessions = [(0, n - 1)]

    # Accumulators
    cycle_log = FACycleLog()
    trade_records: list[dict] = []
    incomplete_records: list[dict] = []
    global_cycle_id = 0

    # Cross-cycle state for prev_cycle_exit_type and cycle_day_seq
    prev_exit_type = "SESSION_START"

    for sess_start, sess_end in sessions:
        # --- Reset state at session start ---
        state = -1  # -1=WATCHING, 1=LONG, 2=SHORT
        watch_price = 0.0
        anchor = 0.0
        add_count = 0
        position_qty = 0
        avg_entry = 0.0
        cycle_start_bar = sess_start
        cycle_trades: list[dict] = []
        cumulative_cost = 0.0

        # MFE/MAE tracking (in points from avg entry)
        mfe_points = 0.0
        mae_points = 0.0

        # Frozen-anchor diagnostics
        progress_hwm = 0.0  # Max favorable progress as % of step_dist
        add_bar_indices: list[int] = []  # bar indices where adds fired
        add_progress_pcts: list[float] = []  # displacement % at each add
        total_abs_movement = 0.0  # sum of |bar-to-bar| price changes
        prev_price_for_waste = 0.0  # previous bar price for waste calc

        # Shadow
        half_block_captured = False
        half_block_profit: Optional[float] = None
        max_adverse_from_entry = 0.0

        # Day tracking
        cycle_day_seq = 0
        prev_exit_type = "SESSION_START"  # reset at session boundary

        for i in range(sess_start, sess_end + 1):
            price = prices[i]

            # ----- WATCHING state -----
            if state == -1:
                if watch_price == 0.0:
                    watch_price = price
                    continue

                up_dist = price - watch_price
                down_dist = watch_price - price

                if up_dist >= step_dist:
                    # Seed LONG
                    global_cycle_id += 1
                    cycle_day_seq += 1
                    state = 1
                    anchor = price
                    position_qty = 1
                    avg_entry = price
                    add_count = 0
                    cycle_start_bar = i
                    cumulative_cost = cost_ticks * 1
                    mfe_points = 0.0
                    mae_points = 0.0
                    progress_hwm = 0.0
                    add_bar_indices = []
                    add_progress_pcts = []
                    total_abs_movement = 0.0
                    prev_price_for_waste = price
                    half_block_captured = False
                    half_block_profit = None
                    max_adverse_from_entry = 0.0

                    trade = {
                        "bar_idx": i, "datetime": dts[i], "action": "SEED",
                        "direction": "Long", "qty": 1, "price": price,
                        "anchor": price, "cost": cost_ticks,
                        "cycle_id": global_cycle_id,
                    }
                    trade_records.append(trade)
                    cycle_trades = [trade]

                elif down_dist >= step_dist:
                    # Seed SHORT
                    global_cycle_id += 1
                    cycle_day_seq += 1
                    state = 2
                    anchor = price
                    position_qty = 1
                    avg_entry = price
                    add_count = 0
                    cycle_start_bar = i
                    cumulative_cost = cost_ticks * 1
                    mfe_points = 0.0
                    mae_points = 0.0
                    progress_hwm = 0.0
                    add_bar_indices = []
                    add_progress_pcts = []
                    total_abs_movement = 0.0
                    prev_price_for_waste = price
                    half_block_captured = False
                    half_block_profit = None
                    max_adverse_from_entry = 0.0

                    trade = {
                        "bar_idx": i, "datetime": dts[i], "action": "SEED",
                        "direction": "Short", "qty": 1, "price": price,
                        "anchor": price, "cost": cost_ticks,
                        "cycle_id": global_cycle_id,
                    }
                    trade_records.append(trade)
                    cycle_trades = [trade]

                continue

            # ----- POSITIONED state -----
            direction_sign = 1.0 if state == 1 else -1.0
            direction_str = "Long" if state == 1 else "Short"

            # Waste tracking: accumulate absolute bar-to-bar movement
            total_abs_movement += abs(price - prev_price_for_waste)
            prev_price_for_waste = price

            # Moves from FROZEN anchor
            favor_move = (price - anchor) * direction_sign
            against_move = -favor_move

            # Track MFE/MAE (from avg entry, in points)
            unrealized_points = (price - avg_entry) * direction_sign
            if unrealized_points > mfe_points:
                mfe_points = unrealized_points
            if unrealized_points < mae_points:
                mae_points = unrealized_points

            # Track max adverse from anchor (for would_flatten_reseed shadow)
            if against_move > max_adverse_from_entry:
                max_adverse_from_entry = against_move

            # Progress tracking (% of step_dist from anchor)
            progress_pct = favor_move / step_dist * 100.0
            if progress_pct > progress_hwm:
                progress_hwm = progress_pct

            # Shadow: half_block_profit
            if not half_block_captured:
                if favor_move >= 0.5 * step_dist:
                    gross_at_snap = (price - avg_entry) * direction_sign / tick_size * position_qty
                    half_block_profit = gross_at_snap - cumulative_cost
                    half_block_captured = True

            # --- Check triggers in PRIORITY ORDER ---
            # Priority 1: SUCCESS
            success_triggered = favor_move >= success_dist
            # Priority 2: FAILURE
            failure_triggered = against_move >= step_dist
            # Priority 3: ADD
            add_triggered = False
            if max_adds > 0 and add_count < max_adds:
                add_threshold = (add_count + 1) * add_dist
                if against_move >= add_threshold:
                    add_triggered = True

            # Fire the FIRST triggered condition
            if success_triggered:
                exit_type = "SUCCESS"
            elif failure_triggered:
                exit_type = "FAILURE"
                add_triggered = False  # suppressed by priority
            else:
                exit_type = None
                # add_triggered may still be True

            # --- Execute EXIT (SUCCESS or FAILURE) ---
            if exit_type is not None:
                # Flatten current position
                flatten_cost = cost_ticks * position_qty
                reseed_cost = cost_ticks * 1
                cumulative_cost += flatten_cost + reseed_cost

                flatten_trade = {
                    "bar_idx": i, "datetime": dts[i], "action": "FLATTEN",
                    "direction": direction_str, "qty": position_qty, "price": price,
                    "anchor": anchor, "cost": flatten_cost,
                    "cycle_id": global_cycle_id,
                }
                trade_records.append(flatten_trade)
                cycle_trades.append(flatten_trade)

                # Compute cycle PnL
                entry_trades = [t for t in cycle_trades if t["action"] in ("SEED", "REVERSAL", "ADD")]
                total_qty = sum(t["qty"] for t in entry_trades)
                if total_qty > 0:
                    wavg = sum(t["price"] * t["qty"] for t in entry_trades) / total_qty
                else:
                    wavg = price
                if state == 1:  # Long
                    gross = (price - wavg) / tick_size * total_qty
                else:  # Short
                    gross = (wavg - price) / tick_size * total_qty
                net = gross - cumulative_cost

                # Shadow: would_flatten_reseed
                wfr = max_adverse_from_entry >= 3.0 * add_dist

                # time_between_adds
                tba_parts: list[str] = []
                for j in range(1, len(add_bar_indices)):
                    tba_parts.append(str(add_bar_indices[j] - add_bar_indices[j - 1]))
                time_between_adds_str = ",".join(tba_parts)

                # progress_at_adds
                progress_at_adds_str = ",".join(str(round(p, 1)) for p in add_progress_pcts)

                # cycle_waste_pct
                net_displacement = abs(price - prices[cycle_start_bar])
                if net_displacement > 0:
                    waste_pct = round(total_abs_movement / net_displacement, 4)
                else:
                    waste_pct = 0.0

                # cycle_start_hour
                try:
                    start_hour = int(pd.Timestamp(dts[cycle_start_bar]).hour)
                except Exception:
                    start_hour = 0

                # Build cycle record
                rec = FACycleRecord(
                    config_id=config.config_id,
                    step_dist=config.step_dist,
                    add_dist=config.add_dist,
                    max_adds=config.max_adds,
                    reversal_target=config.reversal_target,
                    cycle_id=global_cycle_id,
                    start_time=dts[cycle_start_bar],
                    end_time=dts[i],
                    duration_bars=i - cycle_start_bar + 1,
                    duration_minutes=0.0,
                    start_bar_idx=cycle_start_bar,
                    end_bar_idx=i,
                    side="LONG" if state == 1 else "SHORT",
                    add_count=add_count,
                    exit_position=position_qty,
                    pnl_ticks_gross=round(gross, 4),
                    pnl_ticks_net=round(net, 4),
                    mfe_points=round(mfe_points, 4),
                    mae_points=round(mae_points, 4),
                    exit_type=exit_type,
                    progress_hwm=round(progress_hwm, 2),
                    time_between_adds=time_between_adds_str,
                    cycle_day_seq=cycle_day_seq,
                    cycle_start_hour=start_hour,
                    progress_at_adds=progress_at_adds_str,
                    prev_cycle_exit_type=prev_exit_type,
                    cycle_waste_pct=waste_pct,
                    would_flatten_reseed=wfr,
                    half_block_profit=round(half_block_profit, 4) if half_block_profit is not None else None,
                )

                # Duration in minutes
                try:
                    t_start = pd.Timestamp(dts[cycle_start_bar])
                    t_end = pd.Timestamp(dts[i])
                    rec.duration_minutes = round((t_end - t_start).total_seconds() / 60.0, 2)
                except Exception:
                    pass

                # Look up regime context
                if context_bars is not None and cycle_start_bar < len(context_bars):
                    ctx_row = context_bars.iloc[cycle_start_bar]
                    rec.atr_20bar = _safe_float(ctx_row, "atr_20")
                    rec.atr_percentile = _safe_float(ctx_row, "atr_pct")
                    rec.swing_median_20 = _safe_float(ctx_row, "swing_median_20")
                    rec.swing_p90_20 = _safe_float(ctx_row, "swing_p90_20")
                    rec.directional_persistence = _safe_int(ctx_row, "directional_persistence")
                    rec.bar_range_median_20 = _safe_float(ctx_row, "bar_range_median_20")

                cycle_log.append(rec)

                # Update prev_exit_type for next cycle
                prev_exit_type = exit_type

                # --- Immediate re-seed in opposite direction ---
                new_direction = 2 if state == 1 else 1
                new_dir_str = "Short" if state == 1 else "Long"
                global_cycle_id += 1
                cycle_day_seq += 1
                state = new_direction
                anchor = price
                position_qty = 1
                avg_entry = price
                add_count = 0
                cycle_start_bar = i
                cumulative_cost = 0.0  # reseed cost charged to previous cycle
                mfe_points = 0.0
                mae_points = 0.0
                progress_hwm = 0.0
                add_bar_indices = []
                add_progress_pcts = []
                total_abs_movement = 0.0
                prev_price_for_waste = price
                half_block_captured = False
                half_block_profit = None
                max_adverse_from_entry = 0.0

                rev_trade = {
                    "bar_idx": i, "datetime": dts[i], "action": "REVERSAL",
                    "direction": new_dir_str, "qty": 1, "price": price,
                    "anchor": price, "cost": cost_ticks,
                    "cycle_id": global_cycle_id,
                }
                trade_records.append(rev_trade)
                cycle_trades = [rev_trade]
                continue

            # --- Execute ADD ---
            if add_triggered:
                add_cost = cost_ticks * 1
                cumulative_cost += add_cost

                old_qty = position_qty
                position_qty += 1
                avg_entry = (avg_entry * old_qty + price * 1) / position_qty
                add_count += 1

                # Record add diagnostics
                add_bar_indices.append(i)
                # Progress at add = displacement from anchor as % of StepDist (negative = adverse)
                add_pct = round((price - anchor) * direction_sign / step_dist * 100.0, 1)
                add_progress_pcts.append(add_pct)

                # Anchor does NOT change — this is the core frozen-anchor rule

                add_trade = {
                    "bar_idx": i, "datetime": dts[i], "action": "ADD",
                    "direction": direction_str, "qty": 1, "price": price,
                    "anchor": anchor, "cost": add_cost,
                    "cycle_id": global_cycle_id,
                }
                trade_records.append(add_trade)
                cycle_trades.append(add_trade)

        # End of session: capture incomplete cycle
        if state != -1:
            last_price = prices[sess_end]
            last_dt = dts[sess_end]
            direction_sign_inc = 1.0 if state == 1 else -1.0
            unrealized_pnl = (last_price - avg_entry) * direction_sign_inc / tick_size * position_qty

            # Compute progress_hwm for incomplete cycle
            try:
                start_hour_inc = int(pd.Timestamp(dts[cycle_start_bar]).hour)
            except Exception:
                start_hour_inc = 0

            incomplete_records.append({
                "config_id": config.config_id,
                "cycle_id": global_cycle_id,
                "start_time": dts[cycle_start_bar],
                "end_time": last_dt,
                "side": "LONG" if state == 1 else "SHORT",
                "position_size": position_qty,
                "add_count": add_count,
                "avg_entry": round(avg_entry, 4),
                "last_price": last_price,
                "unrealized_pnl_ticks": round(unrealized_pnl, 4),
                "exit_type": "SESSION_END",
                "progress_hwm": round(progress_hwm, 2),
                "cycle_day_seq": cycle_day_seq,
            })

    # Build output DataFrames
    trades_df = pd.DataFrame(trade_records) if trade_records else pd.DataFrame(
        columns=["bar_idx", "datetime", "action", "direction", "qty", "price",
                 "anchor", "cost", "cycle_id"]
    )
    cycles_df = cycle_log.to_dataframe()

    incomplete_cols = [
        "config_id", "cycle_id", "start_time", "end_time", "side",
        "position_size", "add_count", "avg_entry", "last_price",
        "unrealized_pnl_ticks", "exit_type", "progress_hwm", "cycle_day_seq",
    ]
    incomplete_df = pd.DataFrame(incomplete_records) if incomplete_records else pd.DataFrame(
        columns=incomplete_cols
    )

    return SimulationResult(
        cycles=cycles_df,
        trades=trades_df,
        bars_processed=n,
        incomplete_cycles=incomplete_df,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_float(row: pd.Series, col: str) -> float:
    """Extract float from row, returning NaN if missing."""
    try:
        v = row[col]
        return float(v) if not pd.isna(v) else np.nan
    except (KeyError, TypeError):
        return np.nan


def _safe_int(row: pd.Series, col: str) -> int:
    """Extract int from row, returning 0 if missing."""
    try:
        v = row[col]
        return int(v) if not pd.isna(v) else 0
    except (KeyError, TypeError):
        return 0


# ---------------------------------------------------------------------------
# Pullback entry simulation
# ---------------------------------------------------------------------------
# States: WATCHING=-1, CONFIRMING=3, LONG=1, SHORT=2

def run_pullback_simulation(
    config: FrozenAnchorConfig,
    bars: pd.DataFrame,
    *,
    context_bars: Optional[pd.DataFrame] = None,
    tick_size: float = 0.25,
    rth_filter: bool = True,
) -> SimulationResult:
    """Run frozen-anchor simulator with pullback entry (CONFIRMING state).

    Adds a CONFIRMING state between direction detection and position entry.
    The strategy waits for a child-scale pullback before entering, testing
    whether fractal-aligned entry captures the 80% completion edge.

    Three re-entry modes after SUCCESS/FAILURE exits:
        A = Full Re-Watch: return to WATCHING, require full SD move + pullback
        B = Confirm Only: enter CONFIRMING with dir=opposite, skip detection
        C = Pullback Seed Only: pullback entry for first trade only, then
            immediate re-seed (identical to current frozen anchor)
    """
    prices = bars["Last"].values.astype(np.float64)
    dts = bars["datetime"].values if "datetime" in bars.columns else np.arange(len(bars))
    n = len(prices)

    # Config params
    step_dist = config.step_dist
    seed_dist = config.seed_dist  # Detection threshold (may differ from step_dist)
    add_dist = config.add_dist
    max_adds = config.max_adds
    reversal_target = config.reversal_target
    cost_ticks = config.cost_ticks
    success_dist = reversal_target * step_dist
    reentry_mode = config.reentry_mode

    # Determine RTH sessions
    if rth_filter:
        sessions = filter_rth_sessions(bars)
        if not sessions:
            sessions = [(0, n - 1)]
    else:
        sessions = [(0, n - 1)]

    # Accumulators
    cycle_log = FACycleLog()
    missed_log = FAMissedLog()
    trade_records: list[dict] = []
    incomplete_records: list[dict] = []
    global_cycle_id = 0

    prev_exit_type = "SESSION_START"

    for sess_start, sess_end in sessions:
        # --- Reset state at session start ---
        state = -1  # WATCHING
        watch_price = 0.0
        anchor = 0.0
        add_count = 0
        position_qty = 0
        avg_entry = 0.0
        cycle_start_bar = sess_start
        cycle_trades: list[dict] = []
        cumulative_cost = 0.0

        # MFE/MAE
        mfe_points = 0.0
        mae_points = 0.0

        # Frozen-anchor diagnostics
        progress_hwm = 0.0
        add_bar_indices: list[int] = []
        add_progress_pcts: list[float] = []
        total_abs_movement = 0.0
        prev_price_for_waste = 0.0

        # Shadow
        half_block_captured = False
        half_block_profit: Optional[float] = None
        max_adverse_from_entry = 0.0

        # Day tracking
        cycle_day_seq = 0
        prev_exit_type = "SESSION_START"

        # CONFIRMING state variables
        confirm_dir = 0       # 1=Long, 2=Short
        confirm_extreme = 0.0  # HWM (max for Long, min for Short)
        confirm_watch_price = 0.0  # WatchPrice / exit price
        confirm_start_bar = 0
        confirm_start_dt = None
        confirm_extension_met = False
        confirm_is_post_exit = False
        confirm_detect_price = 0.0  # Price at detection (for hypothetical PnL)

        # Pullback diagnostic variables (set on CONFIRMING→POSITIONED, used on EXIT)
        _pb_entry_type = "PULLBACK"
        _pb_detect_time = None
        _pb_confirm_bars = 0
        _pb_hwm = 0.0
        _pb_depth = 0.0
        _pb_runaway = False
        _pb_remaining: Optional[float] = None

        for i in range(sess_start, sess_end + 1):
            price = prices[i]

            # ===== WATCHING state =====
            if state == -1:
                if watch_price == 0.0:
                    watch_price = price
                    continue

                up_dist = price - watch_price
                down_dist = watch_price - price

                if up_dist >= seed_dist:
                    # Direction detected: LONG → CONFIRMING
                    state = 3
                    confirm_dir = 1
                    confirm_extreme = price
                    confirm_watch_price = watch_price
                    confirm_start_bar = i
                    confirm_start_dt = dts[i]
                    confirm_extension_met = True  # Seed move IS the extension
                    confirm_is_post_exit = False
                    confirm_detect_price = price

                elif down_dist >= seed_dist:
                    # Direction detected: SHORT → CONFIRMING
                    state = 3
                    confirm_dir = 2
                    confirm_extreme = price
                    confirm_watch_price = watch_price
                    confirm_start_bar = i
                    confirm_start_dt = dts[i]
                    confirm_extension_met = True
                    confirm_is_post_exit = False
                    confirm_detect_price = price

                continue

            # ===== CONFIRMING state =====
            if state == 3:
                if confirm_dir == 1:  # Long detected
                    # Track HWM
                    if price > confirm_extreme:
                        confirm_extreme = price

                    # Extension check (for post-exit Option B)
                    if not confirm_extension_met:
                        if price >= confirm_watch_price + add_dist:
                            confirm_extension_met = True

                    # Invalidation check
                    if confirm_is_post_exit:
                        # Option B: invalidate if price drops ≥ SD from exit (wrong direction)
                        if price <= confirm_watch_price - step_dist:
                            _log_missed(
                                missed_log, config, dts, i, confirm_start_dt,
                                "LONG", confirm_extreme, confirm_watch_price,
                                "INVALIDATED", price, tick_size, cost_ticks,
                                confirm_detect_price,
                            )
                            state = -1
                            watch_price = price
                            continue
                    else:
                        # First-of-day: invalidate if price returns within AD of WatchPrice
                        if price <= confirm_watch_price + add_dist:
                            _log_missed(
                                missed_log, config, dts, i, confirm_start_dt,
                                "LONG", confirm_extreme, confirm_watch_price,
                                "INVALIDATED", price, tick_size, cost_ticks,
                                confirm_detect_price,
                            )
                            state = -1
                            watch_price = price
                            continue

                    # Pullback check (only if extension met)
                    if confirm_extension_met and confirm_extreme - price >= add_dist:
                        # PULLBACK DETECTED → ENTER LONG
                        extension = confirm_extreme - confirm_watch_price
                        pullback = confirm_extreme - price
                        pb_depth = (pullback / extension * 100.0) if extension > 0 else 0.0
                        hwm_ext = extension
                        parent_target_dist = (confirm_watch_price + step_dist) - price if not confirm_is_post_exit else None
                        runaway = hwm_ext > 2.0 * step_dist

                        global_cycle_id += 1
                        cycle_day_seq += 1
                        state = 1
                        anchor = price
                        position_qty = 1
                        avg_entry = price
                        add_count = 0
                        cycle_start_bar = i
                        cumulative_cost = cost_ticks * 1
                        mfe_points = 0.0
                        mae_points = 0.0
                        progress_hwm = 0.0
                        add_bar_indices = []
                        add_progress_pcts = []
                        total_abs_movement = 0.0
                        prev_price_for_waste = price
                        half_block_captured = False
                        half_block_profit = None
                        max_adverse_from_entry = 0.0

                        # Store pullback diagnostics for the cycle record
                        _pb_entry_type = "PULLBACK"
                        _pb_detect_time = confirm_start_dt
                        _pb_confirm_bars = i - confirm_start_bar
                        _pb_hwm = round(hwm_ext, 4)
                        _pb_depth = round(pb_depth, 2)
                        _pb_runaway = runaway
                        _pb_remaining = round(parent_target_dist, 4) if parent_target_dist is not None else None

                        trade = {
                            "bar_idx": i, "datetime": dts[i], "action": "SEED",
                            "direction": "Long", "qty": 1, "price": price,
                            "anchor": price, "cost": cost_ticks,
                            "cycle_id": global_cycle_id,
                        }
                        trade_records.append(trade)
                        cycle_trades = [trade]
                        continue

                else:  # confirm_dir == 2 (Short detected)
                    # Track HWM (minimum for shorts)
                    if price < confirm_extreme:
                        confirm_extreme = price

                    # Extension check (for post-exit Option B)
                    if not confirm_extension_met:
                        if price <= confirm_watch_price - add_dist:
                            confirm_extension_met = True

                    # Invalidation check
                    if confirm_is_post_exit:
                        # Option B: invalidate if price rises ≥ SD from exit
                        if price >= confirm_watch_price + step_dist:
                            _log_missed(
                                missed_log, config, dts, i, confirm_start_dt,
                                "SHORT", confirm_extreme, confirm_watch_price,
                                "INVALIDATED", price, tick_size, cost_ticks,
                                confirm_detect_price,
                            )
                            state = -1
                            watch_price = price
                            continue
                    else:
                        # First-of-day: invalidate if price returns within AD of WatchPrice
                        if price >= confirm_watch_price - add_dist:
                            _log_missed(
                                missed_log, config, dts, i, confirm_start_dt,
                                "SHORT", confirm_extreme, confirm_watch_price,
                                "INVALIDATED", price, tick_size, cost_ticks,
                                confirm_detect_price,
                            )
                            state = -1
                            watch_price = price
                            continue

                    # Pullback check
                    if confirm_extension_met and price - confirm_extreme >= add_dist:
                        # PULLBACK DETECTED → ENTER SHORT
                        extension = confirm_watch_price - confirm_extreme
                        pullback = price - confirm_extreme
                        pb_depth = (pullback / extension * 100.0) if extension > 0 else 0.0
                        hwm_ext = extension
                        parent_target_dist = price - (confirm_watch_price - step_dist) if not confirm_is_post_exit else None
                        runaway = hwm_ext > 2.0 * step_dist

                        global_cycle_id += 1
                        cycle_day_seq += 1
                        state = 2
                        anchor = price
                        position_qty = 1
                        avg_entry = price
                        add_count = 0
                        cycle_start_bar = i
                        cumulative_cost = cost_ticks * 1
                        mfe_points = 0.0
                        mae_points = 0.0
                        progress_hwm = 0.0
                        add_bar_indices = []
                        add_progress_pcts = []
                        total_abs_movement = 0.0
                        prev_price_for_waste = price
                        half_block_captured = False
                        half_block_profit = None
                        max_adverse_from_entry = 0.0

                        _pb_entry_type = "PULLBACK"
                        _pb_detect_time = confirm_start_dt
                        _pb_confirm_bars = i - confirm_start_bar
                        _pb_hwm = round(hwm_ext, 4)
                        _pb_depth = round(pb_depth, 2)
                        _pb_runaway = runaway
                        _pb_remaining = round(parent_target_dist, 4) if parent_target_dist is not None else None

                        trade = {
                            "bar_idx": i, "datetime": dts[i], "action": "SEED",
                            "direction": "Short", "qty": 1, "price": price,
                            "anchor": price, "cost": cost_ticks,
                            "cycle_id": global_cycle_id,
                        }
                        trade_records.append(trade)
                        cycle_trades = [trade]
                        continue

                continue

            # ===== POSITIONED state (LONG=1 or SHORT=2) =====
            direction_sign = 1.0 if state == 1 else -1.0
            direction_str = "Long" if state == 1 else "Short"

            # Waste tracking
            total_abs_movement += abs(price - prev_price_for_waste)
            prev_price_for_waste = price

            # Moves from FROZEN anchor
            favor_move = (price - anchor) * direction_sign
            against_move = -favor_move

            # Track MFE/MAE
            unrealized_points = (price - avg_entry) * direction_sign
            if unrealized_points > mfe_points:
                mfe_points = unrealized_points
            if unrealized_points < mae_points:
                mae_points = unrealized_points

            # Max adverse from anchor (shadow)
            if against_move > max_adverse_from_entry:
                max_adverse_from_entry = against_move

            # Progress tracking
            progress_pct = favor_move / step_dist * 100.0
            if progress_pct > progress_hwm:
                progress_hwm = progress_pct

            # Shadow: half_block_profit
            if not half_block_captured:
                if favor_move >= 0.5 * step_dist:
                    gross_at_snap = (price - avg_entry) * direction_sign / tick_size * position_qty
                    half_block_profit = gross_at_snap - cumulative_cost
                    half_block_captured = True

            # --- Check triggers in PRIORITY ORDER ---
            success_triggered = favor_move >= success_dist
            failure_triggered = against_move >= step_dist
            add_triggered = False
            if max_adds > 0 and add_count < max_adds:
                add_threshold = (add_count + 1) * add_dist
                if against_move >= add_threshold:
                    add_triggered = True

            if success_triggered:
                exit_type = "SUCCESS"
            elif failure_triggered:
                exit_type = "FAILURE"
                add_triggered = False
            else:
                exit_type = None

            # --- Execute EXIT ---
            if exit_type is not None:
                flatten_cost = cost_ticks * position_qty
                reseed_cost = cost_ticks * 1 if reentry_mode == "C" and cycle_day_seq >= 1 else 0.0
                cumulative_cost += flatten_cost + reseed_cost

                flatten_trade = {
                    "bar_idx": i, "datetime": dts[i], "action": "FLATTEN",
                    "direction": direction_str, "qty": position_qty, "price": price,
                    "anchor": anchor, "cost": flatten_cost,
                    "cycle_id": global_cycle_id,
                }
                trade_records.append(flatten_trade)
                cycle_trades.append(flatten_trade)

                # Compute cycle PnL
                entry_trades = [t for t in cycle_trades if t["action"] in ("SEED", "REVERSAL", "ADD")]
                total_qty = sum(t["qty"] for t in entry_trades)
                if total_qty > 0:
                    wavg = sum(t["price"] * t["qty"] for t in entry_trades) / total_qty
                else:
                    wavg = price
                if state == 1:
                    gross = (price - wavg) / tick_size * total_qty
                else:
                    gross = (wavg - price) / tick_size * total_qty
                net = gross - cumulative_cost

                # Shadow: would_flatten_reseed
                wfr = max_adverse_from_entry >= 3.0 * add_dist

                # time_between_adds
                tba_parts: list[str] = []
                for j in range(1, len(add_bar_indices)):
                    tba_parts.append(str(add_bar_indices[j] - add_bar_indices[j - 1]))
                time_between_adds_str = ",".join(tba_parts)

                # progress_at_adds
                progress_at_adds_str = ",".join(str(round(p, 1)) for p in add_progress_pcts)

                # cycle_waste_pct
                net_displacement = abs(price - prices[cycle_start_bar])
                waste_pct = round(total_abs_movement / net_displacement, 4) if net_displacement > 0 else 0.0

                # cycle_start_hour
                try:
                    start_hour = int(pd.Timestamp(dts[cycle_start_bar]).hour)
                except Exception:
                    start_hour = 0

                # Build cycle record with pullback diagnostics
                rec = FACycleRecord(
                    config_id=config.config_id,
                    step_dist=config.step_dist,
                    add_dist=config.add_dist,
                    max_adds=config.max_adds,
                    reversal_target=config.reversal_target,
                    cycle_id=global_cycle_id,
                    start_time=dts[cycle_start_bar],
                    end_time=dts[i],
                    duration_bars=i - cycle_start_bar + 1,
                    duration_minutes=0.0,
                    start_bar_idx=cycle_start_bar,
                    end_bar_idx=i,
                    side="LONG" if state == 1 else "SHORT",
                    add_count=add_count,
                    exit_position=position_qty,
                    pnl_ticks_gross=round(gross, 4),
                    pnl_ticks_net=round(net, 4),
                    mfe_points=round(mfe_points, 4),
                    mae_points=round(mae_points, 4),
                    exit_type=exit_type,
                    progress_hwm=round(progress_hwm, 2),
                    time_between_adds=time_between_adds_str,
                    cycle_day_seq=cycle_day_seq,
                    cycle_start_hour=start_hour,
                    progress_at_adds=progress_at_adds_str,
                    prev_cycle_exit_type=prev_exit_type,
                    cycle_waste_pct=waste_pct,
                    entry_type=_pb_entry_type,
                    direction_detect_time=_pb_detect_time,
                    confirming_duration_bars=_pb_confirm_bars,
                    hwm_at_entry=_pb_hwm,
                    pullback_depth_pct=_pb_depth,
                    runaway_flag=_pb_runaway,
                    remaining_to_parent_target=_pb_remaining,
                    would_flatten_reseed=wfr,
                    half_block_profit=round(half_block_profit, 4) if half_block_profit is not None else None,
                )

                try:
                    t_start = pd.Timestamp(dts[cycle_start_bar])
                    t_end = pd.Timestamp(dts[i])
                    rec.duration_minutes = round((t_end - t_start).total_seconds() / 60.0, 2)
                except Exception:
                    pass

                if context_bars is not None and cycle_start_bar < len(context_bars):
                    ctx_row = context_bars.iloc[cycle_start_bar]
                    rec.atr_20bar = _safe_float(ctx_row, "atr_20")
                    rec.atr_percentile = _safe_float(ctx_row, "atr_pct")
                    rec.swing_median_20 = _safe_float(ctx_row, "swing_median_20")
                    rec.swing_p90_20 = _safe_float(ctx_row, "swing_p90_20")
                    rec.directional_persistence = _safe_int(ctx_row, "directional_persistence")
                    rec.bar_range_median_20 = _safe_float(ctx_row, "bar_range_median_20")

                cycle_log.append(rec)
                prev_exit_type = exit_type

                # --- POST-EXIT TRANSITION ---
                if reentry_mode == "A":
                    # Full Re-Watch: return to WATCHING
                    state = -1
                    watch_price = price

                elif reentry_mode == "B":
                    # Confirm Only: enter CONFIRMING with opposite direction
                    exited_long = (direction_sign == 1.0)
                    state = 3
                    confirm_dir = 2 if exited_long else 1
                    confirm_extreme = price
                    confirm_watch_price = price  # Reference for invalidation
                    confirm_start_bar = i
                    confirm_start_dt = dts[i]
                    confirm_extension_met = False  # Must extend first
                    confirm_is_post_exit = True
                    confirm_detect_price = price

                elif reentry_mode == "C":
                    # Pullback Seed Only: immediate re-seed opposite
                    new_direction = 2 if (direction_sign == 1.0) else 1
                    new_dir_str = "Short" if (direction_sign == 1.0) else "Long"
                    global_cycle_id += 1
                    cycle_day_seq += 1
                    state = new_direction
                    anchor = price
                    position_qty = 1
                    avg_entry = price
                    add_count = 0
                    cycle_start_bar = i
                    cumulative_cost = 0.0
                    mfe_points = 0.0
                    mae_points = 0.0
                    progress_hwm = 0.0
                    add_bar_indices = []
                    add_progress_pcts = []
                    total_abs_movement = 0.0
                    prev_price_for_waste = price
                    half_block_captured = False
                    half_block_profit = None
                    max_adverse_from_entry = 0.0

                    # Immediate re-seed: entry_type=IMMEDIATE
                    _pb_entry_type = "IMMEDIATE"
                    _pb_detect_time = None
                    _pb_confirm_bars = 0
                    _pb_hwm = 0.0
                    _pb_depth = 0.0
                    _pb_runaway = False
                    _pb_remaining = None

                    rev_trade = {
                        "bar_idx": i, "datetime": dts[i], "action": "REVERSAL",
                        "direction": new_dir_str, "qty": 1, "price": price,
                        "anchor": price, "cost": cost_ticks,
                        "cycle_id": global_cycle_id,
                    }
                    trade_records.append(rev_trade)
                    cycle_trades = [rev_trade]

                continue

            # --- Execute ADD ---
            if add_triggered:
                add_cost = cost_ticks * 1
                cumulative_cost += add_cost

                old_qty = position_qty
                position_qty += 1
                avg_entry = (avg_entry * old_qty + price * 1) / position_qty
                add_count += 1

                add_bar_indices.append(i)
                add_pct = round((price - anchor) * direction_sign / step_dist * 100.0, 1)
                add_progress_pcts.append(add_pct)

                add_trade = {
                    "bar_idx": i, "datetime": dts[i], "action": "ADD",
                    "direction": direction_str, "qty": 1, "price": price,
                    "anchor": anchor, "cost": add_cost,
                    "cycle_id": global_cycle_id,
                }
                trade_records.append(add_trade)
                cycle_trades.append(add_trade)

        # End of session: handle incomplete state
        if state == 3:
            # CONFIRMING at session end → missed entry
            direction_str_miss = "LONG" if confirm_dir == 1 else "SHORT"
            _log_missed(
                missed_log, config, dts, sess_end, confirm_start_dt,
                direction_str_miss, confirm_extreme, confirm_watch_price,
                "SESSION_END", prices[sess_end], tick_size, cost_ticks,
                confirm_detect_price,
            )
            state = -1

        elif state in (1, 2):
            # POSITIONED at session end → incomplete cycle
            last_price = prices[sess_end]
            last_dt = dts[sess_end]
            direction_sign_inc = 1.0 if state == 1 else -1.0
            unrealized_pnl = (last_price - avg_entry) * direction_sign_inc / tick_size * position_qty

            try:
                start_hour_inc = int(pd.Timestamp(dts[cycle_start_bar]).hour)
            except Exception:
                start_hour_inc = 0

            incomplete_records.append({
                "config_id": config.config_id,
                "cycle_id": global_cycle_id,
                "start_time": dts[cycle_start_bar],
                "end_time": last_dt,
                "side": "LONG" if state == 1 else "SHORT",
                "position_size": position_qty,
                "add_count": add_count,
                "avg_entry": round(avg_entry, 4),
                "last_price": last_price,
                "unrealized_pnl_ticks": round(unrealized_pnl, 4),
                "exit_type": "SESSION_END",
                "progress_hwm": round(progress_hwm, 2),
                "cycle_day_seq": cycle_day_seq,
            })

    # Build output DataFrames
    trades_df = pd.DataFrame(trade_records) if trade_records else pd.DataFrame(
        columns=["bar_idx", "datetime", "action", "direction", "qty", "price",
                 "anchor", "cost", "cycle_id"]
    )
    cycles_df = cycle_log.to_dataframe()
    missed_df = missed_log.to_dataframe()

    incomplete_cols = [
        "config_id", "cycle_id", "start_time", "end_time", "side",
        "position_size", "add_count", "avg_entry", "last_price",
        "unrealized_pnl_ticks", "exit_type", "progress_hwm", "cycle_day_seq",
    ]
    incomplete_df = pd.DataFrame(incomplete_records) if incomplete_records else pd.DataFrame(
        columns=incomplete_cols
    )

    return SimulationResult(
        cycles=cycles_df,
        trades=trades_df,
        bars_processed=n,
        incomplete_cycles=incomplete_df,
        missed_entries=missed_df,
    )


def _log_missed(
    missed_log: FAMissedLog,
    config: FrozenAnchorConfig,
    dts,
    bar_idx: int,
    detect_dt,
    direction: str,
    extreme: float,
    watch_price: float,
    reason: str,
    exit_price: float,
    tick_size: float,
    cost_ticks: float,
    detect_price: float,
) -> None:
    """Log a missed entry (direction detected but pullback never occurred)."""
    # Extension = how far price moved from watch_price
    if direction == "LONG":
        hwm_reached = round(extreme - watch_price, 4)
        hyp_pnl = (exit_price - detect_price) / tick_size - 2 * cost_ticks
    else:
        hwm_reached = round(watch_price - extreme, 4)
        hyp_pnl = (detect_price - exit_price) / tick_size - 2 * cost_ticks

    try:
        date_str = str(pd.Timestamp(dts[bar_idx]).date())
    except Exception:
        date_str = ""

    missed_log.append(FAMissedRecord(
        config_id=config.config_id,
        date=date_str,
        direction_detect_time=detect_dt,
        direction=direction,
        hwm_reached=hwm_reached,
        exit_reason=reason,
        hypothetical_immediate_pnl=round(hyp_pnl, 4),
    ))
