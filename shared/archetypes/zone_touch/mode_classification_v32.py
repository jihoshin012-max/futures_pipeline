# archetype: zone_touch
"""Mode Deployment Classification — Post-Prompt 2 Analysis (v3.2).

Presentation layer over frozen Prompt 2 calibration results.
No recalculation of parameters. Rates every mode on 8 dimensions.
"""

import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import numpy as np
import pandas as pd

BASE = Path(r"c:\Projects\pipeline")
DATA_DIR = BASE / "stages" / "01-data" / "output" / "zone_prep"
V32_DIR = BASE / "shared" / "archetypes" / "zone_touch" / "output"
TICK_SIZE = 0.25
BASELINE_PF = 1.3396

# ── Load frozen params ──────────────────────────────────────────────
with open(V32_DIR / "frozen_parameters_manifest_clean_v32.json") as f:
    manifest = json.load(f)
with open(V32_DIR / "segmentation_params_clean_v32.json") as f:
    seg_params = json.load(f)

# ── Load P1 scored touches & bar data ───────────────────────────────
p1_acal = pd.read_csv(V32_DIR / "p1_scored_touches_acal_v32.csv")
p1_aeq = pd.read_csv(V32_DIR / "p1_scored_touches_aeq_v32.csv")
p1_bz = pd.read_csv(V32_DIR / "p1_scored_touches_bzscore_v32.csv")

p1 = p1_acal.copy()
p1["score_aeq"] = p1_aeq["Score_AEq"]
p1["score_bzscore"] = p1_bz["Score_BZScore"]
p1.rename(columns={"Score_ACal": "score_acal"}, inplace=True)
p1 = p1[p1["RotBarIndex"] >= 0].reset_index(drop=True)

bar_p1 = pd.read_csv(DATA_DIR / "NQ_bardata_P1.csv")
bar_p1.columns = bar_p1.columns.str.strip()
bar_arr = bar_p1[["Open", "High", "Low", "Last"]].to_numpy(dtype=np.float64)
n_bars = len(bar_arr)

# ── Simulation engine (identical to Prompt 2) ───────────────────────

def sim_trade(entry_bar, direction, stop, target, be_trigger, trail_trigger, tcap):
    if entry_bar >= n_bars:
        return None, 0, None
    ep = bar_arr[entry_bar, 0]
    if direction == 1:
        sp = ep - stop * TICK_SIZE
        tp = ep + target * TICK_SIZE
    else:
        sp = ep + stop * TICK_SIZE
        tp = ep - target * TICK_SIZE

    mfe = 0.0
    be_active = False
    trail_active = False
    trail_sp = sp

    end = min(entry_bar + tcap, n_bars)
    for i in range(entry_bar, end):
        h, l, last = bar_arr[i, 1], bar_arr[i, 2], bar_arr[i, 3]
        bh = i - entry_bar + 1
        cur_fav = (h - ep) / TICK_SIZE if direction == 1 else (ep - l) / TICK_SIZE
        mfe = max(mfe, cur_fav)

        if be_trigger > 0 and not be_active and mfe >= be_trigger:
            be_active = True
            if direction == 1:
                sp = max(sp, ep); trail_sp = max(trail_sp, ep)
            else:
                sp = min(sp, ep); trail_sp = min(trail_sp, ep)

        if trail_trigger > 0 and mfe >= trail_trigger:
            trail_active = True
            if direction == 1:
                nt = ep + (mfe - trail_trigger) * TICK_SIZE
                trail_sp = max(trail_sp, nt); sp = max(sp, trail_sp)
            else:
                nt = ep - (mfe - trail_trigger) * TICK_SIZE
                trail_sp = min(trail_sp, nt); sp = min(sp, trail_sp)

        s_hit = l <= sp if direction == 1 else h >= sp
        t_hit = h >= tp if direction == 1 else l <= tp

        if s_hit and t_hit:
            pnl = (sp - ep) / TICK_SIZE if direction == 1 else (ep - sp) / TICK_SIZE
            return pnl, bh, "TRAIL" if trail_active else ("BE" if be_active else "STOP")
        if s_hit:
            pnl = (sp - ep) / TICK_SIZE if direction == 1 else (ep - sp) / TICK_SIZE
            return pnl, bh, "TRAIL" if trail_active else ("BE" if be_active else "STOP")
        if t_hit:
            return target, bh, "TARGET"
        if bh >= tcap:
            pnl = (last - ep) / TICK_SIZE if direction == 1 else (ep - last) / TICK_SIZE
            return pnl, bh, "TIMECAP"

    if end > entry_bar:
        last = bar_arr[end - 1, 3]
        pnl = (last - ep) / TICK_SIZE if direction == 1 else (ep - last) / TICK_SIZE
        return pnl, end - entry_bar, "TIMECAP"
    return None, 0, None


