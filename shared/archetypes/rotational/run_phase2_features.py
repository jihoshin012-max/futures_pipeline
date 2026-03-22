# archetype: rotational
# STATUS: ONE-TIME
# PURPOSE: Phase 2 feature discovery on base cycles
# LAST RUN: 2026-03

"""Phase 2 Step 3: Feature Discovery on 10:00-16:00 base cycles.

Computes 17 entry-time features on Phase 1 base cycles and screens via
quintile analysis. Features must improve NPF by >3% when filtered or
they are dropped.

Usage:
    python run_phase2_features.py
"""

import sys
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import mannwhitneyu, spearmanr

_REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from run_seed_investigation import _P1_START, _P1_END, RTH_OPEN_TOD, FLATTEN_TOD

_OUTPUT_DIR = Path(__file__).parent / "phase1_results"
_250TICK_PATH = _REPO / "stages/01-data/data/bar_data/tick/NQ_BarData_250tick_rot_P1.csv"
_SR_PARQUET = Path(__file__).parent / "speedread_results" / "speedread_250tick.parquet"


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_cycles():
    """Load 10:00 start base cycles."""
    path = _OUTPUT_DIR / "full_p1_base_cycles_10am.parquet"
    df = pd.read_parquet(str(path))
    df["entry_time"] = pd.to_datetime(df["entry_time"])
    df["exit_time"] = pd.to_datetime(df["exit_time"])
    # Filter to RTH 10:00+ entries, exclude hours 1/19/20
    df["entry_hour"] = df["entry_time"].dt.hour
    df = df[~df["entry_hour"].isin({1, 19, 20})].copy()
    print(f"  Loaded {len(df):,} cycles from {path.name}")
    return df


def load_250tick_bars():
    """Load 250-tick bars, P1 dates, RTH only, with features pre-computed."""
    print("  Loading 250-tick bars...")
    df = pd.read_csv(str(_250TICK_PATH))
    df.columns = [c.strip() for c in df.columns]
    df["datetime"] = pd.to_datetime(df["Date"] + " " + df["Time"])
    df["date"] = df["datetime"].dt.date
    df = df[(df["date"] >= _P1_START) & (df["date"] <= _P1_END)].copy()
    tod = df["datetime"].dt.hour * 3600 + df["datetime"].dt.minute * 60
    df["tod"] = tod
    rth = df[(tod >= RTH_OPEN_TOD) & (tod < FLATTEN_TOD)].copy().reset_index(drop=True)
    print(f"  RTH bars: {len(rth):,}")
    return rth


def load_speedread_250():
    """Load SpeedRead composite aligned to 250-tick bars."""
    if not _SR_PARQUET.exists():
        print("  WARNING: SpeedRead parquet not found. Volume features will be NaN.")
        return None
    sr = pd.read_parquet(str(_SR_PARQUET))
    sr["datetime"] = pd.to_datetime(sr["datetime"])
    print(f"  SpeedRead 250-tick: {len(sr):,} bars")
    return sr


# ---------------------------------------------------------------------------
# Feature computation
# ---------------------------------------------------------------------------

