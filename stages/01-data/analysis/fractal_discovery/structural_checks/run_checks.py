#!/usr/bin/env python3
"""Structural verification checks for the rotation sweep.

Check 1: P1-only structural alignment -- compare 25->10 completion rates and
         swing distribution stats on P1 data vs full-sample baseline.
Check 2: Directional asymmetry -- split 25->10 completion rates by UP vs DOWN
         parent-scale moves on the full sample.

Uses pre-computed zigzag_results.pkl from fractal_01_prepare.py.
"""
import sys
from pathlib import Path

import numba as nb
import numpy as np
import pandas as pd
from scipy import stats as sp_stats

# Paths
FRACTAL_DIR = Path(__file__).resolve().parent.parent
PICKLE_PATH = FRACTAL_DIR / "zigzag_results.pkl"
OUT_DIR = Path(__file__).resolve().parent
OUT_DIR.mkdir(parents=True, exist_ok=True)

# P1 = sessions 0-59 (60 RTH days, Sept 22 – Dec 12, 2025)
P1_SID_MAX = 59

# Full-sample baseline values (from fractal_02_analyze.py output)
BASELINE_COMPLETION_1RET = 0.7968  # 79.7% at 1 retracement
BASELINE_MEDIAN_P90 = 0.520
BASELINE_SKEWNESS = 1.90


# ---------------------------------------------------------------------------
# Numba: child_walk_completion with direction tracking
# ---------------------------------------------------------------------------

@nb.njit(cache=True)
def child_walk_completion_with_dir(c_prices, c_dirs, c_sids, c_time_secs, parent_thresh):
    """Same as child_walk_completion but also returns attempt direction.

    Returns: (is_success, retrace_count, max_fav_frac, attempt_dir, anchor_ts)
    attempt_dir: +1 = UP attempt (price going up), -1 = DOWN attempt.
    """
    n = len(c_prices)
    mx = n // 2 + 1
    o_succ = np.empty(mx, dtype=nb.boolean)
    o_ret  = np.empty(mx, dtype=np.int32)
    o_fav  = np.empty(mx, dtype=np.float64)
    o_dir  = np.empty(mx, dtype=np.int8)
    o_ts   = np.empty(mx, dtype=np.float32)
    # Track duration (child swing steps from anchor to resolution)
    o_dur  = np.empty(mx, dtype=np.int32)
    cnt = 0

    i = 0
    while i < n - 1:
        cs = c_sids[i]
        anch_p = c_prices[i]
        anch_ts = c_time_secs[i]
        start_i = i

        i += 1
        if c_sids[i] != cs:
            continue

        disp = c_prices[i] - anch_p
        if disp == 0.0:
            continue

        att = np.int8(1) if disp > 0 else np.int8(-1)
        n_ret = np.int32(0)
        max_fav = abs(disp)
        prev_p = c_prices[i]

        # Immediate resolution
        if abs(disp) >= parent_thresh:
            o_succ[cnt] = True
            o_ret[cnt] = 0
            o_fav[cnt] = max_fav / parent_thresh
            o_dir[cnt] = att
            o_ts[cnt] = anch_ts
            o_dur[cnt] = np.int32(i - start_i)
            cnt += 1
            continue

        while True:
            i += 1
            if i >= n or c_sids[i] != cs:
                break
            prev_p = c_prices[i]
            disp = c_prices[i] - anch_p
            fav = disp * att
            if fav > max_fav:
                max_fav = fav
            if c_dirs[i] != att:
                n_ret += 1
            if fav >= parent_thresh:
                o_succ[cnt] = True
                o_ret[cnt] = n_ret
                o_fav[cnt] = max_fav / parent_thresh
                o_dir[cnt] = att
                o_ts[cnt] = anch_ts
                o_dur[cnt] = np.int32(i - start_i)
                cnt += 1
                break
            elif fav <= -parent_thresh:
                o_succ[cnt] = False
                o_ret[cnt] = n_ret
                o_fav[cnt] = max_fav / parent_thresh
                o_dir[cnt] = att
                o_ts[cnt] = anch_ts
                o_dur[cnt] = np.int32(i - start_i)
                cnt += 1
                break

    return (o_succ[:cnt], o_ret[:cnt], o_fav[:cnt],
            o_dir[:cnt], o_ts[:cnt], o_dur[:cnt])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def completion_rate_table(is_success, retrace_count, max_retrace=5):
    """Build completion rate table by retracement count."""
    rows = []
    for r in range(max_retrace):
        mask = retrace_count == r
        total = int(mask.sum())
        success = int(is_success[mask].sum()) if total > 0 else 0
        rate = success / total if total > 0 else 0.0
        rows.append({"retrace_count": r, "total": total, "success": success, "rate": round(rate, 6)})

    # 5+
    mask = retrace_count >= max_retrace
    total = int(mask.sum())
    success = int(is_success[mask].sum()) if total > 0 else 0
    rate = success / total if total > 0 else 0.0
    rows.append({"retrace_count": "5+", "total": total, "success": success, "rate": round(rate, 6)})

    return rows


