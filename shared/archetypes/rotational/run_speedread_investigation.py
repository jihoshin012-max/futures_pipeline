# archetype: rotational
# STATUS: ONE-TIME
# PURPOSE: SpeedRead filter investigation for FRC SD=25
# LAST RUN: 2026-03

"""SpeedRead filter investigation for FRC SD=25 cap=2.

Computes SpeedRead composite on 250-tick bar data, maps to tick data,
runs cycle-level diagnostics, optimizes threshold on P1a, and validates on P1b.

Steps:
  1. Compute SpeedRead composite, verify distribution
  2. Diagnostic: quintile analysis of cycle quality vs SpeedRead
  3. Threshold optimization on P1a
  4. One-shot P1b validation (frozen threshold)

Usage:
    python run_speedread_investigation.py --step 1
    python run_speedread_investigation.py --step 2
    python run_speedread_investigation.py --step 3
    python run_speedread_investigation.py --step 4 --threshold <value>
"""

import sys
import json
import copy
import time
import datetime as dt_mod
from pathlib import Path
from math import tanh

import numpy as np
import pandas as pd

_REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from shared.data_loader import load_bars
from rotational_simulator import RotationalSimulator

EXCLUDE_HOURS = {1, 19, 20}
_P1_START = dt_mod.date(2025, 9, 21)
_P1_END = dt_mod.date(2025, 12, 14)
_P1_MID = _P1_START + (_P1_END - _P1_START) / 2  # ~Nov 2

_250TICK_PATH = "stages/01-data/data/bar_data/tick/NQ_BarData_250tick_rot_P1.csv"
_1TICK_PATH = "stages/01-data/data/bar_data/tick/NQ_BarData_1tick_rot_P1.csv"
_PARAMS_PATH = Path(__file__).parent / "rotational_params.json"
_OUTPUT_DIR = Path(__file__).parent / "speedread_results"


# ============================================================
# SpeedRead Computation
# ============================================================

def compute_speedread(close: np.ndarray, volume: np.ndarray,
                      lookback: int = 10, vol_avg_len: int = 50,
                      price_weight: float = 50.0, vol_weight: float = 50.0,
                      smoothing_bars: int = 3, median_window: int = 200
                      ) -> tuple:
    """Compute SpeedRead composite on 250-tick bar data.

    Returns:
        (composite_smoothed, composite_raw, price_scaled, vol_scaled,
         price_vel_raw, vol_rate_raw, price_travel_series)
    """
    n = len(close)
    price_travel = np.full(n, np.nan)
    price_vel_raw = np.full(n, np.nan)
    price_scaled = np.full(n, np.nan)
    vol_rate_raw = np.full(n, np.nan)
    vol_scaled = np.full(n, np.nan)
    composite_raw = np.full(n, np.nan)
    composite_smoothed = np.full(n, np.nan)

    # --- Price travel ---
    # Sum of absolute bar-to-bar close changes over lookback window
    for i in range(lookback, n):
        travel = 0.0
        for j in range(lookback):
            idx = i - j
            prev_idx = idx - 1
            travel += abs(close[idx] - close[prev_idx])
        price_travel[i] = travel

    # --- Median normalization of price travel ---
    # Rolling 200-bar median of price_travel
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
        avg_vol = 0.0
        for j in range(vol_avg_len):
            avg_vol += volume[i - 1 - j]
        avg_vol /= vol_avg_len

        if avg_vol == 0:
            continue

        # Recent volume INCLUDES current bar
        recent_bars = min(lookback, 5)
        recent_vol = 0.0
        for j in range(recent_bars):
            recent_vol += volume[i - j]
        recent_vol /= recent_bars

        vol_rate_raw[i] = recent_vol / avg_vol
        vol_scaled[i] = 50.0 * (1.0 + tanh((vol_rate_raw[i] - 1.0) * 1.5))

    # --- Composite ---
    total_weight = price_weight + vol_weight
    for i in range(n):
        if np.isnan(price_scaled[i]) or np.isnan(vol_scaled[i]):
            continue
        composite_raw[i] = (price_scaled[i] * price_weight + vol_scaled[i] * vol_weight) / total_weight

    # --- Smoothing: SMA of RAW composite values ---
    cr_series = pd.Series(composite_raw)
    composite_smoothed = cr_series.rolling(smoothing_bars, min_periods=smoothing_bars).mean().values

    return (composite_smoothed, composite_raw, price_scaled, vol_scaled,
            price_vel_raw, vol_rate_raw, price_travel)


def compute_speedread_atr(close: np.ndarray, high: np.ndarray, low: np.ndarray,
                          volume: np.ndarray, lookback: int = 10,
                          vol_avg_len: int = 50, atr_period: int = 20,
                          price_weight: float = 50.0, vol_weight: float = 50.0,
                          smoothing_bars: int = 3) -> np.ndarray:
    """Compute SpeedRead with ORIGINAL (broken) ATR normalization for comparison."""
    n = len(close)

    # Compute ATR manually
    prev_close = np.empty(n)
    prev_close[0] = close[0]
    prev_close[1:] = close[:-1]
    tr = np.maximum(high - low, np.maximum(np.abs(high - prev_close), np.abs(low - prev_close)))
    atr = pd.Series(tr).rolling(atr_period, min_periods=atr_period).mean().values

    composite_raw = np.full(n, np.nan)

    for i in range(max(lookback, vol_avg_len + 1), n):
        if np.isnan(atr[i]) or atr[i] == 0:
            continue

        # Price travel
        travel = 0.0
        for j in range(lookback):
            idx = i - j
            travel += abs(close[idx] - close[idx - 1])

        # BROKEN normalization: price_travel / (atr * lookback)
        pv_raw = travel / (atr[i] * lookback)
        ps = 50.0 * (1.0 + tanh((pv_raw - 1.0) * 1.5))

        # Volume rate (same logic)
        avg_vol = np.mean(volume[i - vol_avg_len:i])
        if avg_vol == 0:
            continue
        recent_bars = min(lookback, 5)
        recent_vol = np.mean(volume[i - recent_bars + 1:i + 1])
        vr_raw = recent_vol / avg_vol
        vs = 50.0 * (1.0 + tanh((vr_raw - 1.0) * 1.5))

        composite_raw[i] = (ps * price_weight + vs * vol_weight) / (price_weight + vol_weight)

    # Smooth
    return pd.Series(composite_raw).rolling(smoothing_bars, min_periods=smoothing_bars).mean().values


# ============================================================
# Step 1: Distribution Analysis
# ============================================================

