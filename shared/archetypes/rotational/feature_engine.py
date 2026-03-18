# archetype: rotational
"""Feature engine for rotational archetype.

Edit this file during Stage 02 autoresearch.
compute_features() takes bar_df only — no touch_row, since rotational is a bar-only archetype.
Features must be entry-time safe: only use bar_df rows up to the current bar index.

Exports: compute_features, compute_hypothesis_features
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

# Resolve repo root: shared/archetypes/rotational/ -> repo root (parents[3])
_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT))

from shared.data_loader import parse_instruments_md  # noqa: E402

# Cache instrument constants at module level (loaded once per import)
# parse_instruments_md resolves relative to cwd; use absolute path
_INSTRUMENTS_MD_PATH = _REPO_ROOT / "_config/instruments.md"
_NQ_CONSTANTS = parse_instruments_md("NQ", str(_INSTRUMENTS_MD_PATH))
_TICK_SIZE = _NQ_CONSTANTS["tick_size"]


def compute_features(bar_df) -> dict:
    """Compute features for rotational archetype. Edit during Stage 02 autoresearch.

    Args:
        bar_df: DataFrame of bars up to and including the current entry bar.
                Must only access rows available at entry time (no lookahead).

    Returns:
        dict mapping feature_name -> float value
        e.g. {'channel_width': 12.0}
    """
    features = {}

    # TODO: implement features during Stage 02 autoresearch

    return features


# ---------------------------------------------------------------------------
# Hypothesis-specific vectorized feature computation
# ---------------------------------------------------------------------------
#
# Entry-time safety contract:
#   - All computations are vectorized over the full bar_df
#   - Rolling windows use the lookback as min_periods, producing NaN for warmup
#   - NO per-bar loops; features are precomputed as static columns
#   - Caller is responsible for using only bar_df.iloc[:i+1] context within sim loop

# Features that require simulator state (direction, cycle state, etc.)
# These cannot be computed statically from bar_df alone.
# Return NaN placeholder columns with a note for diagnostic purposes.
_DYNAMIC_FEATURE_COLUMNS = {
    "H17": "cycle_feedback_state",   # Requires last N cycle outcomes
    "H36": "adverse_speed",          # Requires knowing current position direction
    "H39": "adverse_velocity_ratio", # Requires cycle favorable/adverse leg tracking
    "H21": "cycle_pnl",              # Requires simulator internal PnL tracking
}


def _compute_bar_duration_sec(bar_df: pd.DataFrame) -> pd.Series:
    """Compute bar duration in seconds from datetime column differences."""
    if "datetime" in bar_df.columns:
        dts = pd.to_datetime(bar_df["datetime"])
        dur = dts.diff().dt.total_seconds()
        # Fill first bar with median or a sensible default (10 sec for 10-sec bars)
        median_dur = dur.median()
        if np.isnan(median_dur) or median_dur <= 0:
            median_dur = 10.0
        dur = dur.fillna(median_dur)
        # Guard against zero durations (same-timestamp bars)
        dur = dur.clip(lower=0.1)
        return dur
    else:
        # No datetime column: return a constant (default 10 sec)
        return pd.Series(10.0, index=bar_df.index)


def compute_hypothesis_features(
    bar_df: pd.DataFrame,
    hypothesis_config: dict,
) -> pd.DataFrame:
    """Compute vectorized hypothesis-specific features and return augmented bar_df.

    Takes the full bar DataFrame and adds computed feature columns. All computations
    are vectorized (NO per-bar loops). Rolling windows produce NaN for warmup period
    (entry-time safe by construction).

    Args:
        bar_df: Full bar DataFrame (must have at minimum: Last, ATR, datetime, Volume,
                Ask Volume, Bid Volume columns for relevant hypotheses).
        hypothesis_config: The hypothesis sub-config dict from full config
                          (i.e., config["hypothesis"]).

    Returns:
        A new DataFrame (copy of bar_df) with computed feature columns appended.
        Original bar_df is NOT mutated.
    """
    # Work on a copy so we do not mutate the caller's DataFrame
    df = bar_df.copy()

    trigger = hypothesis_config.get("trigger_mechanism", "fixed")
    trigger_params = hypothesis_config.get("trigger_params", {})
    active_filters = hypothesis_config.get("active_filters", [])
    filter_params = hypothesis_config.get("filter_params", {})
    structural_mods = hypothesis_config.get("structural_mods", [])

    # Check for H19 skip signal (requires multi-source reference data)
    if hypothesis_config.get("_h19_skip", False):
        df["bar_type_divergence"] = np.nan
        df.attrs["SKIPPED_REFERENCE_REQUIRED"] = "H19_BAR_TYPE_DIVERGENCE"
        return df

    # ------------------------------------------------------------------
    # Dimension A triggers — add computed step distance features
    # ------------------------------------------------------------------

    if trigger == "atr_scaled":
        # H1: atr_scaled_step = multiplier * ATR (ATR already in CSV col 35)
        multiplier = float(trigger_params.get("multiplier", 0.5))
        df["atr_scaled_step"] = multiplier * df["ATR"]

    elif trigger == "sd_scaled":
        # H8: rolling_sd = Close.rolling(lookback).std()
        #     sd_scaled_step = multiplier * rolling_sd
        multiplier = float(trigger_params.get("multiplier", 0.75))
        lookback = int(trigger_params.get("lookback", 50))
        df["rolling_sd"] = df["Last"].rolling(lookback, min_periods=lookback).std()
        df["sd_scaled_step"] = multiplier * df["rolling_sd"]

    elif trigger == "vwap_sd":
        # H9: VWAP + SD bands
        k = float(trigger_params.get("k", 2.0))
        vwap_reset = trigger_params.get("vwap_reset", "session")
        df = _compute_vwap_features(df, k=k, vwap_reset=vwap_reset)

    elif trigger == "zscore":
        # H10: z_score = (Close - rolling_mean) / rolling_SD
        threshold = float(trigger_params.get("threshold", 2.0))
        lookback = int(trigger_params.get("lookback", 100))
        roll = df["Last"].rolling(lookback, min_periods=lookback)
        df["rolling_mean"] = roll.mean()
        df["rolling_sd"] = roll.std()
        df["price_zscore"] = (df["Last"] - df["rolling_mean"]) / df["rolling_sd"]

    elif trigger == "sd_band":
        # H3: Uses SD band columns already in bar_df (StdDev_1/2/3 from CSV)
        # No additional computed features needed — columns already present
        pass

    # ------------------------------------------------------------------
    # Active filters — add filter-specific features
    # ------------------------------------------------------------------

    for filter_id in active_filters:
        fp = filter_params.get(filter_id, {})

        if filter_id == "H27":
            # Volatility ROC: ATR rate of change
            n = int(fp.get("lookback", 14))
            df["atr_roc"] = df["ATR"].pct_change(n)

        elif filter_id == "H28":
            # Price ROC (momentum)
            n = int(fp.get("lookback", 10))
            df["price_roc"] = df["Last"].pct_change(n)

        elif filter_id == "H29":
            # Price acceleration (2nd derivative)
            n = int(fp.get("lookback", 10))
            roc = df["Last"].pct_change(n)
            df["price_acceleration"] = roc.pct_change(n)

        elif filter_id == "H30":
            # Volatility compression: rolling ATR std over lookback to detect squeeze
            n = int(fp.get("squeeze_lookback", 20))
            atr_roll = df["ATR"].rolling(n, min_periods=n)
            atr_mean = atr_roll.mean()
            atr_std = atr_roll.std()
            df["volatility_squeeze_state"] = atr_std / atr_mean.clip(lower=1e-9)

        elif filter_id == "H31":
            # Momentum divergence: price direction vs momentum direction
            n = int(fp.get("divergence_lookback", 20))
            price_change = df["Last"].diff(n)
            momentum = df["Last"].pct_change(n // 2)
            df["momentum_divergence"] = np.sign(price_change) - np.sign(momentum)

        elif filter_id == "H32":
            # Volume ROC
            n = int(fp.get("lookback", 10))
            df["volume_roc"] = df["Volume"].pct_change(n)

        elif filter_id == "H33":
            # PriceSpeed filter: price delta / bar duration (points per second)
            bar_dur = _compute_bar_duration_sec(df)
            df["bar_duration_sec"] = bar_dur
            df["price_speed"] = df["Last"].diff().abs() / bar_dur

        elif filter_id == "H34":
            # Absorption rate proxy: AskVol / bar_duration, BidVol / bar_duration
            bar_dur = _compute_bar_duration_sec(df)
            df["bar_duration_sec"] = bar_dur
            df["ask_absorption_rate"] = df["Ask Volume"] / bar_dur
            df["bid_absorption_rate"] = df["Bid Volume"] / bar_dur

        elif filter_id == "H35":
            # Imbalance trend: rolling slope of (AskVol-BidVol)/(AskVol+BidVol)
            n = int(fp.get("lookback", 20))
            total_vol = (df["Ask Volume"] + df["Bid Volume"]).clip(lower=1e-9)
            df["imbalance_ratio"] = (df["Ask Volume"] - df["Bid Volume"]) / total_vol
            df["imbalance_slope"] = df["imbalance_ratio"].rolling(n, min_periods=n).apply(
                lambda x: float(np.polyfit(np.arange(len(x)), x, 1)[0]),
                raw=True,
            )

        elif filter_id in _DYNAMIC_FEATURE_COLUMNS:
            # Requires simulator state — return NaN placeholder
            col_name = _DYNAMIC_FEATURE_COLUMNS[filter_id]
            df[col_name] = np.nan
            df.attrs[f"DYNAMIC_FEATURE_SKIPPED_{filter_id}"] = (
                f"{filter_id} requires simulator state; placeholder NaN column added"
            )

        elif filter_id == "H37":
            # Bar formation rate (bars per minute) — only on vol/tick series
            # On 10-sec bars this should be excluded at the experiment runner level
            bar_dur = _compute_bar_duration_sec(df)
            df["bar_duration_sec"] = bar_dur
            # Rolling bars per minute: window over N seconds
            n_min = int(fp.get("lookback_minutes", 5))
            window_sec = n_min * 60
            # Approximate: count bars in rolling window by counting rows with
            # cumulative duration within window_sec
            # Simplified: bars_per_minute ≈ 60 / rolling_mean_bar_duration
            rolling_dur = bar_dur.rolling(50, min_periods=5).mean()
            df["bar_formation_rate"] = 60.0 / rolling_dur.clip(lower=0.1)

        elif filter_id == "H38":
            # Regime transition speed: derivative of ATR ROC + imbalance slope
            n = int(fp.get("transition_lookback", 10))
            atr_roc = df["ATR"].pct_change(n)
            total_vol = (df["Ask Volume"] + df["Bid Volume"]).clip(lower=1e-9)
            imbalance = (df["Ask Volume"] - df["Bid Volume"]) / total_vol
            imbalance_slope = imbalance.rolling(n, min_periods=n).apply(
                lambda x: float(np.polyfit(np.arange(len(x)), x, 1)[0]),
                raw=True,
            )
            price_roc = df["Last"].pct_change(n)
            price_accel = price_roc.pct_change(n)
            # Composite: normalize and combine
            df["regime_transition_speed"] = (
                atr_roc.fillna(0) + imbalance_slope.fillna(0) + price_accel.fillna(0)
            )

        elif filter_id == "H40":
            # Band-relative speed regime: speed × band-position classification
            bar_dur = _compute_bar_duration_sec(df)
            df["bar_duration_sec"] = bar_dur
            df["price_speed"] = df["Last"].diff().abs() / bar_dur
            # Band state from existing columns
            if "StdDev_1_Top" in df.columns and "StdDev_2_Top" in df.columns:
                inside_sd1 = (
                    (df["Last"] <= df["StdDev_1_Top"]) &
                    (df["Last"] >= df["StdDev_1_Bottom"])
                ).astype(int)
                outside_sd2 = (
                    (df["Last"] > df["StdDev_2_Top"]) |
                    (df["Last"] < df["StdDev_2_Bottom"])
                ).astype(int)
                speed_median = df["price_speed"].rolling(50, min_periods=10).median()
                fast = (df["price_speed"] > speed_median).astype(int)
                # State: 0=inside_sd1+slow, 1=inside_sd1+fast, 2=outside_sd2+slow, 3=outside_sd2+fast
                df["band_speed_state"] = (
                    inside_sd1 * 0 + (1 - inside_sd1) * outside_sd2 * (2 + fast)
                )
            else:
                df["band_speed_state"] = np.nan

        elif filter_id == "H41":
            # Band-relative ATR behavior: ATR trend × band position
            if "StdDev_1_Top" in df.columns and "StdDev_2_Top" in df.columns:
                atr_expanding = (df["ATR"].diff() > 0).astype(int)
                outside_sd2 = (
                    (df["Last"] > df["StdDev_2_Top"]) |
                    (df["Last"] < df["StdDev_2_Bottom"])
                ).astype(int)
                # State: -1=contracting inside, 0=contracting outside (exhaustion),
                # 1=expanding inside (vol shift), 2=expanding outside (trend strengthening)
                df["band_atr_state"] = (
                    atr_expanding * (1 + outside_sd2) - (1 - atr_expanding) * outside_sd2
                ).astype(float)
            else:
                df["band_atr_state"] = np.nan

        elif filter_id == "SPEEDREAD":
            # SpeedRead composite filter — exact replication of SpeedRead.cpp
            df = _compute_speedread_features(df, fp)

        elif filter_id in ("H4", "H5", "H6", "H7", "H11", "H12", "H16"):
            # These filters use existing CSV columns (ZZ, imbalance, time, trades, etc.)
            # No additional computed features needed for initial screening
            # The simulator can read these columns directly
            pass

        # H19, H25, H26 etc. handled contextually or require special routing
        # If not explicitly handled above, no columns added (safe default)

    # ------------------------------------------------------------------
    # H9 also handles structural mods that need speed features
    # (structural_mods like H33/H36 computed features when in structural context)
    # ------------------------------------------------------------------

    return df


def _compute_speedread_features(
    df: pd.DataFrame,
    params: dict,
) -> pd.DataFrame:
    """Compute SpeedRead composite features — exact replication of SpeedRead.cpp.

    Produces 3 columns: speed_price_velocity, speed_volume_rate, speed_composite.
    All entry-time safe (use only completed bars).

    Args:
        df: Bar DataFrame with Last, High, Low, Volume columns.
        params: dict with keys: lookback, vol_avg_len, price_weight, vol_weight,
                smoothing_bars, atr_length. All optional with defaults.
    """
    lookback = int(params.get("lookback", 10))
    vol_avg_len = int(params.get("vol_avg_len", 50))
    price_weight = float(params.get("price_weight", 70))
    vol_weight = float(params.get("vol_weight", 30))
    smoothing_bars = int(params.get("smoothing_bars", 3))
    atr_length = int(params.get("atr_length", 20))

    close = df["Last"].values.astype(float)
    high = df["High"].values.astype(float)
    low = df["Low"].values.astype(float)
    volume = df["Volume"].values.astype(float)
    n = len(df)

    # Step 1: Price Velocity
    # True Range for ATR (computed from scratch, NOT col 35)
    prev_close = np.empty(n)
    prev_close[0] = close[0]
    prev_close[1:] = close[:-1]
    tr = np.maximum(
        high - low,
        np.maximum(np.abs(high - prev_close), np.abs(low - prev_close)),
    )

    # Rolling ATR (mean of TR over atr_length bars)
    atr = np.full(n, np.nan)
    tr_cumsum = np.cumsum(tr)
    for i in range(atr_length - 1, n):
        if i == atr_length - 1:
            atr[i] = tr_cumsum[i] / atr_length
        else:
            atr[i] = (tr_cumsum[i] - tr_cumsum[i - atr_length]) / atr_length

    # Price travel: sum of abs(close[i-j] - close[i-j-1]) for j in range(lookback)
    abs_changes = np.abs(np.diff(close, prepend=close[0]))
    price_travel = np.full(n, np.nan)
    change_cumsum = np.cumsum(abs_changes)
    for i in range(lookback, n):
        price_travel[i] = change_cumsum[i] - change_cumsum[i - lookback]

    price_vel_raw = np.where(
        (atr > 0) & ~np.isnan(atr) & ~np.isnan(price_travel),
        price_travel / (atr * lookback),
        np.nan,
    )
    price_scaled = 50.0 * (1.0 + np.tanh((price_vel_raw - 1.0) * 1.5))

    # Step 2: Volume Rate
    # avg_vol: mean of volume[i-1-j] for j in range(vol_avg_len) — EXCLUDES current bar
    avg_vol = np.full(n, np.nan)
    vol_cumsum = np.cumsum(volume)
    for i in range(vol_avg_len + 1, n):
        # Bars i-1 back to i-vol_avg_len: sum = vol_cumsum[i-1] - vol_cumsum[i-1-vol_avg_len]
        avg_vol[i] = (vol_cumsum[i - 1] - vol_cumsum[i - 1 - vol_avg_len]) / vol_avg_len

    # recent_vol: mean of volume[i-j] for j in range(min(lookback, 5)) — INCLUDES current bar
    recent_bars = min(lookback, 5)
    recent_vol = np.full(n, np.nan)
    for i in range(recent_bars - 1, n):
        recent_vol[i] = (vol_cumsum[i] - (vol_cumsum[i - recent_bars] if i >= recent_bars else 0)) / recent_bars

    vol_rate_raw = np.where(
        (avg_vol > 0) & ~np.isnan(avg_vol) & ~np.isnan(recent_vol),
        recent_vol / avg_vol,
        np.nan,
    )
    vol_scaled = 50.0 * (1.0 + np.tanh((vol_rate_raw - 1.0) * 1.5))

    # Step 3: Composite (raw)
    total_weight = price_weight + vol_weight
    composite_raw = np.where(
        ~np.isnan(price_scaled) & ~np.isnan(vol_scaled),
        (price_scaled * price_weight + vol_scaled * vol_weight) / total_weight,
        np.nan,
    )

    # Step 4: Smoothing — SMA of composite_raw
    composite = np.full(n, np.nan)
    if smoothing_bars <= 1:
        composite = composite_raw.copy()
    else:
        raw_cumsum = np.nancumsum(composite_raw)
        # Track valid count for proper averaging
        valid = (~np.isnan(composite_raw)).astype(float)
        valid_cumsum = np.cumsum(valid)
        for i in range(n):
            start = max(0, i - smoothing_bars + 1)
            cnt = valid_cumsum[i] - (valid_cumsum[start - 1] if start > 0 else 0)
            if cnt >= smoothing_bars:
                composite[i] = (raw_cumsum[i] - (raw_cumsum[start - 1] if start > 0 else 0)) / cnt

    df["speed_price_velocity"] = price_scaled
    df["speed_volume_rate"] = vol_scaled
    df["speed_composite"] = composite

    return df


def _compute_vwap_features(
    df: pd.DataFrame,
    k: float = 2.0,
    vwap_reset: str = "session",
) -> pd.DataFrame:
    """Compute VWAP and VWAP SD bands for H9.

    Session VWAP resets at each new trading day.
    Rolling VWAP uses a rolling cumulative window.

    Args:
        df: Bar DataFrame with Last, Volume, datetime columns.
        k: SD multiplier for bands.
        vwap_reset: "session" resets VWAP at each trading day; "rolling" uses rolling window.

    Returns:
        DataFrame with vwap, vwap_sd_upper, vwap_sd_lower columns added.
    """
    if "datetime" not in df.columns or "Volume" not in df.columns:
        df["vwap"] = np.nan
        df["vwap_sd_upper"] = np.nan
        df["vwap_sd_lower"] = np.nan
        return df

    prices = df["Last"].values
    volumes = df["Volume"].values.clip(0)  # Guard against negatives

    if vwap_reset == "session":
        # Reset VWAP at each new calendar day
        dts = pd.to_datetime(df["datetime"])
        dates = dts.dt.date

        vwap_vals = np.full(len(df), np.nan)
        vwap_sd_upper = np.full(len(df), np.nan)
        vwap_sd_lower = np.full(len(df), np.nan)

        # Group by date and compute cumulative VWAP within each session
        for date, group_idx in df.groupby(dates).groups.items():
            idx = sorted(group_idx)
            p = prices[idx]
            v = volumes[idx]
            cum_pv = np.cumsum(p * v)
            cum_v = np.cumsum(v)
            cum_v_safe = np.where(cum_v > 0, cum_v, 1.0)
            session_vwap = cum_pv / cum_v_safe

            # Rolling SD of price within session (for bands)
            session_vwap_sd = np.full(len(idx), np.nan)
            for i in range(1, len(idx)):
                if i >= 2:
                    session_vwap_sd[i] = float(np.std(p[:i + 1], ddof=1))

            for local_i, abs_i in enumerate(idx):
                vwap_vals[abs_i] = session_vwap[local_i]
                vwap_sd_upper[abs_i] = session_vwap[local_i] + k * (session_vwap_sd[local_i] if not np.isnan(session_vwap_sd[local_i]) else 0.0)
                vwap_sd_lower[abs_i] = session_vwap[local_i] - k * (session_vwap_sd[local_i] if not np.isnan(session_vwap_sd[local_i]) else 0.0)

        df["vwap"] = vwap_vals
        df["vwap_sd_upper"] = vwap_sd_upper
        df["vwap_sd_lower"] = vwap_sd_lower

    else:
        # Rolling VWAP over a 50-bar window
        window = 50
        cum_pv = (df["Last"] * df["Volume"]).rolling(window, min_periods=2).sum()
        cum_v = df["Volume"].rolling(window, min_periods=2).sum().clip(lower=1e-9)
        df["vwap"] = cum_pv / cum_v
        rolling_sd = df["Last"].rolling(window, min_periods=2).std()
        df["vwap_sd_upper"] = df["vwap"] + k * rolling_sd
        df["vwap_sd_lower"] = df["vwap"] - k * rolling_sd

    return df