def compute_bar_features(bars):
    """Compute bar-level features on 250-tick RTH bars.

    Returns bars DataFrame with added feature columns.
    """
    n = len(bars)
    close = bars["Last"].values.astype(np.float64)
    high = bars["High"].values.astype(np.float64)
    low = bars["Low"].values.astype(np.float64)
    volume = bars["Volume"].values.astype(np.float64)
    dates = bars["date"].values

    # --- Session VWAP ---
    hlc_avg = (high + low + close) / 3  # typical price
    cum_pv = np.zeros(n, dtype=np.float64)
    cum_vol = np.zeros(n, dtype=np.float64)
    for i in range(n):
        if i == 0 or dates[i] != dates[i - 1]:
            cum_pv[i] = hlc_avg[i] * volume[i]
            cum_vol[i] = volume[i]
        else:
            cum_pv[i] = cum_pv[i - 1] + hlc_avg[i] * volume[i]
            cum_vol[i] = cum_vol[i - 1] + volume[i]
    vwap = np.where(cum_vol > 0, cum_pv / cum_vol, close)
    bars["vwap"] = vwap
    bars["distance_vwap"] = close - vwap

    # --- ATR (14-bar) ---
    tr = np.maximum(high - low,
                    np.maximum(np.abs(high - np.roll(close, 1)),
                               np.abs(low - np.roll(close, 1))))
    tr[0] = high[0] - low[0]
    atr = pd.Series(tr).ewm(span=14, adjust=False).mean().values
    bars["atr"] = atr
    bars["distance_vwap_atr"] = np.where(atr > 0, bars["distance_vwap"] / atr, 0)

    # --- Session high/low/mid ---
    sess_high = np.zeros(n, dtype=np.float64)
    sess_low = np.zeros(n, dtype=np.float64)
    for i in range(n):
        if i == 0 or dates[i] != dates[i - 1]:
            sess_high[i] = high[i]
            sess_low[i] = low[i]
        else:
            sess_high[i] = max(sess_high[i - 1], high[i])
            sess_low[i] = min(sess_low[i - 1], low[i])
    sess_mid = (sess_high + sess_low) / 2
    bars["distance_session_mid"] = close - sess_mid

    # --- Zigzag structure features (from CSV columns) ---
    zz_len = bars["Zig Zag Line Length"].values.astype(np.float64)
    zz_rev = bars["Reversal Price"].values.astype(np.float64)
    zz_nbars = bars["Zig Zag Num Bars"].values.astype(np.float64)

    # Last completed swing info (track as we go)
    last_swing_len = np.full(n, np.nan)
    last_rev_price = np.full(n, np.nan)
    last_zz_nbars = np.full(n, np.nan)
    curr_sign = 0
    curr_max_len = 0.0
    curr_rev = 0.0
    curr_nbars = 0.0

    for i in range(n):
        v = zz_len[i]
        if v == 0:
            if curr_max_len > 0:
                # Swing just completed
                last_swing_len[i] = curr_max_len
                last_rev_price[i] = curr_rev
                last_zz_nbars[i] = curr_nbars
                curr_max_len = 0.0
                curr_sign = 0
            elif i > 0:
                last_swing_len[i] = last_swing_len[i - 1]
                last_rev_price[i] = last_rev_price[i - 1]
                last_zz_nbars[i] = last_zz_nbars[i - 1]
        else:
            s = 1 if v > 0 else -1
            av = abs(v)
            if s != curr_sign:
                if curr_max_len > 0:
                    last_swing_len[i] = curr_max_len
                    last_rev_price[i] = curr_rev
                    last_zz_nbars[i] = curr_nbars
                curr_sign = s
                curr_max_len = av
                curr_rev = zz_rev[i] if zz_rev[i] != 0 else (last_rev_price[i - 1] if i > 0 else np.nan)
                curr_nbars = zz_nbars[i]
            else:
                if av > curr_max_len:
                    curr_max_len = av
                    curr_nbars = zz_nbars[i]
                    if zz_rev[i] != 0:
                        curr_rev = zz_rev[i]
            if i > 0 and np.isnan(last_swing_len[i]):
                last_swing_len[i] = last_swing_len[i - 1]
                last_rev_price[i] = last_rev_price[i - 1]
                last_zz_nbars[i] = last_zz_nbars[i - 1]

    bars["last_swing_len"] = last_swing_len

    # retracement_pct: how much of the last swing has been retraced
    bars["zigzag_reversal_distance"] = np.abs(close - last_rev_price)
    bars["retracement_pct"] = np.where(
        last_swing_len > 0,
        bars["zigzag_reversal_distance"] / last_swing_len,
        np.nan
    )
    bars["zigzag_num_bars"] = last_zz_nbars

    # --- Session cumulative volume (for volume ratio) ---
    cum_sess_vol = np.zeros(n, dtype=np.float64)
    bar_in_session = np.zeros(n, dtype=np.int32)
    for i in range(n):
        if i == 0 or dates[i] != dates[i - 1]:
            cum_sess_vol[i] = volume[i]
            bar_in_session[i] = 1
        else:
            cum_sess_vol[i] = cum_sess_vol[i - 1] + volume[i]
            bar_in_session[i] = bar_in_session[i - 1] + 1

    # Average cumulative volume by bar-in-session (across all sessions)
    bis_df = pd.DataFrame({"bis": bar_in_session, "cv": cum_sess_vol})
    avg_cv = bis_df.groupby("bis")["cv"].mean()
    expected_vol = np.array([avg_cv.get(b, cum_sess_vol[i]) for i, b in enumerate(bar_in_session)])
    bars["session_volume_ratio"] = np.where(expected_vol > 0, cum_sess_vol / expected_vol, 1.0)

    # Timestamps for mapping
    bars["ts_ns"] = bars["datetime"].values.astype("int64")

    return bars


