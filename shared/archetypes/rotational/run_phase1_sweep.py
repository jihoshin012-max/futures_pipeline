# archetype: rotational
"""Phase 1 Step 2: StepDist x AddDist Sweep (Fixed AND Adaptive).

Runs 30 fixed configs + 9 adaptive configs on full P1, no SpeedRead,
cap_action=walk, ML=1, cap=2, session=09:30-16:00, cost_ticks=1.

Adaptive configs use rolling 200-swing zigzag percentiles from the
CSV "Zig Zag Line Length" column (abs, both directions) — matches
Sierra Chart and live C++ implementation.

Usage:
    python run_phase1_sweep.py                # Run full sweep
    python run_phase1_sweep.py --fixed-only   # Fixed configs only
    python run_phase1_sweep.py --adaptive-only # Adaptive configs only
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

_OUTPUT_DIR = Path(__file__).parent / "phase1_results"
_250TICK_PATH = _REPO / "stages/01-data/data/bar_data/tick/NQ_BarData_250tick_rot_P1.csv"

# Step 2 shared settings
_ML = 1          # max_levels
_CAP = 2         # flatten_reseed_cap
_COST = 1        # cost_ticks
_WINDOW = "full"  # 09:30-16:00 (session_window_end=None)


# ---------------------------------------------------------------------------
# Rolling zigzag percentile lookup from CSV
# ---------------------------------------------------------------------------

def build_zigzag_lookup():
    """Build rolling 200-swing zigzag percentile lookup from CSV.

    Returns dict with:
      - swing_dts: datetime array of swing completions
      - swing_lens: float array of swing lengths
      - pct_ts: int64 ns timestamps for percentile lookup
      - pct_vals: 2D array (n_points x n_percentiles)
      - pct_levels: list of percentile levels
    """
    print("  Building rolling zigzag percentile lookup from CSV...")
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

    # Extract completed swing events with timestamps
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

    swing_dts = np.array([s[0] for s in swings])
    swing_lens = np.array([s[1] for s in swings], dtype=np.float64)
    print(f"  Total RTH zigzag swings: {len(swing_lens):,}")

    # Rolling 200-swing percentiles
    WINDOW = 200
    pct_levels = [65, 70, 75, 80, 85, 90]
    start_idx = WINDOW
    n_pts = len(swing_lens) - start_idx

    pct_ts = np.empty(n_pts, dtype='int64')
    pct_vals = np.empty((n_pts, len(pct_levels)), dtype=np.float64)

    for j in range(n_pts):
        idx = start_idx + j
        window = swing_lens[idx - WINDOW:idx]
        pct_ts[j] = swing_dts[idx].astype('int64')
        pct_vals[j] = np.percentile(window, pct_levels)

    print(f"  Rolling percentile points: {n_pts:,}")
    return {
        'swing_dts': swing_dts, 'swing_lens': swing_lens,
        'pct_ts': pct_ts, 'pct_vals': pct_vals, 'pct_levels': pct_levels,
    }


def make_adaptive_lookup(zz_lookup, sd_pct_idx, ad_pct_idx):
    """Create adaptive_lookup dict for a specific SD/AD percentile combo.

    Args:
        zz_lookup: output of build_zigzag_lookup()
        sd_pct_idx: index into pct_levels for StepDist (e.g., 3 for P80)
        ad_pct_idx: index into pct_levels for AddDist (e.g., 0 for P65)
    """
    return {
        'timestamps': zz_lookup['pct_ts'],
        'sd_values': zz_lookup['pct_vals'][:, sd_pct_idx].copy(),
        'ad_values': zz_lookup['pct_vals'][:, ad_pct_idx].copy(),
    }


def make_std_lookup(zz_lookup):
    """Create std_lookup dict from the same 200-swing zigzag buffer.

    Returns dict with 'timestamps' (int64 ns) and 'std_values' (float64).
    Same timestamps as adaptive_lookup — both use pct_ts from rolling windows.
    """
    swing_lens = zz_lookup['swing_lens']
    swing_dts = zz_lookup['swing_dts']
    WINDOW = 200
    start_idx = WINDOW
    n_pts = len(swing_lens) - start_idx

    std_ts = np.empty(n_pts, dtype='int64')
    std_vals = np.empty(n_pts, dtype=np.float64)

    for j in range(n_pts):
        idx = start_idx + j
        window = swing_lens[idx - WINDOW:idx]
        std_ts[j] = swing_dts[idx].astype('int64')
        std_vals[j] = np.std(window)

    return {'timestamps': std_ts, 'std_values': std_vals}


# ---------------------------------------------------------------------------
# Enhanced analysis for Step 2
# ---------------------------------------------------------------------------

def analyze_step2(sim_result, label):
    """Compute Step 2 metrics from simulation results.

    Returns dict with all spec-required metrics or None if no valid cycles.
    """
    cycles = sim_result["cycle_records"]
    trades = sim_result["trade_records"]
    total_sessions = sim_result["total_sessions"]

    if not cycles:
        return None

    cf = pd.DataFrame(cycles)
    tf = pd.DataFrame(trades)

    # Entry datetime for hour filter
    entry_trades = tf[tf["action"].isin(["SEED", "REVERSAL"])]
    ce = entry_trades.groupby("cycle_id")["datetime"].first().reset_index()
    ce.columns = ["cycle_id", "entry_dt"]
    cf = cf.merge(ce, on="cycle_id", how="left")
    cf["hour"] = pd.to_datetime(cf["entry_dt"]).dt.hour
    # Exclude hours 1, 19, 20
    cf = cf[~cf["hour"].isin({1, 19, 20})].copy()

    if len(cf) == 0:
        return None

    # Per-cycle cost
    valid_ids = set(cf["cycle_id"])
    tf_valid = tf[tf["cycle_id"].isin(valid_ids)]
    cc = tf_valid.groupby("cycle_id")["cost_ticks"].sum()
    cf["cost"] = cf["cycle_id"].map(cc).fillna(0)
    cf["net_1t"] = cf["gross_pnl_ticks"] - cf["cost"]

    nn = len(cf)

    # Gross/Net PF
    gw = cf.loc[cf["gross_pnl_ticks"] > 0, "gross_pnl_ticks"].sum()
    gl = abs(cf.loc[cf["gross_pnl_ticks"] <= 0, "gross_pnl_ticks"].sum())
    gpf = gw / gl if gl else 0

    nw = cf.loc[cf["net_1t"] > 0, "net_1t"].sum()
    nl = abs(cf.loc[cf["net_1t"] <= 0, "net_1t"].sum())
    npf = nw / nl if nl else 0
    net_pnl = cf["net_1t"].sum()

    # Clean % (0 adds)
    clean_pct = (cf["adds_count"] == 0).mean()

    # MAE stats
    mean_mae = cf["mae"].mean()
    p75_mae = cf["mae"].quantile(0.75)
    max_loss = cf["net_1t"].min()

    # Per-session PnL
    session_pnl_raw = cf.groupby("session_id")["net_1t"].sum()
    all_sids = range(1, total_sessions + 1)
    session_pnl = session_pnl_raw.reindex(all_sids, fill_value=0.0)
    mean_daily = session_pnl.mean()
    std_daily = session_pnl.std()
    session_win_pct = (session_pnl > 0).mean()

    # Cycles/hour (full RTH = 6.5 hrs)
    rth_hours = (FLATTEN_TOD - RTH_OPEN_TOD) / 3600  # 6.5
    total_hours = rth_hours * total_sessions
    cycles_per_hour = nn / total_hours if total_hours > 0 else 0

    # EV components: classify each cycle
    # P_clean: 0 adds, no cap-walks
    clean = cf[(cf["adds_count"] == 0) & (cf["cycle_cap_walks"] == 0)]
    # P_1add_recover: exactly 1 add, net > 0
    one_add = cf[(cf["adds_count"] == 1) & (cf["cycle_cap_walks"] == 0)]
    one_add_recover = one_add[one_add["net_1t"] > 0]
    # P_capwalk: any cap-walks
    capwalk = cf[cf["cycle_cap_walks"] > 0]
    # P_deep_loss: everything else (multi-add losses, flatten losses)
    other_ids = set(cf["cycle_id"]) - set(clean["cycle_id"]) - set(one_add["cycle_id"]) - set(capwalk["cycle_id"])
    deep_loss = cf[cf["cycle_id"].isin(other_ids)]

    ev_clean = {"pct": len(clean) / nn, "mean_pnl": clean["net_1t"].mean() if len(clean) > 0 else 0}
    ev_1add = {"pct": len(one_add) / nn, "recover_pct": len(one_add_recover) / len(one_add) if len(one_add) > 0 else 0,
               "mean_pnl": one_add["net_1t"].mean() if len(one_add) > 0 else 0}
    ev_capwalk = {"pct": len(capwalk) / nn, "mean_pnl": capwalk["net_1t"].mean() if len(capwalk) > 0 else 0}
    ev_deep = {"pct": len(deep_loss) / nn, "mean_pnl": deep_loss["net_1t"].mean() if len(deep_loss) > 0 else 0}

    # Adaptive ranges (if adaptive)
    sd_range = {"min": cf["stepdist_used"].min(), "max": cf["stepdist_used"].max(),
                "mean": cf["stepdist_used"].mean()}
    ad_range = {"min": cf["adddist_used"].min(), "max": cf["adddist_used"].max(),
                "mean": cf["adddist_used"].mean()}

    return {
        "label": label,
        "cycles": nn,
        "clean_pct": round(clean_pct, 4),
        "gpf": round(gpf, 4),
        "npf_1t": round(npf, 4),
        "net_pnl": round(float(net_pnl), 1),
        "mean_mae": round(float(mean_mae), 2),
        "p75_mae": round(float(p75_mae), 2),
        "max_single_cycle_loss": round(float(max_loss), 1),
        "mean_daily": round(float(mean_daily), 1),
        "std_daily": round(float(std_daily), 1),
        "session_win_pct": round(float(session_win_pct), 4),
        "cycles_per_hour": round(cycles_per_hour, 2),
        "ev_clean": {k: round(v, 4) for k, v in ev_clean.items()},
        "ev_1add": {k: round(v, 4) for k, v in ev_1add.items()},
        "ev_capwalk": {k: round(v, 4) for k, v in ev_capwalk.items()},
        "ev_deep": {k: round(v, 4) for k, v in ev_deep.items()},
        "sd_range": {k: round(float(v), 2) for k, v in sd_range.items()},
        "ad_range": {k: round(float(v), 2) for k, v in ad_range.items()},
        "sessions": total_sessions,
        "cap_walks": sim_result["cap_walks"],
    }


# ---------------------------------------------------------------------------
# Step 2 sweep configurations
# ---------------------------------------------------------------------------

def get_fixed_configs():
    """Return 30 fixed StepDist x AddDist configs.

    SD: 16, 18, 20, 22, 24, 26
    AD: SD-8 through SD (step 2), floor 10
    """
    configs = []
    seen = set()
    for sd in [16, 18, 20, 22, 24, 26]:
        for ad_raw in range(sd - 8, sd + 1, 2):
            ad = max(ad_raw, 10)
            if ad > sd:
                continue
            key = (sd, ad)
            if key in seen:
                continue
            seen.add(key)
            configs.append({
                "label": f"SD{sd}_AD{ad}",
                "step_dist": float(sd),
                "add_dist": float(ad),
                "seed_dist": float(sd),  # coupled
                "adaptive": False,
            })
    return configs


def get_adaptive_configs():
    """Return 9 adaptive configs.

    SD percentile: P80, P85, P90
    AD percentile: P65, P70, P75
    """
    # pct_levels = [65, 70, 75, 80, 85, 90] -> indices 0-5
    configs = []
    for sd_pct, sd_idx in [(80, 3), (85, 4), (90, 5)]:
        for ad_pct, ad_idx in [(65, 0), (70, 1), (75, 2)]:
            configs.append({
                "label": f"ASD_P{sd_pct}_AAD_P{ad_pct}",
                "sd_pct": sd_pct,
                "ad_pct": ad_pct,
                "sd_pct_idx": sd_idx,
                "ad_pct_idx": ad_idx,
                "adaptive": True,
            })
    return configs


# ---------------------------------------------------------------------------
# Run sweep
# ---------------------------------------------------------------------------

def run_sweep(run_fixed=True, run_adaptive=True):
    """Run Step 2 sweep: 30 fixed + 9 adaptive configs."""
    print("\n" + "=" * 72)
    print("PHASE 1 STEP 2: StepDist x AddDist Sweep")
    print("  Settings: ML=1, cap=2, session=09:30-16:00, cost_ticks=1")
    print("  No SpeedRead, full P1, cap_action=walk")
    print("=" * 72)

    # Load tick data once
    print("\nLoading tick data (one-time)...")
    prices, tod_secs, sr_vals, dts = load_data(period='full_p1', use_speedread=False)

    # Build adaptive lookup if needed
    zz_lookup = None
    if run_adaptive:
        zz_lookup = build_zigzag_lookup()

    results = []
    configs = []
    if run_fixed:
        configs.extend(get_fixed_configs())
    if run_adaptive:
        configs.extend(get_adaptive_configs())

    print(f"\nTotal configs to run: {len(configs)}")
    print(f"\n  {'#':>3} {'Label':<22} {'Cycles':>7} {'NPF':>7} {'NetPnL':>9} "
          f"{'MeanMAE':>8} {'Clean%':>7} {'WinRate':>7} {'Cyc/Hr':>7}")
    print(f"  {'-'*85}")

    for idx, cfg in enumerate(configs):
        t0 = time.time()

        if cfg["adaptive"]:
            adaptive = make_adaptive_lookup(zz_lookup, cfg["sd_pct_idx"], cfg["ad_pct_idx"])
            sim = simulate_daily_flatten(
                prices, tod_secs, sr_vals, dts,
                seed_dist=25.0,    # initial; overridden by adaptive
                step_dist=25.0,    # initial; overridden by adaptive
                add_dist=25.0,     # initial; overridden by adaptive
                flatten_reseed_cap=_CAP,
                max_levels=_ML,
                seed_sr_thresh=-999.0,
                rev_sr_thresh=-999.0,
                watch_mode='rth_open',
                cap_action='walk',
                adaptive_lookup=adaptive,
            )
        else:
            sim = simulate_daily_flatten(
                prices, tod_secs, sr_vals, dts,
                seed_dist=cfg["seed_dist"],
                step_dist=cfg["step_dist"],
                add_dist=cfg["add_dist"],
                flatten_reseed_cap=_CAP,
                max_levels=_ML,
                seed_sr_thresh=-999.0,
                rev_sr_thresh=-999.0,
                watch_mode='rth_open',
                cap_action='walk',
            )

        elapsed = time.time() - t0
        r = analyze_step2(sim, cfg["label"])

        if r is None:
            print(f"  {idx+1:>3} {cfg['label']:<22} -- no cycles -- ({elapsed:.1f}s)")
            continue

        r["config"] = cfg
        r["sim_time_s"] = round(elapsed, 1)
        results.append(r)

        print(f"  {idx+1:>3} {r['label']:<22} {r['cycles']:>7} {r['npf_1t']:>7.4f} "
              f"{r['net_pnl']:>+9.0f} {r['mean_mae']:>8.2f} "
              f"{r['clean_pct']:>7.1%} {r['session_win_pct']:>7.1%} "
              f"{r['cycles_per_hour']:>7.2f}  ({elapsed:.0f}s)")

    # Save all results
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = _OUTPUT_DIR / "step2_sweep_results.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nSaved {len(results)} results to {out_path}")

    # Generate summary tables
    if results:
        print_summary(results)

    return results


# ---------------------------------------------------------------------------
# Summary tables and heatmaps
# ---------------------------------------------------------------------------

def print_summary(results):
    """Print summary tables and identify winners."""
    print("\n" + "=" * 72)
    print("STEP 2 SUMMARY")
    print("=" * 72)

    fixed = [r for r in results if not r["config"].get("adaptive", False)]
    adaptive = [r for r in results if r["config"].get("adaptive", False)]

    # --- Fixed heatmap: NPF ---
    if fixed:
        print("\n--- Fixed Configs: Net PF @1t Heatmap ---")
        sds = sorted(set(r["config"]["step_dist"] for r in fixed))
        ads = sorted(set(r["config"]["add_dist"] for r in fixed))
        npf_map = {(r["config"]["step_dist"], r["config"]["add_dist"]): r["npf_1t"] for r in fixed}

        print(f"  {'SD\\AD':>8}", end="")
        for ad in ads:
            print(f"  {ad:>6.0f}", end="")
        print()
        for sd in sds:
            print(f"  {sd:>8.0f}", end="")
            for ad in ads:
                v = npf_map.get((sd, ad))
                if v is not None:
                    marker = " *" if v >= 1.0 else "  "
                    print(f"  {v:>5.3f}{marker[1]}", end="")
                else:
                    print(f"  {'--':>6}", end="")
            print()
        print(f"  (* = NPF >= 1.0)")

        # --- Fixed heatmap: EV per cycle ---
        print("\n--- Fixed Configs: Net PnL per Cycle (ticks) ---")
        ev_map = {(r["config"]["step_dist"], r["config"]["add_dist"]):
                  r["net_pnl"] / r["cycles"] if r["cycles"] > 0 else 0 for r in fixed}

        print(f"  {'SD\\AD':>8}", end="")
        for ad in ads:
            print(f"  {ad:>7.0f}", end="")
        print()
        for sd in sds:
            print(f"  {sd:>8.0f}", end="")
            for ad in ads:
                v = ev_map.get((sd, ad))
                if v is not None:
                    print(f"  {v:>+7.1f}", end="")
                else:
                    print(f"  {'--':>7}", end="")
            print()

    # --- Adaptive table ---
    if adaptive:
        print("\n--- Adaptive Configs ---")
        print(f"  {'Label':<22} {'NPF':>7} {'NetPnL':>9} {'EV/Cyc':>8} "
              f"{'SD_rng':>12} {'AD_rng':>12} {'Cycles':>7}")
        print(f"  {'-'*80}")
        for r in sorted(adaptive, key=lambda x: -x["npf_1t"]):
            ev_cyc = r["net_pnl"] / r["cycles"] if r["cycles"] > 0 else 0
            sd_rng = f"{r['sd_range']['min']:.0f}-{r['sd_range']['max']:.0f}"
            ad_rng = f"{r['ad_range']['min']:.0f}-{r['ad_range']['max']:.0f}"
            print(f"  {r['label']:<22} {r['npf_1t']:>7.4f} {r['net_pnl']:>+9.0f} "
                  f"{ev_cyc:>+8.1f} {sd_rng:>12} {ad_rng:>12} {r['cycles']:>7}")

    # --- Top configs overall ---
    all_sorted = sorted(results, key=lambda x: -x["npf_1t"])
    top5 = all_sorted[:5]

    print("\n--- Top 5 Configs by Net PF ---")
    print(f"  {'#':>3} {'Label':<22} {'NPF':>7} {'NetPnL':>9} {'EV/Cyc':>8} "
          f"{'MeanMAE':>8} {'Clean%':>7} {'WinRate':>7} {'Cyc/Hr':>7}")
    print(f"  {'-'*90}")
    for i, r in enumerate(top5):
        ev_cyc = r["net_pnl"] / r["cycles"] if r["cycles"] > 0 else 0
        print(f"  {i+1:>3} {r['label']:<22} {r['npf_1t']:>7.4f} {r['net_pnl']:>+9.0f} "
              f"{ev_cyc:>+8.1f} {r['mean_mae']:>8.2f} {r['clean_pct']:>7.1%} "
              f"{r['session_win_pct']:>7.1%} {r['cycles_per_hour']:>7.2f}")

    # --- Adaptive vs Fixed comparison ---
    if fixed and adaptive:
        best_fixed = max(fixed, key=lambda x: x["npf_1t"])
        best_adaptive = max(adaptive, key=lambda x: x["npf_1t"])
        npf_improvement = (best_adaptive["npf_1t"] - best_fixed["npf_1t"]) / best_fixed["npf_1t"] * 100

        print(f"\n--- Adaptive vs Fixed Comparison ---")
        print(f"  Best fixed:    {best_fixed['label']} (NPF={best_fixed['npf_1t']:.4f})")
        print(f"  Best adaptive: {best_adaptive['label']} (NPF={best_adaptive['npf_1t']:.4f})")
        print(f"  NPF improvement: {npf_improvement:+.1f}%")

        sd_range = best_adaptive["sd_range"]
        ad_range = best_adaptive["ad_range"]
        adaptation = sd_range["max"] - sd_range["min"]
        print(f"  SD adaptation range: {sd_range['min']:.0f}-{sd_range['max']:.0f} "
              f"({adaptation:.0f} pts)")

        if npf_improvement > 3.0:
            print(f"\n  VERDICT: Adaptive wins by >{3}% NPF. Adaptive is the foundation.")
        elif adaptation > 4.0:
            print(f"\n  VERDICT: Adaptation range >{4} pts. Adaptive adds value.")
        else:
            print(f"\n  VERDICT: Fixed preferred (simpler). Adaptive improvement <3% "
                  f"and range <4 pts.")

    # EV component breakdown for top 3
    print("\n--- EV Components (Top 3) ---")
    for r in all_sorted[:3]:
        print(f"\n  {r['label']}:")
        print(f"    Clean:    {r['ev_clean']['pct']:>6.1%}  mean PnL={r['ev_clean']['mean_pnl']:>+8.1f}")
        print(f"    1-Add:    {r['ev_1add']['pct']:>6.1%}  mean PnL={r['ev_1add']['mean_pnl']:>+8.1f}"
              f"  recover={r['ev_1add']['recover_pct']:.1%}")
        print(f"    Cap-Walk: {r['ev_capwalk']['pct']:>6.1%}  mean PnL={r['ev_capwalk']['mean_pnl']:>+8.1f}")
        print(f"    Deep:     {r['ev_deep']['pct']:>6.1%}  mean PnL={r['ev_deep']['mean_pnl']:>+8.1f}")


# ---------------------------------------------------------------------------
# Step 2b: ML and Position Cap Re-Evaluation
# ---------------------------------------------------------------------------

def run_step2b():
    """Step 2b: Test ML={1,2} x Cap={2,3} on top 3 winners from Step 2.

    Kill condition: ML=2 or cap=3 must improve EV by >10% over ML=1/cap=2.
    """
    print("\n" + "=" * 72)
    print("PHASE 1 STEP 2b: ML and Position Cap Re-Evaluation")
    print("  ML: 1, 2.  Cap: 2, 3.  4 combos x 3 winners = 12 sims")
    print("  Kill: >10% EV improvement required to justify complexity")
    print("=" * 72)

    # Load Step 2 results to identify winners
    s2_path = _OUTPUT_DIR / "step2_sweep_results.json"
    if not s2_path.exists():
        print("  ERROR: Step 2 results not found. Run Step 2 first.")
        return None
    with open(s2_path) as f:
        s2_results = json.load(f)

    # Top 3 by NPF
    top3 = sorted(s2_results, key=lambda x: -x["npf_1t"])[:3]
    print(f"\n  Top 3 winners from Step 2:")
    for r in top3:
        print(f"    {r['label']}: NPF={r['npf_1t']:.4f}, NetPnL={r['net_pnl']:+.0f}")

    # Load tick data
    print("\nLoading tick data...")
    prices, tod_secs, sr_vals, dts = load_data(period='full_p1', use_speedread=False)

    # Build adaptive lookup for adaptive winners
    zz_lookup = None
    has_adaptive = any(r["config"].get("adaptive", False) for r in top3)
    if has_adaptive:
        zz_lookup = build_zigzag_lookup()

    # ML/cap combos
    ml_cap_combos = [(1, 2), (1, 3), (2, 2), (2, 3)]

    results = []
    print(f"\n  {'#':>3} {'Base':<22} {'ML':>3} {'Cap':>4} {'Cycles':>7} {'NPF':>7} "
          f"{'NetPnL':>9} {'EV/Cyc':>8} {'MaxPos':>7} {'MeanMAE':>8}")
    print(f"  {'-'*90}")

    idx = 0
    for winner in top3:
        cfg = winner["config"]
        for ml, cap in ml_cap_combos:
            idx += 1
            t0 = time.time()

            if cfg.get("adaptive", False):
                adaptive = make_adaptive_lookup(zz_lookup, cfg["sd_pct_idx"], cfg["ad_pct_idx"])
                sim = simulate_daily_flatten(
                    prices, tod_secs, sr_vals, dts,
                    seed_dist=25.0, step_dist=25.0, add_dist=25.0,
                    flatten_reseed_cap=cap,
                    max_levels=ml,
                    seed_sr_thresh=-999.0, rev_sr_thresh=-999.0,
                    watch_mode='rth_open', cap_action='walk',
                    adaptive_lookup=adaptive,
                )
            else:
                sim = simulate_daily_flatten(
                    prices, tod_secs, sr_vals, dts,
                    seed_dist=cfg["seed_dist"],
                    step_dist=cfg["step_dist"],
                    add_dist=cfg["add_dist"],
                    flatten_reseed_cap=cap,
                    max_levels=ml,
                    seed_sr_thresh=-999.0, rev_sr_thresh=-999.0,
                    watch_mode='rth_open', cap_action='walk',
                )

            elapsed = time.time() - t0
            r = analyze_step2(sim, f"{cfg['label']}_ML{ml}_C{cap}")
            if r is None:
                print(f"  {idx:>3} {cfg['label']:<22} {ml:>3} {cap:>4}  -- no cycles --")
                continue

            r["config"] = {**cfg, "max_levels": ml, "cap": cap}
            r["base_label"] = cfg["label"]
            r["ml"] = ml
            r["cap"] = cap
            r["sim_time_s"] = round(elapsed, 1)

            # Max position from cycle records
            max_pos = max(c.get("max_position_qty", 0) for c in sim["cycle_records"]) if sim["cycle_records"] else 0
            r["max_position"] = max_pos

            # Mean position at exit (approx from adds_count + 1)
            cycles_df = pd.DataFrame(sim["cycle_records"])
            if len(cycles_df) > 0:
                r["mean_pos_at_exit"] = round((cycles_df["adds_count"] + 1).mean(), 2)
            else:
                r["mean_pos_at_exit"] = 0

            results.append(r)
            ev_cyc = r["net_pnl"] / r["cycles"] if r["cycles"] > 0 else 0

            print(f"  {idx:>3} {cfg['label']:<22} {ml:>3} {cap:>4} {r['cycles']:>7} "
                  f"{r['npf_1t']:>7.4f} {r['net_pnl']:>+9.0f} {ev_cyc:>+8.1f} "
                  f"{max_pos:>7} {r['mean_mae']:>8.2f}  ({elapsed:.0f}s)")

    # Save results
    out_path = _OUTPUT_DIR / "step2b_ml_cap_results.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nSaved {len(results)} results to {out_path}")

    # --- Evaluation ---
    print(f"\n--- Step 2b Evaluation ---")
    for winner in top3:
        wlabel = winner["config"]["label"]
        w_results = [r for r in results if r["base_label"] == wlabel]
        baseline = [r for r in w_results if r["ml"] == 1 and r["cap"] == 2]
        if not baseline:
            continue
        base = baseline[0]
        base_ev = base["net_pnl"] / base["cycles"] if base["cycles"] > 0 else 0

        print(f"\n  {wlabel} (baseline ML=1/cap=2: NPF={base['npf_1t']:.4f}, EV/cyc={base_ev:+.1f}):")
        for r in w_results:
            if r["ml"] == 1 and r["cap"] == 2:
                continue
            ev_cyc = r["net_pnl"] / r["cycles"] if r["cycles"] > 0 else 0
            ev_change = ((ev_cyc - base_ev) / abs(base_ev) * 100) if base_ev != 0 else 0
            npf_change = ((r["npf_1t"] - base["npf_1t"]) / base["npf_1t"] * 100)
            verdict = "KEEP" if ev_change > 10 else "REJECT"
            print(f"    ML={r['ml']}/cap={r['cap']}: NPF={r['npf_1t']:.4f} ({npf_change:+.1f}%), "
                  f"EV/cyc={ev_cyc:+.1f} ({ev_change:+.1f}%), maxPos={r['max_position']} -> {verdict}")

    # Overall verdict
    all_ev = [(r, r["net_pnl"] / r["cycles"] if r["cycles"] > 0 else 0) for r in results]
    best = max(all_ev, key=lambda x: x[1])
    print(f"\n  Best overall: {best[0]['label']} (EV/cyc={best[1]:+.1f})")

    best_simple = [r for r in results if r["ml"] == 1 and r["cap"] == 2]
    best_simple_ev = max(best_simple, key=lambda x: x["net_pnl"] / x["cycles"] if x["cycles"] > 0 else 0)
    simple_ev = best_simple_ev["net_pnl"] / best_simple_ev["cycles"]
    improvement = ((best[1] - simple_ev) / abs(simple_ev) * 100) if simple_ev != 0 else 0

    if improvement > 10:
        print(f"  VERDICT: ML/cap change improves EV by {improvement:+.1f}% (>10%). Adopt.")
    else:
        print(f"  VERDICT: ML/cap change improves EV by only {improvement:+.1f}% (<10%). Keep ML=1/cap=2.")

    return results


# ---------------------------------------------------------------------------
# Step 3: SeedDist Optimization
# ---------------------------------------------------------------------------

def make_sigma_seed_lookup(zz_lookup, n_sigma):
    """Create adaptive_lookup for sigma-band SeedDist.

    SeedDist = mean + n_sigma * std of rolling 200-swing window, floor 10.
    StepDist and AddDist come from the base adaptive config.
    """
    WINDOW = 200
    swing_lens = zz_lookup['swing_lens']
    swing_dts = zz_lookup['swing_dts']
    start_idx = WINDOW
    n_pts = len(swing_lens) - start_idx

    seed_vals = np.empty(n_pts, dtype=np.float64)
    for j in range(n_pts):
        idx = start_idx + j
        window = swing_lens[idx - WINDOW:idx]
        seed_vals[j] = max(window.mean() + n_sigma * window.std(), 10.0)

    return zz_lookup['pct_ts'][:n_pts], seed_vals


def run_step3():
    """Step 3: SeedDist optimization on top 2-3 configs from Steps 2+2b.

    Fixed SeedDist: 10, 12, 15, 18, 20, SD (=StepDist)
    Sigma-band: mean + N*sigma (N=0.5, 0.75, 1.0, 1.25, 1.5), floor 10
    """
    print("\n" + "=" * 72)
    print("PHASE 1 STEP 3: SeedDist Optimization")
    print("  Fixed SeedDist: 10, 12, 15, 18, 20, SD")
    print("  Sigma-band: mean + N*sigma (N=0.5..1.5), floor 10")
    print("  ML=1, cap=2, session=09:30-16:00, cost_ticks=1")
    print("=" * 72)

    # Load Step 2 results to identify winners
    s2_path = _OUTPUT_DIR / "step2_sweep_results.json"
    with open(s2_path) as f:
        s2_results = json.load(f)
    top3 = sorted(s2_results, key=lambda x: -x["npf_1t"])[:3]

    print(f"\n  Top 3 configs from Step 2 (all ML=1/cap=2):")
    for r in top3:
        print(f"    {r['label']}: NPF={r['npf_1t']:.4f}")

    # Load data
    print("\nLoading tick data...")
    prices, tod_secs, sr_vals, dts = load_data(period='full_p1', use_speedread=False)
    zz_lookup = build_zigzag_lookup()

    # For sigma-band, precompute mean+N*sigma values
    sigma_ns = [0.5, 0.75, 1.0, 1.25, 1.5]
    sigma_lookups = {}
    for n_sig in sigma_ns:
        ts, vals = make_sigma_seed_lookup(zz_lookup, n_sig)
        sigma_lookups[n_sig] = (ts, vals)
        print(f"  Sigma N={n_sig}: seed range {vals.min():.1f}-{vals.max():.1f}, mean={vals.mean():.1f}")

    results = []
    print(f"\n  {'#':>3} {'Base':<18} {'SeedType':<16} {'Cycles':>7} {'NPF':>7} "
          f"{'NetPnL':>9} {'EV/Cyc':>8} {'SeedAcc':>8}")
    print(f"  {'-'*85}")

    idx = 0
    for winner in top3:
        cfg = winner["config"]
        is_adaptive = cfg.get("adaptive", False)

        # --- Fixed SeedDist values ---
        if is_adaptive:
            # For adaptive, SD varies. Use mean SD as reference for "SD" option
            mean_sd = winner["sd_range"]["mean"]
            fixed_seeds = [10, 12, 15, 18, 20, round(mean_sd)]
        else:
            fixed_seeds = [10, 12, 15, 18, 20, int(cfg["step_dist"])]
        # Deduplicate and sort
        fixed_seeds = sorted(set(fixed_seeds))

        for seed_val in fixed_seeds:
            idx += 1
            t0 = time.time()
            seed_label = f"Seed={seed_val}"

            if is_adaptive:
                adaptive = make_adaptive_lookup(zz_lookup, cfg["sd_pct_idx"], cfg["ad_pct_idx"])
                sim = simulate_daily_flatten(
                    prices, tod_secs, sr_vals, dts,
                    seed_dist=float(seed_val),
                    step_dist=25.0, add_dist=25.0,  # overridden by adaptive
                    flatten_reseed_cap=_CAP, max_levels=_ML,
                    seed_sr_thresh=-999.0, rev_sr_thresh=-999.0,
                    watch_mode='rth_open', cap_action='walk',
                    adaptive_lookup=adaptive,
                )
            else:
                sim = simulate_daily_flatten(
                    prices, tod_secs, sr_vals, dts,
                    seed_dist=float(seed_val),
                    step_dist=cfg["step_dist"],
                    add_dist=cfg["add_dist"],
                    flatten_reseed_cap=_CAP, max_levels=_ML,
                    seed_sr_thresh=-999.0, rev_sr_thresh=-999.0,
                    watch_mode='rth_open', cap_action='walk',
                )

            elapsed = time.time() - t0
            r = analyze_step2(sim, f"{cfg['label']}_Seed{seed_val}")
            if r is None:
                print(f"  {idx:>3} {cfg['label']:<18} {seed_label:<16}  -- no cycles --")
                continue

            # Seed accuracy
            trades_df = pd.DataFrame(sim["trade_records"])
            cycles_df = pd.DataFrame(sim["cycle_records"])
            first_actions = trades_df.groupby("cycle_id")["action"].first()
            seed_cids = first_actions[first_actions == "SEED"].index
            seed_cycles = cycles_df[cycles_df["cycle_id"].isin(seed_cids)]
            seed_acc = (seed_cycles["gross_pnl_ticks"] > 0).mean() if len(seed_cycles) > 0 else 0

            r["config"] = {**cfg, "seed_dist": seed_val, "seed_type": "fixed"}
            r["seed_accuracy"] = round(seed_acc, 4)
            r["base_label"] = cfg["label"]
            results.append(r)

            ev_cyc = r["net_pnl"] / r["cycles"] if r["cycles"] > 0 else 0
            print(f"  {idx:>3} {cfg['label']:<18} {seed_label:<16} {r['cycles']:>7} "
                  f"{r['npf_1t']:>7.4f} {r['net_pnl']:>+9.0f} {ev_cyc:>+8.1f} "
                  f"{seed_acc:>8.1%}  ({elapsed:.0f}s)")

        # --- Sigma-band SeedDist (for adaptive configs, or all) ---
        for n_sig in sigma_ns:
            idx += 1
            t0 = time.time()
            seed_label = f"Sigma={n_sig}"
            sig_ts, sig_vals = sigma_lookups[n_sig]

            if is_adaptive:
                # Adaptive SD/AD + sigma-band seed
                base_adaptive = make_adaptive_lookup(zz_lookup, cfg["sd_pct_idx"], cfg["ad_pct_idx"])
                # Override seed values in a custom lookup
                # The simulator uses seed_dist param for non-adaptive seed, but for adaptive
                # we update current_seed at entry. We need a way to pass sigma seed.
                # Simplest: create a modified adaptive_lookup with separate seed array
                # For now: compute mean sigma seed as fixed value (approximation)
                mean_sigma_seed = float(sig_vals.mean())
                sim = simulate_daily_flatten(
                    prices, tod_secs, sr_vals, dts,
                    seed_dist=mean_sigma_seed,
                    step_dist=25.0, add_dist=25.0,
                    flatten_reseed_cap=_CAP, max_levels=_ML,
                    seed_sr_thresh=-999.0, rev_sr_thresh=-999.0,
                    watch_mode='rth_open', cap_action='walk',
                    adaptive_lookup=base_adaptive,
                )
            else:
                # Fixed SD/AD + sigma-band seed (use mean as fixed approx)
                mean_sigma_seed = float(sig_vals.mean())
                sim = simulate_daily_flatten(
                    prices, tod_secs, sr_vals, dts,
                    seed_dist=mean_sigma_seed,
                    step_dist=cfg["step_dist"],
                    add_dist=cfg["add_dist"],
                    flatten_reseed_cap=_CAP, max_levels=_ML,
                    seed_sr_thresh=-999.0, rev_sr_thresh=-999.0,
                    watch_mode='rth_open', cap_action='walk',
                )

            elapsed = time.time() - t0
            r = analyze_step2(sim, f"{cfg['label']}_Sig{n_sig}")
            if r is None:
                print(f"  {idx:>3} {cfg['label']:<18} {seed_label:<16}  -- no cycles --")
                continue

            trades_df = pd.DataFrame(sim["trade_records"])
            cycles_df = pd.DataFrame(sim["cycle_records"])
            first_actions = trades_df.groupby("cycle_id")["action"].first()
            seed_cids = first_actions[first_actions == "SEED"].index
            seed_cycles = cycles_df[cycles_df["cycle_id"].isin(seed_cids)]
            seed_acc = (seed_cycles["gross_pnl_ticks"] > 0).mean() if len(seed_cycles) > 0 else 0

            r["config"] = {**cfg, "seed_dist": round(mean_sigma_seed, 2),
                           "seed_type": f"sigma_{n_sig}", "sigma_n": n_sig,
                           "sigma_seed_range": f"{sig_vals.min():.1f}-{sig_vals.max():.1f}"}
            r["seed_accuracy"] = round(seed_acc, 4)
            r["base_label"] = cfg["label"]
            results.append(r)

            ev_cyc = r["net_pnl"] / r["cycles"] if r["cycles"] > 0 else 0
            print(f"  {idx:>3} {cfg['label']:<18} {seed_label:<16} {r['cycles']:>7} "
                  f"{r['npf_1t']:>7.4f} {r['net_pnl']:>+9.0f} {ev_cyc:>+8.1f} "
                  f"{seed_acc:>8.1%}  ({elapsed:.0f}s)")

    # Save
    out_path = _OUTPUT_DIR / "step3_seeddist_results.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nSaved {len(results)} results to {out_path}")

    # Summary per base config
    print(f"\n--- Step 3 Summary ---")
    for winner in top3:
        wlabel = winner["config"]["label"]
        w_results = [r for r in results if r["base_label"] == wlabel]
        if not w_results:
            continue

        # Baseline = SeedDist coupled (= StepDist)
        coupled_sd = winner["sd_range"]["mean"] if winner["config"].get("adaptive") else winner["config"]["step_dist"]
        baseline = [r for r in w_results
                    if r["config"].get("seed_type") == "fixed"
                    and abs(r["config"]["seed_dist"] - coupled_sd) < 1]
        base_npf = baseline[0]["npf_1t"] if baseline else winner["npf_1t"]

        print(f"\n  {wlabel} (coupled baseline NPF={base_npf:.4f}):")
        sorted_r = sorted(w_results, key=lambda x: -x["npf_1t"])
        for r in sorted_r[:5]:
            ev_cyc = r["net_pnl"] / r["cycles"] if r["cycles"] > 0 else 0
            seed_info = r["config"].get("seed_type", "?")
            seed_val = r["config"].get("seed_dist", "?")
            print(f"    {seed_info:>8} seed={seed_val:>5}: NPF={r['npf_1t']:.4f}, "
                  f"EV/cyc={ev_cyc:+.1f}, seedAcc={r['seed_accuracy']:.1%}, "
                  f"cycles={r['cycles']}")

    # Best overall
    best = max(results, key=lambda x: x["npf_1t"])
    ev_best = best["net_pnl"] / best["cycles"] if best["cycles"] > 0 else 0
    print(f"\n  Best overall: {best['label']} (NPF={best['npf_1t']:.4f}, "
          f"EV/cyc={ev_best:+.1f}, seedAcc={best['seed_accuracy']:.1%})")

    return results


# ---------------------------------------------------------------------------
# Step 4: Session Window Optimization
# ---------------------------------------------------------------------------

def run_step4():
    """Step 4: Test session windows on best config from Steps 2-3.

    Windows: 09:30-11:30, 09:30-13:30, 09:30-16:00 (full RTH)
    Primary metric: PnL per clock-hour (not total PnL).
    """
    print("\n" + "=" * 72)
    print("PHASE 1 STEP 4: Session Window Optimization")
    print("  Windows: 09:30-11:30, 09:30-13:30, 09:30-16:00")
    print("  Primary metric: PnL per clock-hour")
    print("  Best config: ASD P90/P75 + SeedDist=15, ML=1, cap=2")
    print("=" * 72)

    # Best config from Step 3
    best_cfg = {
        "label": "ASD_P90_AAD_P75",
        "adaptive": True,
        "sd_pct_idx": 5,  # P90
        "ad_pct_idx": 2,  # P75
    }
    best_seed = 15.0

    # Also test best fixed (SD20/AD16, seed=20) for comparison
    fixed_cfg = {
        "label": "SD20_AD16",
        "adaptive": False,
        "step_dist": 20.0,
        "add_dist": 16.0,
        "seed_dist": 20.0,
    }

    # Load data
    print("\nLoading tick data...")
    prices, tod_secs, sr_vals, dts = load_data(period='full_p1', use_speedread=False)
    zz_lookup = build_zigzag_lookup()
    adaptive = make_adaptive_lookup(zz_lookup, best_cfg["sd_pct_idx"], best_cfg["ad_pct_idx"])

    windows = [
        ("09:30-11:30", 11 * 3600 + 30 * 60, 2.0),
        ("09:30-13:30", 13 * 3600 + 30 * 60, 4.0),
        ("09:30-16:00", None, 6.5),
    ]

    results = []
    test_configs = [
        ("ASD_P90_P75_Sd15", best_cfg, best_seed, True),
        ("SD20_AD16_Sd20", fixed_cfg, 20.0, False),
    ]

    print(f"\n  {'Config':<22} {'Window':<14} {'Cycles':>7} {'NPF':>7} {'NetPnL':>9} "
          f"{'PnL/Hr':>8} {'WorstDay':>9} {'Cyc/Hr':>7} {'StdDly':>7}")
    print(f"  {'-'*95}")

    for cfg_label, cfg, seed, is_adaptive in test_configs:
        for win_label, win_end, win_hours in windows:
            t0 = time.time()

            if is_adaptive:
                sim = simulate_daily_flatten(
                    prices, tod_secs, sr_vals, dts,
                    seed_dist=seed,
                    step_dist=25.0, add_dist=25.0,
                    flatten_reseed_cap=_CAP, max_levels=_ML,
                    seed_sr_thresh=-999.0, rev_sr_thresh=-999.0,
                    watch_mode='rth_open', cap_action='walk',
                    session_window_end=win_end,
                    adaptive_lookup=adaptive,
                )
            else:
                sim = simulate_daily_flatten(
                    prices, tod_secs, sr_vals, dts,
                    seed_dist=seed,
                    step_dist=cfg["step_dist"],
                    add_dist=cfg["add_dist"],
                    flatten_reseed_cap=_CAP, max_levels=_ML,
                    seed_sr_thresh=-999.0, rev_sr_thresh=-999.0,
                    watch_mode='rth_open', cap_action='walk',
                    session_window_end=win_end,
                )

            elapsed = time.time() - t0
            r = analyze_step2(sim, f"{cfg_label}_{win_label}")
            if r is None:
                print(f"  {cfg_label:<22} {win_label:<14}  -- no cycles --")
                continue

            # PnL per clock-hour
            total_hours = win_hours * r["sessions"]
            pnl_per_hour = r["net_pnl"] / total_hours if total_hours > 0 else 0
            cycles_per_hour = r["cycles"] / total_hours if total_hours > 0 else 0

            # Worst single day
            cycles_df = pd.DataFrame(sim["cycle_records"])
            trades_df = pd.DataFrame(sim["trade_records"])
            if len(cycles_df) > 0:
                entry_trades = trades_df[trades_df["action"].isin(["SEED", "REVERSAL"])]
                ce = entry_trades.groupby("cycle_id")["datetime"].first().reset_index()
                ce.columns = ["cycle_id", "entry_dt"]
                cycles_df = cycles_df.merge(ce, on="cycle_id", how="left")
                cycles_df["hour"] = pd.to_datetime(cycles_df["entry_dt"]).dt.hour
                cf = cycles_df[~cycles_df["hour"].isin({1, 19, 20})].copy()
                valid_ids = set(cf["cycle_id"])
                tf_valid = trades_df[trades_df["cycle_id"].isin(valid_ids)]
                cc = tf_valid.groupby("cycle_id")["cost_ticks"].sum()
                cf["cost"] = cf["cycle_id"].map(cc).fillna(0)
                cf["net_1t"] = cf["gross_pnl_ticks"] - cf["cost"]
                session_pnl = cf.groupby("session_id")["net_1t"].sum()
                worst_day = session_pnl.min() if len(session_pnl) > 0 else 0
            else:
                worst_day = 0

            r["config"] = {**cfg, "window": win_label, "window_end": win_end,
                           "window_hours": win_hours, "seed_dist": seed}
            r["pnl_per_hour"] = round(pnl_per_hour, 2)
            r["cycles_per_hour_window"] = round(cycles_per_hour, 2)
            r["worst_day"] = round(float(worst_day), 1)
            r["window_label"] = win_label
            r["base_label"] = cfg_label
            results.append(r)

            print(f"  {cfg_label:<22} {win_label:<14} {r['cycles']:>7} {r['npf_1t']:>7.4f} "
                  f"{r['net_pnl']:>+9.0f} {pnl_per_hour:>+8.1f} {worst_day:>+9.0f} "
                  f"{cycles_per_hour:>7.2f} {r['std_daily']:>7.1f}  ({elapsed:.0f}s)")

    # Save
    out_path = _OUTPUT_DIR / "step4_window_results.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nSaved {len(results)} results to {out_path}")

    # Summary
    print(f"\n--- Step 4 Summary ---")
    for cfg_label, _, _, _ in test_configs:
        cfg_results = [r for r in results if r["base_label"] == cfg_label]
        if not cfg_results:
            continue
        print(f"\n  {cfg_label}:")
        best_eff = max(cfg_results, key=lambda x: x["pnl_per_hour"])
        best_total = max(cfg_results, key=lambda x: x["net_pnl"])
        print(f"    Best PnL/hour:  {best_eff['window_label']} "
              f"({best_eff['pnl_per_hour']:+.1f} ticks/hr, total={best_eff['net_pnl']:+.0f})")
        print(f"    Best total PnL: {best_total['window_label']} "
              f"({best_total['pnl_per_hour']:+.1f} ticks/hr, total={best_total['net_pnl']:+.0f})")

        if best_eff["window_label"] != best_total["window_label"]:
            eff_total = best_eff["net_pnl"]
            total_total = best_total["net_pnl"]
            print(f"    Trade-off: {best_eff['window_label']} produces "
                  f"{best_eff['pnl_per_hour']:+.1f}/hr but {eff_total:+.0f} total vs "
                  f"{best_total['window_label']} at {best_total['pnl_per_hour']:+.1f}/hr "
                  f"and {total_total:+.0f} total")

    return results


# ---------------------------------------------------------------------------
# Step 5: Freeze Base Config
# ---------------------------------------------------------------------------

def run_step5():
    """Step 5: Freeze best config, save cycle parquet + config JSON + summary."""
    print("\n" + "=" * 72)
    print("PHASE 1 STEP 5: Freeze Base Config")
    print("=" * 72)

    # --- Final config ---
    config = {
        "strategy": "rotational",
        "phase": "Phase 1 Base Parameter Calibration",
        "type": "adaptive",
        "step_dist": {"source": "rolling_zigzag_P90", "percentile": 90, "floor": 10.0},
        "add_dist": {"source": "rolling_zigzag_P75", "percentile": 75, "floor": 10.0},
        "seed_dist": {"value": 15.0, "type": "fixed", "note": "decoupled from StepDist"},
        "zigzag_rolling_window": 200,
        "zigzag_source": "CSV Zig Zag Line Length (abs, both directions) — Sierra Chart HL-based",
        "zigzag_reversal": 5.25,
        "max_levels": 1,
        "position_cap": 2,
        "cap_action": "walk",
        "session_window": "09:30-16:00",
        "session_window_end": None,
        "watch_mode": "rth_open",
        "daily_flatten": "16:00 ET",
        "cost_ticks": 1,
        "tick_size": 0.25,
        "instrument": "NQ",
        "data_period": "Full P1 (Sep 21 - Dec 14, 2025)",
        "speedread": "disabled",
        "feature_filters": "none (pure base economics)",
    }

    # --- Run final simulation to generate cycle dataset ---
    print("\nRunning final simulation with frozen config...")
    prices, tod_secs, sr_vals, dts = load_data(period='full_p1', use_speedread=False)
    zz_lookup = build_zigzag_lookup()
    adaptive = make_adaptive_lookup(zz_lookup, 5, 2)  # P90=idx5, P75=idx2

    sim = simulate_daily_flatten(
        prices, tod_secs, sr_vals, dts,
        seed_dist=15.0,
        step_dist=25.0, add_dist=25.0,  # overridden by adaptive
        flatten_reseed_cap=2, max_levels=1,
        seed_sr_thresh=-999.0, rev_sr_thresh=-999.0,
        watch_mode='rth_open', cap_action='walk',
        adaptive_lookup=adaptive,
    )

    r = analyze_step2(sim, "FROZEN: ASD_P90_P75_Sd15_ML1_C2_FullRTH")

    # --- Build cycle parquet with ALL required fields ---
    print("\nBuilding cycle dataset...")
    cycles_df = pd.DataFrame(sim["cycle_records"])
    trades_df = pd.DataFrame(sim["trade_records"])

    # Entry/exit times from trades
    entry_trades = trades_df[trades_df["action"].isin(["SEED", "REVERSAL"])]
    ce = entry_trades.groupby("cycle_id").agg(
        entry_time=("datetime", "first"),
    ).reset_index()
    cycles_df = cycles_df.merge(ce, on="cycle_id", how="left")

    # Exit time = last trade datetime per cycle
    exit_trades = trades_df.groupby("cycle_id")["datetime"].last().reset_index()
    exit_trades.columns = ["cycle_id", "exit_time"]
    cycles_df = cycles_df.merge(exit_trades, on="cycle_id", how="left")

    # Net PnL with cost
    valid_ids = set(cycles_df["cycle_id"])
    tf_valid = trades_df[trades_df["cycle_id"].isin(valid_ids)]
    cc = tf_valid.groupby("cycle_id")["cost_ticks"].sum()
    cycles_df["cost"] = cycles_df["cycle_id"].map(cc).fillna(0)
    cycles_df["net_pnl_ticks"] = cycles_df["gross_pnl_ticks"] - cycles_df["cost"]

    # Assign block
    cycles_df["entry_hour"] = pd.to_datetime(cycles_df["entry_time"]).dt.hour
    cycles_df["entry_minute"] = pd.to_datetime(cycles_df["entry_time"]).dt.minute
    entry_tod = cycles_df["entry_hour"] * 3600 + cycles_df["entry_minute"] * 60

    def assign_block(tod):
        if 34200 <= tod < 36000: return "Open"
        elif 36000 <= tod < 41400: return "Morning"
        elif 41400 <= tod < 48600: return "Midday"
        elif 48600 <= tod < 54000: return "Afternoon"
        elif 54000 <= tod < 57600: return "Close"
        return "Other"

    cycles_df["block"] = entry_tod.apply(assign_block)

    # Cap walks per cycle
    cw_counts = trades_df[trades_df["action"] == "CAP_WALK"].groupby("cycle_id").size()
    cycles_df["cap_walks"] = cycles_df["cycle_id"].map(cw_counts).fillna(0).astype(int)

    # Duration in seconds
    cycles_df["cycle_duration_s"] = (
        pd.to_datetime(cycles_df["exit_time"]) - pd.to_datetime(cycles_df["entry_time"])
    ).dt.total_seconds()

    # Select and rename columns for output
    out_df = cycles_df[[
        "cycle_id", "session_id", "entry_time", "exit_time", "direction",
        "gross_pnl_ticks", "net_pnl_ticks", "adds_count", "cap_walks",
        "max_position_qty", "max_level_reached",
        "mfe", "mae", "cycle_duration_s", "block",
        "stepdist_used", "adddist_used",
        "entry_price", "exit_price", "avg_entry_price",
        "exit_reason",
    ]].copy()

    # Add ml_used and cap_used (constant for this config)
    out_df["ml_used"] = 1
    out_df["cap_used"] = 2
    out_df["seeddist_used"] = 15.0

    # Save parquet
    parquet_path = _OUTPUT_DIR / "full_p1_base_cycles.parquet"
    out_df.to_parquet(str(parquet_path), index=False)
    print(f"  Saved: {parquet_path} ({len(out_df):,} cycles)")

    # Save config JSON
    config_path = _OUTPUT_DIR / "phase1_base_config.json"
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)
    print(f"  Saved: {config_path}")

    # --- Summary ---
    print(f"\n{'=' * 72}")
    print(f"PHASE 1 BASE CONFIG — FROZEN")
    print(f"{'=' * 72}")
    print(f"\n  Type:           Adaptive (rolling zigzag percentile)")
    print(f"  StepDist:       P90 of rolling 200-swing zigzag (floor 10)")
    print(f"  AddDist:        P75 of rolling 200-swing zigzag (floor 10)")
    print(f"  SeedDist:       15 pts (fixed, decoupled)")
    print(f"  ML:             1 (all adds = 1 contract)")
    print(f"  Position Cap:   2 (cap-walk at StepDist)")
    print(f"  Session:        09:30-16:00 ET (full RTH)")
    print(f"  Watch Mode:     rth_open (watch price = 09:30 first tick)")
    print(f"  Cap Action:     walk (anchor walks at cap, no flatten)")
    print(f"  Cost:           1 tick per side")
    print(f"  SpeedRead:      disabled (Phase 2)")
    print(f"  Feature Filters: none (Phase 2)")

    print(f"\n--- Performance (Full P1, no filters) ---")
    print(f"  Cycles:           {r['cycles']:,}")
    print(f"  Gross PF:         {r['gpf']:.4f}")
    print(f"  Net PF @1t:       {r['npf_1t']:.4f}")
    print(f"  Net PnL (ticks):  {r['net_pnl']:+,.0f}")
    print(f"  Clean %:          {r['clean_pct']:.1%}")
    print(f"  Mean MAE:         {r['mean_mae']:.2f} pts")
    print(f"  P75 MAE:          {r['p75_mae']:.2f} pts")
    print(f"  Max cycle loss:   {r['max_single_cycle_loss']:+,.0f} ticks")
    print(f"  Sessions:         {r['sessions']}")
    print(f"  Mean daily PnL:   {r['mean_daily']:+.1f} ticks")
    print(f"  StdDev daily:     {r['std_daily']:.1f} ticks")
    print(f"  Session win rate: {r['session_win_pct']:.1%}")
    print(f"  Cycles/hour:      {r['cycles_per_hour']:.2f}")
    print(f"  Cap walks:        {r['cap_walks']}")

    print(f"\n--- EV Components ---")
    print(f"  Clean:    {r['ev_clean']['pct']:.1%}  mean PnL={r['ev_clean']['mean_pnl']:+.1f}")
    print(f"  1-Add:    {r['ev_1add']['pct']:.1%}  mean PnL={r['ev_1add']['mean_pnl']:+.1f}  recover={r['ev_1add']['recover_pct']:.1%}")
    print(f"  Cap-Walk: {r['ev_capwalk']['pct']:.1%}  mean PnL={r['ev_capwalk']['mean_pnl']:+.1f}")

    print(f"\n--- Adaptive Ranges ---")
    print(f"  StepDist: {r['sd_range']['min']:.0f}-{r['sd_range']['max']:.0f} pts (mean={r['sd_range']['mean']:.1f})")
    print(f"  AddDist:  {r['ad_range']['min']:.0f}-{r['ad_range']['max']:.0f} pts (mean={r['ad_range']['mean']:.1f})")

    # --- Comparison vs SD=25/AD=25 baseline ---
    print(f"\n--- vs SD=25/AD=25 Baseline ---")
    baseline_path = _OUTPUT_DIR / "step1_full_p1_baseline.json"
    if baseline_path.exists():
        with open(baseline_path) as f:
            bl = json.load(f)
        print(f"  {'Metric':<20} {'Baseline':>12} {'Frozen':>12} {'Change':>10}")
        print(f"  {'-'*55}")
        for key, label in [("npf_1t", "Net PF"), ("net_pnl", "Net PnL"),
                           ("cycles", "Cycles"), ("mean_daily", "Mean Daily")]:
            old = bl.get(key, 0)
            new = r.get(key, 0)
            if isinstance(old, (int, float)) and isinstance(new, (int, float)) and old != 0:
                change = f"{(new - old) / abs(old) * 100:+.1f}%"
            else:
                change = "N/A"
            print(f"  {label:<20} {str(old):>12} {str(new):>12} {change:>10}")
    else:
        print(f"  (No baseline found for comparison)")

    # --- Positive EV confirmation ---
    if r["npf_1t"] >= 1.0:
        print(f"\n  CONFIRMED: Base config shows positive EV unfiltered (NPF={r['npf_1t']:.4f}).")
    else:
        print(f"\n  WARNING: NPF={r['npf_1t']:.4f} < 1.0. Base economics marginal.")

    # --- Phase 2 Queue ---
    print(f"\n{'=' * 72}")
    print(f"PHASE 2 QUEUE (refinements to test on this base config)")
    print(f"{'=' * 72}")
    phase2_queue = [
        "1. SpeedRead filter: seed and reversal SR thresholds",
        "2. Feature filters: regime detection, volatility gates",
        "3. Clock-time rolling window: Test clock-time based rolling window "
        "(e.g., last 60 minutes of zigzag swings) vs current 200-swing count "
        "window. Full RTH won Step 4, so intraday decay in zigzag amplitude "
        "is NOT handled by session restriction. The 200-swing window may "
        "overestimate P90 during afternoon using morning data when volatility "
        "was higher. A time-based window would adapt to intraday vol decay.",
        "4. P2 one-shot validation (frozen params, OOS)",
    ]
    for item in phase2_queue:
        print(f"  {item}")

    # Save Phase 2 queue to config
    config["phase2_queue"] = phase2_queue
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)

    # Save summary
    summary = {
        "frozen_config": config,
        "performance": r,
        "phase2_queue": phase2_queue,
        "files_saved": [
            str(parquet_path),
            str(config_path),
        ],
    }
    summary_path = _OUTPUT_DIR / "step5_summary.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2, default=str)
    print(f"\n  Saved summary: {summary_path}")

    print(f"\n  Phase 1 complete. P2 untouched. Ready for Phase 2 refinements.")

    return summary


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Phase 1 Sweep: Steps 2-5")
    parser.add_argument("--fixed-only", action="store_true",
                        help="Run fixed configs only (Step 2)")
    parser.add_argument("--adaptive-only", action="store_true",
                        help="Run adaptive configs only (Step 2)")
    parser.add_argument("--step2b", action="store_true",
                        help="Step 2b: ML/cap re-evaluation")
    parser.add_argument("--step3", action="store_true",
                        help="Step 3: SeedDist optimization")
    parser.add_argument("--step4", action="store_true",
                        help="Step 4: Session window optimization")
    parser.add_argument("--step5", action="store_true",
                        help="Step 5: Freeze base config and save outputs")
    args = parser.parse_args()

    if args.step2b:
        run_step2b()
    elif args.step3:
        run_step3()
    elif args.step4:
        run_step4()
    elif args.step5:
        run_step5()
    elif args.fixed_only:
        run_sweep(run_fixed=True, run_adaptive=False)
    elif args.adaptive_only:
        run_sweep(run_fixed=False, run_adaptive=True)
    else:
        run_sweep(run_fixed=True, run_adaptive=True)


if __name__ == "__main__":
    main()