def step1_distribution():
    """Compute SpeedRead on full 250-tick bars, report distribution."""
    print("=" * 70)
    print("STEP 1: SpeedRead Distribution Analysis")
    print("=" * 70)

    print("\nLoading 250-tick bar data...")
    ohlc = load_bars(_250TICK_PATH)
    print(f"  Rows: {len(ohlc):,}")
    print(f"  Date range: {ohlc['datetime'].iloc[0]} to {ohlc['datetime'].iloc[-1]}")

    close = ohlc["Last"].values.astype(float)
    high = ohlc["High"].values.astype(float)
    low = ohlc["Low"].values.astype(float)
    volume = ohlc["Volume"].values.astype(float)

    print("\nComputing SpeedRead (median normalization)...")
    t0 = time.time()
    (comp_smooth, comp_raw, p_scaled, v_scaled,
     pv_raw, vr_raw, pt_series) = compute_speedread(close, volume)
    print(f"  Computed in {time.time() - t0:.1f}s")

    # Valid values only
    valid = ~np.isnan(comp_smooth)
    cs = comp_smooth[valid]
    print(f"  Valid bars: {len(cs):,} / {len(comp_smooth):,}")

    print("\n--- MEDIAN-NORMALIZED SpeedRead Distribution ---")
    print(f"  Mean:   {np.mean(cs):.2f}")
    print(f"  Median: {np.median(cs):.2f}")
    print(f"  StdDev: {np.std(cs):.2f}")
    print(f"  P10:    {np.percentile(cs, 10):.2f}")
    print(f"  P25:    {np.percentile(cs, 25):.2f}")
    print(f"  P75:    {np.percentile(cs, 75):.2f}")
    print(f"  P90:    {np.percentile(cs, 90):.2f}")
    spread = np.percentile(cs, 90) - np.percentile(cs, 10)
    print(f"  P10-P90 spread: {spread:.2f}")

    # Histogram
    print("\n  Histogram (10 bins):")
    counts, edges = np.histogram(cs, bins=10)
    for i in range(len(counts)):
        bar = "#" * int(counts[i] / max(counts) * 40)
        print(f"  [{edges[i]:5.1f} - {edges[i+1]:5.1f}] {counts[i]:>6,} {bar}")

    # Now ATR-normalized (broken) for comparison
    print("\nComputing SpeedRead (ATR normalization - BROKEN method)...")
    comp_atr = compute_speedread_atr(close, high, low, volume)
    valid_atr = ~np.isnan(comp_atr)
    ca = comp_atr[valid_atr]
    print(f"  Valid bars: {len(ca):,}")

    print("\n--- ATR-NORMALIZED SpeedRead Distribution (BROKEN) ---")
    print(f"  Mean:   {np.mean(ca):.2f}")
    print(f"  Median: {np.median(ca):.2f}")
    print(f"  StdDev: {np.std(ca):.2f}")
    print(f"  P10:    {np.percentile(ca, 10):.2f}")
    print(f"  P25:    {np.percentile(ca, 25):.2f}")
    print(f"  P75:    {np.percentile(ca, 75):.2f}")
    print(f"  P90:    {np.percentile(ca, 90):.2f}")
    spread_atr = np.percentile(ca, 90) - np.percentile(ca, 10)
    print(f"  P10-P90 spread: {spread_atr:.2f}")

    # Kill condition
    print(f"\n--- KILL CONDITION CHECK ---")
    if spread < 15:
        print(f"  FAIL: Median-fixed P10-P90 spread = {spread:.2f} < 15")
        print("  SpeedRead has insufficient discriminating power. STOP.")
        return False
    else:
        print(f"  PASS: Median-fixed P10-P90 spread = {spread:.2f} >= 15")
        if spread_atr < 15:
            print(f"  Confirmed: ATR spread = {spread_atr:.2f} (broken, too compressed)")
        print("  Proceeding to Step 2.")

    # Save composite with timestamps for Step 2
    _OUTPUT_DIR.mkdir(exist_ok=True)
    out_df = pd.DataFrame({
        "datetime": ohlc["datetime"].values,
        "speedread_composite": comp_smooth,
        "composite_raw": comp_raw,
        "price_scaled": p_scaled,
        "vol_scaled": v_scaled,
    })
    out_path = _OUTPUT_DIR / "speedread_250tick.parquet"
    out_df.to_parquet(out_path, index=False)
    print(f"\nSaved: {out_path}")

    # Also check sub-component distributions
    pv_valid = pv_raw[~np.isnan(pv_raw)]
    vr_valid = vr_raw[~np.isnan(vr_raw)]
    print(f"\n--- Sub-component distributions ---")
    print(f"  Price velocity raw: mean={np.mean(pv_valid):.3f}, "
          f"median={np.median(pv_valid):.3f}, "
          f"P10={np.percentile(pv_valid, 10):.3f}, P90={np.percentile(pv_valid, 90):.3f}")
    print(f"  Volume rate raw:    mean={np.mean(vr_valid):.3f}, "
          f"median={np.median(vr_valid):.3f}, "
          f"P10={np.percentile(vr_valid, 10):.3f}, P90={np.percentile(vr_valid, 90):.3f}")

    return True


# ============================================================
# Step 2: Cycle Quality Diagnostic
# ============================================================

def _build_frc_config():
    """Build FRC SD=25 cap=2 config."""
    with open(_PARAMS_PATH) as f:
        cfg = json.load(f)

    cfg["hypothesis"]["trigger_mechanism"] = "fixed"
    cfg["hypothesis"]["trigger_params"]["step_dist"] = 25.0
    cfg["martingale"]["max_levels"] = 1
    cfg["martingale"]["max_contract_size"] = 8
    cfg["martingale"]["initial_qty"] = 1
    cfg["martingale"]["max_total_position"] = 0
    cfg["martingale"]["anchor_mode"] = "walking"
    cfg["martingale"]["flatten_reseed_cap"] = 2
    cfg["_instrument"] = {"tick_size": 0.25, "cost_ticks": 1}
    cfg["period"] = "P1a"
    # Only tick data path
    cfg["bar_data_primary"] = {
        "bar_data_1tick_rot_P1": cfg["bar_data_primary"]["bar_data_1tick_rot_P1"]
    }
    return cfg


def step2_diagnostic():
    """Run FRC SD=25 cap=2 on P1a, tag cycles with SpeedRead, quintile analysis."""
    print("=" * 70)
    print("STEP 2: Cycle Quality Diagnostic (P1a)")
    print("=" * 70)

    # Load SpeedRead from Step 1
    sr_path = _OUTPUT_DIR / "speedread_250tick.parquet"
    if not sr_path.exists():
        print("ERROR: Run Step 1 first to generate SpeedRead composite.")
        return False
    sr_df = pd.read_parquet(sr_path)
    sr_ts = pd.to_datetime(sr_df["datetime"]).values.astype("int64") // 10**9
    sr_vals = sr_df["speedread_composite"].values

    # Load tick data
    print("\nLoading P1a tick data...")
    t0 = time.time()
    cfg = _build_frc_config()
    tick_bars = load_bars(cfg["bar_data_primary"]["bar_data_1tick_rot_P1"])
    tick_p1a = tick_bars[tick_bars["datetime"].dt.date <= _P1_MID].reset_index(drop=True)
    print(f"  P1a ticks: {len(tick_p1a):,} rows in {time.time() - t0:.1f}s")

    # Run simulator
    print("\nRunning FRC SD=25 cap=2 on P1a...")
    t0 = time.time()
    sim = RotationalSimulator(config=cfg, bar_data=tick_p1a, reference_data=None)
    result = sim.run()
    cycles = result.cycles
    trades = result.trades
    print(f"  Sim completed in {time.time() - t0:.1f}s")
    print(f"  Total cycles: {len(cycles)}")

    # Hour filter
    entry_trades = trades[trades["action"].isin(["SEED", "REVERSAL"])]
    ce = entry_trades.groupby("cycle_id")["datetime"].first().reset_index()
    ce.columns = ["cycle_id", "entry_dt"]
    cycles = cycles.merge(ce, on="cycle_id", how="left")
    cycles["hour"] = pd.to_datetime(cycles["entry_dt"]).dt.hour
    cf = cycles[~cycles["hour"].isin(EXCLUDE_HOURS)].copy()
    valid_ids = set(cf["cycle_id"])
    tf = trades[trades["cycle_id"].isin(valid_ids)]
    print(f"  After hour filter: {len(cf)} cycles")

    # Per-cycle cost
    cc1 = tf.groupby("cycle_id")["cost_ticks"].sum()
    cf["cost_1t"] = cf["cycle_id"].map(cc1).fillna(0)
    cf["net_pnl_1t"] = cf["gross_pnl_ticks"] - cf["cost_1t"]

    # Map SpeedRead to cycle entry timestamps
    entry_ts = pd.to_datetime(cf["entry_dt"]).values.astype("int64") // 10**9
    sr_idx = np.clip(np.searchsorted(sr_ts, entry_ts, side="right") - 1, 0, len(sr_vals) - 1)
    cf["speedread"] = sr_vals[sr_idx]

    # Drop cycles with NaN SpeedRead (early warmup)
    cf_valid = cf.dropna(subset=["speedread"]).copy()
    print(f"  Cycles with valid SpeedRead: {len(cf_valid)}")

    # Overall stats
    gw = cf_valid[cf_valid["gross_pnl_ticks"] > 0]["gross_pnl_ticks"].sum()
    gl = abs(cf_valid[cf_valid["gross_pnl_ticks"] <= 0]["gross_pnl_ticks"].sum())
    gpf = gw / gl if gl > 0 else 0
    nw = cf_valid[cf_valid["net_pnl_1t"] > 0]["net_pnl_1t"].sum()
    nl = abs(cf_valid[cf_valid["net_pnl_1t"] <= 0]["net_pnl_1t"].sum())
    npf = nw / nl if nl > 0 else 0

    print(f"\n--- Overall P1a FRC SD=25 cap=2 ---")
    print(f"  Cycles: {len(cf_valid)}")
    print(f"  Gross PF: {gpf:.4f}")
    print(f"  Net PF @1t: {npf:.4f}")
    print(f"  Net PnL @1t: {cf_valid['net_pnl_1t'].sum():+,.0f} ticks")
    print(f"  Gross PnL: {cf_valid['gross_pnl_ticks'].sum():+,.0f} ticks")

    # Quintile analysis
    cf_valid["quintile"] = pd.qcut(cf_valid["speedread"], 5, labels=["Q1(slow)", "Q2", "Q3", "Q4", "Q5(fast)"])

    print(f"\n--- Quintile Analysis (Q1=slowest, Q5=fastest market) ---")
    print(f"  {'Quintile':<12} {'SR Range':<18} {'Cyc':>5} {'GrPnL':>8} {'GrPF':>6} "
          f"{'AvgGr':>7} {'NP@1t':>6} {'NetPnL':>8}")
    print("  " + "-" * 80)

    quintile_gpf = []
    for q in ["Q1(slow)", "Q2", "Q3", "Q4", "Q5(fast)"]:
        qc = cf_valid[cf_valid["quintile"] == q]
        if len(qc) == 0:
            continue
        qgw = qc[qc["gross_pnl_ticks"] > 0]["gross_pnl_ticks"].sum()
        qgl = abs(qc[qc["gross_pnl_ticks"] <= 0]["gross_pnl_ticks"].sum())
        qgpf = qgw / qgl if qgl > 0 else 0
        qnw = qc[qc["net_pnl_1t"] > 0]["net_pnl_1t"].sum()
        qnl = abs(qc[qc["net_pnl_1t"] <= 0]["net_pnl_1t"].sum())
        qnpf = qnw / qnl if qnl > 0 else 0
        sr_lo = qc["speedread"].min()
        sr_hi = qc["speedread"].max()
        avg_g = qc["gross_pnl_ticks"].mean()
        print(f"  {q:<12} [{sr_lo:5.1f}-{sr_hi:5.1f}] {len(qc):>5} "
              f"{qc['gross_pnl_ticks'].sum():>+8,.0f} {qgpf:>6.3f} "
              f"{avg_g:>+7.1f} {qnpf:>6.3f} {qc['net_pnl_1t'].sum():>+8,.0f}")
        quintile_gpf.append(qgpf)

    # Save cycle-level data (always, regardless of kill condition)
    _OUTPUT_DIR.mkdir(exist_ok=True)
    out_path = _OUTPUT_DIR / "cycles_with_speedread_p1a.parquet"
    cf_valid.to_parquet(out_path, index=False)
    print(f"\nSaved: {out_path}")

    # Kill condition: check for monotonic degradation
    if len(quintile_gpf) == 5:
        q1_gpf = quintile_gpf[0]
        q5_gpf = quintile_gpf[4]
        pct_diff = abs(q5_gpf - q1_gpf) / q1_gpf * 100 if q1_gpf > 0 else 0
        print(f"\n--- KILL CONDITION CHECK (original hypothesis: fast = bad) ---")
        print(f"  Q1 Gross PF: {q1_gpf:.3f}")
        print(f"  Q5 Gross PF: {q5_gpf:.3f}")
        print(f"  Q1-Q5 difference: {pct_diff:.1f}%")
        if pct_diff < 10:
            print(f"  FAIL: Q5 gross PF within 10% of Q1 ({pct_diff:.1f}%)")
            print("  Original hypothesis killed. Data saved for reverse filter.")
            return False
        elif q5_gpf >= q1_gpf:
            print(f"  FAIL: Q5 >= Q1 (fast markets are BETTER, not worse)")
            print("  Original hypothesis killed. Data saved for reverse filter.")
            return False
        else:
            print(f"  PASS: Q5 < Q1 with {pct_diff:.1f}% gap -- fast markets degrade rotation quality.")
            print("  Proceeding to Step 3.")

    return True