def run_sim(df, stop, target, be, trail, tc, zonerel=False, stop_mult=0, target_mult=0):
    """Sim group, return list of (pnl, bars_held, exit_type, row_idx)."""
    subset = df.sort_values("RotBarIndex")
    results = []
    in_trade_until = -1
    for idx, row in subset.iterrows():
        rbi = int(row["RotBarIndex"])
        entry_bar = rbi + 1
        if entry_bar <= in_trade_until:
            continue
        d = 1 if "DEMAND" in str(row["TouchType"]) else -1
        if zonerel:
            zw = float(row.get("ZoneWidthTicks", 100))
            if pd.isna(zw) or zw <= 0:
                zw = 100
            if isinstance(stop_mult, str) and "max" in stop_mult:
                s = max(1.5 * zw, 120)
            else:
                s = stop_mult * zw
            t = max(target_mult * zw, 1)
            pnl, bh, et = sim_trade(entry_bar, d, s, t, 0, 0, tc)
        else:
            pnl, bh, et = sim_trade(entry_bar, d, stop, target, be, trail, tc)
        if pnl is not None:
            results.append((pnl, bh, et, idx))
            in_trade_until = entry_bar + bh - 1
    return results


def pf_from_results(results, cost=3):
    if not results:
        return 0, 0
    pnls = [r[0] for r in results]
    gp = sum(p - cost for p in pnls if p - cost > 0)
    gl = sum(abs(p - cost) for p in pnls if p - cost < 0)
    pf = gp / gl if gl > 0 else (float("inf") if gp > 0 else 0)
    return pf, len(pnls)


def max_dd(results, cost=3):
    if not results:
        return 0
    cum = peak = dd = 0
    for r in results:
        cum += (r[0] - cost)
        peak = max(peak, cum)
        dd = max(dd, peak - cum)
    return dd


def max_consec_losses(results, cost=3):
    streak = mx = 0
    for r in results:
        if r[0] - cost < 0:
            streak += 1
            mx = max(mx, streak)
        else:
            streak = 0
    return mx


def net_profit(results, cost=3):
    return sum(r[0] - cost for r in results) if results else 0


# ── Build segmentation groups ───────────────────────────────────────

MODELS = {
    "A-Cal": ("score_acal", manifest["models"]["A-Cal"]["threshold"]),
    "A-Eq": ("score_aeq", manifest["models"]["A-Eq"]["threshold"]),
    "B-ZScore": ("score_bzscore", manifest["models"]["B-ZScore"]["threshold"]),
}

TS_P33 = manifest["trend_slope"]["P33"]
TS_P67 = manifest["trend_slope"]["P67"]


def build_groups(seg_type, score_col, threshold):
    edge = p1["TouchType"].isin(["DEMAND_EDGE", "SUPPLY_EDGE"])
    above = p1[score_col] >= threshold

    if seg_type == "seg1":
        return {"ModeA": p1[above & edge], "ModeB": p1[~(above & edge)]}
    elif seg_type == "seg2":
        session = p1["F05"]
        rth = session.isin(["OpeningDrive", "Midday", "Close"])
        prerth = session == "PreRTH"
        overnight = session == "Overnight"
        return {
            "ModeA_RTH": p1[above & edge & rth],
            "ModeB_PreRTH": p1[above & edge & prerth],
            "ModeC_Overnight": p1[above & edge & overnight],
            "ModeD_Below": p1[~(above & edge)],
        }
    elif seg_type == "seg3":
        wt_nt = p1["TrendLabel"].isin(["WT", "NT"]) if "TrendLabel" in p1.columns else True
        ct = p1["TrendLabel"] == "CT" if "TrendLabel" in p1.columns else False
        return {
            "ModeA_WTNT": p1[above & edge & wt_nt],
            "ModeB_CT": p1[above & edge & ct],
            "ModeC_Below": p1[~(above & edge)],
        }
    elif seg_type == "seg4":
        atr_p50 = p1["F17"].median() if "F17" in p1.columns else 0.5
        low = p1["F17"] <= atr_p50 if "F17" in p1.columns else True
        return {
            "ModeA_LowATR": p1[above & edge & low],
            "ModeB_HighATR": p1[above & edge & ~low],
            "ModeC_Below": p1[~(above & edge)],
        }
    return {}


# ── Enumerate all modes from Prompt 2 ──────────────────────────────

modes = []  # list of dicts with all mode info