def compute_zigzag_rolling_stats(bars):
    """Compute rolling 200-swing mean and std from CSV zigzag."""
    zz_len = bars["Zig Zag Line Length"].values.astype(np.float64)
    dts = bars["datetime"].values

    # Extract completed swings
    swings = []
    curr_sign, curr_max = 0, 0.0
    for i in range(len(zz_len)):
        v = zz_len[i]
        if v == 0:
            if curr_max > 0:
                swings.append((dts[i], curr_max))
            curr_max, curr_sign = 0.0, 0
        else:
            s = 1 if v > 0 else -1
            av = abs(v)
            if s != curr_sign:
                if curr_max > 0:
                    swings.append((dts[i], curr_max))
                curr_sign, curr_max = s, av
            elif av > curr_max:
                curr_max = av
    if curr_max > 0:
        swings.append((dts[-1], curr_max))

    swing_dts = np.array([s[0] for s in swings])
    swing_lens = np.array([s[1] for s in swings], dtype=np.float64)

    WINDOW = 200
    n_pts = len(swing_lens) - WINDOW
    if n_pts <= 0:
        return np.array([]), np.array([]), np.array([])

    ts = np.empty(n_pts, dtype="int64")
    means = np.empty(n_pts, dtype=np.float64)
    stds = np.empty(n_pts, dtype=np.float64)
    p85s = np.empty(n_pts, dtype=np.float64)

    for j in range(n_pts):
        idx = WINDOW + j
        w = swing_lens[idx - WINDOW:idx]
        ts[j] = swing_dts[idx].astype("int64")
        means[j] = w.mean()
        stds[j] = w.std()
        p85s[j] = np.percentile(w, 85)

    return ts, means, stds, p85s


def map_cycles_to_bars(cycles, bars):
    """Map each cycle entry to the nearest preceding 250-tick bar.

    Returns array of bar indices (one per cycle).
    """
    cycle_ts = cycles["entry_time"].values.astype("int64")
    bar_ts = bars["ts_ns"].values
    # Find the last bar before or at each cycle entry
    bar_idx = np.searchsorted(bar_ts, cycle_ts, side="right") - 1
    bar_idx = np.clip(bar_idx, 0, len(bars) - 1)
    return bar_idx