# ============================================================
# Step A: Reverse Filter -- Optimize Slow-Cutoff Threshold on P1a
# ============================================================

def _compute_pf(df, pnl_col="gross_pnl_ticks"):
    """Compute profit factor from a cycle DataFrame."""
    w = df[df[pnl_col] > 0][pnl_col].sum()
    l = abs(df[df[pnl_col] <= 0][pnl_col].sum())
    return w / l if l > 0 else 0


def stepA_optimize():
    """Sweep reverse SpeedRead thresholds on P1a -- remove SLOW entries.

    FILTER DIRECTION: composite < threshold -> SKIP (slow, bad for SD=25).
                      composite >= threshold -> TRADE (fast, good for SD=25).
    """
    print("=" * 70)
    print("STEP A: Reverse SpeedRead Threshold Optimization (P1a)")
    print("  Filter: composite < threshold -> SKIP, composite >= threshold -> TRADE")
    print("=" * 70)

    # Load existing cycle data from Step 2 (no simulator rerun)
    cyc_path = _OUTPUT_DIR / "cycles_with_speedread_p1a.parquet"
    if not cyc_path.exists():
        print("ERROR: Run Step 2 first to generate cycle-level data.")
        return None
    cf = pd.read_parquet(cyc_path)

    total_cycles = len(cf)
    print(f"  Total cycles (P1a, hour-filtered): {total_cycles}")
    print(f"  SpeedRead range: [{cf['speedread'].min():.1f}, {cf['speedread'].max():.1f}]")

    # Baseline (unfiltered)
    gpf_all = _compute_pf(cf, "gross_pnl_ticks")
    npf_all = _compute_pf(cf, "net_pnl_1t")
    print(f"  Baseline: GrPF={gpf_all:.4f}, NP@1t={npf_all:.4f}, Net={cf['net_pnl_1t'].sum():+,.0f}")

    # Fine-grained sweep: 1-point increments from composite 30 to 55
    # (P20 ~ 42, P50 ~ 50, so this covers filtering 0-50% of slowest cycles)
    thresholds = np.arange(30.0, 56.0, 1.0)

    print(f"\n  {'Thresh':>7} {'Retained':>8} {'Ret%':>6} {'GrPF':>6} {'NP@1t':>6} "
          f"{'NetPnL':>9} {'dNP':>6}")
    print("  " + "-" * 62)

    best_npf = 0
    best_thresh = None
    results = []

    for thresh in thresholds:
        # REVERSE FILTER: keep composite >= threshold (fast markets)
        retained = cf[cf["speedread"] >= thresh]
        n = len(retained)
        ret_pct = n / total_cycles

        gpf = _compute_pf(retained, "gross_pnl_ticks")
        npf = _compute_pf(retained, "net_pnl_1t")
        net_pnl = retained["net_pnl_1t"].sum()

        marker = ""
        if ret_pct >= 0.60 and npf > best_npf:
            best_npf = npf
            best_thresh = thresh
            marker = " <<<"

        results.append({
            "threshold": thresh, "retained": n, "retention": ret_pct,
            "gpf": gpf, "npf_1t": npf, "net_pnl": net_pnl,
        })

        print(f"  {thresh:>7.1f} {n:>8} {ret_pct:>6.1%} {gpf:>6.3f} {npf:>6.3f} "
              f"{net_pnl:>+9,.0f} {npf - npf_all:>+6.3f}{marker}")

    # Sensitivity check: is the best threshold in a stable region?
    print(f"\n--- Sensitivity Check (+/-2 points around best) ---")
    if best_thresh is not None:
        for delta in [-2, -1, 0, +1, +2]:
            t = best_thresh + delta
            row = next((r for r in results if r["threshold"] == t), None)
            if row:
                tag = " << selected" if delta == 0 else ""
                print(f"  T={t:.1f}: NP@1t={row['npf_1t']:.4f}, ret={row['retention']:.1%}{tag}")

        # Check stability: NP@1t within 10% at +/-2 points
        center = next(r for r in results if r["threshold"] == best_thresh)
        neighbors = [r for r in results if abs(r["threshold"] - best_thresh) <= 2.0]
        npf_range = max(r["npf_1t"] for r in neighbors) - min(r["npf_1t"] for r in neighbors)
        pct_swing = npf_range / center["npf_1t"] * 100 if center["npf_1t"] > 0 else 999
        stable = pct_swing <= 10
        print(f"  NP@1t swing in +/-2 window: {npf_range:.4f} ({pct_swing:.1f}%)")
        print(f"  Stability: {'STABLE' if stable else 'UNSTABLE (>10% swing)'}")

    # Report at fixed retention levels
    print(f"\n--- Net PF at key retention levels ---")
    for target_ret in [0.60, 0.65, 0.70, 0.75, 0.80]:
        closest = min(results, key=lambda r: abs(r["retention"] - target_ret))
        print(f"  {target_ret:.0%} retention: T={closest['threshold']:.1f}, "
              f"GrPF={closest['gpf']:.3f}, NP@1t={closest['npf_1t']:.3f}, "
              f"Net={closest['net_pnl']:+,.0f}")

    # Final selection
    if best_thresh is not None:
        best_row = next(r for r in results if r["threshold"] == best_thresh)
        print(f"\n{'='*60}")
        print(f"  SELECTED THRESHOLD: {best_thresh:.1f}")
        print(f"  Net PF @1t: {best_npf:.4f}")
        print(f"  Retention:  {best_row['retention']:.1%}")
        print(f"  Gross PF:   {best_row['gpf']:.3f}")
        print(f"  Net PnL:    {best_row['net_pnl']:+,.0f} ticks")
        print(f"{'='*60}")

        # Gate for Step B: NP@1t > 1.15
        if best_npf <= 1.15:
            print(f"\n  GATE: NP@1t = {best_npf:.4f} <= 1.15")
            print("  Insufficient margin for P1b. Consider stopping.")
        else:
            print(f"\n  GATE PASSED: NP@1t = {best_npf:.4f} > 1.15")
            print(f"  Freeze threshold = {best_thresh:.1f} for Step B.")

        # Save frozen threshold
        thresh_file = _OUTPUT_DIR / "frozen_threshold_reverse.json"
        with open(thresh_file, "w") as f:
            json.dump({
                "threshold": round(best_thresh, 4),
                "direction": "reverse",
                "filter_rule": "composite < threshold -> SKIP, composite >= threshold -> TRADE",
                "npf_1t_p1a": round(best_npf, 4),
                "retention_p1a": round(best_row["retention"], 4),
                "gpf_p1a": round(best_row["gpf"], 4),
                "net_pnl_p1a": int(best_row["net_pnl"]),
            }, f, indent=2)
        print(f"\nSaved: {thresh_file}")
    else:
        print("\n  No threshold found with retention >= 60%.")

    return best_thresh