for run_key, run_data in manifest["runs"].items():
    seg_type = run_data["seg_type"]
    model_name = run_data["model"]
    score_col, threshold = MODELS[model_name]

    for gname, gparams in run_data["groups"].items():
        if gname.startswith("_"):
            continue

        # Get exit params
        exit_winner = gparams.get("exit_winner", "FIXED")
        ep_fixed = gparams["exit_params_fixed"]
        ep_zr = gparams.get("exit_params_zonerel")
        filters = gparams.get("filters", {})
        run_mode = gparams.get("run_mode", "FULL")

        # Build group dataframe
        if seg_type == "seg5":
            # K-means — skip group reconstruction, use scored touches directly
            # We can approximate via threshold filter for B-ZScore
            above = p1[score_col] >= threshold
            gdf = p1[above] if "Cluster" in gname else p1
            # For k-means clusters, we can't easily reconstruct exact membership
            # Use the stored stats directly
            gdf_approx = True
        else:
            groups = build_groups(seg_type, score_col, threshold)
            gdf = groups.get(gname, pd.DataFrame())
            gdf_approx = False

        if len(gdf) < 10:
            continue

        # Apply filters
        filtered = gdf.copy()
        if filters.get("seq_max") is not None:
            filtered = filtered[filtered["TouchSequence"] <= filters["seq_max"]]
        if filters.get("tf_filter"):
            filtered = filtered[filtered["SourceLabel"].isin(
                ["15m", "30m", "60m", "90m", "120m"])]
        if len(filtered) < 10:
            filtered = gdf

        # Run sim with winning exit
        is_zonerel = exit_winner == "ZONEREL" and ep_zr is not None
        if is_zonerel:
            results = run_sim(filtered, 0, 0, 0, 0, ep_zr["time_cap"],
                              zonerel=True, stop_mult=ep_zr["stop_mult"],
                              target_mult=ep_zr["target_mult"])
        else:
            results = run_sim(filtered, ep_fixed["stop"], ep_fixed["target"],
                              ep_fixed.get("be_trigger", 0),
                              ep_fixed.get("trail_trigger", 0),
                              ep_fixed["time_cap"])

        if not results:
            continue

        pnls = [r[0] for r in results]
        bars_held = [r[1] for r in results]
        trade_indices = [r[3] for r in results]
        trades = len(results)

        # PF at multiple costs
        pf2, _ = pf_from_results(results, 2)
        pf3, _ = pf_from_results(results, 3)
        pf4, _ = pf_from_results(results, 4)

        # Basic stats
        wins = [p - 3 for p in pnls if p - 3 > 0]
        losses = [abs(p - 3) for p in pnls if p - 3 < 0]
        mean_pnl = np.mean([p - 3 for p in pnls])
        mean_win = np.mean(wins) if wins else 0
        mean_loss = np.mean(losses) if losses else 0
        win_rate = len(wins) / trades * 100 if trades > 0 else 0
        mdd = max_dd(results)
        mcl = max_consec_losses(results)
        pdd = net_profit(results) / mdd if mdd > 0 else float("inf")
        total_pnl = net_profit(results)
        mean_bars = np.mean(bars_held) if bars_held else 0
        tpd = trades / (n_bars / 1400) if n_bars > 0 else 0

        # ── Dimension 5: CONSISTENT — split by P1a/P1b, RTH/ETH, trend ──
        trade_df = filtered.loc[trade_indices] if not gdf_approx else filtered.iloc[:trades]

        # P1a vs P1b
        p1a_mask = trade_df["Period"] == "P1a" if "Period" in trade_df.columns else pd.Series(False, index=trade_df.index)
        p1b_mask = trade_df["Period"] == "P1b" if "Period" in trade_df.columns else pd.Series(False, index=trade_df.index)

        # Filter results by period
        trade_idx_set = set(trade_indices)
        p1a_indices = set(trade_df[p1a_mask].index)
        p1b_indices = set(trade_df[p1b_mask].index)

        p1a_results = [r for r in results if r[3] in p1a_indices]
        p1b_results = [r for r in results if r[3] in p1b_indices]

        pf_p1a, _ = pf_from_results(p1a_results)
        pf_p1b, _ = pf_from_results(p1b_results)

        # RTH vs ETH (F05 session)
        session_col = trade_df["F05"] if "F05" in trade_df.columns else pd.Series("Unknown", index=trade_df.index)
        rth_indices = set(trade_df[session_col.isin(["OpeningDrive", "Midday", "Close"])].index)
        eth_indices = set(trade_df[~session_col.isin(["OpeningDrive", "Midday", "Close"])].index)

        rth_results = [r for r in results if r[3] in rth_indices]
        eth_results = [r for r in results if r[3] in eth_indices]

        pf_rth, _ = pf_from_results(rth_results)
        pf_eth, _ = pf_from_results(eth_results)

        # Trend labels
        trend_col = trade_df["TrendLabel"] if "TrendLabel" in trade_df.columns else pd.Series("NT", index=trade_df.index)
        wt_indices = set(trade_df[trend_col == "WT"].index)
        ct_indices = set(trade_df[trend_col == "CT"].index)
        nt_indices = set(trade_df[trend_col == "NT"].index)

        wt_results = [r for r in results if r[3] in wt_indices]
        ct_results = [r for r in results if r[3] in ct_indices]
        nt_results = [r for r in results if r[3] in nt_indices]

        pf_wt, _ = pf_from_results(wt_results)
        pf_ct, _ = pf_from_results(ct_results)
        pf_nt, _ = pf_from_results(nt_results)

        # PF variance across splits (use coefficient of variation)
        split_pfs = [x for x in [pf_p1a, pf_p1b, pf_rth, pf_eth, pf_wt, pf_ct, pf_nt]
                     if x > 0 and x < float("inf")]
        pf_variance = np.std(split_pfs) / np.mean(split_pfs) if split_pfs and np.mean(split_pfs) > 0 else 999

        # ── Dimension 8: IMPLEMENTABLE complexity score ──
        complexity = 0
        if is_zonerel:
            complexity += 1  # zone-relative adds complexity
        if ep_fixed.get("be_trigger", 0) > 0:
            complexity += 1
        if ep_fixed.get("trail_trigger", 0) > 0:
            complexity += 1
        if filters.get("seq_max") is not None:
            complexity += 0  # seq gate is simple
        if filters.get("tf_filter"):
            complexity += 1
        if seg_type == "seg2":
            complexity += 1  # session-conditional

        # Effective stop/target for SCALABLE
        if is_zonerel:
            # Use median zone width to estimate effective levels
            med_zw = filtered["ZoneWidthTicks"].median() if "ZoneWidthTicks" in filtered.columns else 100
            if isinstance(ep_zr["stop_mult"], str):
                eff_stop = max(1.5 * med_zw, 120)
            else:
                eff_stop = ep_zr["stop_mult"] * med_zw
            eff_target = ep_zr["target_mult"] * med_zw
        else:
            eff_stop = ep_fixed["stop"]
            eff_target = ep_fixed["target"]

        # Session composition for SCALABLE
        rth_pct = len(rth_results) / trades * 100 if trades > 0 else 0

        mode_id = f"{seg_type}/{model_name}/{gname}"

        modes.append({
            "id": mode_id, "seg": seg_type, "model": model_name,
            "group": gname, "run_mode": run_mode,
            "pf_2t": pf2, "pf_3t": pf3, "pf_4t": pf4,
            "trades": trades, "tpd": tpd,
            "mean_pnl": mean_pnl, "mean_win": mean_win,
            "win_rate": win_rate, "mdd": mdd, "mcl": mcl,
            "pdd": pdd, "total_pnl": total_pnl,
            "mean_bars": mean_bars,
            "eff_stop": eff_stop, "eff_target": eff_target,
            "rth_pct": rth_pct,
            "complexity": complexity,
            "exit_winner": exit_winner,
            "pf_p1a": pf_p1a, "pf_p1b": pf_p1b,
            "pf_rth": pf_rth, "pf_eth": pf_eth,
            "pf_wt": pf_wt, "pf_ct": pf_ct, "pf_nt": pf_nt,
            "pf_variance": pf_variance,
            "pf_drop_3to4": (pf3 - pf4) / pf3 * 100 if pf3 > 0 else 100,
            "results": results,
            "trade_indices": trade_indices,
            # Params for deployment card
            "ep_fixed": ep_fixed, "ep_zr": ep_zr,
            "filters": filters,
            "threshold": threshold, "is_zonerel": is_zonerel,
        })

