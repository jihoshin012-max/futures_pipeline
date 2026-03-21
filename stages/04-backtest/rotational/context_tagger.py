# archetype: rotational
"""Context tagger — pre-compute regime context columns on bar data.

Adds ATR, ATR percentile, bar range stats, zig-zag swing stats,
and directional persistence to the bar DataFrame ONCE before any
simulation runs. The simulation loop then looks up context at each
cycle's start bar index — zero additional computation per config.

Requires numba for zig-zag computation. Uses the same zigzag_core
function from the fractal analysis scripts.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import percentileofscore

# Import the validated numba zig-zag engine
_ZIGZAG_DIR = str(Path(__file__).resolve().parents[3] / ".claude" / "skills" / "fractal_monitor" / "scripts")
if _ZIGZAG_DIR not in sys.path:
    sys.path.insert(0, _ZIGZAG_DIR)

from zigzag import zigzag_core, assign_session_ids  # noqa: E402


def compute_atr(bars: pd.DataFrame, period: int = 20) -> pd.Series:
    """Compute Average True Range over `period` bars.

    For tick data (O=H=L=Last), TR = 0 on each bar, so ATR is meaningless.
    This function is designed for aggregated OHLC bars (e.g., 250-tick).
    For tick data, use a reference bar source for ATR.
    """
    high = bars["High"].astype(float)
    low = bars["Low"].astype(float)
    close = bars["Last"].astype(float)
    prev_close = close.shift(1)

    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)

    return tr.rolling(period, min_periods=1).mean()


def _atr_percentile(atr_series: pd.Series, lookback: int = 500) -> pd.Series:
    """Rank current ATR vs trailing `lookback` bars (exclude current)."""
    result = np.full(len(atr_series), np.nan)
    vals = atr_series.values

    for i in range(1, len(vals)):
        start = max(0, i - lookback)
        window = vals[start:i]  # exclude current
        if len(window) > 0 and not np.isnan(vals[i]):
            result[i] = percentileofscore(window[~np.isnan(window)], vals[i])

    return pd.Series(result, index=atr_series.index)


def _compute_zigzag_context_for_bars(
    prices: np.ndarray,
    session_ids: np.ndarray,
    threshold: float,
    n_bars: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Run zig-zag and compute rolling swing stats mapped back to bar indices.

    Returns two arrays of length n_bars:
        swing_median: median of last 20 completed swing sizes at each bar
        swing_p90: P90 of last 20 completed swing sizes at each bar
    """
    sw_idx, sw_price, sw_dir, sw_sid = zigzag_core(
        prices.astype(np.float32),
        session_ids,
        threshold,
    )

    # Compute swing sizes (distance between consecutive swing points)
    swing_sizes = np.abs(np.diff(sw_price))
    # Each swing size corresponds to the interval [sw_idx[i], sw_idx[i+1]]
    # The swing completes at sw_idx[i+1]
    swing_end_idx = sw_idx[1:len(swing_sizes) + 1]

    median_out = np.full(n_bars, np.nan)
    p90_out = np.full(n_bars, np.nan)

    if len(swing_sizes) == 0:
        return median_out, p90_out

    # For each bar, find the last 20 completed swings before that bar
    sw_ptr = 0
    recent_swings: list[float] = []

    for bar_i in range(n_bars):
        # Advance pointer to include all swings completed at or before this bar
        while sw_ptr < len(swing_sizes) and swing_end_idx[sw_ptr] <= bar_i:
            recent_swings.append(swing_sizes[sw_ptr])
            if len(recent_swings) > 20:
                recent_swings.pop(0)
            sw_ptr += 1

        if len(recent_swings) > 0:
            arr = np.array(recent_swings)
            median_out[bar_i] = np.median(arr)
            p90_out[bar_i] = np.percentile(arr, 90)

    return median_out, p90_out