# ============================================================
# Step B: P1b One-Shot Validation (Reverse Filter)
# ============================================================

def _process_cycles_with_costs(cycles, trades):
    """Hour-filter cycles and compute per-cycle net PnL @1t."""
    entry_trades = trades[trades["action"].isin(["SEED", "REVERSAL"])]
    ce = entry_trades.groupby("cycle_id")["datetime"].first().reset_index()
    ce.columns = ["cycle_id", "entry_dt"]
    cycles = cycles.merge(ce, on="cycle_id", how="left")
    cycles["hour"] = pd.to_datetime(cycles["entry_dt"]).dt.hour
    cf = cycles[~cycles["hour"].isin(EXCLUDE_HOURS)].copy()
    valid_ids = set(cf["cycle_id"])
    tf = trades[trades["cycle_id"].isin(valid_ids)]
    cc1 = tf.groupby("cycle_id")["cost_ticks"].sum()
    cf["cost_1t"] = cf["cycle_id"].map(cc1).fillna(0)
    cf["net_pnl_1t"] = cf["gross_pnl_ticks"] - cf["cost_1t"]
    return cf, tf


def stepB_validate(threshold: float = None):
    """P1b one-shot validation with REVERSE SpeedRead filter.

    FILTER: composite < threshold -> SKIP. composite >= threshold -> TRADE.
    """
    print("=" * 70)
    print("STEP B: P1b One-Shot Validation (Reverse SpeedRead Filter)")
    print("  Filter: composite < threshold -> SKIP, composite >= threshold -> TRADE")
    print("=" * 70)

    # Load frozen threshold
    if threshold is None:
        thresh_file = _OUTPUT_DIR / "frozen_threshold_reverse.json"
        if not thresh_file.exists():
            print("ERROR: No frozen threshold. Run Step A first or pass --threshold.")
            return None
        with open(thresh_file) as f:
            info = json.load(f)
        threshold = info["threshold"]
        print(f"  Loaded frozen threshold: {threshold:.4f}")
        print(f"  P1a stats: NP@1t={info['npf_1t_p1a']:.4f}, retention={info['retention_p1a']:.1%}")
    else:
        print(f"  Using provided threshold: {threshold:.4f}")

    # Load SpeedRead from Step 1 (full P1 period)
    sr_path = _OUTPUT_DIR / "speedread_250tick.parquet"
    sr_df = pd.read_parquet(sr_path)
    sr_ts = pd.to_datetime(sr_df["datetime"]).values.astype("int64") // 10**9
    sr_vals = sr_df["speedread_composite"].values

    # Load tick data -- P1b only
    print("\nLoading P1b tick data...")
    t0 = time.time()
    cfg = _build_frc_config()
    cfg["period"] = "P1b"
    tick_bars = load_bars(cfg["bar_data_primary"]["bar_data_1tick_rot_P1"])
    tick_p1b = tick_bars[tick_bars["datetime"].dt.date > _P1_MID].reset_index(drop=True)
    print(f"  P1b ticks: {len(tick_p1b):,} rows in {time.time() - t0:.1f}s")

    # ---- UNFILTERED baseline ----
    print("\nRunning UNFILTERED FRC SD=25 cap=2 on P1b...")
    t0 = time.time()
    sim_base = RotationalSimulator(config=cfg, bar_data=tick_p1b, reference_data=None)
    result_base = sim_base.run()
    cf_base, tf_base = _process_cycles_with_costs(result_base.cycles, result_base.trades)
    print(f"  Sim completed in {time.time() - t0:.1f}s")

    gpf_b = _compute_pf(cf_base, "gross_pnl_ticks")
    npf_b = _compute_pf(cf_base, "net_pnl_1t")
    print(f"\n  UNFILTERED P1b: {len(cf_base)} cycles, GrPF={gpf_b:.4f}, NP@1t={npf_b:.4f}, "
          f"Net={cf_base['net_pnl_1t'].sum():+,.0f} ticks")

    # ---- FILTERED (REVERSE: keep composite >= threshold) ----
    entry_ts = pd.to_datetime(cf_base["entry_dt"]).values.astype("int64") // 10**9
    sr_idx = np.clip(np.searchsorted(sr_ts, entry_ts, side="right") - 1, 0, len(sr_vals) - 1)
    cf_base["speedread"] = sr_vals[sr_idx]

    cf_valid = cf_base.dropna(subset=["speedread"])
    # REVERSE FILTER: keep fast (>= threshold), skip slow (< threshold)
    cf_filt = cf_valid[cf_valid["speedread"] >= threshold].copy()

    gpf_f = _compute_pf(cf_filt, "gross_pnl_ticks")
    npf_f = _compute_pf(cf_filt, "net_pnl_1t")
    retention = len(cf_filt) / len(cf_base) if len(cf_base) > 0 else 0

    print(f"\n{'='*60}")
    print(f"  FILTERED P1b RESULTS (threshold={threshold:.2f})")
    print(f"  Filter: composite < {threshold:.1f} -> SKIP")
    print(f"{'='*60}")
    print(f"  Cycles:     {len(cf_filt)} / {len(cf_base)} (retention={retention:.1%})")
    print(f"  Gross PF:   {gpf_f:.4f}")
    print(f"  Net PF @1t: {npf_f:.4f}")
    print(f"  Net PnL:    {cf_filt['net_pnl_1t'].sum():+,.0f} ticks")
    print(f"  Gross PnL:  {cf_filt['gross_pnl_ticks'].sum():+,.0f} ticks")

    # Improvement vs unfiltered
    print(f"\n--- vs Unfiltered ---")
    print(f"  NP@1t: {npf_b:.4f} -> {npf_f:.4f} ({npf_f - npf_b:+.4f})")
    print(f"  GrPF:  {gpf_b:.4f} -> {gpf_f:.4f} ({gpf_f - gpf_b:+.4f})")
    print(f"  Net:   {cf_base['net_pnl_1t'].sum():+,.0f} -> {cf_filt['net_pnl_1t'].sum():+,.0f}")

    # Pass criteria
    print(f"\n--- PASS CRITERIA ---")
    checks = [
        ("Net PF @1t > 1.0", npf_f > 1.0, f"{npf_f:.4f}"),
        ("Retention >= 50%", retention >= 0.50, f"{retention:.1%}"),
        ("Gross PF > 1.10", gpf_f > 1.10, f"{gpf_f:.4f}"),
    ]
    all_pass = True
    for desc, passed, val in checks:
        status = "PASS" if passed else "FAIL"
        if not passed:
            all_pass = False
        print(f"  [{status}] {desc}: {val}")

    if all_pass:
        print(f"\n  *** ALL CRITERIA MET -- Reverse SpeedRead filter validated on P1b ***")
    else:
        print(f"\n  *** VALIDATION FAILED -- Reverse SpeedRead filter does not pass P1b ***")

    # Save results
    result_file = _OUTPUT_DIR / "p1b_validation_reverse.json"
    with open(result_file, "w") as f:
        json.dump({
            "threshold": threshold,
            "direction": "reverse",
            "filter_rule": "composite < threshold -> SKIP, composite >= threshold -> TRADE",
            "unfiltered": {
                "cycles": int(len(cf_base)),
                "gpf": round(gpf_b, 4),
                "npf_1t": round(npf_b, 4),
                "net_pnl_1t": int(cf_base["net_pnl_1t"].sum()),
            },
            "filtered": {
                "cycles": int(len(cf_filt)),
                "retention": round(retention, 4),
                "gpf": round(gpf_f, 4),
                "npf_1t": round(npf_f, 4),
                "net_pnl_1t": int(cf_filt["net_pnl_1t"].sum()),
            },
            "pass": all_pass,
        }, f, indent=2)
    print(f"\nSaved: {result_file}")

    # Save filtered P1b cycles for Step C
    if all_pass:
        cf_filt.to_parquet(_OUTPUT_DIR / "p1b_filtered_cycles.parquet", index=False)
        cf_base.to_parquet(_OUTPUT_DIR / "p1b_all_cycles.parquet", index=False)

    return all_pass


