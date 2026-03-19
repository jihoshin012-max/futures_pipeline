# archetype: rotational
"""Phase 1: Base Parameter Calibration.

Step 1:  Simulator enhancement verification (AddDist decoupling, session window, cap-walk).
Step 1b: Zigzag sensitivity check (4.0, 5.25, 7.0 pt reversals).

Usage:
    python run_phase1_base.py --verify      # V1.1 baseline match (P1a, SR, flatten_reseed)
    python run_phase1_base.py --baseline    # Full P1 baseline, no SR, cap_action=walk
    python run_phase1_base.py --zigzag      # Step 1b: zigzag sensitivity check
"""

import sys
import json
import time
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

_REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from run_seed_investigation import (
    simulate_daily_flatten, analyze, load_data, _save_result, _load_result,
    STEP_DIST, FLATTEN_CAP, MAX_LEVELS, COST_TICKS, TICK_SIZE, INIT_QTY,
    RTH_OPEN_TOD, FLATTEN_TOD,
    _P1_START, _P1_END,
)

_250TICK_PATH = _REPO / "stages/01-data/data/bar_data/tick/NQ_BarData_250tick_rot_P1.csv"

_OUTPUT_DIR = Path(__file__).parent / "phase1_results"


def save_phase1(filename, data):
    """Save Phase 1 result to JSON."""
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = _OUTPUT_DIR / filename
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)
    print(f"  Saved: {path}")


def load_phase1(filename):
    """Load Phase 1 result from JSON."""
    path = _OUTPUT_DIR / filename
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Step 1 Verification: V1.1 baseline match
# ---------------------------------------------------------------------------

def verify_v11_baseline():
    """Run SD=25/AD=25 with V1.1 settings and compare to stored baseline.

    V1.1 settings: P1a, SpeedRead enabled (SR>=48), cap_action='flatten_reseed',
    SD=25, AD=25 (coupled), ML=1, cap=2, session=09:30-16:00.
    """
    print("\n" + "=" * 70)
    print("PHASE 1 STEP 1: V1.1 Baseline Verification")
    print("  SD=25, AD=25, ML=1, cap=2, SR>=48, cap_action=flatten_reseed")
    print("  Period: P1a (to match stored baseline)")
    print("=" * 70)

    # Load P1a data with SpeedRead (same as V1.1)
    prices, tod_secs, sr_vals, dts = load_data(period='p1a', use_speedread=True)

    t0 = time.time()
    sim = simulate_daily_flatten(
        prices, tod_secs, sr_vals, dts,
        seed_dist=25.0,
        step_dist=25.0,
        add_dist=25.0,        # coupled: AD = SD
        flatten_reseed_cap=2,
        max_levels=1,
        seed_sr_thresh=48.0,
        rev_sr_thresh=48.0,
        watch_mode='current',
        reset_on_reversal=False,
        cost_ticks=1,
        session_window_end=None,  # full RTH
        cap_action='flatten_reseed',  # V1.1 compat
    )
    elapsed = time.time() - t0
    print(f"  Simulation: {elapsed:.1f}s")

    r = analyze(sim, "V1.1 verify: SD=25/AD=25/ML=1/cap=2/SR>=48")
    if r is None:
        print("  ERROR: No valid cycles.")
        return False

    # Load stored V1.1 baseline for comparison
    v11 = _load_result("step1_baseline.json")

    print(f"\n--- Verification Results ---")
    print(f"  {'Metric':<25} {'V1.1 Baseline':>15} {'New Simulator':>15} {'Match':>8}")
    print(f"  {'-'*63}")

    checks = []
    if v11:
        for key, label in [("cycles", "Cycles"), ("gpf", "Gross PF"),
                           ("npf_1t", "Net PF @1t"), ("net_pnl", "Net PnL"),
                           ("sessions", "Sessions"),
                           ("mean_daily", "Mean Daily PnL"),
                           ("session_win_pct", "Session Win %"),
                           ("seed_accuracy", "Seed Accuracy")]:
            old = v11.get(key, "N/A")
            new = r.get(key, "N/A")
            if isinstance(old, (int, float)) and isinstance(new, (int, float)):
                match = "OK" if abs(old - new) < 0.01 else "DIFF"
            else:
                match = "OK" if old == new else "DIFF"
            checks.append(match)
            print(f"  {label:<25} {str(old):>15} {str(new):>15} {match:>8}")
    else:
        print("  WARNING: No stored V1.1 baseline found. Showing new results only.")
        for key, label in [("cycles", "Cycles"), ("gpf", "Gross PF"),
                           ("npf_1t", "Net PF @1t"), ("net_pnl", "Net PnL"),
                           ("sessions", "Sessions"),
                           ("mean_daily", "Mean Daily PnL"),
                           ("session_win_pct", "Session Win %"),
                           ("seed_accuracy", "Seed Accuracy")]:
            print(f"  {label:<25} {'N/A':>15} {str(r.get(key, 'N/A')):>15}")

    print(f"\n  Cap walks: {sim['cap_walks']}")

    all_ok = all(c == "OK" for c in checks) if checks else False
    if all_ok:
        print(f"\n  PASS: New simulator exactly matches V1.1 baseline.")
    elif checks:
        n_diff = sum(1 for c in checks if c == "DIFF")
        print(f"\n  WARNING: {n_diff} metric(s) differ from V1.1 baseline.")
        print(f"  Review differences above. Small diffs may be acceptable.")

    save_phase1("step1_v11_verify.json", r)
    return r