def _compute_directional_persistence(
    prices: np.ndarray,
    session_ids: np.ndarray,
    threshold: float,
    n_bars: int,
) -> np.ndarray:
    """Run zig-zag and compute directional persistence at each bar.

    Directional persistence = count of consecutive swings in the same
    direction immediately preceding this bar. Resets when direction flips.
    """
    sw_idx, sw_price, sw_dir, sw_sid = zigzag_core(
        prices.astype(np.float32),
        session_ids,
        threshold,
    )

    persistence_out = np.zeros(n_bars, dtype=np.int32)

    if len(sw_dir) < 2:
        return persistence_out

    # Compute direction of each swing (between consecutive swing points)
    # swing_dir[i] = direction from sw_price[i] to sw_price[i+1]
    swing_directions = np.sign(np.diff(sw_price)).astype(np.int8)
    swing_end_idx = sw_idx[1:len(swing_directions) + 1]

    # Build consecutive-same-direction count for each completed swing
    consec_counts = np.ones(len(swing_directions), dtype=np.int32)
    for i in range(1, len(swing_directions)):
        if sw_sid[i] == sw_sid[i + 1] and swing_directions[i] == swing_directions[i - 1]:
            consec_counts[i] = consec_counts[i - 1] + 1
        else:
            consec_counts[i] = 1

    # Map back to bars: each bar gets the persistence from the last completed swing
    sw_ptr = 0
    current_persistence = 0

    for bar_i in range(n_bars):
        while sw_ptr < len(swing_directions) and swing_end_idx[sw_ptr] <= bar_i:
            current_persistence = consec_counts[sw_ptr]
            sw_ptr += 1
        persistence_out[bar_i] = current_persistence

    return persistence_out


def tag_context(bars: pd.DataFrame) -> pd.DataFrame:
    """Pre-compute all regime context columns on bar DataFrame.

    Adds columns:
        atr_20, atr_pct, bar_range, bar_range_median_20,
        swing_median_20, swing_p90_20, directional_persistence

    For tick data (O=H=L=Last), ATR is computed from the tick price
    differences (will be very small). For production use with tick data,
    ATR should come from a reference bar source (250-tick bars).

    Args:
        bars: DataFrame with at least columns: High, Low, Last, datetime.
              Must have session-identifying info for zig-zag boundaries.

    Returns:
        bars with context columns appended (same index, no copy unless needed).
    """
    bars = bars.copy()
    n = len(bars)

    # --- ATR (20-bar) ---
    bars["atr_20"] = compute_atr(bars, period=20)

    # --- ATR percentile (rank vs trailing 500 bars) ---
    bars["atr_pct"] = _atr_percentile(bars["atr_20"], lookback=500)

    # --- Bar range ---
    bars["bar_range"] = bars["High"].astype(float) - bars["Low"].astype(float)
    bars["bar_range_median_20"] = bars["bar_range"].rolling(20, min_periods=1).median()

    # --- Session IDs for zig-zag ---
    # Extract trading date from datetime for session boundaries
    if "datetime" in bars.columns:
        dt_series = pd.to_datetime(bars["datetime"])
        dates = dt_series.dt.date
        # Simple session ID: increment on date change
        date_ints = dates.astype(str).str.replace("-", "").astype(np.int32).values
        session_ids = assign_session_ids(date_ints)
    else:
        session_ids = np.zeros(n, dtype=np.int32)

    prices = bars["Last"].values.astype(np.float64)

    # --- Zig-zag context (5pt threshold) ---
    swing_med, swing_p90 = _compute_zigzag_context_for_bars(
        prices, session_ids, threshold=5.0, n_bars=n,
    )
    bars["swing_median_20"] = swing_med
    bars["swing_p90_20"] = swing_p90

    # --- Directional persistence (10pt threshold) ---
    bars["directional_persistence"] = _compute_directional_persistence(
        prices, session_ids, threshold=10.0, n_bars=n,
    )

    return bars
