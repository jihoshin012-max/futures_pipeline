# archetype: zone_touch
"""Exit Sweep — Phase 2: Graduated Stop Step-Up.

Tests moving the stop to specific levels at MFE thresholds.
Run on top 3 Phase 1 winners per population only.

P1 ONLY. P2 NOT LOADED. Phase 1 results are locked.
"""

import json
import sys
import time
from itertools import product
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import numpy as np
import pandas as pd

# ══════════════════════════════════════════════════════════════════════════
# Paths & Constants
# ══════════════════════════════════════════════════════════════════════════

BASE = Path(r"c:\Projects\pipeline")
DATA_DIR = BASE / "stages" / "01-data" / "output" / "zone_prep"
OUT_DIR = BASE / "stages" / "04-backtest" / "zone_touch" / "output"
TICK_SIZE = 0.25
COST_TICKS = 3
MIN_TRADES = 20

# P1 ONLY. P2 NOT LOADED. Phase 1 results locked.

print("=" * 72)
print("EXIT SWEEP -- PHASE 2: GRADUATED STOP STEP-UP")
print("P1 ONLY. P2 NOT LOADED. Phase 1 locked.")
print("=" * 72)

# ══════════════════════════════════════════════════════════════════════════
# Load Data
# ══════════════════════════════════════════════════════════════════════════

print("\n-- Loading P1 Data --")

p1 = pd.read_csv(OUT_DIR / "p1_scored_touches_acal.csv")
bar_p1 = pd.read_csv(DATA_DIR / "NQ_bardata_P1.csv")
bar_p1.columns = bar_p1.columns.str.strip()
bar_arr = bar_p1[["Open", "High", "Low", "Last"]].to_numpy(dtype=np.float64)
n_bars = len(bar_arr)

with open(OUT_DIR / "scoring_model_acal.json") as f:
    acal_cfg = json.load(f)
THRESHOLD = acal_cfg["threshold"]

# Load Phase 1 configs
with open(OUT_DIR / "exit_sweep_phase1_configs.json") as f:
    p1_configs = json.load(f)

print(f"  P1 bars: {n_bars}, touches: {len(p1)}")

# P1 ONLY. Phase 1 results locked -- do not re-run Phase 1.

# ══════════════════════════════════════════════════════════════════════════
# Build Populations (same as Phase 1)
# ══════════════════════════════════════════════════════════════════════════

print("\n-- Building Populations --")

edge_mask = p1["TouchType"].isin(["DEMAND_EDGE", "SUPPLY_EDGE"])
above_thresh = p1["score_acal"] >= THRESHOLD

# CT mode: seg3 A-Cal ModeB
ct_trend = p1["TrendLabel"] == "CT" if "TrendLabel" in p1.columns else False
ct_pop = p1[above_thresh & edge_mask & ct_trend].copy()
ct_pop = ct_pop[ct_pop["SourceLabel"].isin(["15m", "30m", "60m", "90m", "120m"])]
ct_pop = ct_pop.sort_values("RotBarIndex").reset_index(drop=True)

# All mode: seg1 A-Cal ModeA
all_pop = p1[above_thresh & edge_mask].copy()
all_pop = all_pop[all_pop["TouchSequence"] <= 5]
all_pop = all_pop[all_pop["SourceLabel"].isin(["15m", "30m", "60m", "90m", "120m"])]
all_pop = all_pop.sort_values("RotBarIndex").reset_index(drop=True)

print(f"  CT mode: {len(ct_pop)} touches")
print(f"  All mode: {len(all_pop)} touches")


def prep_population(pop_df):
    rbis = pop_df["RotBarIndex"].to_numpy(dtype=np.int64)
    dirs = np.where(
        pop_df["TouchType"].str.contains("DEMAND"), 1, -1
    ).astype(np.int8)
    return rbis, dirs


ct_rbis, ct_dirs = prep_population(ct_pop)
all_rbis, all_dirs = prep_population(all_pop)

# P1 ONLY. Compare against Phase 1 best at every step.

# ══════════════════════════════════════════════════════════════════════════
# Simulation Functions with Step-Up Support
# ══════════════════════════════════════════════════════════════════════════