# ---------------------------------------------------------------------------
# Step 1 Baseline: Full P1, no SR, cap_action=walk
# ---------------------------------------------------------------------------

def establish_full_p1_baseline():
    """Run SD=25/AD=25 on full P1 with Phase 1 settings (no SR, cap_action=walk).

    This establishes the comparison baseline for all Phase 1 sweeps.
    """
    print("\n" + "=" * 70)
    print("PHASE 1 STEP 1: Full P1 Baseline (Phase 1 Settings)")
    print("  SD=25, AD=25, ML=1, cap=2, NO SpeedRead, cap_action=walk")
    print("  Period: Full P1 (Sep 21 - Dec 14)")
    print("=" * 70)

    # Load full P1 data WITHOUT SpeedRead
    prices, tod_secs, sr_vals, dts = load_data(period='full_p1', use_speedread=False)

    t0 = time.time()
    sim = simulate_daily_flatten(
        prices, tod_secs, sr_vals, dts,
        seed_dist=25.0,
        step_dist=25.0,
        add_dist=25.0,
        flatten_reseed_cap=2,
        max_levels=1,
        seed_sr_thresh=-999.0,   # disabled (all pass)
        rev_sr_thresh=-999.0,    # disabled (all pass)
        watch_mode='rth_open',   # watch price at 09:30 ET (user constraint)
        reset_on_reversal=False,
        cost_ticks=1,
        session_window_end=None,  # full RTH
        cap_action='walk',        # Phase 1 behavior
    )
    elapsed = time.time() - t0
    print(f"  Simulation: {elapsed:.1f}s")

    r = analyze(sim, "Full-P1 baseline: SD=25/AD=25/ML=1/cap=2/noSR/walk")
    if r is None:
        print("  ERROR: No valid cycles.")
        return False

    print(f"\n--- Full P1 Baseline Results ---")
    print(f"  Total completed cycles: {r['cycles']}")
    print(f"  Gross PF:               {r['gpf']:.4f}")
    print(f"  Net PF @1t:             {r['npf_1t']:.4f}")
    print(f"  Net PnL (ticks):        {r['net_pnl']:+,}")
    print(f"  Trading sessions:       {r['sessions']}")
    print(f"  Mean cycles/session:    {r['cycles_per_session']:.1f}")
    print(f"  Mean net PnL/session:   {r['mean_daily']:+.1f}")
    print(f"  StdDev daily PnL:       {r['std_daily']:.1f}")
    print(f"  Session win rate:       {r['session_win_pct']:.1%}")
    print(f"  Seed accuracy:          {r['seed_accuracy']:.1%}")
    print(f"  Cap walks:              {sim['cap_walks']}")

    print(f"\n  Per-session PnL distribution:")
    print(f"    P10:    {r['p10']:+.1f}")
    print(f"    P25:    {r['p25']:+.1f}")
    print(f"    Median: {r['p50']:+.1f}")
    print(f"    P75:    {r['p75']:+.1f}")
    print(f"    P90:    {r['p90']:+.1f}")

    print(f"\n  Worst 5 sessions:")
    for sid, pnl in r["worst5"].items():
        print(f"    Session {sid}: {pnl:+.1f} ticks")

    # Positive EV check
    if r['npf_1t'] < 1.0:
        print(f"\n  WARNING: Net PF {r['npf_1t']:.4f} < 1.0 at baseline.")
        print(f"  Base economics negative at SD=25/AD=25. This is expected —")
        print(f"  Phase 1 sweep targets lower SD/AD combos for positive EV.")
    else:
        print(f"\n  Baseline shows positive EV (NPF={r['npf_1t']:.4f}).")

    save_phase1("step1_full_p1_baseline.json", r)
    return r


