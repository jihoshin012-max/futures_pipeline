# archetype: rotational
"""Compare C++ SpeedRead V2 log against Python SpeedRead computation.

Joins on timestamp, compares all intermediate and final values,
and checks threshold-critical disagreements around composite=48.
"""

import sys
from pathlib import Path
from math import tanh

import numpy as np
import pandas as pd

_REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO))

from shared.data_loader import load_bars

_250TICK_PATH = "stages/01-data/data/bar_data/tick/NQ_BarData_250tick_rot_P1.csv"
_CPP_LOG_PATH = "stages/01-data/data/bar_data/tick/NQ_SpeedRead_V2_Log_250tick_rot_P1.csv"


def compute_speedread_full(close, volume, lookback=10, vol_avg_len=50,
                           price_weight=50.0, vol_weight=50.0,
                           smoothing_bars=3, median_window=200):
    """Compute SpeedRead with ALL intermediates for comparison."""
    n = len(close)
    price_travel = np.full(n, np.nan)
    price_vel_raw = np.full(n, np.nan)
    price_scaled = np.full(n, np.nan)
    avg_vol_arr = np.full(n, np.nan)
    recent_vol_arr = np.full(n, np.nan)
    vol_rate_raw = np.full(n, np.nan)
    vol_scaled = np.full(n, np.nan)
    composite_raw = np.full(n, np.nan)

    # --- Price travel ---
    for i in range(lookback, n):
        travel = 0.0
        for j in range(lookback):
            idx = i - j
            travel += abs(close[idx] - close[idx - 1])
        price_travel[i] = travel

    # --- Median normalization ---
    pt_series = pd.Series(price_travel)
    median_pt = pt_series.rolling(median_window, min_periods=median_window).median().values

    for i in range(n):
        if np.isnan(price_travel[i]) or np.isnan(median_pt[i]) or median_pt[i] == 0:
            continue
        price_vel_raw[i] = price_travel[i] / median_pt[i]
        price_scaled[i] = 50.0 * (1.0 + tanh((price_vel_raw[i] - 1.0) * 1.5))

    # --- Volume rate ---
    for i in range(vol_avg_len + 1, n):
        # Average volume EXCLUDES current bar (starts at i-1)
        av = 0.0
        for j in range(vol_avg_len):
            av += volume[i - 1 - j]
        av /= vol_avg_len
        avg_vol_arr[i] = av

        if av == 0:
            continue

        # Recent volume INCLUDES current bar
        recent_bars = min(lookback, 5)
        rv = 0.0
        for j in range(recent_bars):
            rv += volume[i - j]
        rv /= recent_bars
        recent_vol_arr[i] = rv

        vol_rate_raw[i] = rv / av
        vol_scaled[i] = 50.0 * (1.0 + tanh((vol_rate_raw[i] - 1.0) * 1.5))

    # --- Composite ---
    total_weight = price_weight + vol_weight
    for i in range(n):
        if np.isnan(price_scaled[i]) or np.isnan(vol_scaled[i]):
            continue
        composite_raw[i] = (price_scaled[i] * price_weight + vol_scaled[i] * vol_weight) / total_weight

    # --- Smoothing: SMA of RAW composite ---
    cr_series = pd.Series(composite_raw)
    composite_smoothed = cr_series.rolling(smoothing_bars, min_periods=smoothing_bars).mean().values

    return pd.DataFrame({
        "PriceTravel": price_travel,
        "MedianPriceTravel": median_pt,
        "PriceVelRaw": price_vel_raw,
        "PriceScaled": price_scaled,
        "AvgVol": avg_vol_arr,
        "RecentVol": recent_vol_arr,
        "VolRateRaw": vol_rate_raw,
        "VolScaled": vol_scaled,
        "CompositeRaw": composite_raw,
        "CompositeSmoothed": composite_smoothed,
    })