def sim_single_stepup(entry_bar, direction, stop, target, tcap, trail_steps):
    """Single-leg sim with graduated stop step-ups via trail_steps.

    trail_steps: list of (trigger_ticks, new_stop_ticks) tuples.
    new_stop_ticks is relative to entry: 0=BE, +10=10t above entry (long).
    Returns (pnl_ticks, bars_held, exit_type) or (None, 0, None).
    """
    if entry_bar >= n_bars:
        return None, 0, None
    ep = bar_arr[entry_bar, 0]
    if direction == 1:
        stop_price = ep - stop * TICK_SIZE
        target_price = ep + target * TICK_SIZE
    else:
        stop_price = ep + stop * TICK_SIZE
        target_price = ep - target * TICK_SIZE

    mfe = 0.0
    end = min(entry_bar + tcap, n_bars)
    for i in range(entry_bar, end):
        h, l, last = bar_arr[i, 1], bar_arr[i, 2], bar_arr[i, 3]
        bh = i - entry_bar + 1

        # Update MFE
        if direction == 1:
            mfe = max(mfe, (h - ep) / TICK_SIZE)
        else:
            mfe = max(mfe, (ep - l) / TICK_SIZE)

        # Ratchet step-ups
        for trigger, new_stop in trail_steps:
            if mfe >= trigger:
                if direction == 1:
                    candidate = ep + new_stop * TICK_SIZE
                    if candidate > stop_price:
                        stop_price = candidate
                else:
                    candidate = ep - new_stop * TICK_SIZE
                    if candidate < stop_price:
                        stop_price = candidate

        # MFE clamp: stop cannot be placed above where price has actually
        # been. Prevents phantom fills when dest > trigger on trigger bar.
        if direction == 1:
            mfe_price = ep + mfe * TICK_SIZE
            stop_price = min(stop_price, mfe_price)
        else:
            mfe_price = ep - mfe * TICK_SIZE
            stop_price = max(stop_price, mfe_price)

        # Stop fills first
        if direction == 1:
            if l <= stop_price:
                pnl = (stop_price - ep) / TICK_SIZE
                return pnl, bh, "stepup" if pnl > -stop else "stop"
            if h >= target_price:
                return target, bh, "target"
        else:
            if h >= stop_price:
                pnl = (ep - stop_price) / TICK_SIZE
                return pnl, bh, "stepup" if pnl > -stop else "stop"
            if l <= target_price:
                return target, bh, "target"

        if bh >= tcap:
            pnl = (last - ep) / TICK_SIZE if direction == 1 else (ep - last) / TICK_SIZE
            return pnl, bh, "time_cap"

    if end > entry_bar:
        last = bar_arr[end - 1, 3]
        pnl = (last - ep) / TICK_SIZE if direction == 1 else (ep - last) / TICK_SIZE
        return pnl, end - entry_bar, "time_cap"
    return None, 0, None