# ---------------------------------------------------------------------------
# Session window quick test
# ---------------------------------------------------------------------------

def test_session_window():
    """Quick verification that session_window_end parameter works correctly."""
    print("\n" + "=" * 70)
    print("SESSION WINDOW VERIFICATION")
    print("=" * 70)

    prices, tod_secs, sr_vals, dts = load_data(period='p1a', use_speedread=False)

    windows = [
        ("09:30-11:30", 11 * 3600 + 30 * 60),
        ("09:30-13:30", 13 * 3600 + 30 * 60),
        ("09:30-16:00 (full)", None),
    ]

    print(f"\n  {'Window':<20} {'Cycles':>7} {'NPF':>7} {'NetPnL':>9} {'Cyc/Hr':>7}")
    print(f"  {'-'*55}")

    for label, window_end in windows:
        sim = simulate_daily_flatten(
            prices, tod_secs, sr_vals, dts,
            seed_dist=25.0, step_dist=25.0, add_dist=25.0,
            flatten_reseed_cap=2, max_levels=1,
            seed_sr_thresh=-999.0, rev_sr_thresh=-999.0,
            watch_mode='rth_open',
            session_window_end=window_end,
            cap_action='walk',
        )
        r = analyze(sim, label)
        if r is None:
            print(f"  {label:<20} — no cycles —")
            continue

        # Compute hours per session for cycles/hour
        if window_end:
            hours_per_session = (window_end - RTH_OPEN_TOD) / 3600
        else:
            hours_per_session = (FLATTEN_TOD - RTH_OPEN_TOD) / 3600
        total_hours = hours_per_session * r['sessions']
        cyc_per_hr = r['cycles'] / total_hours if total_hours > 0 else 0

        print(f"  {label:<20} {r['cycles']:>7} {r['npf_1t']:>7.4f} "
              f"{r['net_pnl']:>+9,} {cyc_per_hr:>7.1f}")

    print(f"\n  If cycle counts decrease with narrower windows, session_window_end works.")


# ---------------------------------------------------------------------------
# Step 1b: Zigzag Sensitivity Check
# ---------------------------------------------------------------------------

