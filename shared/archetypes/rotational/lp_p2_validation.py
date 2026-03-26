# archetype: rotational
"""LP P2 Validation — run frozen config on P2 holdout data.

Runs SD=25 HS=125 MCS=2 on P2 1-tick data, saves cycle data,
computes all metrics for comparison against P1 baseline.

Usage:
    python lp_p2_validation.py
"""

from __future__ import annotations

import csv
import math
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

# Import simulation from sweep
from lp_sweep import load_bars_numpy, run_sim

TICK_VALUE = 5.0
COMMISSION_PER_RT = 3.50

# Frozen config
SD = 25.0
HS = 125.0
MCS = 2
ML = 1
MF = 0

# Time blocks
TIME_BLOCKS = [
    ("09:30-10:00", 34200, 36000), ("10:00-10:30", 36000, 37800),
    ("10:30-11:00", 37800, 39600), ("11:00-11:30", 39600, 41400),
    ("11:30-12:00", 41400, 43200), ("12:00-12:30", 43200, 45000),
    ("12:30-13:00", 45000, 46800), ("13:00-13:30", 46800, 48600),
    ("13:30-14:00", 48600, 50400), ("14:00-14:30", 50400, 52200),
    ("14:30-15:00", 52200, 54000), ("15:00-15:30", 54000, 55800),
    ("15:30-15:50", 55800, 57000),
]


def parse_time_sec(dt):
    t = dt.split(" ")[1].split(":")
    return int(t[0]) * 3600 + int(t[1]) * 60 + int(t[2])


def get_block(dt):
    s = parse_time_sec(dt)
    for label, start, end in TIME_BLOCKS:
        if start <= s < end:
            return label
    return "outside"


def compute_net(c):
    pos = min(1 * (2 ** c["depth"]), MCS)
    return c["pnl_ticks"] * TICK_VALUE - pos * COMMISSION_PER_RT