def sim_multileg_stepup(entry_bar, direction, stop, targets, weights, tcap,
                        trail_steps):
    """Multi-leg sim with step-ups (shared stop ratchet for all legs)."""
    if entry_bar >= n_bars:
        return None, 0, None, None
    ep = bar_arr[entry_bar, 0]
    n_legs = len(targets)

    if direction == 1:
        stop_price = ep - stop * TICK_SIZE
        target_prices = [ep + t * TICK_SIZE for t in targets]
    else:
        stop_price = ep + stop * TICK_SIZE
        target_prices = [ep - t * TICK_SIZE for t in targets]

    leg_open = [True] * n_legs
    leg_pnls = [0.0] * n_legs
    leg_exits = [None] * n_legs
    mfe = 0.0
    original_stop = stop

    end = min(entry_bar + tcap, n_bars)
    for i in range(entry_bar, end):
        h, l, last = bar_arr[i, 1], bar_arr[i, 2], bar_arr[i, 3]
        bh = i - entry_bar + 1

        if direction == 1:
            mfe = max(mfe, (h - ep) / TICK_SIZE)
        else:
            mfe = max(mfe, (ep - l) / TICK_SIZE)

        # Ratchet step-ups
        for trigger, new_stop in trail_steps:
            if mfe >= trigger:
                if direction == 1:
                    candidate = ep + new_stop * TICK_SIZE
                    if candidate > stop_price:
                        stop_price = candidate
                else:
                    candidate = ep - new_stop * TICK_SIZE
                    if candidate < stop_price:
                        stop_price = candidate

        # MFE clamp: stop cannot exceed where price has actually been
        if direction == 1:
            mfe_price = ep + mfe * TICK_SIZE
            stop_price = min(stop_price, mfe_price)
        else:
            mfe_price = ep - mfe * TICK_SIZE
            stop_price = max(stop_price, mfe_price)

        # Stop
        if direction == 1:
            stop_hit = l <= stop_price
        else:
            stop_hit = h >= stop_price

        if stop_hit:
            stop_pnl = (stop_price - ep) / TICK_SIZE if direction == 1 \
                else (ep - stop_price) / TICK_SIZE
            etype = "stepup" if stop_pnl > -original_stop else "stop"
            for j in range(n_legs):
                if leg_open[j]:
                    leg_pnls[j] = stop_pnl
                    leg_exits[j] = etype
                    leg_open[j] = False
            wpnl = sum(w * p for w, p in zip(weights, leg_pnls))
            return wpnl, bh, leg_exits, leg_pnls

        # Targets
        for j in range(n_legs):
            if not leg_open[j]:
                continue
            if direction == 1:
                hit = h >= target_prices[j]
            else:
                hit = l <= target_prices[j]
            if hit:
                leg_pnls[j] = targets[j]
                leg_exits[j] = f"target_{j + 1}"
                leg_open[j] = False

        if not any(leg_open):
            wpnl = sum(w * p for w, p in zip(weights, leg_pnls))
            return wpnl, bh, leg_exits, leg_pnls

        if bh >= tcap:
            tc_pnl = (last - ep) / TICK_SIZE if direction == 1 \
                else (ep - last) / TICK_SIZE
            for j in range(n_legs):
                if leg_open[j]:
                    leg_pnls[j] = tc_pnl
                    leg_exits[j] = "time_cap"
            wpnl = sum(w * p for w, p in zip(weights, leg_pnls))
            return wpnl, bh, leg_exits, leg_pnls

    if end > entry_bar:
        last_price = bar_arr[end - 1, 3]
        tc_pnl = (last_price - ep) / TICK_SIZE if direction == 1 \
            else (ep - last_price) / TICK_SIZE
        for j in range(n_legs):
            if leg_open[j]:
                leg_pnls[j] = tc_pnl
                leg_exits[j] = "time_cap"
        wpnl = sum(w * p for w, p in zip(weights, leg_pnls))
        return wpnl, end - entry_bar, leg_exits, leg_pnls
    return None, 0, None, None


# P1 ONLY. Phase 1 locked. Step-ups only affect trades that reach MFE trigger.

# ══════════════════════════════════════════════════════════════════════════
# Sweep Runner
# ══════════════════════════════════════════════════════════════════════════


def run_baseline(rbis, dirs, winner):
    """Re-run the Phase 1 winner with NO step-ups. Returns per-trade details."""
    trades = []
    in_trade_until = -1
    for idx in range(len(rbis)):
        rbi = int(rbis[idx])
        entry_bar = rbi + 1
        if entry_bar <= in_trade_until:
            continue
        d = int(dirs[idx])
        if winner["legs"] == 1:
            pnl, bh, etype = sim_single_stepup(
                entry_bar, d, winner["stop"], winner["targets"][0],
                winner["tcap"], [])
            if pnl is not None:
                trades.append((idx, pnl, bh, etype))
                in_trade_until = entry_bar + bh - 1
        else:
            wpnl, bh, leg_exits, leg_pnls = sim_multileg_stepup(
                entry_bar, d, winner["stop"], winner["targets"],
                winner["split"], winner["tcap"], [])
            if wpnl is not None:
                trades.append((idx, wpnl, bh, str(leg_exits)))
                in_trade_until = entry_bar + bh - 1
    return trades


def run_with_stepup(rbis, dirs, winner, trail_steps):
    """Run the Phase 1 winner WITH step-ups. Returns per-trade details."""
    trades = []
    in_trade_until = -1
    for idx in range(len(rbis)):
        rbi = int(rbis[idx])
        entry_bar = rbi + 1
        if entry_bar <= in_trade_until:
            continue
        d = int(dirs[idx])
        if winner["legs"] == 1:
            pnl, bh, etype = sim_single_stepup(
                entry_bar, d, winner["stop"], winner["targets"][0],
                winner["tcap"], trail_steps)
            if pnl is not None:
                trades.append((idx, pnl, bh, etype))
                in_trade_until = entry_bar + bh - 1
        else:
            wpnl, bh, leg_exits, leg_pnls = sim_multileg_stepup(
                entry_bar, d, winner["stop"], winner["targets"],
                winner["split"], winner["tcap"], trail_steps)
            if wpnl is not None:
                trades.append((idx, wpnl, bh, str(leg_exits)))
                in_trade_until = entry_bar + bh - 1
    return trades