def compute_all_features(cycles, bars, sr_df=None):
    """Compute all 17 features for each cycle entry.

    Returns DataFrame with feature columns added to cycles.
    """
    print("  Computing bar-level features...")
    bars = compute_bar_features(bars)

    print("  Computing zigzag rolling stats...")
    zz_ts, zz_means, zz_stds, zz_p85s = compute_zigzag_rolling_stats(bars)

    print("  Mapping cycles to bars...")
    bar_idx = map_cycles_to_bars(cycles, bars)
    cycles = cycles.copy()

    # --- Bar-level features (1-6, 10) ---
    for feat in ["distance_vwap", "distance_vwap_atr", "distance_session_mid",
                 "retracement_pct", "zigzag_num_bars", "zigzag_reversal_distance",
                 "session_volume_ratio", "atr"]:
        cycles[feat] = bars[feat].values[bar_idx]

    # --- Zigzag rolling stats (7-8) ---
    cycle_ts = cycles["entry_time"].values.astype("int64")
    zz_idx = np.searchsorted(zz_ts, cycle_ts, side="right") - 1
    zz_idx = np.clip(zz_idx, 0, len(zz_means) - 1)
    cycles["rotation_mean"] = zz_means[zz_idx]
    cycles["rotation_std"] = zz_stds[zz_idx]

    # --- Entry sigma level (9) — seed entries only ---
    # Approximate: (entry_price - watch_price) / rotation_std
    # We don't have watch_price directly; use seed_dist as proxy for distance from watch
    # For seeds: distance from watch = seed_dist (by definition)
    # For reversals: NaN
    is_seed = cycles["exit_reason"].shift(1).isna() | (cycles["exit_reason"].shift(1) == "daily_flatten")
    # Actually, check if first trade was a SEED — we have seeddist_used=15
    # entry_sigma_level = seeddist_used / rotation_std for all entries (approximation)
    cycles["entry_sigma_level"] = cycles["seeddist_used"] / cycles["rotation_std"]

    # --- SpeedRead volume rate (11) ---
    if sr_df is not None:
        sr_ts = sr_df["datetime"].values.astype("int64")
        sr_comp = sr_df["speedread_composite"].values.astype(np.float64)
        sr_idx = np.searchsorted(sr_ts, cycle_ts, side="right") - 1
        sr_idx = np.clip(sr_idx, 0, len(sr_df) - 1)
        cycles["volume_rate"] = sr_comp[sr_idx]
    else:
        cycles["volume_rate"] = np.nan

    # --- Path-dependent features (12-14) ---
    sess_pnl = []
    sess_count = []
    prior_pnl = []
    running_pnl = 0.0
    running_count = 0
    prev_session = None
    prev_net = 0.0

    for _, row in cycles.iterrows():
        sid = row["session_id"]
        if sid != prev_session:
            running_pnl = 0.0
            running_count = 0
            prev_session = sid
        sess_pnl.append(running_pnl)
        sess_count.append(running_count)
        prior_pnl.append(prev_net)
        running_pnl += row["net_pnl_ticks"]
        running_count += 1
        prev_net = row["net_pnl_ticks"]

    cycles["session_pnl"] = sess_pnl
    cycles["session_cycle_count"] = sess_count
    cycles["prior_cycle_pnl"] = prior_pnl

    # --- Cycle-level momentum features (15-17) ---
    CYCLE_WINDOW = 20

    # 15: clean_cycle_probability (rolling % of clean cycles)
    is_clean = (cycles["adds_count"] == 0).astype(float).values
    clean_prob = pd.Series(is_clean).rolling(CYCLE_WINDOW, min_periods=1).mean().values
    # Shift by 1 to avoid lookahead (use last 20 PRIOR cycles)
    cycles["clean_cycle_probability"] = np.roll(clean_prob, 1)
    cycles.iloc[0, cycles.columns.get_loc("clean_cycle_probability")] = np.nan

    # 16: current_sd_vs_p85
    sd_used = cycles["stepdist_used"].values
    zz_p85_at_entry = zz_p85s[zz_idx]
    cycles["current_sd_vs_p85"] = np.where(zz_p85_at_entry > 0, sd_used / zz_p85_at_entry, np.nan)

    # 17: mae_risk_ratio (rolling mean MAE / StepDist over last 20 cycles)
    mae_vals = cycles["mae"].values
    mae_roll = pd.Series(mae_vals).rolling(CYCLE_WINDOW, min_periods=1).mean().values
    mae_ratio = np.where(sd_used > 0, mae_roll / sd_used, np.nan)
    cycles["mae_risk_ratio"] = np.roll(mae_ratio, 1)
    cycles.iloc[0, cycles.columns.get_loc("mae_risk_ratio")] = np.nan

    return cycles


# ---------------------------------------------------------------------------
# Quintile screening
# ---------------------------------------------------------------------------

FEATURE_NAMES = [
    "distance_vwap", "distance_vwap_atr", "distance_session_mid",
    "retracement_pct", "zigzag_num_bars", "zigzag_reversal_distance",
    "rotation_mean", "rotation_std", "entry_sigma_level",
    "session_volume_ratio", "volume_rate",
    "session_pnl", "session_cycle_count", "prior_cycle_pnl",
    "clean_cycle_probability", "current_sd_vs_p85", "mae_risk_ratio",
]

