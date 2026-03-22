# archetype: zone_touch
"""Zone touch simulator — pure function implementing the zone_touch archetype.

Interface: run(bar_df, touch_row, config, bar_offset) -> SimResult
           run_multileg(bar_df, touch_row, config, bar_offset) -> MultiLegResult

This is the fixed archetype-specific simulation function. It evaluates each
touch against bar data and returns a SimResult. It is a pure function with no
I/O, no global state, and no side effects.

Exports: run, SimResult, run_multileg, MultiLegResult
"""

from dataclasses import dataclass, field
from typing import List
import pandas as pd


@dataclass
class SimResult:
    """Result of a single touch simulation."""
    pnl_ticks: float
    win: bool
    exit_reason: str
    bars_held: int


@dataclass
class MultiLegResult:
    """Result of a multi-leg touch simulation with partial exits."""
    pnl_ticks: float          # weighted PnL across all legs
    win: bool
    bars_held: int            # bar of last leg exit
    leg_pnls: List[float] = field(default_factory=list)
    leg_exit_reasons: List[str] = field(default_factory=list)
    leg_exit_bars: List[int] = field(default_factory=list)


def run(
    bar_df: pd.DataFrame,
    touch_row: pd.Series,
    config: dict,
    bar_offset: int,
) -> SimResult:
    """Simulate a single zone touch and return a SimResult.

    Pure function — no I/O, no prints, no global state.
    All inputs come via function arguments.

    Args:
        bar_df: Bar DataFrame with columns Open, High, Low, Last.
                Must include bars from bar_offset onward.
        touch_row: pd.Series with TouchPrice (float), ApproachDir (int: 1=long,-1=short),
                   and mode (str: "M1", "M3", etc.).
        config: Full config dict. Must include tick_size (float) and a per-mode
                block (e.g. config["M1"]) with stop_ticks, leg_targets,
                trail_steps, time_cap_bars. If tick_size is absent, defaults to 0.25.
        bar_offset: Integer index into bar_df where the entry bar begins.

    Returns:
        SimResult(pnl_ticks, win, exit_reason, bars_held)

    Exit reasons:
        "target_1": First leg_target hit (win).
        "stop":     Stop loss hit (loss or breakeven if BE was triggered).
        "time_cap": time_cap_bars exhausted with no prior exit (market exit).
    """
    # --- Extract inputs ---
    entry_price: float = float(touch_row["TouchPrice"])
    direction: int = int(touch_row["ApproachDir"])  # 1 = long, -1 = short
    mode: str = touch_row["mode"]

    tick_size: float = float(config.get("tick_size", 0.25))

    mode_config: dict = config[mode]
    stop_ticks: float = float(mode_config["stop_ticks"])
    leg_targets: list = list(mode_config["leg_targets"])
    trail_steps: list = list(mode_config.get("trail_steps", []))
    time_cap_bars: int = int(mode_config["time_cap_bars"])

    # For v1: use only the first leg_target (single-target mode).
    # Multi-leg partial exits require position tracking — future enhancement.
    target_ticks: float = float(leg_targets[0])

    # --- Stop level as absolute price ---
    # For LONG: stop_price = entry - stop_ticks * tick_size (below entry)
    # For SHORT: stop_price = entry + stop_ticks * tick_size (above entry)
    # After trail ratchets, stop moves in the favorable direction:
    #   LONG: stop_price moves UP toward/above entry
    #   SHORT: stop_price moves DOWN toward/below entry
    if direction == 1:
        stop_price: float = entry_price - stop_ticks * tick_size
    else:
        stop_price: float = entry_price + stop_ticks * tick_size

    # Target price
    if direction == 1:
        target_price: float = entry_price + target_ticks * tick_size
    else:
        target_price: float = entry_price - target_ticks * tick_size

    # Track highest MFE in ticks seen so far (for trail step triggers)
    max_mfe_ticks: float = 0.0

    bars = bar_df.iloc[bar_offset:].reset_index(drop=True)
    n_bars = len(bars)

    for i in range(n_bars):
        bar = bars.iloc[i]
        high: float = float(bar["High"])
        low: float = float(bar["Low"])
        last: float = float(bar["Last"])
        bars_held: int = i + 1

        # --- Compute MFE for this bar in ticks ---
        if direction == 1:  # Long: favorable direction is up
            bar_mfe_ticks = (high - entry_price) / tick_size
        else:  # Short: favorable direction is down
            bar_mfe_ticks = (entry_price - low) / tick_size

        # Update running max MFE
        max_mfe_ticks = max(max_mfe_ticks, bar_mfe_ticks)

        # --- Ratchet trail stops based on updated MFE ---
        # trail_steps are ordered by trigger_ticks ascending.
        # Apply all triggered steps: the last one sets the tightest (most favorable) stop.
        # Stop only moves in the favorable direction — it never moves back.
        for step in trail_steps:
            trigger = float(step["trigger_ticks"])
            new_stop = float(step["new_stop_ticks"])
            if max_mfe_ticks >= trigger:
                # Compute candidate new stop price
                if direction == 1:
                    # Long: new stop is at entry + new_stop * tick_size
                    # (new_stop_ticks=0 → stop at entry; positive → stop above entry)
                    candidate_stop_price = entry_price + new_stop * tick_size
                    # Stop can only move up (favorable direction for long)
                    if candidate_stop_price > stop_price:
                        stop_price = candidate_stop_price
                else:
                    # Short: new stop is at entry - new_stop * tick_size
                    candidate_stop_price = entry_price - new_stop * tick_size
                    # Stop can only move down (favorable direction for short)
                    if candidate_stop_price < stop_price:
                        stop_price = candidate_stop_price

        # --- Check stop ---
        # For LONG: stop triggers if bar's Low <= stop_price
        # For SHORT: stop triggers if bar's High >= stop_price
        if direction == 1:
            stop_triggered = low <= stop_price
        else:
            stop_triggered = high >= stop_price

        if stop_triggered:
            # PnL = exit price (stop_price) minus entry, in ticks
            if direction == 1:
                pnl_ticks = (stop_price - entry_price) / tick_size
            else:
                pnl_ticks = (entry_price - stop_price) / tick_size
            return SimResult(
                pnl_ticks=pnl_ticks,
                win=pnl_ticks > 0,
                exit_reason="stop",
                bars_held=bars_held,
            )

        # --- Check target ---
        # For LONG: target triggers if bar's High >= target_price
        # For SHORT: target triggers if bar's Low <= target_price
        if direction == 1:
            target_triggered = high >= target_price
        else:
            target_triggered = low <= target_price

        if target_triggered:
            return SimResult(
                pnl_ticks=target_ticks,
                win=True,
                exit_reason="target_1",
                bars_held=bars_held,
            )

        # --- Check time cap ---
        if bars_held >= time_cap_bars:
            # Exit at market: use bar's close (Last) price
            if direction == 1:
                pnl_ticks = (last - entry_price) / tick_size
            else:
                pnl_ticks = (entry_price - last) / tick_size
            return SimResult(
                pnl_ticks=pnl_ticks,
                win=pnl_ticks > 0,
                exit_reason="time_cap",
                bars_held=bars_held,
            )

    # If we run out of bars before any exit condition (should not normally happen
    # if time_cap_bars <= len(bars)), exit at the last bar's close.
    last_bar = bars.iloc[-1]
    last_price = float(last_bar["Last"])
    if direction == 1:
        pnl_ticks = (last_price - entry_price) / tick_size
    else:
        pnl_ticks = (entry_price - last_price) / tick_size
    return SimResult(
        pnl_ticks=pnl_ticks,
        win=pnl_ticks > 0,
        exit_reason="time_cap",
        bars_held=len(bars),
    )