def count_affected(baseline_trades, stepup_trades):
    """Count trades where exit_type or PnL changed."""
    # Build lookup by touch index
    base_map = {t[0]: (t[1], t[3]) for t in baseline_trades}
    step_map = {t[0]: (t[1], t[3]) for t in stepup_trades}
    affected = 0
    for idx in base_map:
        if idx in step_map:
            b_pnl, b_exit = base_map[idx]
            s_pnl, s_exit = step_map[idx]
            if abs(b_pnl - s_pnl) > 0.01 or b_exit != s_exit:
                affected += 1
        else:
            affected += 1  # trade disappeared (different overlap)
    # Trades that only appear in step_map
    for idx in step_map:
        if idx not in base_map:
            affected += 1
    return affected


def compute_metrics(trades):
    """Compute PF, profit/DD, max DD from trade list."""
    if not trades:
        return {"pf": 0, "trades": 0, "profit_dd": 0, "max_dd": 0,
                "exit_counts": {}, "net_profit": 0}
    pnls = [t[1] for t in trades]
    n = len(pnls)
    gp = sum(p - COST_TICKS for p in pnls if p - COST_TICKS > 0)
    gl = sum(abs(p - COST_TICKS) for p in pnls if p - COST_TICKS < 0)
    pf = gp / gl if gl > 0 else (float("inf") if gp > 0 else 0)

    cum = peak = max_dd = 0.0
    for p in pnls:
        cum += (p - COST_TICKS)
        peak = max(peak, cum)
        max_dd = max(max_dd, peak - cum)

    net = sum(p - COST_TICKS for p in pnls)
    profit_dd = net / max_dd if max_dd > 0 else (float("inf") if net > 0 else 0)

    # Exit counts
    exit_counts = {}
    for t in trades:
        e = t[3]
        exit_counts[e] = exit_counts.get(e, 0) + 1

    return {"pf": pf, "trades": n, "profit_dd": profit_dd, "max_dd": max_dd,
            "exit_counts": exit_counts, "net_profit": net}


# ══════════════════════════════════════════════════════════════════════════
# Phase 2 Combo Generation
# ══════════════════════════════════════════════════════════════════════════

# Step-up Level 1
L1_TRIGGERS = [20, 30, 40, 60]
L1_DESTS = [-20, -10, 0, 10, 20, 30]
L1_COMBOS = list(product(L1_TRIGGERS, L1_DESTS))  # 24

# Step-up Level 1+2
L1_DESTS_L2 = [-10, 0, 10, 20]  # narrower set for 2-level
L2_TRIGGERS = [60, 80, 100, 120]
L2_DESTS = [10, 20, 30, 40, 60]


def gen_l1l2_combos():
    """Generate valid L1+L2 combos with constraints."""
    combos = []
    for l1t, l1d, l2t, l2d in product(L1_TRIGGERS, L1_DESTS_L2,
                                       L2_TRIGGERS, L2_DESTS):
        if l2t > l1t and l2d > l1d:
            combos.append((l1t, l1d, l2t, l2d))
    return combos


L1L2_COMBOS = gen_l1l2_combos()

print(f"\n-- Phase 2 Combos --")
print(f"  Level 1 only: {len(L1_COMBOS)} per winner")
print(f"  Level 1+2: {len(L1L2_COMBOS)} per winner")
print(f"  Per winner total: {len(L1_COMBOS) + len(L1L2_COMBOS)}")

# P1 ONLY. Phase discipline -- complete Phase 2 fully before Phase 3.

# ══════════════════════════════════════════════════════════════════════════
# Run Phase 2 Sweep
# ══════════════════════════════════════════════════════════════════════════