# ============================================================
# Step C: Regime Diagnostics (if Step B passes)
# ============================================================

def stepC_diagnostics():
    """Collect regime diagnostics from P1b filtered results for future adaptive-SD work."""
    print("=" * 70)
    print("STEP C: Regime Diagnostics (P1b filtered results)")
    print("=" * 70)

    # Check that Step B passed
    val_file = _OUTPUT_DIR / "p1b_validation_reverse.json"
    if not val_file.exists():
        print("ERROR: Run Step B first.")
        return
    with open(val_file) as f:
        val = json.load(f)
    if not val.get("pass"):
        print("Step B did not pass. Skipping diagnostics.")
        return

    # Load filtered P1b cycles
    filt_path = _OUTPUT_DIR / "p1b_filtered_cycles.parquet"
    if not filt_path.exists():
        print("ERROR: No filtered P1b cycles saved. Re-run Step B.")
        return
    cf = pd.read_parquet(filt_path)

    print(f"  Filtered P1b cycles: {len(cf)}")
    print(f"  SpeedRead range: [{cf['speedread'].min():.1f}, {cf['speedread'].max():.1f}]")

    # Load trades for additional cycle metrics
    # We need to re-run sim to get trade-level data -- but we can derive duration/adds from cycles df
    # cycles df has: gross_pnl_ticks, adds_count, max_position_qty, entry_dt, speedread
    # We need cycle amplitude -- approximate from gross_pnl + we don't have MAE in the saved data

    # Split into tertiles by SpeedRead composite
    cf["sr_tertile"] = pd.qcut(cf["speedread"], 3, labels=["T1(med)", "T2(fast)", "T3(fastest)"])

    print(f"\n--- Regime Tertiles (within retained fast-market cycles) ---")
    print(f"  {'Tertile':<14} {'SR Range':<18} {'Cyc':>5} {'GrPF':>6} {'AvgGr':>7} "
          f"{'Adds':>5} {'MaxPos':>6}")
    print("  " + "-" * 70)

    for t in ["T1(med)", "T2(fast)", "T3(fastest)"]:
        tc = cf[cf["sr_tertile"] == t]
        if len(tc) == 0:
            continue
        gpf = _compute_pf(tc, "gross_pnl_ticks")
        avg_g = tc["gross_pnl_ticks"].mean()
        avg_adds = tc["adds_count"].mean() if "adds_count" in tc.columns else 0
        avg_mp = tc["max_position_qty"].mean() if "max_position_qty" in tc.columns else 0
        sr_lo = tc["speedread"].min()
        sr_hi = tc["speedread"].max()
        print(f"  {t:<14} [{sr_lo:5.1f}-{sr_hi:5.1f}] {len(tc):>5} {gpf:>6.3f} {avg_g:>+7.1f} "
              f"{avg_adds:>5.1f} {avg_mp:>6.1f}")

    # Direction decomposition within tertiles
    if "entry_dir" not in cf.columns:
        # Try to infer from trades -- skip if not available
        print("\n  (Direction decomposition skipped -- entry_dir not in saved data)")
    else:
        print(f"\n--- Direction x Speed Regime ---")
        print(f"  {'Tertile':<14} {'Dir':<6} {'Cyc':>5} {'GrPF':>6}")
        print("  " + "-" * 40)
        for t in ["T1(med)", "T2(fast)", "T3(fastest)"]:
            for d in ["Long", "Short"]:
                tc = cf[(cf["sr_tertile"] == t) & (cf.get("entry_dir", "") == d)]
                if len(tc) == 0:
                    continue
                gpf = _compute_pf(tc, "gross_pnl_ticks")
                print(f"  {t:<14} {d:<6} {len(tc):>5} {gpf:>6.3f}")

    print("\n  Diagnostics complete. Data collected for adaptive-SD investigation.")


# ============================================================
# Adaptive-SD Investigation: Steps D1-D4
# ============================================================

def _run_frc_config(step_dist, period="P1a"):
    """Build and return FRC config for a given step distance."""
    with open(_PARAMS_PATH) as f:
        cfg = json.load(f)
    cfg["hypothesis"]["trigger_mechanism"] = "fixed"
    cfg["hypothesis"]["trigger_params"]["step_dist"] = float(step_dist)
    cfg["martingale"]["max_levels"] = 1
    cfg["martingale"]["max_contract_size"] = 8
    cfg["martingale"]["initial_qty"] = 1
    cfg["martingale"]["max_total_position"] = 0
    cfg["martingale"]["anchor_mode"] = "walking"
    cfg["martingale"]["flatten_reseed_cap"] = 2
    cfg["_instrument"] = {"tick_size": 0.25, "cost_ticks": 1}
    cfg["period"] = period
    cfg["bar_data_primary"] = {
        "bar_data_1tick_rot_P1": cfg["bar_data_primary"]["bar_data_1tick_rot_P1"]
    }
    return cfg


def _run_sim_and_tag(cfg, tick_p1a, sr_ts, sr_vals, label):
    """Run simulator, hour-filter, compute costs, tag with SpeedRead. Returns cycle df."""
    sim = RotationalSimulator(config=cfg, bar_data=tick_p1a, reference_data=None)
    result = sim.run()
    cycles = result.cycles
    trades = result.trades

    if cycles.empty:
        return None

    # Hour filter + costs
    entry_trades = trades[trades["action"].isin(["SEED", "REVERSAL"])]
    ce = entry_trades.groupby("cycle_id").agg(
        entry_dt=("datetime", "first"),
        entry_dir=("direction", "first"),
    ).reset_index()
    cycles = cycles.merge(ce, on="cycle_id", how="left")
    cycles["hour"] = pd.to_datetime(cycles["entry_dt"]).dt.hour
    cf = cycles[~cycles["hour"].isin(EXCLUDE_HOURS)].copy()
    valid_ids = set(cf["cycle_id"])
    tf = trades[trades["cycle_id"].isin(valid_ids)]
    cc1 = tf.groupby("cycle_id")["cost_ticks"].sum()
    cf["cost_1t"] = cf["cycle_id"].map(cc1).fillna(0)
    cf["net_pnl_1t"] = cf["gross_pnl_ticks"] - cf["cost_1t"]

    # Tag with SpeedRead
    entry_ts = pd.to_datetime(cf["entry_dt"]).values.astype("int64") // 10**9
    sr_idx = np.clip(np.searchsorted(sr_ts, entry_ts, side="right") - 1, 0, len(sr_vals) - 1)
    cf["speedread"] = sr_vals[sr_idx]
    cf["label"] = label

    return cf.dropna(subset=["speedread"]).copy()