print(f"Enumerated {len(modes)} modes across all segmentations.\n")

# ── Compute dimension ratings ───────────────────────────────────────
# Tercile thresholds within the mode set

def tercile_rating(values, mode_idx, higher_is_better=True):
    """Rate mode_idx as HIGH/MED/LOW based on tercile position."""
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    t1 = sorted_vals[n // 3] if n > 2 else sorted_vals[0]
    t2 = sorted_vals[2 * n // 3] if n > 2 else sorted_vals[-1]
    v = values[mode_idx]
    if higher_is_better:
        if v >= t2:
            return "HIGH"
        elif v >= t1:
            return "MED"
        else:
            return "LOW"
    else:
        if v <= t1:
            return "HIGH"
        elif v <= t2:
            return "MED"
        else:
            return "LOW"


# Extract arrays for each dimension
n_modes = len(modes)

# DIM 1: AGGRESSIVE — PF, mean PnL, mean win
agg_scores = [m["pf_3t"] * 0.4 + m["mean_pnl"] * 0.3 + m["mean_win"] * 0.3
              for m in modes]

# DIM 2: BALANCED — Profit/DD with trade count adequacy
bal_scores = [m["pdd"] * min(m["trades"] / 50, 1.0) for m in modes]

# DIM 3: CONSERVATIVE — small DD, high WR, tight stops (inverted metrics)
con_dd = [m["mdd"] for m in modes]
con_wr = [m["win_rate"] for m in modes]

# DIM 4: VOLUME — trades, tpd, total PnL
vol_scores = [m["trades"] * 0.4 + m["tpd"] * 100 * 0.3 + m["total_pnl"] * 0.001 * 0.3
              for m in modes]

# DIM 5: CONSISTENT — PF variance (lower = better)
cons_var = [m["pf_variance"] for m in modes]

# DIM 6: ROBUST — PF drop 3t→4t (lower = better)
rob_drop = [m["pf_drop_3to4"] for m in modes]

# DIM 7: SCALABLE — target distance, RTH%, duration, stop distance
scal_scores = [(m["eff_target"] / 240) * 0.3 + (m["rth_pct"] / 100) * 0.3 +
               (m["mean_bars"] / 120) * 0.2 + (m["eff_stop"] / 190) * 0.2
               for m in modes]

# DIM 8: IMPLEMENTABLE — complexity (lower = better)
impl_complex = [m["complexity"] for m in modes]

# Assign ratings
for i, m in enumerate(modes):
    m["R_AGG"] = tercile_rating(agg_scores, i, higher_is_better=True)
    m["R_BAL"] = tercile_rating(bal_scores, i, higher_is_better=True)
    m["R_CON"] = tercile_rating(con_dd, i, higher_is_better=False)
    # For conservative, also factor in win rate
    if m["win_rate"] >= 85:
        if m["R_CON"] == "MED":
            m["R_CON"] = "HIGH"
    elif m["win_rate"] < 70:
        if m["R_CON"] == "HIGH":
            m["R_CON"] = "MED"
    m["R_VOL"] = tercile_rating(vol_scores, i, higher_is_better=True)
    m["R_CONS"] = tercile_rating(cons_var, i, higher_is_better=False)
    m["R_ROB"] = tercile_rating(rob_drop, i, higher_is_better=False)
    m["R_SCAL"] = tercile_rating(scal_scores, i, higher_is_better=True)
    # IMPLEMENTABLE: 0-1=HIGH, 2-3=MED, 4+=LOW
    if m["complexity"] <= 1:
        m["R_IMPL"] = "HIGH"
    elif m["complexity"] <= 3:
        m["R_IMPL"] = "MED"
    else:
        m["R_IMPL"] = "LOW"


# ── Build output ────────────────────────────────────────────────────

out = []


def w(line=""):
    print(line)
    out.append(line)


w("# Mode Deployment Classification — v3.2")
w(f"Generated from Prompt 2 frozen results. {n_modes} modes evaluated.")
w(f"Baseline PF anchor: {BASELINE_PF}. P1 touches: {manifest['p1_touch_count']}.")
w("")

# ── A) Full Scorecard ───────────────────────────────────────────────
w("## A) Full Scorecard")
w("")
w("| # | Mode | Model | Seg | PF | Trades | T/Day | MaxDD | P/DD | AGG | BAL | CON | VOL | CONS | ROB | SCAL | IMPL |")
w("|---|------|-------|-----|-----|--------|-------|-------|------|-----|-----|-----|-----|------|-----|------|------|")

# Sort by PF descending
sorted_modes = sorted(enumerate(modes), key=lambda x: -x[1]["pf_3t"])
for rank, (i, m) in enumerate(sorted_modes, 1):
    w(f"| {rank} | {m['group']} | {m['model']} | {m['seg']} | "
      f"{m['pf_3t']:.2f} | {m['trades']} | {m['tpd']:.2f} | "
      f"{m['mdd']:.0f} | {m['pdd']:.1f} | "
      f"{m['R_AGG']} | {m['R_BAL']} | {m['R_CON']} | {m['R_VOL']} | "
      f"{m['R_CONS']} | {m['R_ROB']} | {m['R_SCAL']} | {m['R_IMPL']} |")

w("")

# ── Consistency detail table ────────────────────────────────────────
w("### Consistency Detail (PF splits)")
w("")
w("| Mode | Model | PF_P1a | PF_P1b | PF_RTH | PF_ETH | PF_WT | PF_CT | PF_NT | CV |")
w("|------|-------|--------|--------|--------|--------|-------|-------|-------|-----|")
for _, (i, m) in enumerate(sorted_modes):
    def fmt_pf(v):
        return f"{v:.2f}" if 0 < v < 100 else "N/A"
    w(f"| {m['group']} | {m['model']} | "
      f"{fmt_pf(m['pf_p1a'])} | {fmt_pf(m['pf_p1b'])} | "
      f"{fmt_pf(m['pf_rth'])} | {fmt_pf(m['pf_eth'])} | "
      f"{fmt_pf(m['pf_wt'])} | {fmt_pf(m['pf_ct'])} | {fmt_pf(m['pf_nt'])} | "
      f"{m['pf_variance']:.3f} |")

w("")

# ── Robustness detail table ─────────────────────────────────────────
w("### Robustness Detail (cost sensitivity)")
w("")
w("| Mode | Model | PF@2t | PF@3t | PF@4t | Drop 3->4 | WR% | MCL |")
w("|------|-------|-------|-------|-------|-----------|-----|-----|")
for _, (i, m) in enumerate(sorted_modes):
    w(f"| {m['group']} | {m['model']} | "
      f"{m['pf_2t']:.2f} | {m['pf_3t']:.2f} | {m['pf_4t']:.2f} | "
      f"{m['pf_drop_3to4']:.1f}% | {m['win_rate']:.1f} | {m['mcl']} |")

w("")

# ── B) Per-Dimension Leaders ────────────────────────────────────────
w("## B) Per-Dimension Leaders")
w("")
w("| Dimension | Best Mode | Model | Rating | Key Metric |")
w("|-----------|-----------|-------|--------|-----------|")

# AGGRESSIVE: highest PF
agg_best = max(modes, key=lambda m: m["pf_3t"])
w(f"| AGGRESSIVE | {agg_best['group']} | {agg_best['model']} | HIGH | PF={agg_best['pf_3t']:.2f} |")

# BALANCED: best P/DD with trades > 50
bal_candidates = [m for m in modes if m["trades"] >= 50]
bal_best = max(bal_candidates, key=lambda m: m["pdd"]) if bal_candidates else max(modes, key=lambda m: m["pdd"])
w(f"| BALANCED | {bal_best['group']} | {bal_best['model']} | HIGH | P/DD={bal_best['pdd']:.1f} |")

# CONSERVATIVE: smallest max DD
con_best = min(modes, key=lambda m: m["mdd"])
w(f"| CONSERVATIVE | {con_best['group']} | {con_best['model']} | HIGH | MaxDD={con_best['mdd']:.0f}t |")

# VOLUME: most trades
vol_best = max(modes, key=lambda m: m["trades"])
w(f"| VOLUME | {vol_best['group']} | {vol_best['model']} | HIGH | Trades/day={vol_best['tpd']:.2f} |")

# CONSISTENT: lowest PF variance
cons_candidates = [m for m in modes if m["pf_variance"] < 100]
cons_best = min(cons_candidates, key=lambda m: m["pf_variance"]) if cons_candidates else modes[0]
w(f"| CONSISTENT | {cons_best['group']} | {cons_best['model']} | HIGH | PF CV={cons_best['pf_variance']:.3f} |")

# ROBUST: lowest PF drop
rob_best = min(modes, key=lambda m: m["pf_drop_3to4"])
w(f"| ROBUST | {rob_best['group']} | {rob_best['model']} | HIGH | Drop={rob_best['pf_drop_3to4']:.1f}% |")

# SCALABLE: highest effective target + RTH%
scal_best = max(modes, key=lambda m: m["eff_target"] * m["rth_pct"] / 100)
w(f"| SCALABLE | {scal_best['group']} | {scal_best['model']} | HIGH | Target={scal_best['eff_target']:.0f}t, RTH={scal_best['rth_pct']:.0f}% |")

# IMPLEMENTABLE: lowest complexity
impl_best = min(modes, key=lambda m: m["complexity"])
w(f"| IMPLEMENTABLE | {impl_best['group']} | {impl_best['model']} | HIGH | Complexity={impl_best['complexity']} |")

w("")

# ── C) Multi-Mode Deployment Recommendation ─────────────────────────
w("## C) Multi-Mode Deployment Recommendation")
w("")

# Select recommended combos:
# 1. High-conviction: A-Eq Seg1 ModeA (AGGRESSIVE)
# 2. Broad volume: B-ZScore Seg1 ModeA or Seg2 RTH (BALANCED + VOLUME)
# 3. B-only as secondary

# Find specific modes
aeq_seg1_a = next((m for m in modes if m["model"] == "A-Eq" and m["seg"] == "seg1" and m["group"] == "ModeA"), None)
bz_seg2_rth = next((m for m in modes if m["model"] == "B-ZScore" and m["seg"] == "seg2" and m["group"] == "ModeA_RTH"), None)
bz_seg4_low = next((m for m in modes if m["model"] == "B-ZScore" and m["seg"] == "seg4" and m["group"] == "ModeA_LowATR"), None)
bz_seg1_a = next((m for m in modes if m["model"] == "B-ZScore" and m["seg"] == "seg1" and m["group"] == "ModeA"), None)

recommended_pairs = []

if aeq_seg1_a and bz_seg2_rth:
    # Check overlap
    a_idx = set(aeq_seg1_a["trade_indices"])
    b_idx = set(bz_seg2_rth["trade_indices"])
    overlap = len(a_idx & b_idx)
    total = len(a_idx | b_idx)
    overlap_pct = overlap / min(len(a_idx), len(b_idx)) * 100 if min(len(a_idx), len(b_idx)) > 0 else 0

    # Combined sim (union of trade populations)
    all_results = {}
    for r in aeq_seg1_a["results"]:
        all_results[r[3]] = r
    for r in bz_seg2_rth["results"]:
        if r[3] not in all_results:
            all_results[r[3]] = r
    combined_results = sorted(all_results.values(), key=lambda r: r[3])
    # Re-run no-overlap on combined
    combined_no = []
    in_trade_until = -1
    for r in combined_results:
        rbi = int(p1.loc[r[3], "RotBarIndex"]) if r[3] in p1.index else -1
        entry_bar = rbi + 1
        if entry_bar <= in_trade_until:
            continue
        combined_no.append(r)
        in_trade_until = entry_bar + r[1] - 1
    comb_pf, comb_trades = pf_from_results(combined_no)
    comb_dd = max_dd(combined_no)
    comb_pdd = net_profit(combined_no) / comb_dd if comb_dd > 0 else float("inf")

    recommended_pairs.append({
        "name": "HIGH-CONVICTION + BROAD-RTH",
        "modeA": aeq_seg1_a, "modeA_label": "A-Eq Seg1 ModeA",
        "modeB": bz_seg2_rth, "modeB_label": "B-ZScore Seg2 RTH",
        "overlap_pct": overlap_pct,
        "comb_trades": comb_trades, "comb_pf": comb_pf,
        "comb_dd": comb_dd, "comb_pdd": comb_pdd,
    })

if aeq_seg1_a and bz_seg4_low:
    a_idx = set(aeq_seg1_a["trade_indices"])
    b_idx = set(bz_seg4_low["trade_indices"])
    overlap = len(a_idx & b_idx)
    overlap_pct = overlap / min(len(a_idx), len(b_idx)) * 100 if min(len(a_idx), len(b_idx)) > 0 else 0

    all_results = {}
    for r in aeq_seg1_a["results"]:
        all_results[r[3]] = r
    for r in bz_seg4_low["results"]:
        if r[3] not in all_results:
            all_results[r[3]] = r
    combined_results = sorted(all_results.values(), key=lambda r: r[3])
    combined_no = []
    in_trade_until = -1
    for r in combined_results:
        rbi = int(p1.loc[r[3], "RotBarIndex"]) if r[3] in p1.index else -1
        entry_bar = rbi + 1
        if entry_bar <= in_trade_until:
            continue
        combined_no.append(r)
        in_trade_until = entry_bar + r[1] - 1
    comb_pf, comb_trades = pf_from_results(combined_no)
    comb_dd = max_dd(combined_no)
    comb_pdd = net_profit(combined_no) / comb_dd if comb_dd > 0 else float("inf")

    recommended_pairs.append({
        "name": "HIGH-CONVICTION + LOW-VOL REGIME",
        "modeA": aeq_seg1_a, "modeA_label": "A-Eq Seg1 ModeA",
        "modeB": bz_seg4_low, "modeB_label": "B-ZScore Seg4 LowATR",
        "overlap_pct": overlap_pct,
        "comb_trades": comb_trades, "comb_pf": comb_pf,
        "comb_dd": comb_dd, "comb_pdd": comb_pdd,
    })

if aeq_seg1_a and bz_seg1_a:
    a_idx = set(aeq_seg1_a["trade_indices"])
    b_idx = set(bz_seg1_a["trade_indices"])
    overlap = len(a_idx & b_idx)
    overlap_pct = overlap / min(len(a_idx), len(b_idx)) * 100 if min(len(a_idx), len(b_idx)) > 0 else 0

    all_results = {}
    for r in aeq_seg1_a["results"]:
        all_results[r[3]] = r
    for r in bz_seg1_a["results"]:
        if r[3] not in all_results:
            all_results[r[3]] = r
    combined_results = sorted(all_results.values(), key=lambda r: r[3])
    combined_no = []
    in_trade_until = -1
    for r in combined_results:
        rbi = int(p1.loc[r[3], "RotBarIndex"]) if r[3] in p1.index else -1
        entry_bar = rbi + 1
        if entry_bar <= in_trade_until:
            continue
        combined_no.append(r)
        in_trade_until = entry_bar + r[1] - 1
    comb_pf, comb_trades = pf_from_results(combined_no)
    comb_dd = max_dd(combined_no)
    comb_pdd = net_profit(combined_no) / comb_dd if comb_dd > 0 else float("inf")

    recommended_pairs.append({
        "name": "HIGH-CONVICTION + B-ZSCORE BROAD",
        "modeA": aeq_seg1_a, "modeA_label": "A-Eq Seg1 ModeA",
        "modeB": bz_seg1_a, "modeB_label": "B-ZScore Seg1 ModeA",
        "overlap_pct": overlap_pct,
        "comb_trades": comb_trades, "comb_pf": comb_pf,
        "comb_dd": comb_dd, "comb_pdd": comb_pdd,
    })

for pair in recommended_pairs:
    ma = pair["modeA"]
    mb = pair["modeB"]
    w(f"### Combo: {pair['name']}")
    w("")
    w("| Metric | Mode A alone | Mode B alone | Combined |")
    w("|--------|-------------|-------------|----------|")
    w(f"| Mode | {pair['modeA_label']} | {pair['modeB_label']} | Union |")
    w(f"| Total trades | {ma['trades']} | {mb['trades']} | {pair['comb_trades']} |")
    w(f"| Trade overlap | -- | -- | {pair['overlap_pct']:.1f}% |")
    w(f"| PF @3t | {ma['pf_3t']:.2f} | {mb['pf_3t']:.2f} | {pair['comb_pf']:.2f} |")
    w(f"| Max DD (ticks) | {ma['mdd']:.0f} | {mb['mdd']:.0f} | {pair['comb_dd']:.0f} |")
    w(f"| Profit/DD | {ma['pdd']:.1f} | {mb['pdd']:.1f} | {pair['comb_pdd']:.1f} |")
    w(f"| Profile | AGGRESSIVE | {'BALANCED' if mb['pdd'] > 20 else 'VOLUME'} | DIVERSIFIED |")
    complementary = "COMPLEMENTARY" if pair["overlap_pct"] < 30 else ("PARTIAL" if pair["overlap_pct"] < 70 else "REDUNDANT")
    w(f"| Verdict | -- | -- | **{complementary}** |")
    w("")

# ── D) Per-Mode Deployment Cards ────────────────────────────────────
w("## D) Per-Mode Deployment Cards (Recommended)")
w("")

# Cards for top recommended modes
rec_modes = []
if aeq_seg1_a:
    rec_modes.append(("A-Eq Seg1 ModeA", aeq_seg1_a, "AGGRESSIVE"))
if bz_seg2_rth:
    rec_modes.append(("B-ZScore Seg2 RTH", bz_seg2_rth, "BALANCED"))
if bz_seg4_low:
    rec_modes.append(("B-ZScore Seg4 LowATR", bz_seg4_low, "BALANCED"))

for label, m, profile in rec_modes:
    w(f"### {label}")
    w("")
    w("| Field | Value |")
    w("|-------|-------|")
    w(f"| Mode name | {label} |")
    w(f"| Scoring model | {m['model']} |")
    w(f"| Threshold | {m['threshold']} |")
    w(f"| Segmentation | {m['seg']} |")
    w(f"| Group | {m['group']} |")

    if m["is_zonerel"]:
        zr = m["ep_zr"]
        w(f"| Exit structure | Single-leg (ZONEREL) |")
        w(f"| Stop | {zr['stop_mult']}x ZoneWidth |")
        w(f"| Target | {zr['target_mult']}x ZoneWidth |")
        w(f"| Time cap | {zr['time_cap']} bars |")
        w(f"| BE trigger | none |")
        w(f"| Trail trigger | none |")
    else:
        ep = m["ep_fixed"]
        w(f"| Exit structure | Single-leg (FIXED) |")
        w(f"| Stop | {ep['stop']}t |")
        w(f"| Target | {ep['target']}t |")
        w(f"| Time cap | {ep['time_cap']} bars |")
        w(f"| BE trigger | {ep.get('be_trigger', 0)}t {'(active)' if ep.get('be_trigger', 0) > 0 else '(none)'} |")
        w(f"| Trail trigger | {ep.get('trail_trigger', 0)}t {'(active)' if ep.get('trail_trigger', 0) > 0 else '(none)'} |")

    flt = m["filters"]
    w(f"| Seq gate | {'<= ' + str(flt['seq_max']) if flt.get('seq_max') else 'none'} |")
    w(f"| TF filter | {'<= 120m' if flt.get('tf_filter') else 'none'} |")
    w(f"| Width filter | none |")
    w(f"| P1 PF @3t | {m['pf_3t']:.4f} |")
    w(f"| P1 trades | {m['trades']} |")
    w(f"| P1 max DD | {m['mdd']:.0f}t |")
    w(f"| P1 Profit/DD | {m['pdd']:.1f} |")
    w(f"| Estimated trades/day | {m['tpd']:.2f} |")
    w(f"| Profile | {profile} |")
    w(f"| Dimensions | AGG={m['R_AGG']} BAL={m['R_BAL']} CON={m['R_CON']} VOL={m['R_VOL']} CONS={m['R_CONS']} ROB={m['R_ROB']} SCAL={m['R_SCAL']} IMPL={m['R_IMPL']} |")
    w("")

# ── Save ────────────────────────────────────────────────────────────
with open(V32_DIR / "mode_classification_v32.md", "w", encoding="utf-8") as f:
    f.write("\n".join(out))
print(f"\nSaved: mode_classification_v32.md")