def run_multileg(
    bar_df: pd.DataFrame,
    touch_row: pd.Series,
    config: dict,
    bar_offset: int,
) -> MultiLegResult:
    """Simulate a multi-leg zone touch with partial exits.

    Pure function — no I/O, no prints, no global state.

    Config mode block must include:
        leg_targets: list of tick targets [T1, T2, ...], ascending order
        leg_weights: list of position fractions [w1, w2, ...], sum to 1.0
        stop_ticks: initial stop distance
        trail_steps: list of {trigger_ticks, new_stop_ticks} (optional)
        time_cap_bars: max bars before forced exit
        stop_move_after_leg: int or None — after this leg index (0-based) fills,
            move remaining legs' stop to stop_move_destination ticks from entry.
            None = shared stop throughout (default).
        stop_move_destination: float — ticks from entry for the moved stop
            (0 = break-even, positive = above entry for long). Only used if
            stop_move_after_leg is set.

    Intra-bar conflict: stop fills first. On a bar where both stop and a
    target could trigger, stop wins and all remaining open legs exit at stop.

    Returns:
        MultiLegResult with weighted PnL and per-leg details.
    """
    entry_price: float = float(touch_row["TouchPrice"])
    direction: int = int(touch_row["ApproachDir"])
    mode: str = touch_row["mode"]

    tick_size: float = float(config.get("tick_size", 0.25))

    mode_config: dict = config[mode]
    stop_ticks: float = float(mode_config["stop_ticks"])
    leg_targets: list = [float(t) for t in mode_config["leg_targets"]]
    leg_weights: list = [float(w) for w in mode_config["leg_weights"]]
    trail_steps: list = list(mode_config.get("trail_steps", []))
    time_cap_bars: int = int(mode_config["time_cap_bars"])
    stop_move_after_leg = mode_config.get("stop_move_after_leg", None)
    stop_move_dest: float = float(mode_config.get("stop_move_destination", 0))

    n_legs = len(leg_targets)

    # --- Initial stop price ---
    if direction == 1:
        stop_price: float = entry_price - stop_ticks * tick_size
    else:
        stop_price: float = entry_price + stop_ticks * tick_size

    # Target prices (ascending order)
    target_prices = []
    for t in leg_targets:
        if direction == 1:
            target_prices.append(entry_price + t * tick_size)
        else:
            target_prices.append(entry_price - t * tick_size)

    # Per-leg state
    leg_open = [True] * n_legs
    leg_pnls: List[float] = [0.0] * n_legs
    leg_exit_reasons: List[str] = [""] * n_legs
    leg_exit_bars: List[int] = [0] * n_legs
    legs_filled = 0

    max_mfe_ticks: float = 0.0

    bars = bar_df.iloc[bar_offset:].reset_index(drop=True)
    n_bars_avail = len(bars)

    for i in range(n_bars_avail):
        bar = bars.iloc[i]
        high: float = float(bar["High"])
        low: float = float(bar["Low"])
        last: float = float(bar["Last"])
        bars_held: int = i + 1

        # --- MFE ---
        if direction == 1:
            bar_mfe = (high - entry_price) / tick_size
        else:
            bar_mfe = (entry_price - low) / tick_size
        max_mfe_ticks = max(max_mfe_ticks, bar_mfe)

        # --- Trail ratchet (shared stop for all open legs) ---
        for step in trail_steps:
            trigger = float(step["trigger_ticks"])
            new_stop = float(step["new_stop_ticks"])
            if max_mfe_ticks >= trigger:
                if direction == 1:
                    candidate = entry_price + new_stop * tick_size
                    if candidate > stop_price:
                        stop_price = candidate
                else:
                    candidate = entry_price - new_stop * tick_size
                    if candidate < stop_price:
                        stop_price = candidate

        # --- Check stop (all remaining open legs exit) ---
        if direction == 1:
            stop_triggered = low <= stop_price
        else:
            stop_triggered = high >= stop_price

        if stop_triggered:
            if direction == 1:
                stop_pnl = (stop_price - entry_price) / tick_size
            else:
                stop_pnl = (entry_price - stop_price) / tick_size
            for j in range(n_legs):
                if leg_open[j]:
                    leg_pnls[j] = stop_pnl
                    leg_exit_reasons[j] = "stop"
                    leg_exit_bars[j] = bars_held
                    leg_open[j] = False
            weighted_pnl = sum(w * p for w, p in zip(leg_weights, leg_pnls))
            return MultiLegResult(
                pnl_ticks=weighted_pnl, win=weighted_pnl > 0,
                bars_held=bars_held, leg_pnls=list(leg_pnls),
                leg_exit_reasons=list(leg_exit_reasons),
                leg_exit_bars=list(leg_exit_bars),
            )

        # --- Check targets (ascending order) ---
        for j in range(n_legs):
            if not leg_open[j]:
                continue
            if direction == 1:
                hit = high >= target_prices[j]
            else:
                hit = low <= target_prices[j]
            if hit:
                leg_pnls[j] = leg_targets[j]
                leg_exit_reasons[j] = f"target_{j + 1}"
                leg_exit_bars[j] = bars_held
                leg_open[j] = False
                legs_filled += 1

                # Move stop after leg fill if configured
                if (stop_move_after_leg is not None
                        and legs_filled == stop_move_after_leg + 1):
                    if direction == 1:
                        new_sp = entry_price + stop_move_dest * tick_size
                        if new_sp > stop_price:
                            stop_price = new_sp
                    else:
                        new_sp = entry_price - stop_move_dest * tick_size
                        if new_sp < stop_price:
                            stop_price = new_sp

        # All legs closed?
        if not any(leg_open):
            weighted_pnl = sum(w * p for w, p in zip(leg_weights, leg_pnls))
            return MultiLegResult(
                pnl_ticks=weighted_pnl, win=weighted_pnl > 0,
                bars_held=bars_held, leg_pnls=list(leg_pnls),
                leg_exit_reasons=list(leg_exit_reasons),
                leg_exit_bars=list(leg_exit_bars),
            )

        # --- Time cap ---
        if bars_held >= time_cap_bars:
            if direction == 1:
                tc_pnl = (last - entry_price) / tick_size
            else:
                tc_pnl = (entry_price - last) / tick_size
            for j in range(n_legs):
                if leg_open[j]:
                    leg_pnls[j] = tc_pnl
                    leg_exit_reasons[j] = "time_cap"
                    leg_exit_bars[j] = bars_held
                    leg_open[j] = False
            weighted_pnl = sum(w * p for w, p in zip(leg_weights, leg_pnls))
            return MultiLegResult(
                pnl_ticks=weighted_pnl, win=weighted_pnl > 0,
                bars_held=bars_held, leg_pnls=list(leg_pnls),
                leg_exit_reasons=list(leg_exit_reasons),
                leg_exit_bars=list(leg_exit_bars),
            )

    # Ran out of bars
    last_bar = bars.iloc[-1]
    last_price = float(last_bar["Last"])
    if direction == 1:
        tc_pnl = (last_price - entry_price) / tick_size
    else:
        tc_pnl = (entry_price - last_price) / tick_size
    for j in range(n_legs):
        if leg_open[j]:
            leg_pnls[j] = tc_pnl
            leg_exit_reasons[j] = "time_cap"
            leg_exit_bars[j] = n_bars_avail
            leg_open[j] = False
    weighted_pnl = sum(w * p for w, p in zip(leg_weights, leg_pnls))
    return MultiLegResult(
        pnl_ticks=weighted_pnl, win=weighted_pnl > 0,
        bars_held=n_bars_avail, leg_pnls=list(leg_pnls),
        leg_exit_reasons=list(leg_exit_reasons),
        leg_exit_bars=list(leg_exit_bars),
    )