def stepD1_baselines():
    """Step D1: Baseline diagnostics at SD=10 and SD=15 on P1a."""
    print("=" * 70)
    print("STEP D1: Adaptive-SD Baselines (P1a only)")
    print("=" * 70)

    # Load SpeedRead composite
    sr_path = _OUTPUT_DIR / "speedread_250tick.parquet"
    if not sr_path.exists():
        print("ERROR: SpeedRead composite not found. Run Step 1 first.")
        return False
    sr_df = pd.read_parquet(sr_path)
    sr_ts = pd.to_datetime(sr_df["datetime"]).values.astype("int64") // 10**9
    sr_vals = sr_df["speedread_composite"].values

    # Load P1a tick data
    print("\nLoading P1a tick data...")
    t0 = time.time()
    cfg_25 = _run_frc_config(25)
    tick_bars = load_bars(cfg_25["bar_data_primary"]["bar_data_1tick_rot_P1"])
    tick_p1a = tick_bars[tick_bars["datetime"].dt.date <= _P1_MID].reset_index(drop=True)
    print(f"  P1a ticks: {len(tick_p1a):,} rows in {time.time() - t0:.1f}s")

    all_cycles = {}

    for sd in [10, 15, 25]:
        cfg = _run_frc_config(sd)
        print(f"\nRunning FRC SD={sd} cap=2 on P1a...")
        t1 = time.time()
        cf = _run_sim_and_tag(cfg, tick_p1a, sr_ts, sr_vals, f"SD={sd}")
        elapsed = time.time() - t1
        print(f"  Completed in {elapsed:.1f}s")

        if cf is None or len(cf) == 0:
            print(f"  No cycles for SD={sd}")
            continue

        all_cycles[sd] = cf
        gpf = _compute_pf(cf, "gross_pnl_ticks")
        npf = _compute_pf(cf, "net_pnl_1t")
        net = cf["net_pnl_1t"].sum()
        adds = cf["adds_count"].mean() if "adds_count" in cf.columns else 0

        print(f"  Cycles: {len(cf)}")
        print(f"  Gross PF: {gpf:.4f}")
        print(f"  Net PF @1t: {npf:.4f}")
        print(f"  Net PnL: {net:+,.0f} ticks")
        print(f"  Avg gross/cycle: {cf['gross_pnl_ticks'].mean():+.1f}")
        print(f"  Avg adds/cycle: {adds:.2f}")

    # Summary table
    print(f"\n{'='*70}")
    print(f"  {'Config':<12} {'Cycles':>7} {'GrPF':>6} {'NP@1t':>6} {'NetPnL':>9} {'AvgGr':>7}")
    print(f"  {'-'*52}")
    for sd in [10, 15, 25]:
        if sd not in all_cycles:
            continue
        cf = all_cycles[sd]
        gpf = _compute_pf(cf, "gross_pnl_ticks")
        npf = _compute_pf(cf, "net_pnl_1t")
        print(f"  SD={sd:<8} {len(cf):>7} {gpf:>6.3f} {npf:>6.3f} "
              f"{cf['net_pnl_1t'].sum():>+9,.0f} {cf['gross_pnl_ticks'].mean():>+7.1f}")

    # Kill condition: both SD=10 and SD=15 gross PF < 1.0
    gpf_10 = _compute_pf(all_cycles[10], "gross_pnl_ticks") if 10 in all_cycles else 0
    gpf_15 = _compute_pf(all_cycles[15], "gross_pnl_ticks") if 15 in all_cycles else 0
    print(f"\n--- KILL CONDITION CHECK ---")
    if gpf_10 < 1.0 and gpf_15 < 1.0:
        print(f"  FAIL: Both SD=10 (GrPF={gpf_10:.3f}) and SD=15 (GrPF={gpf_15:.3f}) have gross PF < 1.0")
        print("  Smaller step distances cannot work even in ideal conditions. STOP.")
        # Still save data for diagnostic value
        _OUTPUT_DIR.mkdir(exist_ok=True)
        for sd, cf in all_cycles.items():
            cf.to_parquet(_OUTPUT_DIR / f"cycles_sd{sd}_p1a.parquet", index=False)
        return False
    else:
        print(f"  SD=10 GrPF={gpf_10:.3f}, SD=15 GrPF={gpf_15:.3f}")
        print(f"  At least one has gross PF >= 1.0. Proceeding to Step D2.")

    # Save cycle data
    _OUTPUT_DIR.mkdir(exist_ok=True)
    for sd, cf in all_cycles.items():
        cf.to_parquet(_OUTPUT_DIR / f"cycles_sd{sd}_p1a.parquet", index=False)
    print(f"\nSaved cycle data for SD=10, 15, 25.")

    return True


def stepD2_quintile_diagnostic():
    """Step D2: Speed-quality quintile diagnostic across SD=10, SD=15, SD=25."""
    print("=" * 70)
    print("STEP D2: Speed-Quality Quintile Diagnostic (P1a)")
    print("  Question: Does the speed-quality relationship INVERT at smaller SD?")
    print("=" * 70)

    # Load cycle data for all SDs
    all_data = {}
    for sd in [10, 15, 25]:
        path = _OUTPUT_DIR / f"cycles_sd{sd}_p1a.parquet"
        if not path.exists():
            print(f"ERROR: Missing cycle data for SD={sd}. Run Step D1 first.")
            return False
        all_data[sd] = pd.read_parquet(path)
        print(f"  SD={sd}: {len(all_data[sd])} cycles loaded")

    # Quintile analysis per SD
    # Use SD-specific quintile boundaries (cycle counts differ)
    quintile_results = {}  # {sd: {quintile_label: {gpf, npf, ...}}}

    for sd in [10, 15, 25]:
        cf = all_data[sd]
        cf["quintile"] = pd.qcut(cf["speedread"], 5, labels=["Q1(slow)", "Q2", "Q3", "Q4", "Q5(fast)"])
        quintile_results[sd] = {}

        print(f"\n--- SD={sd} Quintile Breakdown ---")
        print(f"  {'Quintile':<12} {'SR Range':<18} {'Cyc':>5} {'GrPnL':>8} {'GrPF':>6} "
              f"{'AvgGr':>7} {'NP@1t':>6} {'NetPnL':>8}")
        print("  " + "-" * 80)

        for q in ["Q1(slow)", "Q2", "Q3", "Q4", "Q5(fast)"]:
            qc = cf[cf["quintile"] == q]
            if len(qc) == 0:
                continue
            gpf = _compute_pf(qc, "gross_pnl_ticks")
            npf = _compute_pf(qc, "net_pnl_1t")
            sr_lo = qc["speedread"].min()
            sr_hi = qc["speedread"].max()
            avg_g = qc["gross_pnl_ticks"].mean()
            print(f"  {q:<12} [{sr_lo:5.1f}-{sr_hi:5.1f}] {len(qc):>5} "
                  f"{qc['gross_pnl_ticks'].sum():>+8,.0f} {gpf:>6.3f} "
                  f"{avg_g:>+7.1f} {npf:>6.3f} {qc['net_pnl_1t'].sum():>+8,.0f}")
            quintile_results[sd][q] = {"gpf": gpf, "npf": npf, "cycles": len(qc), "avg_g": avg_g}

    # Side-by-side comparison table
    print(f"\n{'='*90}")
    print("  SIDE-BY-SIDE COMPARISON: Gross PF by Quintile")
    print(f"{'='*90}")
    print(f"  {'Quintile':<12} {'SD=10 GrPF':>10} {'SD=10 NP':>8} "
          f"{'SD=15 GrPF':>10} {'SD=15 NP':>8} "
          f"{'SD=25 GrPF':>10} {'SD=25 NP':>8}")
    print("  " + "-" * 70)

    for q in ["Q1(slow)", "Q2", "Q3", "Q4", "Q5(fast)"]:
        row = f"  {q:<12}"
        for sd in [10, 15, 25]:
            d = quintile_results[sd].get(q, {})
            gpf = d.get("gpf", 0)
            npf = d.get("npf", 0)
            row += f" {gpf:>10.3f} {npf:>8.3f}"
        print(row)

    # Inversion check
    print(f"\n--- INVERSION CHECK ---")
    inverted = {}
    for sd in [10, 15]:
        q1 = quintile_results[sd].get("Q1(slow)", {}).get("gpf", 0)
        q5 = quintile_results[sd].get("Q5(fast)", {}).get("gpf", 0)
        is_inverted = q1 > q5 and q1 > 1.0
        inverted[sd] = is_inverted
        direction = "INVERTED (slow > fast)" if is_inverted else "SAME as SD=25 (fast > slow)"
        print(f"  SD={sd}: Q1 GrPF={q1:.3f}, Q5 GrPF={q5:.3f} -> {direction}")

    # SD=25 for reference
    q1_25 = quintile_results[25].get("Q1(slow)", {}).get("gpf", 0)
    q5_25 = quintile_results[25].get("Q5(fast)", {}).get("gpf", 0)
    print(f"  SD=25: Q1 GrPF={q1_25:.3f}, Q5 GrPF={q5_25:.3f} -> CONFIRMED (fast > slow)")

    # Kill condition
    any_inverted = any(inverted.values())
    # Also check: any SD with gross PF > 1.0 in at least one quintile
    any_profitable_quintile = False
    for sd in [10, 15]:
        for q, d in quintile_results[sd].items():
            if d.get("gpf", 0) > 1.0:
                any_profitable_quintile = True
                break

    print(f"\n--- KILL CONDITION ---")
    if not any_inverted:
        print("  FAIL: No inversion found. Speed helps rotation at ALL step distances.")
        print("  SD=25 + SpeedRead>=48 is the terminal config. No regime-switching opportunity.")
        if any_profitable_quintile:
            print("  (Some quintiles are profitable, but the gradient is same-direction as SD=25)")
        return False
    else:
        for sd in [10, 15]:
            if inverted[sd]:
                print(f"  PASS: SD={sd} shows inversion. Regime-switching may be viable.")
        print("  Proceeding to Step D3.")

    return True