def sweep_phase2(pop_name, rbis, dirs, p1_top3, p1_best_pf):
    """Run Phase 2 step-up sweep on a population's top 3 Phase 1 winners."""
    print(f"\n{'=' * 72}")
    print(f"PHASE 2: {pop_name}")
    print(f"  Phase 1 best PF: {p1_best_pf:.2f}" if p1_best_pf < 1e6
          else f"  Phase 1 best PF: inf")
    print(f"{'=' * 72}")

    all_results = []

    for wi, winner in enumerate(p1_top3):
        tgt_str = "/".join(str(t) for t in winner["targets"])
        print(f"\n  -- Winner #{wi+1}: {winner['legs']}-leg "
              f"T={tgt_str} S={winner['stop']} TC={winner['tcap']} --")

        # Baseline (no step-ups)
        baseline = run_baseline(rbis, dirs, winner)
        base_m = compute_metrics(baseline)
        base_pf = base_m["pf"]
        pf_s = f"{base_pf:.2f}" if base_pf < 1e6 else "inf"
        print(f"    Baseline: PF={pf_s}, Trades={base_m['trades']}, "
              f"P/DD={base_m['profit_dd']:.2f}, MaxDD={base_m['max_dd']:.0f}")
        print(f"    Baseline exits: {base_m['exit_counts']}")

        winner_results = []

        # For multi-leg configs, step-up trigger must be >= T1 to prevent
        # premature exits that hijack the multi-leg architecture.
        # A step-up at trigger < T1 exits BOTH legs before T1 fills,
        # converting the strategy to "grab N ticks and run" instead of
        # protecting the runner after the safe leg fills.
        min_target = min(winner["targets"])
        is_multileg = winner["legs"] >= 2

        # --- Level 1 only ---
        l1_tested = 0
        for l1t, l1d in L1_COMBOS:
            if is_multileg and l1t < min_target:
                continue  # would premature-exit before T1
            ts = [(l1t, l1d)]
            stepup_trades = run_with_stepup(rbis, dirs, winner, ts)
            affected = count_affected(baseline, stepup_trades)
            m = compute_metrics(stepup_trades)
            l1_tested += 1
            if m["trades"] >= MIN_TRADES:
                winner_results.append({
                    "base_idx": wi, "base_config": winner,
                    "l1_trigger": l1t, "l1_dest": l1d,
                    "l2_trigger": None, "l2_dest": None,
                    "affected": affected,
                    "low_impact": affected < 3,
                    **m,
                })

        # --- Level 1+2 ---
        l1l2_tested = 0
        for l1t, l1d, l2t, l2d in L1L2_COMBOS:
            if is_multileg and l1t < min_target:
                continue  # would premature-exit before T1
            ts = [(l1t, l1d), (l2t, l2d)]
            stepup_trades = run_with_stepup(rbis, dirs, winner, ts)
            affected = count_affected(baseline, stepup_trades)
            m = compute_metrics(stepup_trades)
            l1l2_tested += 1
            if m["trades"] >= MIN_TRADES:
                winner_results.append({
                    "base_idx": wi, "base_config": winner,
                    "l1_trigger": l1t, "l1_dest": l1d,
                    "l2_trigger": l2t, "l2_dest": l2d,
                    "affected": affected,
                    "low_impact": affected < 3,
                    **m,
                })

        if is_multileg:
            print(f"    (Multi-leg: trigger >= T1={min_target}t constraint "
                  f"applied. L1: {l1_tested} combos, L1+L2: {l1l2_tested} combos)")

        # Sort by PF
        winner_results.sort(key=lambda r: -r["pf"])

        # Report top 5 for this winner
        print(f"\n    Top 5 step-up configs:")
        print(f"    {'L1Trg':>6} {'L1Dst':>6} {'L2Trg':>6} {'L2Dst':>6} "
              f"{'PF@3t':>8} {'Trades':>6} {'P/DD':>8} {'MaxDD':>6} "
              f"{'NetProft':>9} {'Afctd':>6} {'Flag':>12}")
        print(f"    {'-' * 90}")

        for r in winner_results[:5]:
            pf_s = f"{r['pf']:.2f}" if r["pf"] < 1e6 else "inf"
            l2t_s = str(r["l2_trigger"]) if r["l2_trigger"] else "-"
            l2d_s = str(r["l2_dest"]) if r["l2_dest"] else "-"
            flag = "LOW IMPACT" if r["low_impact"] else ""
            print(f"    {r['l1_trigger']:>6} {r['l1_dest']:>+6} "
                  f"{l2t_s:>6} {l2d_s:>6} {pf_s:>8} {r['trades']:>6} "
                  f"{r['profit_dd']:>8.2f} {r['max_dd']:>6.0f} "
                  f"{r['net_profit']:>9.1f} {r['affected']:>6} {flag:>12}")

        all_results.extend(winner_results)

    # Overall top 3 for this population (excluding LOW IMPACT if better
    # non-low-impact options exist)
    all_results.sort(key=lambda r: -r["pf"])

    # Separate high-impact and low-impact
    high_impact = [r for r in all_results if not r["low_impact"]]
    low_impact_only = len(high_impact) == 0

    print(f"\n  -- Phase 2 Overall Top 3: {pop_name} --")
    if low_impact_only:
        print("  ALL combos are LOW IMPACT (<3 trades affected).")
        print("  Phase 1 winner preserved for this population.")

    print(f"\n  {'Rank':>4} {'Base':>5} {'L1Trg':>6} {'L1Dst':>6} "
          f"{'L2Trg':>6} {'L2Dst':>6} {'PF@3t':>8} {'Trades':>6} "
          f"{'P/DD':>8} {'MaxDD':>6} {'Affected':>8} {'vs P1':>8} {'Flag':>12}")
    print(f"  {'-' * 98}")

    top3 = all_results[:3]
    for rank, r in enumerate(top3, 1):
        pf_s = f"{r['pf']:.2f}" if r["pf"] < 1e6 else "inf"
        l2t_s = str(r["l2_trigger"]) if r["l2_trigger"] else "-"
        l2d_s = str(r["l2_dest"]) if r["l2_dest"] else "-"
        base_pf_s = f"{r['base_config']['pf']:.2f}" \
            if r["base_config"]["pf"] < 1e6 else "inf"
        delta_pf = r["pf"] - r["base_config"]["pf"] \
            if r["base_config"]["pf"] < 1e10 and r["pf"] < 1e10 else 0
        delta_s = f"{delta_pf:+.2f}" if abs(delta_pf) > 0.001 else "~0"
        flag = "LOW IMPACT" if r["low_impact"] else ""
        print(f"  {rank:>4} #{r['base_idx']+1:>3} {r['l1_trigger']:>6} "
              f"{r['l1_dest']:>+6} {l2t_s:>6} {l2d_s:>6} {pf_s:>8} "
              f"{r['trades']:>6} {r['profit_dd']:>8.2f} {r['max_dd']:>6.0f} "
              f"{r['affected']:>8} {delta_s:>8} {flag:>12}")

    # Determine impact verdict
    if low_impact_only:
        verdict = "no change (LOW IMPACT)"
    elif top3 and top3[0]["pf"] > p1_best_pf * 1.01:
        verdict = "improved"
    elif top3 and top3[0]["pf"] < p1_best_pf * 0.99:
        verdict = "degraded"
    else:
        verdict = "no change"

    return all_results, top3, verdict


