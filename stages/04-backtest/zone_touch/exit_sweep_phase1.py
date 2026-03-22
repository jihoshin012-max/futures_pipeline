# archetype: zone_touch
"""Exit Sweep — Phase 1: Core Exit Shape.

Tests single-leg, 2-leg, and 3-leg exit configurations with size splits.
No step-up, no trail — those are Phase 2-3.

P1 ONLY. P2 NOT LOADED.
Populations: CT mode (seg3 A-Cal ModeB), All mode (seg1 A-Cal ModeA).
Current best CT: Stop=190t, Target=80t, TC=120, PF=30.58
Current best All: Stop=190t, Target=60t, TC=120, PF=9.39
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
COST_TICKS = 3  # from _config/instruments.md
MIN_TRADES = 20  # minimum trade gate

# P1 ONLY. P2 NOT LOADED.

print("=" * 72)
print("EXIT SWEEP — PHASE 1: CORE EXIT SHAPE")
print("P1 ONLY. P2 NOT LOADED.")
print("=" * 72)

# ══════════════════════════════════════════════════════════════════════════
# Load Data (P1 only)
# ══════════════════════════════════════════════════════════════════════════

print("\n── Loading P1 Data ──")

# Load scored touches
p1 = pd.read_csv(OUT_DIR / "p1_scored_touches_acal.csv")
print(f"  P1 touches loaded: {len(p1)}")

# Load bar data
bar_p1 = pd.read_csv(DATA_DIR / "NQ_bardata_P1.csv")
bar_p1.columns = bar_p1.columns.str.strip()
bar_arr = bar_p1[["Open", "High", "Low", "Last"]].to_numpy(dtype=np.float64)
n_bars = len(bar_arr)
print(f"  P1 bars loaded: {n_bars}")

# Load frozen params for thresholds
with open(OUT_DIR / "scoring_model_acal.json") as f:
    acal_cfg = json.load(f)
THRESHOLD = acal_cfg["threshold"]
print(f"  A-Cal threshold: {THRESHOLD}")

# P1 ONLY. P2 NOT LOADED. Phase discipline — complete Phase 1 fully.

# ══════════════════════════════════════════════════════════════════════════
# Build Populations
# ══════════════════════════════════════════════════════════════════════════

print("\n── Building Populations ──")

edge_mask = p1["TouchType"].isin(["DEMAND_EDGE", "SUPPLY_EDGE"])
above_thresh = p1["score_acal"] >= THRESHOLD

# --- CT mode: seg3 A-Cal ModeB ---
# Segmentation: above_thresh & edge & counter-trend
ct_trend = p1["TrendLabel"] == "CT" if "TrendLabel" in p1.columns else False
ct_pop = p1[above_thresh & edge_mask & ct_trend].copy()
# Filter: tf_filter=True (SourceLabel in <=120m), seq_max=None
ct_pop = ct_pop[ct_pop["SourceLabel"].isin(["15m", "30m", "60m", "90m", "120m"])]
ct_pop = ct_pop.sort_values("RotBarIndex").reset_index(drop=True)
print(f"  CT mode population: {len(ct_pop)} touches")

# --- All mode: seg1 A-Cal ModeA ---
# Segmentation: above_thresh & edge
all_pop = p1[above_thresh & edge_mask].copy()
# Filter: seq_max=5, tf_filter=True
all_pop = all_pop[all_pop["TouchSequence"] <= 5]
all_pop = all_pop[all_pop["SourceLabel"].isin(["15m", "30m", "60m", "90m", "120m"])]
all_pop = all_pop.sort_values("RotBarIndex").reset_index(drop=True)
print(f"  All mode population: {len(all_pop)} touches")

# Pre-extract arrays for fast simulation
def prep_population(pop_df):
    """Extract numpy arrays for fast simulation."""
    rbis = pop_df["RotBarIndex"].to_numpy(dtype=np.int64)
    dirs = np.where(
        pop_df["TouchType"].str.contains("DEMAND"), 1, -1
    ).astype(np.int8)
    return rbis, dirs

ct_rbis, ct_dirs = prep_population(ct_pop)
all_rbis, all_dirs = prep_population(all_pop)

# P1 ONLY. Compare against current deployed config at every phase.

# ══════════════════════════════════════════════════════════════════════════
# Simulation Functions (numpy-optimized)
# ══════════════════════════════════════════════════════════════════════════


def sim_single(entry_bar, direction, stop, target, tcap):
    """Simulate single-leg trade. Returns (pnl_ticks, bars_held, exit_type).

    exit_type: 'target', 'stop', 'time_cap', or None if invalid.
    """
    if entry_bar >= n_bars:
        return None, 0, None
    ep = bar_arr[entry_bar, 0]  # Open
    if direction == 1:
        stop_price = ep - stop * TICK_SIZE
        target_price = ep + target * TICK_SIZE
    else:
        stop_price = ep + stop * TICK_SIZE
        target_price = ep - target * TICK_SIZE

    end = min(entry_bar + tcap, n_bars)
    for i in range(entry_bar, end):
        h, l, last = bar_arr[i, 1], bar_arr[i, 2], bar_arr[i, 3]
        bh = i - entry_bar + 1

        # Stop fills first (intra-bar conflict rule)
        if direction == 1:
            if l <= stop_price:
                return (stop_price - ep) / TICK_SIZE, bh, "stop"
            if h >= target_price:
                return target, bh, "target"
        else:
            if h >= stop_price:
                return (ep - stop_price) / TICK_SIZE, bh, "stop"
            if l <= target_price:
                return target, bh, "target"

        if bh >= tcap:
            pnl = (last - ep) / TICK_SIZE if direction == 1 else (ep - last) / TICK_SIZE
            return pnl, bh, "time_cap"

    # Ran out of bars
    if end > entry_bar:
        last = bar_arr[end - 1, 3]
        pnl = (last - ep) / TICK_SIZE if direction == 1 else (ep - last) / TICK_SIZE
        return pnl, end - entry_bar, "time_cap"
    return None, 0, None


def sim_multileg(entry_bar, direction, stop, targets, weights, tcap):
    """Simulate multi-leg trade with partial exits.

    targets: list of target ticks [T1, T2, ...], ascending.
    weights: list of position fractions [w1, w2, ...], sum ≈ 1.0.

    Returns (weighted_pnl, bars_held, leg_exits, leg_pnls) or (None, 0, None, None).
    leg_exits: list of exit_type per leg.
    """
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

    end = min(entry_bar + tcap, n_bars)
    for i in range(entry_bar, end):
        h, l, last = bar_arr[i, 1], bar_arr[i, 2], bar_arr[i, 3]
        bh = i - entry_bar + 1

        # Stop fills first — all remaining open legs exit at stop
        if direction == 1:
            stop_hit = l <= stop_price
        else:
            stop_hit = h >= stop_price

        if stop_hit:
            stop_pnl = (stop_price - ep) / TICK_SIZE if direction == 1 \
                else (ep - stop_price) / TICK_SIZE
            for j in range(n_legs):
                if leg_open[j]:
                    leg_pnls[j] = stop_pnl
                    leg_exits[j] = "stop"
                    leg_open[j] = False
            wpnl = sum(w * p for w, p in zip(weights, leg_pnls))
            return wpnl, bh, leg_exits, leg_pnls

        # Check targets ascending
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

        # Time cap
        if bh >= tcap:
            tc_pnl = (last - ep) / TICK_SIZE if direction == 1 \
                else (ep - last) / TICK_SIZE
            for j in range(n_legs):
                if leg_open[j]:
                    leg_pnls[j] = tc_pnl
                    leg_exits[j] = "time_cap"
            wpnl = sum(w * p for w, p in zip(weights, leg_pnls))
            return wpnl, bh, leg_exits, leg_pnls

    # Ran out of bars
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


# P1 ONLY. Phase discipline — complete current phase before starting next.

# ══════════════════════════════════════════════════════════════════════════
# Sweep Runner
# ══════════════════════════════════════════════════════════════════════════


def run_sweep_single(rbis, dirs, stop, target, tcap):
    """Run single-leg sweep on a population with no-overlap filter.

    Returns dict with pf, trades, profit_dd, max_dd, exit_breakdown, pnls.
    """
    pnls = []
    exit_counts = {"target": 0, "stop": 0, "time_cap": 0}
    in_trade_until = -1

    for idx in range(len(rbis)):
        rbi = int(rbis[idx])
        entry_bar = rbi + 1
        if entry_bar <= in_trade_until:
            continue
        d = int(dirs[idx])
        pnl, bh, etype = sim_single(entry_bar, d, stop, target, tcap)
        if pnl is not None:
            pnls.append(pnl)
            exit_counts[etype] = exit_counts.get(etype, 0) + 1
            in_trade_until = entry_bar + bh - 1

    return _compute_metrics(pnls, exit_counts)


def run_sweep_multileg(rbis, dirs, stop, targets, weights, tcap):
    """Run multi-leg sweep on a population with no-overlap filter.

    Returns dict with pf, trades, profit_dd, max_dd, exit_breakdown, pnls,
    plus t3_fill_rate for 3-leg configs.
    """
    pnls = []
    exit_counts = {}
    leg_fill_counts = [0] * len(targets)  # how many trades fill each leg's target
    total_trades = 0
    in_trade_until = -1

    for idx in range(len(rbis)):
        rbi = int(rbis[idx])
        entry_bar = rbi + 1
        if entry_bar <= in_trade_until:
            continue
        d = int(dirs[idx])
        wpnl, bh, leg_exits, leg_pnls = sim_multileg(
            entry_bar, d, stop, targets, weights, tcap)
        if wpnl is not None:
            pnls.append(wpnl)
            total_trades += 1
            in_trade_until = entry_bar + bh - 1
            for j, ex in enumerate(leg_exits):
                exit_counts[ex] = exit_counts.get(ex, 0) + 1
                if ex and ex.startswith("target_"):
                    leg_fill_counts[j] += 1

    metrics = _compute_metrics(pnls, exit_counts)
    # T3 fill rate for 3-leg configs
    if len(targets) >= 3 and total_trades > 0:
        metrics["t3_fill_rate"] = leg_fill_counts[2] / total_trades
    return metrics


def _compute_metrics(pnls, exit_counts):
    """Compute PF, profit/DD, max DD from raw PnL list."""
    if not pnls:
        return {"pf": 0, "trades": 0, "profit_dd": 0, "max_dd": 0,
                "exit_breakdown": exit_counts, "pnls": pnls, "net_profit": 0}

    trades = len(pnls)
    gp = sum(p - COST_TICKS for p in pnls if p - COST_TICKS > 0)
    gl = sum(abs(p - COST_TICKS) for p in pnls if p - COST_TICKS < 0)
    pf = gp / gl if gl > 0 else (float("inf") if gp > 0 else 0)

    # Max drawdown
    cum = 0.0
    peak = 0.0
    max_dd = 0.0
    for p in pnls:
        cum += (p - COST_TICKS)
        peak = max(peak, cum)
        dd = peak - cum
        max_dd = max(max_dd, dd)

    net = sum(p - COST_TICKS for p in pnls)
    profit_dd = net / max_dd if max_dd > 0 else (float("inf") if net > 0 else 0)

    # Exit breakdown as percentages
    total_exits = sum(exit_counts.values())
    exit_pcts = {}
    if total_exits > 0:
        for k, v in exit_counts.items():
            exit_pcts[k] = round(v / total_exits * 100, 1)

    return {
        "pf": pf, "trades": trades, "profit_dd": profit_dd,
        "max_dd": max_dd, "exit_breakdown": exit_counts,
        "exit_pcts": exit_pcts, "pnls": pnls, "net_profit": net,
    }


# P1 ONLY. Include exit_type breakdown for every winner.

# ══════════════════════════════════════════════════════════════════════════
# Combo Generation
# ══════════════════════════════════════════════════════════════════════════

print("\n── Generating Phase 1 Combos ──")

TARGETS = [40, 60, 80, 120]
STOPS = [90, 120, 160, 190, 240]
TCAPS = [30, 50, 80, 120, 160]
T2_VALS = [80, 120, 160]
T3_VALS = [160, 200, 240, 300]

# Single-leg: 4×5×5 = 100
single_combos = list(product(TARGETS, STOPS, TCAPS))
print(f"  Single-leg combos: {len(single_combos)}")

# Two-leg: T1 × T2 × Stop × TCap × Split, T2 > T1
SPLITS_2 = [(0.5, 0.5), (0.67, 0.33)]
two_combos = []
for t1, t2, s, tc, split in product(TARGETS, T2_VALS, STOPS, TCAPS, SPLITS_2):
    if t2 > t1:
        two_combos.append((t1, t2, s, tc, split))
print(f"  Two-leg combos: {len(two_combos)}")

# Three-leg: T1 × T2 × T3 × Stop × TCap × Split, T3 > T2 > T1
SPLITS_3 = [(1/3, 1/3, 1/3), (0.5, 0.25, 0.25)]
three_combos = []
for t1, t2, t3, s, tc, split in product(TARGETS, T2_VALS, T3_VALS, STOPS, TCAPS, SPLITS_3):
    if t3 > t2 > t1:
        three_combos.append((t1, t2, t3, s, tc, split))
print(f"  Three-leg combos: {len(three_combos)}")
print(f"  TOTAL Phase 1 combos: {len(single_combos) + len(two_combos) + len(three_combos)}")

# ══════════════════════════════════════════════════════════════════════════
# Run Sweep
# ══════════════════════════════════════════════════════════════════════════


def sweep_population(name, rbis, dirs, current_best):
    """Run all Phase 1 combos on a population. Returns sorted results list."""
    print(f"\n{'=' * 72}")
    print(f"SWEEPING: {name}")
    print(f"  Touches: {len(rbis)}, Current best PF: {current_best['pf']}")
    print(f"  Current config: Stop={current_best['stop']}t, "
          f"Target={current_best['target']}t, TC={current_best['tc']}")
    print(f"{'=' * 72}")

    results = []
    t0 = time.time()

    # --- Single-leg ---
    print(f"\n  Single-leg ({len(single_combos)} combos)...", end=" ", flush=True)
    for target, stop, tcap in single_combos:
        m = run_sweep_single(rbis, dirs, stop, target, tcap)
        if m["trades"] >= MIN_TRADES:
            results.append({
                "legs": 1, "targets": [target], "split": [1.0],
                "stop": stop, "tcap": tcap, **m,
            })
    print(f"done ({len(results)} valid)")

    # P1 ONLY. Phase 1 constraints: T2 > T1, T3 > T2 > T1.

    # --- Two-leg ---
    n_before = len(results)
    print(f"  Two-leg ({len(two_combos)} combos)...", end=" ", flush=True)
    for t1, t2, stop, tcap, split in two_combos:
        m = run_sweep_multileg(rbis, dirs, stop, [t1, t2],
                               list(split), tcap)
        if m["trades"] >= MIN_TRADES:
            results.append({
                "legs": 2, "targets": [t1, t2], "split": list(split),
                "stop": stop, "tcap": tcap, **m,
            })
    print(f"done ({len(results) - n_before} valid)")

    # --- Three-leg ---
    n_before_3 = len(results)
    print(f"  Three-leg ({len(three_combos)} combos)...", end=" ", flush=True)
    for t1, t2, t3, stop, tcap, split in three_combos:
        m = run_sweep_multileg(rbis, dirs, stop, [t1, t2, t3],
                               list(split), tcap)
        if m["trades"] >= MIN_TRADES:
            # Flag low T3 fill rate
            t3_fill = m.get("t3_fill_rate", 0)
            m["t3_low_fill"] = t3_fill < 0.15
            results.append({
                "legs": 3, "targets": [t1, t2, t3], "split": list(split),
                "stop": stop, "tcap": tcap, **m,
            })
    print(f"done ({len(results) - n_before_3} valid)")

    elapsed = time.time() - t0
    print(f"\n  Total valid combos: {len(results)} (elapsed: {elapsed:.1f}s)")

    # Sort by PF descending
    results.sort(key=lambda r: -r["pf"])

    # --- Print top 10 ---
    print(f"\n  ── Top 10 {name} ──")
    print(f"  {'Rank':>4} {'Legs':>4} {'Targets':>18} {'Split':>14} "
          f"{'Stop':>5} {'TCap':>5} {'PF@3t':>8} {'Trades':>6} "
          f"{'P/DD':>8} {'Tgt%':>5} {'Stp%':>5} {'TC%':>5}")
    print(f"  {'-' * 100}")

    for rank, r in enumerate(results[:10], 1):
        tgt_str = "/".join(str(t) for t in r["targets"])
        split_str = "/".join(f"{s:.0%}" for s in r["split"])
        ep = r["exit_pcts"]
        # Sum all target exit pcts
        tgt_pct = sum(v for k, v in ep.items() if "target" in str(k))
        stp_pct = ep.get("stop", 0)
        tc_pct = ep.get("time_cap", 0)
        pf_str = f"{r['pf']:.2f}" if r["pf"] < 1e6 else "inf"

        flag = ""
        if r.get("t3_low_fill"):
            flag = " [T3<15%]"

        print(f"  {rank:>4} {r['legs']:>4} {tgt_str:>18} {split_str:>14} "
              f"{r['stop']:>5} {r['tcap']:>5} {pf_str:>8} {r['trades']:>6} "
              f"{r['profit_dd']:>8.2f} {tgt_pct:>5.1f} {stp_pct:>5.1f} "
              f"{tc_pct:>5.1f}{flag}")

    # Compare rank 1 vs current best
    if results:
        best = results[0]
        print(f"\n  Phase 1 best: PF={best['pf']:.2f}, "
              f"Trades={best['trades']}, P/DD={best['profit_dd']:.2f}")
        print(f"  Current deployed: PF={current_best['pf']:.2f}")
        delta = best["pf"] - current_best["pf"]
        print(f"  Delta: {delta:+.2f} PF")

    return results


# Current deployed configs
CT_CURRENT = {"stop": 190, "target": 80, "tc": 120, "pf": 30.58}
ALL_CURRENT = {"stop": 190, "target": 60, "tc": 120, "pf": 9.39}

# Run sweeps
ct_results = sweep_population("CT mode (seg3 A-Cal ModeB)", ct_rbis, ct_dirs, CT_CURRENT)
all_results = sweep_population("All mode (seg1 A-Cal ModeA)", all_rbis, all_dirs, ALL_CURRENT)

# P1 ONLY. Minimum trade gate (≥ 20) applied. Compare against current deployed.

# ══════════════════════════════════════════════════════════════════════════
# Per-Leg Stop Behavior Tests (multi-leg winners only)
# ══════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 72)
print("PER-LEG STOP BEHAVIOR TESTS (multi-leg top-3 winners only)")
print("=" * 72)


def sim_multileg_perstop(entry_bar, direction, stop, targets, weights, tcap,
                         stop_mode="shared"):
    """Multi-leg sim with per-leg stop behavior.

    stop_mode:
        'shared': all legs share same stop (default)
        'move_after_t1': after T1 fills, remaining legs' stop moves to entry (0t)
        'move_after_t2': after T2 fills, remaining leg's stop moves to T1
    """
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
    legs_filled = 0

    end = min(entry_bar + tcap, n_bars)
    for i in range(entry_bar, end):
        h, l, last = bar_arr[i, 1], bar_arr[i, 2], bar_arr[i, 3]
        bh = i - entry_bar + 1

        # Stop check
        if direction == 1:
            stop_hit = l <= stop_price
        else:
            stop_hit = h >= stop_price

        if stop_hit:
            stop_pnl = (stop_price - ep) / TICK_SIZE if direction == 1 \
                else (ep - stop_price) / TICK_SIZE
            for j in range(n_legs):
                if leg_open[j]:
                    leg_pnls[j] = stop_pnl
                    leg_exits[j] = "stop"
                    leg_open[j] = False
            wpnl = sum(w * p for w, p in zip(weights, leg_pnls))
            return wpnl, bh, leg_exits, leg_pnls

        # Target checks
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
                legs_filled += 1

                # Per-leg stop moves
                if stop_mode == "move_after_t1" and legs_filled == 1:
                    # Move remaining legs' stop to entry
                    if direction == 1:
                        stop_price = max(stop_price, ep)
                    else:
                        stop_price = min(stop_price, ep)
                elif stop_mode == "move_after_t2" and legs_filled == 2:
                    # Move remaining leg's stop to T1
                    t1_price = target_prices[0]
                    if direction == 1:
                        stop_price = max(stop_price, t1_price)
                    else:
                        stop_price = min(stop_price, t1_price)

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


def test_perstop(name, rbis, dirs, winner):
    """Test per-leg stop behaviors on a multi-leg winner."""
    if winner["legs"] < 2:
        return None

    print(f"\n  {name}: testing per-leg stop on "
          f"{winner['legs']}-leg {'/'.join(str(t) for t in winner['targets'])}")

    stop_modes = ["shared", "move_after_t1"]
    if winner["legs"] >= 3:
        stop_modes.append("move_after_t2")

    results = {}
    for mode in stop_modes:
        pnls = []
        exit_counts = {}
        in_trade_until = -1
        for idx in range(len(rbis)):
            rbi = int(rbis[idx])
            entry_bar = rbi + 1
            if entry_bar <= in_trade_until:
                continue
            d = int(dirs[idx])
            wpnl, bh, leg_exits, _ = sim_multileg_perstop(
                entry_bar, d, winner["stop"], winner["targets"],
                winner["split"], winner["tcap"], stop_mode=mode)
            if wpnl is not None:
                pnls.append(wpnl)
                in_trade_until = entry_bar + bh - 1
                for ex in leg_exits:
                    if ex:
                        exit_counts[ex] = exit_counts.get(ex, 0) + 1

        m = _compute_metrics(pnls, exit_counts)
        results[mode] = m
        pf_str = f"{m['pf']:.2f}" if m["pf"] < 1e6 else "inf"
        print(f"    {mode:>20}: PF={pf_str}, Trades={m['trades']}, "
              f"P/DD={m['profit_dd']:.2f}")

    return results


def run_perstop_tests(name, rbis, dirs, results):
    """Run per-leg stop tests on top-3 multi-leg winners."""
    multileg_winners = [r for r in results[:3] if r["legs"] >= 2]
    if not multileg_winners:
        print(f"\n  {name}: No multi-leg winners in top 3 — skipping per-leg stop tests.")
        return

    for i, w in enumerate(multileg_winners):
        test_perstop(f"{name} #{i+1}", rbis, dirs, w)


run_perstop_tests("CT mode", ct_rbis, ct_dirs, ct_results)
run_perstop_tests("All mode", all_rbis, all_dirs, all_results)

# P1 ONLY. Phase 1 complete — lock results. Only top 3 advance to Phase 2.

# ══════════════════════════════════════════════════════════════════════════
# Save Results
# ══════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 72)
print("SAVING PHASE 1 RESULTS")
print("=" * 72)


def format_result_row(rank, r):
    """Format one result row for markdown table."""
    tgt_str = "/".join(str(t) for t in r["targets"])
    split_str = "/".join(f"{int(s*100)}" for s in r["split"])
    ep = r["exit_pcts"]
    tgt_pct = sum(v for k, v in ep.items() if "target" in str(k))
    stp_pct = ep.get("stop", 0)
    tc_pct = ep.get("time_cap", 0)
    pf_str = f"{r['pf']:.2f}" if r["pf"] < 1e6 else "inf"
    flag = " ⚠️T3<15%" if r.get("t3_low_fill") else ""
    return (f"| {rank} | {r['legs']} | {tgt_str} | {split_str} | {r['stop']} | "
            f"{r['tcap']} | {pf_str} | {r['trades']} | {r['profit_dd']:.2f} | "
            f"{r['max_dd']:.0f} | {r['net_profit']:.1f} | "
            f"{tgt_pct:.1f}% | {stp_pct:.1f}% | {tc_pct:.1f}%{flag} |")


def build_report(ct_res, all_res):
    """Build Phase 1 results markdown."""
    lines = [
        "# Exit Sweep — Phase 1 Results",
        "",
        "P1 ONLY. P2 NOT LOADED.",
        "",
        f"Date: {time.strftime('%Y-%m-%d %H:%M')}",
        "",
        "## CT mode (seg3 A-Cal ModeB)",
        "",
        f"Population: {len(ct_rbis)} touches",
        f"Current deployed: Stop=190t, Target=80t, TC=120, PF=30.58",
        "",
        "| Rank | Legs | Targets | Split | Stop | TCap | PF@3t | Trades | P/DD | MaxDD | NetProfit | Tgt% | Stp% | TC% |",
        "|------|------|---------|-------|------|------|-------|--------|------|-------|-----------|------|------|-----|",
    ]
    for rank, r in enumerate(ct_res[:10], 1):
        lines.append(format_result_row(rank, r))

    lines += [
        "",
        "## All mode (seg1 A-Cal ModeA)",
        "",
        f"Population: {len(all_rbis)} touches",
        f"Current deployed: Stop=190t, Target=60t, TC=120, PF=9.39",
        "",
        "| Rank | Legs | Targets | Split | Stop | TCap | PF@3t | Trades | P/DD | MaxDD | NetProfit | Tgt% | Stp% | TC% |",
        "|------|------|---------|-------|------|------|-------|--------|------|-------|-----------|------|------|-----|",
    ]
    for rank, r in enumerate(all_res[:10], 1):
        lines.append(format_result_row(rank, r))

    # Phase 1 winners summary
    ct_best = ct_res[0] if ct_res else None
    all_best = all_res[0] if all_res else None
    lines += [
        "",
        "## Phase 1 Winners",
        "",
    ]
    if ct_best:
        tgt = "/".join(str(t) for t in ct_best["targets"])
        pf_s = f"{ct_best['pf']:.2f}" if ct_best["pf"] < 1e6 else "inf"
        lines.append(f"**CT mode:** {ct_best['legs']}-leg, Targets={tgt}, "
                      f"Stop={ct_best['stop']}t, TC={ct_best['tcap']}, "
                      f"PF={pf_s}, Trades={ct_best['trades']}")
    if all_best:
        tgt = "/".join(str(t) for t in all_best["targets"])
        pf_s = f"{all_best['pf']:.2f}" if all_best["pf"] < 1e6 else "inf"
        lines.append(f"**All mode:** {all_best['legs']}-leg, Targets={tgt}, "
                      f"Stop={all_best['stop']}t, TC={all_best['tcap']}, "
                      f"PF={pf_s}, Trades={all_best['trades']}")

    lines += [
        "",
        "Phase 1 winners — advancing top 3 per population to Phase 2.",
        "",
        "## Self-Check",
        "- [x] P1 only — P2 not loaded",
        "- [x] Phase 1 tested single-leg, 2-leg, and 3-leg with size splits",
        "- [x] Phase 1 constraints enforced (T3 > T2 > T1)",
        f"- [x] Minimum trade gate (≥ {MIN_TRADES}) applied",
        "- [x] Three-leg T3 fill rate reported",
        "- [x] Per-leg stop tested for multi-leg Phase 1 winners",
        "- [x] Compared against current deployed config",
    ]
    return "\n".join(lines)


# Save markdown report
report = build_report(ct_results, all_results)
report_path = OUT_DIR / "exit_sweep_phase1_results.md"
report_path.write_text(report, encoding="utf-8")
print(f"  Report saved: {report_path}")

# Save machine-readable top-3 per population for Phase 2
def extract_top3(results):
    """Extract top 3 as serializable dicts (no pnls array)."""
    top3 = []
    for r in results[:3]:
        entry = {k: v for k, v in r.items() if k != "pnls"}
        top3.append(entry)
    return top3


phase1_configs = {
    "ct_mode": {
        "current_best": CT_CURRENT,
        "top3": extract_top3(ct_results),
    },
    "all_mode": {
        "current_best": ALL_CURRENT,
        "top3": extract_top3(all_results),
    },
}
configs_path = OUT_DIR / "exit_sweep_phase1_configs.json"
with open(configs_path, "w") as f:
    json.dump(phase1_configs, f, indent=2, default=str)
print(f"  Configs saved: {configs_path}")

# ══════════════════════════════════════════════════════════════════════════
# Final Summary
# ══════════════════════════════════════════════════════════════════════════

print("\n" + "=" * 72)
ct_w = ct_results[0] if ct_results else None
all_w = all_results[0] if all_results else None

if ct_w:
    ct_tgt = "/".join(str(t) for t in ct_w["targets"])
    ct_pf = f"{ct_w['pf']:.2f}" if ct_w["pf"] < 1e6 else "inf"
    print(f"Phase 1 winners — CT mode: {ct_w['legs']}-leg "
          f"Targets={ct_tgt} Stop={ct_w['stop']}t TC={ct_w['tcap']} PF={ct_pf}")
if all_w:
    all_tgt = "/".join(str(t) for t in all_w["targets"])
    all_pf = f"{all_w['pf']:.2f}" if all_w["pf"] < 1e6 else "inf"
    print(f"Phase 1 winners — All mode: {all_w['legs']}-leg "
          f"Targets={all_tgt} Stop={all_w['stop']}t TC={all_w['tcap']} PF={all_pf}")

print(f"\nAdvancing top 3 per population to Phase 2.")
print("=" * 72)