def main():
    out_dir = Path(r"C:\Projects\pipeline\shared\archetypes\rotational\docs")

    # Load P2 bars
    print("Loading P2 bar data...")
    t0 = time.time()
    bars = load_bars_numpy(
        r"C:\Projects\pipeline\stages\01-data\data\bar_data\tick\NQ_BarData_1tick_rot_P2.csv"
    )
    print(f"Loaded {bars['n']} bars in {time.time()-t0:.1f}s")

    # Run frozen config
    print(f"\nRunning frozen config: SD={SD} HS={HS} MCS={MCS}...")
    t1 = time.time()
    cycles = run_sim(bars, SD, HS, MF, ML, MCS)
    print(f"Completed in {time.time()-t1:.1f}s: {len(cycles)} cycles")

    # Save cycle data
    cycle_path = out_dir / "p2_cycles_sd25_hs125.csv"
    fields = [
        "cycle_id", "watch_start_dt", "watch_price", "watch_high", "watch_low",
        "watch_bars", "seed_dt", "exit_dt", "direction",
        "seed_price", "avg_entry_price", "exit_price", "exit_type",
        "depth", "max_position", "pnl_ticks", "pnl_dollars",
        "bars_held", "mfe_ticks", "mae_ticks",
    ]
    with open(cycle_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for c in cycles:
            row = {}
            for k in fields:
                v = c.get(k, "")
                if isinstance(v, float):
                    row[k] = f"{v:.2f}"
                else:
                    row[k] = v
            w.writerow(row)
    print(f"Cycles saved to {cycle_path}")

    # === Overall metrics ===
    pnls = [compute_net(c) for c in cycles]
    n = len(pnls)
    wins = sum(1 for p in pnls if p >= 0)
    mean_pnl = sum(pnls) / n
    var = sum((p - mean_pnl) ** 2 for p in pnls) / (n - 1)
    sigma = math.sqrt(var)

    # Max consecutive losses
    mcl = 0; cl = 0
    for p in pnls:
        if p < 0: cl += 1; mcl = max(mcl, cl)
        else: cl = 0

    # PropScore
    ps = (mean_pnl / sigma) * math.sqrt(2000 / 3000) if sigma > 0 else 0

    # Depth/exit counts
    d0 = sum(1 for c in cycles if c["depth"] == 0)
    d1 = sum(1 for c in cycles if c["depth"] >= 1)
    rev = sum(1 for c in cycles if c["exit_type"] == "REVERSAL")
    hs_count = sum(1 for c in cycles if c["exit_type"] == "HARD_STOP")
    eod = sum(1 for c in cycles if c["exit_type"] == "EOD_FLATTEN")

    # Daily stats
    daily = defaultdict(float)
    for c, pnl in zip(cycles, pnls):
        daily[c["seed_dt"].split(" ")[0]] += pnl
    daily_pnls = np.array(list(daily.values()))
    n_days = len(daily_pnls)
    losing_days = sum(1 for d in daily_pnls if d < 0)

    # Equity curve
    cum = np.cumsum(pnls)
    peak = np.maximum.accumulate(cum)
    dd = peak - cum
    max_dd = float(np.max(dd))

    # Sharpe/Sortino/Calmar
    mean_daily = np.mean(daily_pnls)
    std_daily = np.std(daily_pnls, ddof=1)
    down_daily = daily_pnls[daily_pnls < 0]
    down_std = np.std(down_daily, ddof=1) if len(down_daily) > 1 else 1.0
    sharpe = (mean_daily / std_daily) * np.sqrt(252) if std_daily > 0 else 0
    sortino = (mean_daily / down_std) * np.sqrt(252) if down_std > 0 else 0
    daily_cum = np.cumsum(daily_pnls)
    daily_peak = np.maximum.accumulate(daily_cum)
    daily_max_dd = float(np.max(daily_peak - daily_cum))
    calmar = (mean_daily * 252) / daily_max_dd if daily_max_dd > 0 else 0

    print(f"\n{'='*60}")
    print(f"P2 VALIDATION RESULTS — SD={SD} HS={HS} MCS={MCS}")
    print(f"{'='*60}")
    print(f"\n--- Overall ---")
    print(f"  Cycles: {n}, Trading days: {n_days}")
    print(f"  Win rate: {wins/n:.1%} ({wins}W / {n-wins}L)")
    print(f"  Net E[R]: ${mean_pnl:.2f}")
    print(f"  Sigma: ${sigma:.2f}")
    print(f"  PropScore: {ps:.4f}")
    print(f"  Total profit: ${sum(pnls):.2f}")
    print(f"  Max DD: ${max_dd:.2f}")
    print(f"  Profit/DD: {sum(pnls)/max_dd:.2f}" if max_dd > 0 else "  Profit/DD: N/A")
    print(f"  Max consecutive losses: {mcl}")
    print(f"  Depth: d0={d0} d1={d1}")
    print(f"  Exits: REVERSAL={rev} HARD_STOP={hs_count} EOD={eod}")

    print(f"\n--- Ratios (annualized from {n_days} days) ---")
    print(f"  Sharpe:  {sharpe:.2f}")
    print(f"  Sortino: {sortino:.2f}")
    print(f"  Calmar:  {calmar:.2f}")
    print(f"  Daily: mean=${mean_daily:.2f} std=${std_daily:.2f}")
    print(f"  Losing days: {losing_days}/{n_days} ({losing_days/n_days:.0%})")
    print(f"  Worst day: ${np.min(daily_pnls):.2f}, Best day: ${np.max(daily_pnls):.2f}")

    # === Regime analysis ===
    categories = {
        "clean_rotation": [], "martingale_save": [],
        "fast_trend": [], "trend_overcame": [],
        "eod_incomplete": [],
    }
    for c, pnl in zip(cycles, pnls):
        if c["exit_type"] == "REVERSAL":
            if c["depth"] == 0: categories["clean_rotation"].append(pnl)
            else: categories["martingale_save"].append(pnl)
        elif c["exit_type"] == "HARD_STOP":
            if c["depth"] == 0: categories["fast_trend"].append(pnl)
            else: categories["trend_overcame"].append(pnl)
        else:
            categories["eod_incomplete"].append(pnl)

    print(f"\n--- Regime ---")
    print(f"  {'Regime':<20} {'Count':>6} {'%':>6} {'Avg PnL':>10} {'Total':>12}")
    print("  " + "-" * 60)
    for name, cat_pnls in categories.items():
        cn = len(cat_pnls)
        if cn > 0:
            print(f"  {name:<20} {cn:>6} {cn/n:>6.1%} ${sum(cat_pnls)/cn:>9.2f} ${sum(cat_pnls):>11.2f}")

    # === Time blocks ===
    block_data = defaultdict(list)
    for c, pnl in zip(cycles, pnls):
        b = get_block(c["seed_dt"])
        if b != "outside":
            block_data[b].append({"pnl": pnl, "exit": c["exit_type"], "depth": c["depth"]})

    print(f"\n--- Time Blocks ---")
    print(f"  {'Block':<14} {'Cycles':>7} {'WinRate':>8} {'E[R]':>10} {'Total':>12} {'Rev':>5} {'Stop':>5} {'EOD':>4}")
    print("  " + "-" * 75)
    for label, _, _ in TIME_BLOCKS:
        bc = block_data.get(label, [])
        if not bc:
            continue
        bn = len(bc)
        bpnls = [x["pnl"] for x in bc]
        bwins = sum(1 for p in bpnls if p >= 0)
        brev = sum(1 for x in bc if x["exit"] == "REVERSAL")
        bstop = sum(1 for x in bc if x["exit"] == "HARD_STOP")
        beod = sum(1 for x in bc if x["exit"] == "EOD_FLATTEN")
        print(f"  {label:<14} {bn:>7} {bwins/bn:>8.1%} ${sum(bpnls)/bn:>9.2f} ${sum(bpnls):>11.2f} {brev:>5} {bstop:>5} {beod:>4}")

    # === P1 vs P2 comparison table ===
    print(f"\n--- P1 vs P2 Comparison ---")
    print(f"  {'Metric':<30} {'P1':>12} {'P2':>12}")
    print("  " + "-" * 55)
    p1 = {  # hardcoded from P1 results
        "cycles": 3165, "win_rate": 0.734, "net_er": 33.19, "sigma": 768.64,
        "prop_score": 0.0353, "max_dd": 20277, "mcl": 6,
        "d0_pct": 1624/3165, "d1_pct": 1541/3165,
        "regime_rotation": 0.501, "regime_save": 0.224, "regime_trend": 0.258,
        "sharpe": 4.87, "sortino": 8.64, "calmar": 25.82,
    }
    p2_vals = {
        "cycles": n, "win_rate": wins/n, "net_er": mean_pnl, "sigma": sigma,
        "prop_score": ps, "max_dd": max_dd, "mcl": mcl,
        "d0_pct": d0/n, "d1_pct": d1/n,
        "regime_rotation": len(categories["clean_rotation"])/n,
        "regime_save": len(categories["martingale_save"])/n,
        "regime_trend": len(categories["trend_overcame"])/n,
        "sharpe": sharpe, "sortino": sortino, "calmar": calmar,
    }
    comparisons = [
        ("Cycles", f"{p1['cycles']}", f"{p2_vals['cycles']}"),
        ("Win rate", f"{p1['win_rate']:.1%}", f"{p2_vals['win_rate']:.1%}"),
        ("Net E[R]", f"${p1['net_er']:.2f}", f"${p2_vals['net_er']:.2f}"),
        ("Sigma", f"${p1['sigma']:.2f}", f"${p2_vals['sigma']:.2f}"),
        ("PropScore", f"{p1['prop_score']:.4f}", f"{p2_vals['prop_score']:.4f}"),
        ("Max DD", f"${p1['max_dd']:,.0f}", f"${p2_vals['max_dd']:,.0f}"),
        ("Max consec losses", f"{p1['mcl']}", f"{p2_vals['mcl']}"),
        ("Depth 0 %", f"{p1['d0_pct']:.1%}", f"{p2_vals['d0_pct']:.1%}"),
        ("Depth 1 %", f"{p1['d1_pct']:.1%}", f"{p2_vals['d1_pct']:.1%}"),
        ("% Clean rotation", f"{p1['regime_rotation']:.1%}", f"{p2_vals['regime_rotation']:.1%}"),
        ("% Martingale save", f"{p1['regime_save']:.1%}", f"{p2_vals['regime_save']:.1%}"),
        ("% Trend overcame", f"{p1['regime_trend']:.1%}", f"{p2_vals['regime_trend']:.1%}"),
        ("Sharpe", f"{p1['sharpe']:.2f}", f"{p2_vals['sharpe']:.2f}"),
        ("Sortino", f"{p1['sortino']:.2f}", f"{p2_vals['sortino']:.2f}"),
        ("Calmar", f"{p1['calmar']:.2f}", f"{p2_vals['calmar']:.2f}"),
    ]
    for label, v1, v2 in comparisons:
        print(f"  {label:<30} {v1:>12} {v2:>12}")

    print(f"\nTotal time: {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