PATH_DEPENDENT = {"session_pnl", "session_cycle_count", "prior_cycle_pnl"}


def quintile_analysis(cycles, feature_name, baseline_npf):
    """Run quintile analysis on a single feature.

    Returns dict with quintile stats, Spearman correlation, and verdict.
    """
    valid = cycles[[feature_name, "net_pnl_ticks", "gross_pnl_ticks"]].dropna()
    if len(valid) < 50:
        return {"feature": feature_name, "status": "insufficient_data", "n": len(valid)}

    # Quintile split
    try:
        valid["quintile"] = pd.qcut(valid[feature_name], 5, labels=[1, 2, 3, 4, 5], duplicates="drop")
    except ValueError:
        return {"feature": feature_name, "status": "cant_split", "n": len(valid)}

    quintiles = {}
    for q in sorted(valid["quintile"].unique()):
        qdf = valid[valid["quintile"] == q]
        gw = qdf.loc[qdf["net_pnl_ticks"] > 0, "net_pnl_ticks"].sum()
        gl = abs(qdf.loc[qdf["net_pnl_ticks"] <= 0, "net_pnl_ticks"].sum())
        npf = gw / gl if gl > 0 else (99.0 if gw > 0 else 0)
        ev = qdf["net_pnl_ticks"].mean()
        quintiles[int(q)] = {
            "n": len(qdf),
            "npf": round(npf, 4),
            "ev_per_cycle": round(float(ev), 2),
            "feature_range": f"{qdf[feature_name].min():.3f} - {qdf[feature_name].max():.3f}",
        }

    # Best quintile NPF improvement
    best_q = max(quintiles.values(), key=lambda x: x["npf"])
    worst_q = min(quintiles.values(), key=lambda x: x["npf"])
    npf_improvement = (best_q["npf"] - baseline_npf) / baseline_npf * 100 if baseline_npf > 0 else 0

    # Spearman correlation with gross PnL
    rho, p_rho = spearmanr(valid[feature_name], valid["gross_pnl_ticks"])

    # MWU: Q1 vs Q5
    q1 = valid[valid["quintile"] == valid["quintile"].min()]["net_pnl_ticks"]
    q5 = valid[valid["quintile"] == valid["quintile"].max()]["net_pnl_ticks"]
    if len(q1) > 5 and len(q5) > 5:
        _, mwu_p = mannwhitneyu(q1, q5, alternative="two-sided")
    else:
        mwu_p = 1.0

    # SpeedRead redundancy check
    if "volume_rate" in cycles.columns and feature_name != "volume_rate":
        sr_valid = cycles[[feature_name, "volume_rate"]].dropna()
        if len(sr_valid) > 50:
            sr_rho, _ = spearmanr(sr_valid[feature_name], sr_valid["volume_rate"])
        else:
            sr_rho = 0
    else:
        sr_rho = 0

    passed = npf_improvement > 3.0
    return {
        "feature": feature_name,
        "status": "evaluated",
        "n": len(valid),
        "quintiles": quintiles,
        "best_quintile_npf": best_q["npf"],
        "worst_quintile_npf": worst_q["npf"],
        "npf_spread": round(best_q["npf"] - worst_q["npf"], 4),
        "npf_improvement_pct": round(npf_improvement, 2),
        "spearman_rho": round(rho, 4),
        "spearman_p": round(p_rho, 6),
        "mwu_p": round(mwu_p, 6),
        "sr_correlation": round(sr_rho, 4),
        "sr_redundant": abs(sr_rho) > 0.7,
        "passed": passed,
        "path_dependent": feature_name in PATH_DEPENDENT,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("\n" + "=" * 72)
    print("PHASE 2 STEP 3: Feature Discovery (10:00-16:00 base cycles)")
    print("  17 features, quintile analysis, 3% NPF improvement threshold")
    print("=" * 72)

    t0 = time.time()
    cycles = load_cycles()
    bars = load_250tick_bars()
    sr_df = load_speedread_250()

    cycles = compute_all_features(cycles, bars, sr_df)
    print(f"  Feature computation: {time.time() - t0:.1f}s")

    # Baseline NPF
    gw = cycles.loc[cycles["net_pnl_ticks"] > 0, "net_pnl_ticks"].sum()
    gl = abs(cycles.loc[cycles["net_pnl_ticks"] <= 0, "net_pnl_ticks"].sum())
    baseline_npf = gw / gl if gl > 0 else 0
    print(f"\n  Baseline NPF: {baseline_npf:.4f} ({len(cycles)} cycles)")

    # Run quintile analysis for all 17 features
    results = []
    independent = []
    path_dep = []

    print(f"\n  {'#':>3} {'Feature':<28} {'NPF_sprd':>9} {'Best_Q':>7} {'Imprv%':>7} "
          f"{'Rho':>6} {'MWU_p':>7} {'SR_r':>6} {'Pass':>5}")
    print(f"  {'-'*90}")

    for i, feat in enumerate(FEATURE_NAMES):
        r = quintile_analysis(cycles, feat, baseline_npf)
        results.append(r)

        if r["status"] != "evaluated":
            print(f"  {i+1:>3} {feat:<28} -- {r['status']} (n={r['n']}) --")
            continue

        marker = "YES" if r["passed"] else "no"
        cat = "PATH" if r["path_dependent"] else ""
        print(f"  {i+1:>3} {feat:<28} {r['npf_spread']:>9.4f} {r['best_quintile_npf']:>7.4f} "
              f"{r['npf_improvement_pct']:>+7.1f}% {r['spearman_rho']:>6.3f} "
              f"{r['mwu_p']:>7.4f} {r['sr_correlation']:>6.3f} {marker:>5} {cat}")

        if r["path_dependent"]:
            path_dep.append(r)
        else:
            independent.append(r)

    # --- Summary ---
    print(f"\n" + "=" * 72)
    print("FEATURE DISCOVERY SUMMARY")
    print("=" * 72)

    passed_indep = [r for r in independent if r.get("passed")]
    passed_path = [r for r in path_dep if r.get("passed")]

    print(f"\n  Independent features passing 3% threshold ({len(passed_indep)}):")
    for r in sorted(passed_indep, key=lambda x: -x["npf_improvement_pct"]):
        print(f"    {r['feature']:<28} +{r['npf_improvement_pct']:.1f}% NPF, "
              f"best Q NPF={r['best_quintile_npf']:.4f}, rho={r['spearman_rho']:.3f}")
        if r["sr_redundant"]:
            print(f"      WARNING: SR correlation |r|={abs(r['sr_correlation']):.3f} > 0.7 — likely redundant with SpeedRead")

    print(f"\n  Path-dependent features passing 3% threshold ({len(passed_path)}):")
    for r in sorted(passed_path, key=lambda x: -x["npf_improvement_pct"]):
        print(f"    {r['feature']:<28} +{r['npf_improvement_pct']:.1f}% NPF, "
              f"best Q NPF={r['best_quintile_npf']:.4f}")

    # Quintile detail for top 3 features
    all_passed = sorted([r for r in results if r.get("passed")],
                        key=lambda x: -x.get("npf_improvement_pct", 0))
    if all_passed:
        print(f"\n  --- Top Feature Quintile Detail ---")
        for r in all_passed[:5]:
            print(f"\n  {r['feature']} (improvement={r['npf_improvement_pct']:+.1f}%):")
            for q, qd in sorted(r["quintiles"].items()):
                print(f"    Q{q}: n={qd['n']:>4}, NPF={qd['npf']:.4f}, "
                      f"EV/cyc={qd['ev_per_cycle']:+.1f}, range={qd['feature_range']}")

    # Save
    out_path = _OUTPUT_DIR / "phase2_feature_discovery.json"
    out_path.write_text(json.dumps(results, indent=2, default=str))
    print(f"\n  Saved: {out_path}")

    if not passed_indep and not passed_path:
        print(f"\n  VERDICT: No features pass 3% NPF threshold. Drop all feature filters.")
        print(f"  The base config with SR filter is the final config.")
    else:
        print(f"\n  VERDICT: {len(passed_indep)} independent + {len(passed_path)} path-dependent features pass.")
        print(f"  Test combined filters in Step 4 or adopt individually.")

    return results


if __name__ == "__main__":
    main()