def swing_size_stats(prices, sids):
    """Compute swing size distribution stats from consecutive swing prices.

    Only includes same-session pairs (excludes cross-session gaps which
    inflate skewness and distort the distribution).
    """
    same_sess = sids[:-1] == sids[1:]
    sizes = np.abs(np.diff(prices))[same_sess]
    if len(sizes) == 0:
        return {}
    return {
        "count": len(sizes),
        "mean": round(float(np.mean(sizes)), 2),
        "median": round(float(np.median(sizes)), 2),
        "p90": round(float(np.percentile(sizes, 90)), 2),
        "skewness": round(float(sp_stats.skew(sizes)), 4),
        "median_p90_ratio": round(float(np.median(sizes) / np.percentile(sizes, 90)), 4),
    }


# ---------------------------------------------------------------------------
# Check 1: P1-only alignment
# ---------------------------------------------------------------------------

def check1_p1_alignment(results: dict) -> pd.DataFrame:
    """Compare P1-only vs full-sample 25->10 completion rates and swing stats."""
    print("\n=== CHECK 1: P1-only Structural Alignment ===")

    # Get child (10pt) swings for RTH
    child = results[("RTH", 10)]
    c_prices = child["price"]
    c_dirs = child["dir"]
    c_sids = child["sid"]
    c_ts = child["time_secs"]

    # --- Full sample ---
    print("  Running child-walk (full sample)...")
    succ_full, ret_full, _, _, _, _ = child_walk_completion_with_dir(
        c_prices, c_dirs, c_sids, c_ts, 25.0
    )
    full_table = completion_rate_table(succ_full, ret_full)

    # --- P1 only (sid 0-59) ---
    p1_mask = c_sids <= P1_SID_MAX
    print(f"  P1 child swings: {p1_mask.sum():,} / {len(c_prices):,}")
    print("  Running child-walk (P1 only)...")
    succ_p1, ret_p1, _, _, _, _ = child_walk_completion_with_dir(
        c_prices[p1_mask], c_dirs[p1_mask], c_sids[p1_mask], c_ts[p1_mask], 25.0
    )
    p1_table = completion_rate_table(succ_p1, ret_p1)

    # --- Swing size stats at 25pt threshold ---
    sw25 = results[("RTH", 25)]
    full_stats = swing_size_stats(sw25["price"], sw25["sid"])

    p1_25_mask = sw25["sid"] <= P1_SID_MAX
    p1_stats = swing_size_stats(sw25["price"][p1_25_mask], sw25["sid"][p1_25_mask])

    print(f"\n  25pt swing stats (full):  median/P90={full_stats['median_p90_ratio']:.3f}, "
          f"skewness={full_stats['skewness']:.2f}")
    print(f"  25pt swing stats (P1):    median/P90={p1_stats['median_p90_ratio']:.3f}, "
          f"skewness={p1_stats['skewness']:.2f}")

    # Build comparison table
    rows = []
    for f_row, p_row in zip(full_table, p1_table):
        rc = f_row["retrace_count"]
        delta = p_row["rate"] - f_row["rate"]
        rows.append({
            "retrace_count": rc,
            "full_total": f_row["total"],
            "full_success": f_row["success"],
            "full_rate": f_row["rate"],
            "p1_total": p_row["total"],
            "p1_success": p_row["success"],
            "p1_rate": p_row["rate"],
            "delta_pp": round(delta * 100, 2),
        })

    df = pd.DataFrame(rows)

    # Print results
    print("\n  Completion rates (25->10, RTH, child-walk):")
    print(f"  {'Ret':>5s} {'Full':>8s} {'P1':>8s} {'Delta':>8s}")
    for _, row in df.iterrows():
        flag = " ***" if abs(row["delta_pp"]) > 5.0 and row["retrace_count"] != 0 else ""
        print(f"  {str(row['retrace_count']):>5s} {row['full_rate']:>8.4f} {row['p1_rate']:>8.4f} "
              f"{row['delta_pp']:>+7.2f}pp{flag}")

    # Verdicts
    rate_1ret_p1 = df.loc[df["retrace_count"] == 1, "p1_rate"].values[0]
    delta_1ret = abs(rate_1ret_p1 - BASELINE_COMPLETION_1RET) * 100

    print(f"\n  VERDICTS:")
    verdict_comp = "PASS" if delta_1ret <= 5.0 else "FLAG"
    print(f"    Completion rate (1-ret): P1={rate_1ret_p1:.4f} vs baseline={BASELINE_COMPLETION_1RET:.4f} "
          f"-> delta={delta_1ret:.1f}pp -> {verdict_comp}")

    med_p90_delta = abs(p1_stats["median_p90_ratio"] - BASELINE_MEDIAN_P90)
    verdict_ratio = "PASS" if med_p90_delta <= 0.05 else "FLAG"
    print(f"    Median/P90 ratio: P1={p1_stats['median_p90_ratio']:.3f} vs baseline={BASELINE_MEDIAN_P90:.3f} "
          f"-> delta={med_p90_delta:.3f} -> {verdict_ratio}")

    skew_delta = abs(p1_stats["skewness"] - BASELINE_SKEWNESS)
    verdict_skew = "PASS" if skew_delta <= 0.3 else "FLAG"
    print(f"    Skewness: P1={p1_stats['skewness']:.2f} vs baseline={BASELINE_SKEWNESS:.2f} "
          f"-> delta={skew_delta:.2f} -> {verdict_skew}")

    # Save
    df.to_csv(OUT_DIR / "p1_alignment.csv", index=False)
    print(f"\n  Saved: p1_alignment.csv")

    return df, {
        "completion_1ret": {"p1": rate_1ret_p1, "baseline": BASELINE_COMPLETION_1RET,
                            "delta_pp": round(delta_1ret, 2), "verdict": verdict_comp},
        "median_p90_ratio": {"p1": p1_stats["median_p90_ratio"], "baseline": BASELINE_MEDIAN_P90,
                             "delta": round(med_p90_delta, 4), "verdict": verdict_ratio},
        "skewness": {"p1": p1_stats["skewness"], "baseline": BASELINE_SKEWNESS,
                     "delta": round(skew_delta, 2), "verdict": verdict_skew},
    }