def stepD3_efficiency_ratio():
    """Step D3: Efficiency ratio diagnostic within slow-market cycles."""
    print("=" * 70)
    print("STEP D3: Efficiency Ratio Diagnostic (slow-market cycles)")
    print("=" * 70)

    # Load 250-tick bar data for efficiency ratio computation
    print("\nComputing efficiency ratio on 250-tick bars...")
    ohlc = load_bars(_250TICK_PATH)
    # Filter to P1a
    ohlc_p1a = ohlc[ohlc["datetime"].dt.date <= _P1_MID].reset_index(drop=True)
    close = ohlc_p1a["Last"].values.astype(float)

    lookback = 10
    n = len(close)
    eff_ratio = np.full(n, np.nan)

    for i in range(lookback, n):
        net_disp = abs(close[i] - close[i - lookback])
        travel = 0.0
        for j in range(lookback):
            idx = i - j
            travel += abs(close[idx] - close[idx - 1])
        if travel > 0:
            eff_ratio[i] = net_disp / travel
        else:
            eff_ratio[i] = 0.0

    er_valid = eff_ratio[~np.isnan(eff_ratio)]
    print(f"  Bars: {len(ohlc_p1a):,}, valid ER: {len(er_valid):,}")
    print(f"  ER distribution: mean={np.mean(er_valid):.3f}, median={np.median(er_valid):.3f}, "
          f"P10={np.percentile(er_valid, 10):.3f}, P90={np.percentile(er_valid, 90):.3f}")

    # Timestamps for mapping
    er_ts = ohlc_p1a["datetime"].values.astype("int64") // 10**9

    # Find which SD showed strongest inversion in D2
    # Load cycle data and check
    best_inversion_sd = None
    best_inversion_gap = 0
    for sd in [10, 15]:
        path = _OUTPUT_DIR / f"cycles_sd{sd}_p1a.parquet"
        if not path.exists():
            continue
        cf = pd.read_parquet(path)
        cf["quintile"] = pd.qcut(cf["speedread"], 5, labels=["Q1(slow)", "Q2", "Q3", "Q4", "Q5(fast)"])
        q1 = cf[cf["quintile"] == "Q1(slow)"]
        q5 = cf[cf["quintile"] == "Q5(fast)"]
        gpf_q1 = _compute_pf(q1, "gross_pnl_ticks")
        gpf_q5 = _compute_pf(q5, "gross_pnl_ticks")
        gap = gpf_q1 - gpf_q5
        if gap > best_inversion_gap:
            best_inversion_gap = gap
            best_inversion_sd = sd

    if best_inversion_sd is None:
        print("  No inverted SD found. Cannot proceed with efficiency ratio analysis.")
        return False

    print(f"\n  Strongest inversion: SD={best_inversion_sd} (Q1-Q5 gap = {best_inversion_gap:+.3f})")

    # Load that SD's cycle data
    cf = pd.read_parquet(_OUTPUT_DIR / f"cycles_sd{best_inversion_sd}_p1a.parquet")
    cf["quintile"] = pd.qcut(cf["speedread"], 5, labels=["Q1(slow)", "Q2", "Q3", "Q4", "Q5(fast)"])

    # Tag cycles with efficiency ratio
    entry_ts = pd.to_datetime(cf["entry_dt"]).values.astype("int64") // 10**9
    er_idx = np.clip(np.searchsorted(er_ts, entry_ts, side="right") - 1, 0, len(eff_ratio) - 1)
    cf["eff_ratio"] = eff_ratio[er_idx]

    # Focus on Q1 + Q2 (slow-market cycles)
    slow = cf[cf["quintile"].isin(["Q1(slow)", "Q2"])].dropna(subset=["eff_ratio"]).copy()
    print(f"\n  Slow-market cycles (Q1+Q2): {len(slow)}")
    print(f"  ER in slow cycles: mean={slow['eff_ratio'].mean():.3f}, "
          f"median={slow['eff_ratio'].median():.3f}")

    if len(slow) < 30:
        print("  Too few slow-market cycles for meaningful tertile analysis.")
        return False

    # Split into tertiles by efficiency ratio
    slow["er_tertile"] = pd.qcut(slow["eff_ratio"], 3, labels=["T1(choppy)", "T2(mixed)", "T3(trending)"])

    print(f"\n--- Efficiency Ratio Tertiles within Slow-Market Cycles (SD={best_inversion_sd}) ---")
    print(f"  {'Tertile':<14} {'ER Range':<18} {'Cyc':>5} {'GrPF':>6} {'NP@1t':>6} "
          f"{'AvgGr':>7} {'NetPnL':>8}")
    print("  " + "-" * 70)

    for t in ["T1(choppy)", "T2(mixed)", "T3(trending)"]:
        tc = slow[slow["er_tertile"] == t]
        if len(tc) == 0:
            continue
        gpf = _compute_pf(tc, "gross_pnl_ticks")
        npf = _compute_pf(tc, "net_pnl_1t")
        er_lo = tc["eff_ratio"].min()
        er_hi = tc["eff_ratio"].max()
        avg_g = tc["gross_pnl_ticks"].mean()
        print(f"  {t:<14} [{er_lo:.3f}-{er_hi:.3f}] {len(tc):>5} {gpf:>6.3f} {npf:>6.3f} "
              f"{avg_g:>+7.1f} {tc['net_pnl_1t'].sum():>+8,.0f}")

    # Also show the same for fast-market cycles (Q4+Q5) as control
    fast = cf[cf["quintile"].isin(["Q4", "Q5(fast)"])].dropna(subset=["eff_ratio"]).copy()
    if len(fast) >= 30:
        fast["er_tertile"] = pd.qcut(fast["eff_ratio"], 3,
                                      labels=["T1(choppy)", "T2(mixed)", "T3(trending)"],
                                      duplicates="drop")
        print(f"\n--- Control: ER Tertiles within Fast-Market Cycles (SD={best_inversion_sd}) ---")
        print(f"  {'Tertile':<14} {'ER Range':<18} {'Cyc':>5} {'GrPF':>6} {'AvgGr':>7}")
        print("  " + "-" * 55)
        for t in ["T1(choppy)", "T2(mixed)", "T3(trending)"]:
            tc = fast[fast["er_tertile"] == t]
            if len(tc) == 0:
                continue
            gpf = _compute_pf(tc, "gross_pnl_ticks")
            er_lo = tc["eff_ratio"].min()
            er_hi = tc["eff_ratio"].max()
            print(f"  {t:<14} [{er_lo:.3f}-{er_hi:.3f}] {len(tc):>5} {gpf:>6.3f} "
                  f"{tc['gross_pnl_ticks'].mean():>+7.1f}")

    # Kill condition: no ER separation in slow cycles
    t1_gpf = _compute_pf(slow[slow["er_tertile"] == "T1(choppy)"], "gross_pnl_ticks")
    t3_gpf = _compute_pf(slow[slow["er_tertile"] == "T3(trending)"], "gross_pnl_ticks")
    print(f"\n--- EFFICIENCY RATIO KILL CONDITION ---")
    print(f"  T1(choppy) GrPF: {t1_gpf:.3f}")
    print(f"  T3(trending) GrPF: {t3_gpf:.3f}")
    if abs(t1_gpf - t3_gpf) < 0.05:
        print("  FAIL: No meaningful ER separation. Choppy vs trending doesn't matter within slow markets.")
        print("  Regime-switching would rely on speed alone (no directionality axis).")
    else:
        direction = "choppy > trending" if t1_gpf > t3_gpf else "trending > choppy"
        print(f"  Separation found: {direction} (gap = {abs(t1_gpf - t3_gpf):.3f})")

    # Save enriched data
    cf.to_parquet(_OUTPUT_DIR / f"cycles_sd{best_inversion_sd}_er_p1a.parquet", index=False)
    print(f"\nSaved enriched cycle data for SD={best_inversion_sd}.")

    return True


