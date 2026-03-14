# archetype: zone_touch
"""Zone touch simulator — pure function implementing the zone_touch archetype.

Interface: run(bar_df, touch_row, config, bar_offset) -> SimResult

This is the fixed archetype-specific simulation function. It evaluates each
touch against bar data and returns a SimResult. It is a pure function with no
I/O, no global state, and no side effects.

Exports: run, SimResult
"""

from dataclasses import dataclass
import pandas as pd


@dataclass
class SimResult:
    """Result of a single touch simulation."""
    pnl_ticks: float
    win: bool
    exit_reason: str
    bars_held: int


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