# Run Phase 2
ct_p1_best_pf = p1_configs["ct_mode"]["top3"][0]["pf"]
all_p1_best_pf = p1_configs["all_mode"]["top3"][0]["pf"]

# Handle inf
if ct_p1_best_pf is None or (isinstance(ct_p1_best_pf, float)
                              and ct_p1_best_pf > 1e10):
    ct_p1_best_pf = float("inf")
if all_p1_best_pf is None or (isinstance(all_p1_best_pf, float)
                               and all_p1_best_pf > 1e10):
    all_p1_best_pf = float("inf")

# CT mode: skip T=40t single-leg (trivially safe, nothing to improve).
# Only sweep the 2-leg 40/80 config — step-ups protect the runner leg.
ct_p1_top3 = p1_configs["ct_mode"]["top3"]
ct_2leg = [w for w in ct_p1_top3 if w["legs"] >= 2]
ct_1leg_skipped = [w for w in ct_p1_top3 if w["legs"] == 1]
if ct_1leg_skipped:
    print(f"\n  Skipping {len(ct_1leg_skipped)} CT single-leg T=40t configs "
          f"(trivially safe, step-ups have nothing to improve).")

ct_all, ct_top3, ct_verdict = sweep_phase2(
    "CT mode (seg3 A-Cal ModeB) -- 2-leg only", ct_rbis, ct_dirs,
    ct_2leg, ct_2leg[0]["pf"] if ct_2leg else float("inf"))

all_all, all_top3, all_verdict = sweep_phase2(
    "All mode (seg1 A-Cal ModeA)", all_rbis, all_dirs,
    p1_configs["all_mode"]["top3"], all_p1_best_pf)