def compute_zigzag_swings_hl(highs, lows, reversal_pts):
    """Compute zigzag swing lengths from bar high/low arrays.

    Uses elif guard to prevent same-bar extend+reverse.
    Returns array of completed swing lengths (absolute points).

    NOTE: For Step 2 adaptive configs, use the CSV "Zig Zag Line Length"
    column (abs, both directions) instead of this function. The CSV
    matches Sierra Chart's HL-based zigzag with intra-bar detection.
    """
    n = len(highs)
    if n < 2:
        return np.array([])

    swings = []
    current_high = highs[0]
    current_low = lows[0]
    direction = 0  # 0=undetermined, 1=up, -1=down

    for i in range(1, n):
        h = highs[i]
        l = lows[i]

        if direction == 0:
            if h > current_high:
                current_high = h
            if l < current_low:
                current_low = l
            if current_high - current_low >= reversal_pts:
                if h >= current_high:
                    direction = 1
                    swing_start = current_low
                else:
                    direction = -1
                    swing_start = current_high

        elif direction == 1:
            if h > current_high:
                current_high = h
            elif current_high - l >= reversal_pts:
                swings.append(current_high - swing_start)
                direction = -1
                swing_start = current_high
                current_low = l

        elif direction == -1:
            if l < current_low:
                current_low = l
            elif h - current_low >= reversal_pts:
                swings.append(swing_start - current_low)
                direction = 1
                swing_start = current_low
                current_high = h

    return np.array(swings)


def load_250tick_rth_p1():
    """Load 250-tick bars, filter to P1 dates and RTH hours only."""
    print("  Loading 250-tick bars...")
    df = pd.read_csv(str(_250TICK_PATH))
    # Strip whitespace from column names
    df.columns = [c.strip() for c in df.columns]

    # Parse datetime
    df["datetime"] = pd.to_datetime(df["Date"] + " " + df["Time"])
    df["date"] = df["datetime"].dt.date

    # Filter to P1 dates
    df = df[(df["date"] >= _P1_START) & (df["date"] <= _P1_END)].copy()
    print(f"  P1 bars: {len(df):,}")

    # Filter to RTH (09:30-16:00 ET)
    tod = df["datetime"].dt.hour * 3600 + df["datetime"].dt.minute * 60
    rth_mask = (tod >= RTH_OPEN_TOD) & (tod < FLATTEN_TOD)
    df_rth = df[rth_mask].copy()
    print(f"  RTH bars: {len(df_rth):,}")

    return df_rth