# ---------------------------------------------------------------------------
# Check 2: Directional asymmetry
# ---------------------------------------------------------------------------

def check2_directional_asymmetry(results: dict) -> pd.DataFrame:
    """Split 25->10 completion by UP vs DOWN direction on full sample."""
    print("\n=== CHECK 2: Directional Asymmetry (Full Sample, RTH) ===")

    child = results[("RTH", 10)]
    c_prices = child["price"]
    c_dirs = child["dir"]
    c_sids = child["sid"]
    c_ts = child["time_secs"]

    print("  Running child-walk with direction tracking...")
    succ, ret, fav, att_dir, ts, dur = child_walk_completion_with_dir(
        c_prices, c_dirs, c_sids, c_ts, 25.0
    )

    up_mask = att_dir == 1
    down_mask = att_dir == -1

    print(f"  UP attempts: {up_mask.sum():,}")
    print(f"  DOWN attempts: {down_mask.sum():,}")

    # Build tables per direction
    up_table = completion_rate_table(succ[up_mask], ret[up_mask])
    down_table = completion_rate_table(succ[down_mask], ret[down_mask])

    rows = []
    for u_row, d_row in zip(up_table, down_table):
        rc = u_row["retrace_count"]
        delta = u_row["rate"] - d_row["rate"]
        rows.append({
            "retrace_count": rc,
            "up_total": u_row["total"],
            "up_success": u_row["success"],
            "up_rate": u_row["rate"],
            "down_total": d_row["total"],
            "down_success": d_row["success"],
            "down_rate": d_row["rate"],
            "delta_pp": round(delta * 100, 2),
        })

    df = pd.DataFrame(rows)

    # Median swing duration per direction
    up_dur_med = float(np.median(dur[up_mask])) if up_mask.any() else 0.0
    down_dur_med = float(np.median(dur[down_mask])) if down_mask.any() else 0.0

    print(f"\n  Median swing duration (child steps): UP={up_dur_med:.0f}, DOWN={down_dur_med:.0f}")

    # Print
    print(f"\n  Completion rates (25->10, RTH, full sample):")
    print(f"  {'Ret':>5s} {'UP':>8s} {'DOWN':>8s} {'Delta':>8s}")
    for _, row in df.iterrows():
        flag = " ***" if abs(row["delta_pp"]) > 10.0 and row["retrace_count"] != 0 else ""
        print(f"  {str(row['retrace_count']):>5s} {row['up_rate']:>8.4f} {row['down_rate']:>8.4f} "
              f"{row['delta_pp']:>+7.2f}pp{flag}")

    # Verdict
    rate_1ret_up = df.loc[df["retrace_count"] == 1, "up_rate"].values[0]
    rate_1ret_down = df.loc[df["retrace_count"] == 1, "down_rate"].values[0]
    asym_delta = abs(rate_1ret_up - rate_1ret_down) * 100

    verdict = "PASS" if asym_delta <= 10.0 else "FLAG"
    print(f"\n  VERDICT:")
    print(f"    1-ret UP={rate_1ret_up:.4f} vs DOWN={rate_1ret_down:.4f} "
          f"-> delta={asym_delta:.1f}pp -> {verdict}")
    if asym_delta > 10.0:
        better = "UP" if rate_1ret_up > rate_1ret_down else "DOWN"
        print(f"    *** {better} moves complete significantly more often -- "
              f"consider asymmetric parameters for long vs short ***")

    # Add duration to the CSV as extra rows
    df["up_median_duration"] = up_dur_med
    df["down_median_duration"] = down_dur_med

    df.to_csv(OUT_DIR / "directional_asymmetry.csv", index=False)
    print(f"\n  Saved: directional_asymmetry.csv")

    return df, {
        "up_rate_1ret": rate_1ret_up,
        "down_rate_1ret": rate_1ret_down,
        "delta_pp": round(asym_delta, 2),
        "verdict": verdict,
        "up_count": int(up_mask.sum()),
        "down_count": int(down_mask.sum()),
        "up_median_duration": round(up_dur_med, 1),
        "down_median_duration": round(down_dur_med, 1),
    }