def main():
    print("=" * 80)
    print("SpeedRead C++ vs Python Comparison")
    print("=" * 80)

    # --- Load C++ log ---
    print("\nLoading C++ log...")
    cpp = pd.read_csv(_CPP_LOG_PATH)
    cpp.columns = [c.strip() for c in cpp.columns]
    cpp["datetime"] = pd.to_datetime(cpp["Date"].astype(str).str.strip() + " " +
                                      cpp["Time"].astype(str).str.strip(), format="mixed")
    print(f"  C++ rows: {len(cpp):,}")
    print(f"  BarIndex range: {cpp['BarIndex'].iloc[0]} to {cpp['BarIndex'].iloc[-1]}")
    print(f"  Date range: {cpp['datetime'].iloc[0]} to {cpp['datetime'].iloc[-1]}")

    # --- Load 250-tick bars and compute Python SpeedRead ---
    print("\nLoading 250-tick bar data and computing Python SpeedRead...")
    ohlc = load_bars(_250TICK_PATH)
    close = ohlc["Last"].values.astype(float)
    volume = ohlc["Volume"].values.astype(float)

    py_intermediates = compute_speedread_full(close, volume)
    py_intermediates["bar_index"] = np.arange(len(py_intermediates))
    py_intermediates["datetime"] = ohlc["datetime"].values
    print(f"  Python rows: {len(py_intermediates):,}")

    # ==========================================================
    # A. ROW MATCHING (by BarIndex)
    # ==========================================================
    print(f"\n{'='*80}")
    print("A. ROW MATCHING (joined on BarIndex = Python row index)")
    print(f"{'='*80}")

    # C++ BarIndex maps directly to Python 0-based row index
    # Verify Close prices match on first few rows
    sample_checks = []
    for _, row in cpp.head(5).iterrows():
        bi = int(row["BarIndex"])
        if bi < len(ohlc):
            cpp_close = row["Close"]
            py_close = ohlc.iloc[bi]["Last"]
            sample_checks.append((bi, cpp_close, py_close, cpp_close == py_close))
    print(f"\n  Close price alignment check (first 5 C++ rows):")
    for bi, cc, pc, ok in sample_checks:
        print(f"    BarIndex={bi}: C++={cc}, Py={pc} -> {'OK' if ok else 'MISMATCH'}")
    if not all(ok for _, _, _, ok in sample_checks):
        print("\n  FATAL: Close prices don't match. BarIndex alignment is wrong.")
        return

    # Join by BarIndex
    merged = pd.merge(
        cpp.rename(columns={"BarIndex": "bar_index"}),
        py_intermediates,
        on="bar_index", how="inner", suffixes=("_cpp", "_py"))
    # Use Python datetime (has sub-second precision)
    merged["datetime"] = merged["datetime_py"]

    cpp_min_bi = int(cpp["BarIndex"].min())
    cpp_max_bi = int(cpp["BarIndex"].max())
    py_max_bi = len(py_intermediates) - 1

    print(f"\n  C++ rows:      {len(cpp):,} (BarIndex {cpp_min_bi}-{cpp_max_bi})")
    print(f"  Python rows:   {len(py_intermediates):,} (index 0-{py_max_bi})")
    print(f"  Matched rows:  {len(merged):,}")
    unmatched_cpp = len(cpp) - len(merged)
    unmatched_py = len(py_intermediates) - len(merged)
    print(f"  C++ unmatched: {unmatched_cpp:,} (BarIndex outside Python range or C++ extends past P1)")
    print(f"  Python unmatched: {unmatched_py:,} (warm-up rows before C++ starts logging)")

    # ==========================================================
    # B. PER-COLUMN COMPARISON
    # ==========================================================
    print(f"\n{'='*80}")
    print("B. PER-COLUMN COMPARISON (matched rows only)")
    print(f"{'='*80}")

    columns = [
        "PriceTravel", "MedianPriceTravel", "PriceVelRaw", "PriceScaled",
        "AvgVol", "RecentVol", "VolRateRaw", "VolScaled",
        "CompositeRaw", "CompositeSmoothed",
    ]

    print(f"\n  {'Column':<22} {'MeanDelta':>10} {'MaxDelta':>10} {'MaxDelta Timestamp':<26} {'Corr':>8}")
    print("  " + "-" * 80)

    first_fail_col = None
    any_fail = False

    for col in columns:
        cpp_col = f"{col}_cpp"
        py_col = f"{col}_py"

        if cpp_col not in merged.columns or py_col not in merged.columns:
            print(f"  {col:<22} MISSING COLUMN")
            continue

        # Drop rows where either is NaN
        mask = merged[cpp_col].notna() & merged[py_col].notna()
        m = merged[mask]

        if len(m) == 0:
            print(f"  {col:<22} NO VALID PAIRS")
            continue

        delta = (m[py_col].values - m[cpp_col].values)
        abs_delta = np.abs(delta)
        mean_d = np.mean(abs_delta)
        max_d = np.max(abs_delta)
        max_idx = np.argmax(abs_delta)
        max_ts = m.iloc[max_idx]["datetime"]

        # Correlation
        if np.std(m[cpp_col].values) > 0 and np.std(m[py_col].values) > 0:
            corr = np.corrcoef(m[cpp_col].values, m[py_col].values)[0, 1]
        else:
            corr = float("nan")

        # Check fail thresholds
        fail = ""
        if col == "CompositeSmoothed" and max_d > 5.0:
            fail = " FAIL(max>5)"
            any_fail = True
        elif col == "PriceTravel" and mean_d > 1.0:
            fail = " FAIL(mean>1)"
            any_fail = True
        elif not np.isnan(corr) and corr < 0.99:
            fail = " FAIL(corr<0.99)"
            any_fail = True

        if fail and first_fail_col is None:
            first_fail_col = col

        # Mean signed delta for bias check
        mean_signed = np.mean(delta)
        bias_tag = ""
        if col == "CompositeSmoothed" and abs(mean_signed) > 0.1:
            bias_tag = f"  bias={mean_signed:+.3f}"

        corr_str = f"{corr:.6f}" if not np.isnan(corr) else "N/A"
        print(f"  {col:<22} {mean_d:>10.4f} {max_d:>10.4f} {str(max_ts):<26} {corr_str:>8}{fail}{bias_tag}")

    # ==========================================================
    # C. THRESHOLD-CRITICAL ANALYSIS
    # ==========================================================
    print(f"\n{'='*80}")
    print("C. THRESHOLD-CRITICAL ANALYSIS (CompositeSmoothed near 48)")
    print(f"{'='*80}")

    cs_cpp = "CompositeSmoothed_cpp"
    cs_py = "CompositeSmoothed_py"

    # Both must be non-NaN
    mask = merged[cs_cpp].notna() & merged[cs_py].notna()
    m = merged[mask].copy()

    # Bars where either is in [45, 51]
    in_range = m[((m[cs_cpp] >= 45) & (m[cs_cpp] <= 51)) |
                 ((m[cs_py] >= 45) & (m[cs_py] <= 51))].copy()

    print(f"\n  Bars in threshold range [45, 51]: {len(in_range):,} / {len(m):,}")

    if len(in_range) > 0:
        delta_range = np.abs(in_range[cs_py].values - in_range[cs_cpp].values)
        print(f"  Mean delta in range: {np.mean(delta_range):.4f}")
        print(f"  Max delta in range:  {np.max(delta_range):.4f}")

        # Disagreements: one says >=48, other says <48
        cpp_pass = in_range[cs_cpp] >= 48
        py_pass = in_range[cs_py] >= 48
        disagree = in_range[cpp_pass != py_pass]
        disagree_rate = len(disagree) / len(in_range) * 100 if len(in_range) > 0 else 0

        print(f"\n  Threshold disagreements: {len(disagree)} / {len(in_range)} ({disagree_rate:.2f}%)")

        if len(disagree) > 0:
            print(f"\n  First 10 disagreements:")
            print(f"  {'Timestamp':<26} {'C++ Val':>8} {'Py Val':>8} {'Delta':>8} {'C++>=48':>8} {'Py>=48':>7}")
            print("  " + "-" * 70)
            for _, row in disagree.head(10).iterrows():
                cv = row[cs_cpp]
                pv = row[cs_py]
                d = pv - cv
                print(f"  {str(row['datetime']):<26} {cv:>8.3f} {pv:>8.3f} {d:>+8.3f} "
                      f"{'Y' if cv >= 48 else 'N':>8} {'Y' if pv >= 48 else 'N':>7}")

        # Fail check
        if disagree_rate > 1.0:
            print(f"\n  FAIL: Disagreement rate {disagree_rate:.2f}% > 1.0%")
            any_fail = True
        elif len(disagree) > 0:
            print(f"\n  WARNING: {len(disagree)} disagreements, but rate {disagree_rate:.2f}% < 1.0%")
        else:
            print(f"\n  PASS: Zero threshold disagreements")

    # ==========================================================
    # SUMMARY
    # ==========================================================
    print(f"\n{'='*80}")
    print("SUMMARY")
    print(f"{'='*80}")

    if any_fail:
        print(f"\n  RESULT: FAIL")
        if first_fail_col:
            print(f"  First divergent column: {first_fail_col}")
            print(f"  Bug is at or upstream of the {first_fail_col} computation stage.")
        print(f"\n  DO NOT proceed to autotrader integration.")
    else:
        print(f"\n  RESULT: PASS")
        print(f"  All columns within tolerance. C++ and Python SpeedRead implementations agree.")


if __name__ == "__main__":
    main()