def step1b_zigzag_sensitivity():
    """Step 1b: Zigzag sensitivity check.

    Compute RTH P50, P75, P85, P90, P95 using three zigzag reversal settings.
    Pass: P85 and P90 shift <= 15% across settings.
    Kill: P85/P90 shift > 15%.
    """
    print("\n" + "=" * 70)
    print("PHASE 1 STEP 1b: Zigzag Sensitivity Check")
    print("  Reversal settings: 4.0, 5.25, 7.0 points")
    print("  Data: 250-tick bars, P1 dates, RTH only")
    print("=" * 70)

    df_rth = load_250tick_rth_p1()

    highs = df_rth["High"].values.astype(np.float64)
    lows = df_rth["Low"].values.astype(np.float64)

    reversal_settings = [4.0, 5.25, 7.0]
    percentiles = [50, 75, 85, 90, 95]
    results = {}

    print(f"\n  {'Reversal':>8}  {'Swings':>7}  {'P50':>7}  {'P75':>7}  {'P85':>7}  {'P90':>7}  {'P95':>7}")
    print(f"  {'-'*60}")

    for rev in reversal_settings:
        swings = compute_zigzag_swings_hl(highs, lows, rev)
        if len(swings) == 0:
            print(f"  {rev:>8.2f}  — no swings —")
            continue

        pcts = np.percentile(swings, percentiles)
        results[rev] = {
            "n_swings": len(swings),
            "percentiles": {f"P{p}": round(v, 2) for p, v in zip(percentiles, pcts)},
            "mean": round(float(swings.mean()), 2),
            "median": round(float(np.median(swings)), 2),
        }

        print(f"  {rev:>8.2f}  {len(swings):>7,}  "
              + "  ".join(f"{v:>7.2f}" for v in pcts))

    # Also show pre-computed 5.25 from CSV for cross-validation
    if "Zig Zag Line Length" in df_rth.columns:
        csv_zz = df_rth["Zig Zag Line Length"].dropna()
        csv_zz = csv_zz[csv_zz > 0]
        if len(csv_zz) > 0:
            csv_pcts = np.percentile(csv_zz, percentiles)
            print(f"\n  CSV 5.25  {len(csv_zz):>7,}  "
                  + "  ".join(f"{v:>7.2f}" for v in csv_pcts))
            print(f"  (Pre-computed zigzag from CSV for cross-validation)")

    # --- Pass/Kill evaluation ---
    if len(results) < 2:
        print("\n  ERROR: Not enough valid reversal settings to evaluate.")
        return False

    print(f"\n--- Sensitivity Analysis ---")

    # Compute shift for P85 and P90
    rev_keys = sorted(results.keys())
    for pct_label in ["P85", "P90"]:
        vals = [results[r]["percentiles"][pct_label] for r in rev_keys]
        min_val = min(vals)
        max_val = max(vals)
        shift_pct = ((max_val - min_val) / min_val * 100) if min_val > 0 else 0

        print(f"  {pct_label}: min={min_val:.2f}, max={max_val:.2f}, "
              f"shift={shift_pct:.1f}%", end="")
        if shift_pct <= 15:
            print(f"  PASS (≤15%)")
        else:
            print(f"  FAIL (>15%)")

    p85_vals = [results[r]["percentiles"]["P85"] for r in rev_keys]
    p90_vals = [results[r]["percentiles"]["P90"] for r in rev_keys]
    p85_shift = (max(p85_vals) - min(p85_vals)) / min(p85_vals) * 100 if min(p85_vals) > 0 else 999
    p90_shift = (max(p90_vals) - min(p90_vals)) / min(p90_vals) * 100 if min(p90_vals) > 0 else 999

    passed = p85_shift <= 15 and p90_shift <= 15

    if passed:
        print(f"\n  PASS: 5.25 pt zigzag is robust. Percentile framework validated.")
        print(f"  Proceed with adaptive configs in Step 2.")
    else:
        print(f"\n  *** KILL CONDITION: P85/P90 shift > 15% ***")
        print(f"  Zigzag reversal is itself a fragile parameter.")
        print(f"  Run FIXED configs ONLY in Step 2 (no adaptive).")

    # Save results
    save_data = {
        "reversal_settings": reversal_settings,
        "results": {str(k): v for k, v in results.items()},
        "p85_shift_pct": round(p85_shift, 2),
        "p90_shift_pct": round(p90_shift, 2),
        "passed": passed,
    }
    save_phase1("step1b_zigzag_sensitivity.json", save_data)

    # Sanity check against spec expectations
    if 5.25 in results:
        p85 = results[5.25]["percentiles"]["P85"]
        p90 = results[5.25]["percentiles"]["P90"]
        med = results[5.25]["percentiles"]["P50"]
        print(f"\n  Sanity check (5.25 pt reversal):")
        print(f"    Median: {med:.2f} (expected ~11.0)")
        print(f"    P85:    {p85:.2f} (expected ~19.5)")
        print(f"    P90:    {p90:.2f} (expected ~22.25)")

    return passed


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Phase 1 Base Parameter Calibration")
    parser.add_argument("--verify", action="store_true",
                        help="Verify V1.1 baseline match (P1a, SR, flatten_reseed)")
    parser.add_argument("--baseline", action="store_true",
                        help="Establish full-P1 baseline (no SR, cap_action=walk)")
    parser.add_argument("--test-window", action="store_true",
                        help="Quick test session_window_end parameter")
    parser.add_argument("--zigzag", action="store_true",
                        help="Step 1b: zigzag sensitivity check")
    parser.add_argument("--all", action="store_true",
                        help="Run all Step 1 + 1b checks")
    args = parser.parse_args()

    if args.all or args.verify:
        verify_v11_baseline()
    if args.all or args.baseline:
        establish_full_p1_baseline()
    if args.all or args.test_window:
        test_session_window()
    if args.all or args.zigzag:
        step1b_zigzag_sensitivity()

    if not any([args.verify, args.baseline, args.test_window, args.zigzag, args.all]):
        print("No action specified. Use --verify, --baseline, --test-window, --zigzag, or --all.")
        parser.print_help()


if __name__ == "__main__":
    main()
