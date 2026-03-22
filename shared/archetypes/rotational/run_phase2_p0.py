# archetype: rotational
# STATUS: ONE-TIME
# PURPOSE: Phase 2 P0 priority investigations (window, start time, SR block)
# LAST RUN: 2026-03

"""Phase 2 P0: Priority investigations before standard Phase 2.

P0-1: Clock-time rolling window (60 min) vs 200-swing count window
P0-2: Session start 10:00 vs 09:30 (skip Open block)
P0-3: SpeedRead quintile diagnostic broken by block

Usage:
    python run_phase2_p0.py --all         # Run all P0 investigations
    python run_phase2_p0.py --window      # P0-1: clock-time window comparison
    python run_phase2_p0.py --start-time  # P0-2: delayed session start
    python run_phase2_p0.py --sr-block    # P0-3: SpeedRead by block
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
    simulate_daily_flatten, load_data,
    COST_TICKS, TICK_SIZE, RTH_OPEN_TOD, FLATTEN_TOD,
    _P1_START, _P1_END, INIT_QTY,
)
from run_phase1_sweep import (
    build_zigzag_lookup, make_adaptive_lookup, analyze_step2, _OUTPUT_DIR,
    _250TICK_PATH, _CAP, _ML,
)

_P0_DIR = _OUTPUT_DIR / "p0_investigations"


def save_p0(filename, data):
    _P0_DIR.mkdir(parents=True, exist_ok=True)
    path = _P0_DIR / filename
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)
    print(f"  Saved: {path}")


# ---------------------------------------------------------------------------
# P0-1: Clock-time rolling window
# ---------------------------------------------------------------------------

def build_clocktime_zigzag_lookup(window_minutes=60):
    """Build rolling zigzag percentile lookup using a TIME-BASED window.

    Instead of last N swings, uses all swings within the last `window_minutes`
    minutes. This adapts to intraday volatility decay: afternoon gets tighter
    thresholds based on recent afternoon data, not morning data.
    """
    print(f"  Building clock-time ({window_minutes} min) zigzag lookup...")
    df = pd.read_csv(str(_250TICK_PATH))
    df.columns = [c.strip() for c in df.columns]
    df['datetime'] = pd.to_datetime(df['Date'] + ' ' + df['Time'])
    df['date'] = df['datetime'].dt.date

    df = df[(df['date'] >= _P1_START) & (df['date'] <= _P1_END)].copy()
    tod = df['datetime'].dt.hour * 3600 + df['datetime'].dt.minute * 60
    rth_mask = (tod >= RTH_OPEN_TOD) & (tod < FLATTEN_TOD)
    rth = df[rth_mask].copy()

    zz_len = rth['Zig Zag Line Length'].values
    dts_arr = rth['datetime'].values

    # Extract completed swing events
    swings = []
    curr_sign, curr_max, curr_dt = 0, 0.0, None
    for i in range(len(zz_len)):
        v = zz_len[i]
        if v == 0:
            if curr_max > 0:
                swings.append((curr_dt, curr_max))
            curr_max, curr_sign = 0.0, 0
        else:
            s = 1 if v > 0 else -1
            av = abs(v)
            if s != curr_sign:
                if curr_max > 0:
                    swings.append((curr_dt, curr_max))
                curr_sign, curr_max, curr_dt = s, av, dts_arr[i]
            elif av > curr_max:
                curr_max, curr_dt = av, dts_arr[i]
    if curr_max > 0:
        swings.append((curr_dt, curr_max))

    swing_dts = np.array([s[0] for s in swings], dtype='datetime64[ns]')
    swing_lens = np.array([s[1] for s in swings], dtype=np.float64)
    swing_ts_ns = swing_dts.astype('int64')
    print(f"  Total RTH swings: {len(swing_lens):,}")

    window_ns = int(window_minutes * 60 * 1e9)
    pct_levels = [65, 70, 75, 80, 85, 90]
    MIN_SWINGS = 30  # minimum swings in window to compute percentile

    # For each swing, find all swings in [t - window_ns, t)
    pct_ts_list = []
    pct_vals_list = []

    for j in range(len(swing_lens)):
        t = swing_ts_ns[j]
        t_start = t - window_ns

        # Binary search for window start
        left = np.searchsorted(swing_ts_ns[:j], t_start, side='left')
        window = swing_lens[left:j]

        if len(window) < MIN_SWINGS:
            continue

        pct_ts_list.append(t)
        pct_vals_list.append(np.percentile(window, pct_levels))

    pct_ts = np.array(pct_ts_list, dtype='int64')
    pct_vals = np.array(pct_vals_list, dtype=np.float64)
    print(f"  Clock-time percentile points: {len(pct_ts):,} (min {MIN_SWINGS} swings)")

    return {
        'pct_ts': pct_ts, 'pct_vals': pct_vals, 'pct_levels': pct_levels,
        'swing_dts': swing_dts, 'swing_lens': swing_lens,
    }


def make_clocktime_adaptive_lookup(ct_lookup, sd_pct_idx, ad_pct_idx):
    """Create adaptive_lookup from clock-time based percentiles."""
    return {
        'timestamps': ct_lookup['pct_ts'],
        'sd_values': ct_lookup['pct_vals'][:, sd_pct_idx].copy(),
        'ad_values': ct_lookup['pct_vals'][:, ad_pct_idx].copy(),
    }


def run_block_breakdown(sim, label):
    """Compute per-block NPF and EV from simulation results."""
    cycles_df = pd.DataFrame(sim["cycle_records"])
    trades_df = pd.DataFrame(sim["trade_records"])
    if len(cycles_df) == 0:
        return {}

    entry_trades = trades_df[trades_df["action"].isin(["SEED", "REVERSAL"])]
    ce = entry_trades.groupby("cycle_id")["datetime"].first().reset_index()
    ce.columns = ["cycle_id", "entry_dt"]
    cycles_df = cycles_df.merge(ce, on="cycle_id", how="left")
    cycles_df["entry_hour"] = pd.to_datetime(cycles_df["entry_dt"]).dt.hour
    cycles_df["entry_min"] = pd.to_datetime(cycles_df["entry_dt"]).dt.minute
    cf = cycles_df[~cycles_df["entry_hour"].isin({1, 19, 20})].copy()

    valid_ids = set(cf["cycle_id"])
    tf_valid = trades_df[trades_df["cycle_id"].isin(valid_ids)]
    cc = tf_valid.groupby("cycle_id")["cost_ticks"].sum()
    cf["cost"] = cf["cycle_id"].map(cc).fillna(0)
    cf["net_1t"] = cf["gross_pnl_ticks"] - cf["cost"]

    entry_tod = cf["entry_hour"] * 3600 + cf["entry_min"] * 60

    def assign_block(tod):
        if 34200 <= tod < 36000: return "Open"
        elif 36000 <= tod < 41400: return "Morning"
        elif 41400 <= tod < 48600: return "Midday"
        elif 48600 <= tod < 54000: return "Afternoon"
        elif 54000 <= tod < 57600: return "Close"
        return "Other"

    cf["block"] = entry_tod.apply(assign_block)

    blocks = {}
    for b in ["Open", "Morning", "Midday", "Afternoon", "Close"]:
        sub = cf[cf["block"] == b]
        if len(sub) == 0:
            continue
        nw = sub.loc[sub["net_1t"] > 0, "net_1t"].sum()
        nl = abs(sub.loc[sub["net_1t"] <= 0, "net_1t"].sum())
        npf = nw / nl if nl else 0
        blocks[b] = {
            "cycles": len(sub),
            "npf": round(npf, 4),
            "net_pnl": round(float(sub["net_1t"].sum()), 1),
            "ev_per_cycle": round(float(sub["net_1t"].mean()), 1),
            "capwalk_pct": round(float((sub["cycle_cap_walks"] > 0).mean()), 4),
        }
    return blocks


def p0_1_window_comparison():
    """P0-1: Compare 200-swing window vs 60-min clock-time window."""
    print("\n" + "=" * 72)
    print("P0-1: Clock-Time Rolling Window vs 200-Swing Count Window")
    print("=" * 72)

    # Load data
    print("\nLoading tick data...")
    prices, tod_secs, sr_vals, dts = load_data(period='full_p1', use_speedread=False)

    # Build both lookups
    zz_count = build_zigzag_lookup()       # 200-swing count window
    zz_60min = build_clocktime_zigzag_lookup(60)   # 60-min time window
    zz_90min = build_clocktime_zigzag_lookup(90)   # 90-min for comparison

    # P90=idx5, P75=idx2 in both lookups
    configs = [
        ("200-swing (baseline)", zz_count, make_adaptive_lookup, False),
        ("60-min clock-time", zz_60min, make_clocktime_adaptive_lookup, True),
        ("90-min clock-time", zz_90min, make_clocktime_adaptive_lookup, True),
    ]

    results = []
    print(f"\n  {'Window':<24} {'Cycles':>7} {'NPF':>7} {'NetPnL':>9} {'EV/Cyc':>8}")
    print(f"  {'-'*60}")

    for label, lookup, make_fn, is_ct in configs:
        t0 = time.time()
        if is_ct:
            adaptive = make_fn(lookup, 5, 2)  # P90, P75
        else:
            adaptive = make_fn(lookup, 5, 2)

        sim = simulate_daily_flatten(
            prices, tod_secs, sr_vals, dts,
            seed_dist=15.0,
            step_dist=25.0, add_dist=25.0,
            flatten_reseed_cap=2, max_levels=1,
            seed_sr_thresh=-999.0, rev_sr_thresh=-999.0,
            watch_mode='rth_open', cap_action='walk',
            adaptive_lookup=adaptive,
        )
        elapsed = time.time() - t0
        r = analyze_step2(sim, label)
        blocks = run_block_breakdown(sim, label)

        ev_cyc = r["net_pnl"] / r["cycles"] if r and r["cycles"] > 0 else 0
        print(f"  {label:<24} {r['cycles']:>7} {r['npf_1t']:>7.4f} "
              f"{r['net_pnl']:>+9.0f} {ev_cyc:>+8.1f}  ({elapsed:.0f}s)")

        # Show effective SD/AD ranges
        sd_vals = adaptive['sd_values']
        ad_vals = adaptive['ad_values']
        print(f"    SD range: {sd_vals.min():.1f}-{sd_vals.max():.1f} (mean={sd_vals.mean():.1f})")
        print(f"    AD range: {ad_vals.min():.1f}-{ad_vals.max():.1f} (mean={ad_vals.mean():.1f})")

        result_entry = {
            "label": label, "metrics": r, "blocks": blocks,
            "sd_range": {"min": round(float(sd_vals.min()), 2),
                         "max": round(float(sd_vals.max()), 2),
                         "mean": round(float(sd_vals.mean()), 2)},
            "ad_range": {"min": round(float(ad_vals.min()), 2),
                         "max": round(float(ad_vals.max()), 2),
                         "mean": round(float(ad_vals.mean()), 2)},
        }
        results.append(result_entry)

    # Block-level comparison
    print(f"\n--- Block-Level NPF Comparison ---")
    block_names = ["Open", "Morning", "Midday", "Afternoon", "Close"]
    print(f"  {'Block':<12}", end="")
    for r in results:
        print(f" {r['label'][:16]:>16}", end="")
    print()
    print(f"  {'-'*60}")
    for b in block_names:
        print(f"  {b:<12}", end="")
        for r in results:
            bl = r["blocks"].get(b, {})
            npf = bl.get("npf", 0)
            print(f" {npf:>16.4f}", end="")
        print()

    print(f"\n--- Block-Level EV/Cycle Comparison ---")
    print(f"  {'Block':<12}", end="")
    for r in results:
        print(f" {r['label'][:16]:>16}", end="")
    print()
    print(f"  {'-'*60}")
    for b in block_names:
        print(f"  {b:<12}", end="")
        for r in results:
            bl = r["blocks"].get(b, {})
            ev = bl.get("ev_per_cycle", 0)
            print(f" {ev:>+16.1f}", end="")
        print()

    save_p0("p0_1_window_comparison.json", results)
    return results


# ---------------------------------------------------------------------------
# P0-2: Session start time
# ---------------------------------------------------------------------------

def p0_2_start_time():
    """P0-2: Test session start at 10:00 vs 09:30."""
    print("\n" + "=" * 72)
    print("P0-2: Session Start Time (09:30 vs 10:00)")
    print("=" * 72)

    print("\nLoading tick data...")
    prices, tod_secs, sr_vals, dts = load_data(period='full_p1', use_speedread=False)
    zz_lookup = build_zigzag_lookup()
    adaptive = make_adaptive_lookup(zz_lookup, 5, 2)  # P90, P75

    start_times = [
        ("09:30 (baseline)", 9 * 3600 + 30 * 60),
        ("09:45", 9 * 3600 + 45 * 60),
        ("10:00", 10 * 3600),
        ("10:15", 10 * 3600 + 15 * 60),
        ("10:30", 10 * 3600 + 30 * 60),
    ]

    results = []
    print(f"\n  {'Start':<20} {'Cycles':>7} {'NPF':>7} {'NetPnL':>9} {'EV/Cyc':>8} "
          f"{'PnL/Hr':>8} {'WinRate':>7}")
    print(f"  {'-'*70}")

    for label, start_tod in start_times:
        t0 = time.time()
        sim = simulate_daily_flatten(
            prices, tod_secs, sr_vals, dts,
            seed_dist=15.0,
            step_dist=25.0, add_dist=25.0,
            flatten_reseed_cap=2, max_levels=1,
            seed_sr_thresh=-999.0, rev_sr_thresh=-999.0,
            watch_mode='rth_open', cap_action='walk',
            adaptive_lookup=adaptive,
            seed_start_tod=start_tod,
        )
        elapsed = time.time() - t0
        r = analyze_step2(sim, label)
        blocks = run_block_breakdown(sim, label)

        if r is None:
            print(f"  {label:<20}  -- no cycles --")
            continue

        # PnL per clock-hour (trading hours = flatten - start)
        trading_hours = (FLATTEN_TOD - start_tod) / 3600
        total_hours = trading_hours * r["sessions"]
        pnl_per_hr = r["net_pnl"] / total_hours if total_hours > 0 else 0

        ev_cyc = r["net_pnl"] / r["cycles"] if r["cycles"] > 0 else 0
        print(f"  {label:<20} {r['cycles']:>7} {r['npf_1t']:>7.4f} "
              f"{r['net_pnl']:>+9.0f} {ev_cyc:>+8.1f} {pnl_per_hr:>+8.1f} "
              f"{r['session_win_pct']:>7.1%}  ({elapsed:.0f}s)")

        results.append({
            "label": label, "start_tod": start_tod,
            "trading_hours_per_session": trading_hours,
            "pnl_per_hour": round(pnl_per_hr, 2),
            "metrics": r, "blocks": blocks,
        })

    # Block comparison for 09:30 vs 10:00
    if len(results) >= 2:
        print(f"\n--- Block NPF: 09:30 vs 10:00 ---")
        r930 = results[0]
        r1000 = [r for r in results if r["start_tod"] == 10 * 3600]
        if r1000:
            r1000 = r1000[0]
            for b in ["Open", "Morning", "Midday", "Afternoon", "Close"]:
                b930 = r930["blocks"].get(b, {})
                b1000 = r1000["blocks"].get(b, {})
                n930 = b930.get("npf", 0)
                n1000 = b1000.get("npf", 0)
                c930 = b930.get("cycles", 0)
                c1000 = b1000.get("cycles", 0)
                print(f"  {b:<12} 09:30: NPF={n930:.4f} ({c930} cyc)  "
                      f"10:00: NPF={n1000:.4f} ({c1000} cyc)")

    save_p0("p0_2_start_time.json", results)
    return results


# ---------------------------------------------------------------------------
# P0-3: SpeedRead quintile diagnostic by block
# ---------------------------------------------------------------------------

def p0_3_sr_block_diagnostic():
    """P0-3: SpeedRead quintile analysis broken down by block."""
    print("\n" + "=" * 72)
    print("P0-3: SpeedRead Quintile Diagnostic by Block")
    print("=" * 72)

    # Load data WITH SpeedRead
    print("\nLoading tick data with SpeedRead...")
    prices, tod_secs, sr_vals, dts = load_data(period='full_p1', use_speedread=True)
    zz_lookup = build_zigzag_lookup()
    adaptive = make_adaptive_lookup(zz_lookup, 5, 2)

    # Run simulation with NO SR filter to get all cycles + their SR values
    sim = simulate_daily_flatten(
        prices, tod_secs, sr_vals, dts,
        seed_dist=15.0,
        step_dist=25.0, add_dist=25.0,
        flatten_reseed_cap=2, max_levels=1,
        seed_sr_thresh=-999.0, rev_sr_thresh=-999.0,  # accept all
        watch_mode='rth_open', cap_action='walk',
        adaptive_lookup=adaptive,
    )

    cycles_df = pd.DataFrame(sim["cycle_records"])
    trades_df = pd.DataFrame(sim["trade_records"])

    if len(cycles_df) == 0:
        print("  No cycles!")
        return None

    # Get entry SR value for each cycle
    entry_trades = trades_df[trades_df["action"].isin(["SEED", "REVERSAL"])].copy()
    # Map each entry to its SR value via bar_idx
    entry_sr = entry_trades.groupby("cycle_id").first()[["datetime", "bar_idx"]].reset_index()
    entry_sr.columns = ["cycle_id", "entry_dt", "entry_bar_idx"]

    # Get SR value at entry bar
    sr_at_entry = []
    for _, row in entry_sr.iterrows():
        idx = int(row["entry_bar_idx"])
        sr_at_entry.append(sr_vals[idx] if idx < len(sr_vals) else -1)
    entry_sr["entry_sr"] = sr_at_entry

    cycles_df = cycles_df.merge(entry_sr[["cycle_id", "entry_dt", "entry_sr"]], on="cycle_id", how="left")
    cycles_df["entry_hour"] = pd.to_datetime(cycles_df["entry_dt"]).dt.hour
    cycles_df["entry_min"] = pd.to_datetime(cycles_df["entry_dt"]).dt.minute

    # Filter valid cycles
    cf = cycles_df[~cycles_df["entry_hour"].isin({1, 19, 20})].copy()
    valid_ids = set(cf["cycle_id"])
    tf_valid = trades_df[trades_df["cycle_id"].isin(valid_ids)]
    cc = tf_valid.groupby("cycle_id")["cost_ticks"].sum()
    cf["cost"] = cf["cycle_id"].map(cc).fillna(0)
    cf["net_1t"] = cf["gross_pnl_ticks"] - cf["cost"]

    # Assign blocks
    entry_tod = cf["entry_hour"] * 3600 + cf["entry_min"] * 60
    def assign_block(tod):
        if 34200 <= tod < 36000: return "Open"
        elif 36000 <= tod < 41400: return "Morning"
        elif 41400 <= tod < 48600: return "Midday"
        elif 48600 <= tod < 54000: return "Afternoon"
        elif 54000 <= tod < 57600: return "Close"
        return "Other"
    cf["block"] = entry_tod.apply(assign_block)

    # SR quintiles (overall)
    cf["sr_quintile"] = pd.qcut(cf["entry_sr"], 5, labels=["Q1(low)", "Q2", "Q3", "Q4", "Q5(high)"],
                                duplicates='drop')

    # Overall SR quintile summary
    print(f"\n--- Overall SR Quintile Summary ---")
    print(f"  {'Quintile':<12} {'SR Range':>14} {'Cycles':>7} {'NPF':>7} {'EV/Cyc':>8} {'CapWk%':>7}")
    print(f"  {'-'*60}")
    for q in cf["sr_quintile"].cat.categories:
        sub = cf[cf["sr_quintile"] == q]
        if len(sub) == 0:
            continue
        sr_min = sub["entry_sr"].min()
        sr_max = sub["entry_sr"].max()
        nw = sub.loc[sub["net_1t"] > 0, "net_1t"].sum()
        nl = abs(sub.loc[sub["net_1t"] <= 0, "net_1t"].sum())
        npf = nw / nl if nl else 0
        ev = sub["net_1t"].mean()
        cw = (sub["cycle_cap_walks"] > 0).mean()
        print(f"  {str(q):<12} {sr_min:>6.1f}-{sr_max:>6.1f} {len(sub):>7} "
              f"{npf:>7.4f} {ev:>+8.1f} {cw:>7.1%}")

    # Per-block SR quintile breakdown
    results = {}
    block_names = ["Open", "Morning", "Midday", "Afternoon", "Close"]
    for b in block_names:
        bsub = cf[cf["block"] == b]
        if len(bsub) < 20:
            continue

        # Block-specific quintiles
        try:
            bsub = bsub.copy()
            bsub["block_sr_q"] = pd.qcut(bsub["entry_sr"], 5,
                                          labels=["Q1(low)", "Q2", "Q3", "Q4", "Q5(high)"],
                                          duplicates='drop')
        except ValueError:
            continue

        print(f"\n--- {b} Block: SR Quintile Breakdown ---")
        print(f"  {'Quintile':<12} {'SR Range':>14} {'Cycles':>7} {'NPF':>7} {'EV/Cyc':>8} {'CapWk%':>7}")
        print(f"  {'-'*60}")

        block_data = []
        for q in bsub["block_sr_q"].cat.categories:
            sub = bsub[bsub["block_sr_q"] == q]
            if len(sub) == 0:
                continue
            sr_min = sub["entry_sr"].min()
            sr_max = sub["entry_sr"].max()
            nw = sub.loc[sub["net_1t"] > 0, "net_1t"].sum()
            nl = abs(sub.loc[sub["net_1t"] <= 0, "net_1t"].sum())
            npf = nw / nl if nl else 0
            ev = sub["net_1t"].mean()
            cw = (sub["cycle_cap_walks"] > 0).mean()
            print(f"  {str(q):<12} {sr_min:>6.1f}-{sr_max:>6.1f} {len(sub):>7} "
                  f"{npf:>7.4f} {ev:>+8.1f} {cw:>7.1%}")
            block_data.append({
                "quintile": str(q), "sr_range": f"{sr_min:.1f}-{sr_max:.1f}",
                "cycles": len(sub), "npf": round(npf, 4),
                "ev_per_cycle": round(float(ev), 1),
                "capwalk_pct": round(float(cw), 4),
            })
        results[b] = block_data

    # Gradient analysis
    print(f"\n--- SR Gradient by Block (Q5 NPF - Q1 NPF) ---")
    for b in block_names:
        if b not in results or len(results[b]) < 2:
            continue
        q1_npf = results[b][0]["npf"]
        q5_npf = results[b][-1]["npf"]
        gradient = q5_npf - q1_npf
        direction = "HIGH SR better" if gradient > 0 else "LOW SR better"
        print(f"  {b:<12} Q1={q1_npf:.4f}  Q5={q5_npf:.4f}  gradient={gradient:+.4f}  ({direction})")

    save_p0("p0_3_sr_block_diagnostic.json", results)
    return results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Phase 2 P0 Investigations")
    parser.add_argument("--all", action="store_true", help="Run all P0 investigations")
    parser.add_argument("--window", action="store_true", help="P0-1: clock-time window")
    parser.add_argument("--start-time", action="store_true", help="P0-2: delayed start")
    parser.add_argument("--sr-block", action="store_true", help="P0-3: SR by block")
    args = parser.parse_args()

    if args.all or args.window:
        p0_1_window_comparison()
    if args.all or args.start_time:
        p0_2_start_time()
    if args.all or args.sr_block:
        p0_3_sr_block_diagnostic()

    if not any([args.all, args.window, args.start_time, args.sr_block]):
        print("No action. Use --all, --window, --start-time, or --sr-block.")


if __name__ == "__main__":
    main()