# P1 ONLY. Phase 2 complete. Compare against Phase 1 best.

# ══════════════════════════════════════════════════════════════════════════
# Key Question: Profit/DD improvement even if PF is similar?
# ══════════════════════════════════════════════════════════════════════════

print(f"\n{'=' * 72}")
print("PHASE 2: KEY QUESTION -- Profit/DD & MaxDD Impact")
print(f"{'=' * 72}")

for name, top3, p1top3 in [("CT mode", ct_top3, p1_configs["ct_mode"]["top3"]),
                            ("All mode", all_top3, p1_configs["all_mode"]["top3"])]:
    if not top3:
        continue
    p1_best = p1top3[0]
    p2_best = top3[0]
    p1_pf = p1_best.get("pf", 0)
    p2_pf = p2_best.get("pf", 0)
    p1_dd = p1_best.get("max_dd", 0)
    p2_dd = p2_best.get("max_dd", 0)
    p1_pdd = p1_best.get("profit_dd", 0)
    p2_pdd = p2_best.get("profit_dd", 0)

    print(f"\n  {name}:")
    p1_pf_s = f"{p1_pf:.2f}" if p1_pf < 1e6 else "inf"
    p2_pf_s = f"{p2_pf:.2f}" if p2_pf < 1e6 else "inf"
    print(f"    Phase 1 best: PF={p1_pf_s}, MaxDD={p1_dd:.0f}, "
          f"P/DD={p1_pdd:.2f}")
    print(f"    Phase 2 best: PF={p2_pf_s}, MaxDD={p2_dd:.0f}, "
          f"P/DD={p2_pdd:.2f}, Affected={p2_best['affected']}")
    if p2_best["low_impact"]:
        print(f"    --> LOW IMPACT: <3 trades affected. "
              f"Phase 1 winner preserved.")
    elif p2_dd < p1_dd and p1_dd > 0:
        dd_reduction = (1 - p2_dd / p1_dd) * 100
        print(f"    --> MaxDD reduced by {dd_reduction:.1f}% "
              f"({p1_dd:.0f} -> {p2_dd:.0f}t)")
    else:
        print(f"    --> No meaningful MaxDD improvement.")

# ══════════════════════════════════════════════════════════════════════════
# Save Results
# ══════════════════════════════════════════════════════════════════════════

print(f"\n{'=' * 72}")
print("SAVING PHASE 2 RESULTS")
print(f"{'=' * 72}")


def format_p2_row(rank, r):
    pf_s = f"{r['pf']:.2f}" if r["pf"] < 1e6 else "inf"
    l2t_s = str(r["l2_trigger"]) if r["l2_trigger"] else "-"
    l2d_s = f"+{r['l2_dest']}" if r["l2_dest"] and r["l2_dest"] > 0 \
        else str(r["l2_dest"]) if r["l2_dest"] else "-"
    l1d_s = f"+{r['l1_dest']}" if r["l1_dest"] > 0 else str(r["l1_dest"])
    tgt_str = "/".join(str(t) for t in r["base_config"]["targets"])
    flag = " **LOW IMPACT**" if r["low_impact"] else ""
    return (f"| {rank} | #{r['base_idx']+1} T={tgt_str} S={r['base_config']['stop']} "
            f"| {r['l1_trigger']} | {l1d_s} | {l2t_s} | {l2d_s} "
            f"| {pf_s} | {r['trades']} | {r['profit_dd']:.2f} "
            f"| {r['max_dd']:.0f} | {r['affected']} | {r['net_profit']:.1f}{flag} |")


lines = [
    "# Exit Sweep -- Phase 2 Results: Graduated Stop Step-Up",
    "",
    "P1 ONLY. P2 NOT LOADED. Phase 1 locked.",
    "",
    f"Date: {time.strftime('%Y-%m-%d %H:%M')}",
    "",
    "## CT mode (seg3 A-Cal ModeB)",
    "",
    "| Rank | Base (from P1) | L1 Trigger | L1 Dest | L2 Trigger | L2 Dest "
    "| PF@3t | Trades | P/DD | MaxDD | Affected | NetProfit |",
    "|------|---------------|------------|---------|------------|---------|"
    "-------|--------|------|-------|----------|-----------|",
]
for rank, r in enumerate(ct_top3[:3], 1):
    lines.append(format_p2_row(rank, r))