# ---------------------------------------------------------------------------
# Summary report
# ---------------------------------------------------------------------------

def write_summary(check1_verdicts: dict, check2_verdicts: dict) -> None:
    """Write structural_checks.md summary."""
    lines = [
        "# Structural Verification Checks",
        f"**Date:** {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}",
        f"**Data:** NQ 1-tick, RTH only",
        f"**P1 range:** Sept 22 – Dec 12, 2025 (60 RTH days, sessions 0–59)",
        f"**Full sample:** Sept 22, 2025 – Mar 2026 (120 RTH days)",
        "",
        "---",
        "",
        "## Check 1: P1-Only Structural Alignment",
        "",
        f"Does the P1 calibration window share the same structural properties as the",
        f"full sample that the fractal hypothesis was built on?",
        "",
        f"### 25->10 Completion Rate (1 retracement)",
        f"- **P1:** {check1_verdicts['completion_1ret']['p1']:.4f} "
        f"({check1_verdicts['completion_1ret']['p1']*100:.1f}%)",
        f"- **Baseline:** {check1_verdicts['completion_1ret']['baseline']:.4f} "
        f"({check1_verdicts['completion_1ret']['baseline']*100:.1f}%)",
        f"- **Delta:** {check1_verdicts['completion_1ret']['delta_pp']:.1f}pp",
        f"- **Verdict:** **{check1_verdicts['completion_1ret']['verdict']}** "
        f"(threshold: ±5pp)",
        "",
        f"### 25pt Swing Size Distribution",
        f"- **Median/P90 ratio:** P1={check1_verdicts['median_p90_ratio']['p1']:.3f} "
        f"vs baseline={check1_verdicts['median_p90_ratio']['baseline']:.3f} "
        f"(delta={check1_verdicts['median_p90_ratio']['delta']:.3f}) "
        f"-> **{check1_verdicts['median_p90_ratio']['verdict']}**",
        f"- **Skewness:** P1={check1_verdicts['skewness']['p1']:.2f} "
        f"vs baseline={check1_verdicts['skewness']['baseline']:.2f} "
        f"(delta={check1_verdicts['skewness']['delta']:.2f}) "
        f"-> **{check1_verdicts['skewness']['verdict']}**",
        "",
        "---",
        "",
        "## Check 2: Directional Asymmetry",
        "",
        "Do UP moves and DOWN moves complete at significantly different rates?",
        "",
        f"### 25->10 Completion Rate at 1 Retracement (Full Sample, RTH)",
        f"- **UP moves:** {check2_verdicts['up_rate_1ret']:.4f} "
        f"({check2_verdicts['up_rate_1ret']*100:.1f}%, n={check2_verdicts['up_count']:,})",
        f"- **DOWN moves:** {check2_verdicts['down_rate_1ret']:.4f} "
        f"({check2_verdicts['down_rate_1ret']*100:.1f}%, n={check2_verdicts['down_count']:,})",
        f"- **Delta:** {check2_verdicts['delta_pp']:.1f}pp",
        f"- **Verdict:** **{check2_verdicts['verdict']}** (threshold: ±10pp)",
        "",
        f"### Median Swing Duration (child steps)",
        f"- UP: {check2_verdicts['up_median_duration']:.0f} steps",
        f"- DOWN: {check2_verdicts['down_median_duration']:.0f} steps",
        "",
    ]

    # Overall verdict
    all_pass = all(v["verdict"] == "PASS" for v in [
        check1_verdicts["completion_1ret"],
        check1_verdicts["median_p90_ratio"],
        check1_verdicts["skewness"],
        check2_verdicts,
    ])
    lines.extend([
        "---",
        "",
        f"## Overall: **{'ALL PASS' if all_pass else 'FLAGS DETECTED -- review before Prompt 3'}**",
    ])

    (OUT_DIR / "structural_checks.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"\n  Saved: structural_checks.md")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    import pickle

    print("Loading zigzag_results.pkl...")
    with open(PICKLE_PATH, "rb") as f:
        results = pickle.load(f)
    print(f"  Loaded ({len(results)} entries)")

    # Warm up numba
    _p = np.array([100.0, 103.0, 100.0, 104.0], dtype=np.float64)
    _d = np.array([1, -1, 1, -1], dtype=np.int8)
    _s = np.array([0, 0, 0, 0], dtype=np.int32)
    _t = np.array([0.0, 1.0, 2.0, 3.0], dtype=np.float32)
    _ = child_walk_completion_with_dir(_p, _d, _s, _t, 3.0)
    del _p, _d, _s, _t

    _, check1_verdicts = check1_p1_alignment(results)
    _, check2_verdicts = check2_directional_asymmetry(results)
    write_summary(check1_verdicts, check2_verdicts)

    print("\n  STRUCTURAL CHECKS COMPLETE.")


if __name__ == "__main__":
    main()