def stepD4_regime_map():
    """Step D4: Synthesize findings into regime map and recommendation."""
    print("=" * 70)
    print("STEP D4: Regime Map and Recommendation")
    print("=" * 70)

    # Load all available cycle data
    all_data = {}
    for sd in [10, 15, 25]:
        path = _OUTPUT_DIR / f"cycles_sd{sd}_p1a.parquet"
        if path.exists():
            all_data[sd] = pd.read_parquet(path)

    if not all_data:
        print("ERROR: No cycle data found. Run earlier steps first.")
        return

    # Build regime map from quintile data
    print("\n--- REGIME MAP (P1a data) ---\n")
    regime_data = {}
    for sd, cf in all_data.items():
        cf["quintile"] = pd.qcut(cf["speedread"], 5, labels=["Q1(slow)", "Q2", "Q3", "Q4", "Q5(fast)"])
        for q in ["Q1(slow)", "Q2", "Q3", "Q4", "Q5(fast)"]:
            qc = cf[cf["quintile"] == q]
            if len(qc) == 0:
                continue
            gpf = _compute_pf(qc, "gross_pnl_ticks")
            npf = _compute_pf(qc, "net_pnl_1t")
            regime_data[(sd, q)] = {"gpf": gpf, "npf": npf, "cycles": len(qc),
                                     "net_pnl": qc["net_pnl_1t"].sum()}

    # Print regime map: for each quintile, which SD is best?
    print(f"  {'Quintile':<12}", end="")
    for sd in sorted(all_data.keys()):
        print(f" {'SD='+str(sd)+' GrPF':>11} {'NP@1t':>7}", end="")
    print(f" {'Best SD':>8}")
    print("  " + "-" * (12 + len(all_data) * 19 + 8))

    best_sd_map = {}
    for q in ["Q1(slow)", "Q2", "Q3", "Q4", "Q5(fast)"]:
        print(f"  {q:<12}", end="")
        best_gpf = 0
        best = None
        for sd in sorted(all_data.keys()):
            d = regime_data.get((sd, q), {})
            gpf = d.get("gpf", 0)
            npf = d.get("npf", 0)
            marker = ""
            if gpf > best_gpf:
                best_gpf = gpf
                best = sd
            print(f" {gpf:>11.3f} {npf:>7.3f}", end="")
        tag = f"SD={best}" if best and best_gpf > 1.0 else "SKIP"
        best_sd_map[q] = (best, best_gpf)
        print(f" {tag:>8}")

    # Compute hypothetical regime-switching portfolio
    print(f"\n--- HYPOTHETICAL REGIME-SWITCHING PORTFOLIO (P1a) ---")
    print("  For each speed quintile, pick the SD with highest gross PF (if > 1.0).\n")

    total_cycles = 0
    total_gross = 0.0
    total_gross_w = 0.0
    total_gross_l = 0.0
    total_net = 0.0
    total_net_w = 0.0
    total_net_l = 0.0
    skipped_quintiles = []

    for q in ["Q1(slow)", "Q2", "Q3", "Q4", "Q5(fast)"]:
        best, best_gpf = best_sd_map[q]
        if best is None or best_gpf <= 1.0:
            skipped_quintiles.append(q)
            continue
        cf = all_data[best]
        cf_q = cf[cf["quintile"] == q] if "quintile" in cf.columns else pd.DataFrame()
        if cf_q.empty:
            cf["quintile"] = pd.qcut(cf["speedread"], 5, labels=["Q1(slow)", "Q2", "Q3", "Q4", "Q5(fast)"])
            cf_q = cf[cf["quintile"] == q]

        n = len(cf_q)
        gw = cf_q[cf_q["gross_pnl_ticks"] > 0]["gross_pnl_ticks"].sum()
        gl = abs(cf_q[cf_q["gross_pnl_ticks"] <= 0]["gross_pnl_ticks"].sum())
        nw = cf_q[cf_q["net_pnl_1t"] > 0]["net_pnl_1t"].sum()
        nl = abs(cf_q[cf_q["net_pnl_1t"] <= 0]["net_pnl_1t"].sum())
        net = cf_q["net_pnl_1t"].sum()

        total_cycles += n
        total_gross_w += gw
        total_gross_l += gl
        total_net_w += nw
        total_net_l += nl
        total_net += net
        print(f"  {q}: SD={best}, {n} cycles, GrPF={best_gpf:.3f}, Net={net:+,.0f}")

    if skipped_quintiles:
        print(f"  Skipped (GrPF<=1.0): {', '.join(skipped_quintiles)}")

    if total_gross_l > 0 and total_net_l > 0:
        combined_gpf = total_gross_w / total_gross_l
        combined_npf = total_net_w / total_net_l
        # Total cycles across all SDs for retention calc
        max_cycles_any_sd = max(len(cf) for cf in all_data.values())
        retention = total_cycles / max_cycles_any_sd if max_cycles_any_sd > 0 else 0
        print(f"\n  Combined: {total_cycles} cycles, GrPF={combined_gpf:.3f}, "
              f"NP@1t={combined_npf:.3f}, Net={total_net:+,.0f}")
        print(f"  Retention vs largest SD: {retention:.1%}")

    # Recommendation
    print(f"\n{'='*70}")
    print("  RECOMMENDATION")
    print(f"{'='*70}")

    # Check if regime-switching adds value over SD=25 + SpeedRead>=48
    validated_npf = 1.117  # Known P1b result
    validated_net = 12653

    if total_net_l > 0:
        combined_npf = total_net_w / total_net_l
        if combined_npf > 1.3 and total_cycles > 800:
            print("  Regime-switching shows promise on P1a.")
            print(f"  Combined NP@1t={combined_npf:.3f} vs validated SD=25 NP@1t={validated_npf:.3f}")
            print(f"  However, this adds parameters (multiple thresholds + SD per regime).")
            print(f"  P1b validation would need a FROZEN regime map with all thresholds pre-specified.")
            print(f"\n  Suggested P1b plan:")
            print(f"  - Freeze the regime map above (quintile boundaries + SD assignments)")
            print(f"  - Run once on P1b with the multi-SD config")
            print(f"  - Pass criteria: NP@1t > 1.0, retention > 50%")
        else:
            print("  Regime-switching does NOT clearly beat validated SD=25 + SpeedRead>=48.")
            print(f"  Combined NP@1t={combined_npf:.3f} on P1a, but with more parameters.")
            print(f"  Validated config (NP@1t={validated_npf:.3f} on P1b) is simpler and proven.")
            print(f"  RECOMMENDATION: Ship SD=25 + SpeedRead>=48. No further SD optimization warranted.")
    else:
        print("  No profitable quintiles found for regime-switching.")
        print(f"  RECOMMENDATION: Ship SD=25 + SpeedRead>=48 as terminal config.")


# ============================================================
# Main
# ============================================================

def main():
    import argparse
    parser = argparse.ArgumentParser(description="SpeedRead filter investigation")
    parser.add_argument("--step", type=str, required=True,
                        choices=["1", "2", "A", "B", "C", "D1", "D2", "D3", "D4"],
                        help="Step to run")
    parser.add_argument("--threshold", type=float, default=None,
                        help="Override frozen threshold for Step B")
    args = parser.parse_args()

    if args.step == "1":
        step1_distribution()
    elif args.step == "2":
        step2_diagnostic()
    elif args.step == "A":
        stepA_optimize()
    elif args.step == "B":
        stepB_validate(threshold=args.threshold)
    elif args.step == "C":
        stepC_diagnostics()
    elif args.step == "D1":
        stepD1_baselines()
    elif args.step == "D2":
        stepD2_quintile_diagnostic()
    elif args.step == "D3":
        stepD3_efficiency_ratio()
    elif args.step == "D4":
        stepD4_regime_map()


if __name__ == "__main__":
    main()