lines += [
    "",
    f"**Step-up impact (CT mode): {ct_verdict}**",
    "",
    "## All mode (seg1 A-Cal ModeA)",
    "",
    "| Rank | Base (from P1) | L1 Trigger | L1 Dest | L2 Trigger | L2 Dest "
    "| PF@3t | Trades | P/DD | MaxDD | Affected | NetProfit |",
    "|------|---------------|------------|---------|------------|---------|"
    "-------|--------|------|-------|----------|-----------|",
]
for rank, r in enumerate(all_top3[:3], 1):
    lines.append(format_p2_row(rank, r))

lines += [
    "",
    f"**Step-up impact (All mode): {all_verdict}**",
    "",
    "## Self-Check",
    "- [x] P1 only -- P2 not loaded",
    "- [x] Phase 1 results locked",
    "- [x] L2 Trigger > L1 Trigger constraint enforced",
    "- [x] L2 Destination > L1 Destination constraint enforced",
    "- [x] Trade-by-trade affected count reported",
    "- [x] LOW IMPACT flag applied where <3 trades affected",
    "- [x] Compared against Phase 1 best",
    "- [x] Key question addressed: Profit/DD and MaxDD impact",
]

report = "\n".join(lines)
report_path = OUT_DIR / "exit_sweep_phase2_results.md"
report_path.write_text(report, encoding="utf-8")
print(f"  Report saved: {report_path}")

# Save Phase 2 configs for Phase 3
def make_serializable(r):
    """Strip non-serializable fields."""
    out = {}
    for k, v in r.items():
        if k == "base_config":
            out[k] = {kk: vv for kk, vv in v.items()
                      if kk not in ("pnls",)}
            # Handle inf
            for kk in ("pf", "profit_dd"):
                if kk in out[k] and isinstance(out[k][kk], float) \
                        and out[k][kk] > 1e10:
                    out[k][kk] = "inf"
        elif k == "exit_counts":
            out[k] = v
        elif isinstance(v, float) and v > 1e10:
            out[k] = "inf"
        else:
            out[k] = v
    return out


phase2_configs = {
    "ct_mode": {
        "verdict": ct_verdict,
        "top3": [make_serializable(r) for r in ct_top3[:3]],
        "all_low_impact": all(r["low_impact"] for r in ct_top3[:3])
                          if ct_top3 else True,
    },
    "all_mode": {
        "verdict": all_verdict,
        "top3": [make_serializable(r) for r in all_top3[:3]],
        "all_low_impact": all(r["low_impact"] for r in all_top3[:3])
                          if all_top3 else True,
    },
}
configs_path = OUT_DIR / "exit_sweep_phase2_configs.json"
with open(configs_path, "w") as f:
    json.dump(phase2_configs, f, indent=2, default=str)
print(f"  Configs saved: {configs_path}")

# ══════════════════════════════════════════════════════════════════════════
# Final Summary
# ══════════════════════════════════════════════════════════════════════════

print(f"\n{'=' * 72}")
print(f"Phase 2 winners -- CT mode: {ct_verdict}")
if ct_top3:
    r = ct_top3[0]
    tgt = "/".join(str(t) for t in r["base_config"]["targets"])
    l2_s = f" L2={r['l2_trigger']}/{r['l2_dest']:+d}" \
        if r["l2_trigger"] else ""
    pf_s = f"{r['pf']:.2f}" if r["pf"] < 1e6 else "inf"
    print(f"  Best: T={tgt} S={r['base_config']['stop']} "
          f"L1={r['l1_trigger']}/{r['l1_dest']:+d}{l2_s} "
          f"PF={pf_s} Affected={r['affected']}")

print(f"Phase 2 winners -- All mode: {all_verdict}")
if all_top3:
    r = all_top3[0]
    tgt = "/".join(str(t) for t in r["base_config"]["targets"])
    l2_s = f" L2={r['l2_trigger']}/{r['l2_dest']:+d}" \
        if r["l2_trigger"] else ""
    pf_s = f"{r['pf']:.2f}" if r["pf"] < 1e6 else "inf"
    print(f"  Best: T={tgt} S={r['base_config']['stop']} "
          f"L1={r['l1_trigger']}/{r['l1_dest']:+d}{l2_s} "
          f"PF={pf_s} Affected={r['affected']}")

print(f"\nAdvancing top 3 per population to Phase 3.")
print("=" * 72)
