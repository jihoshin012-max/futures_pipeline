# archetype: rotational
"""LP Sweep — run 108 parameter configurations on full P1 1-tick data.

Loads bars once, runs LPSimulator for each config, computes metrics,
outputs sweep_results.csv with per-config E[R], sigma, PropScore, P_pass.

Usage:
    python lp_sweep.py [--bar-file PATH] [--output-dir PATH]
"""

from __future__ import annotations

import csv
import math
import time
from itertools import product
from pathlib import Path

from lp_simulator import LPSimulator, load_bars, write_cycles_csv


# ---------------------------------------------------------------------------
#  Sweep grid
# ---------------------------------------------------------------------------
STEP_DISTS = [10.0, 15.0, 20.0, 25.0, 30.0, 50.0]
HARD_STOPS = [20.0, 30.0, 40.0, 60.0, 80.0, 120.0]
MAX_FADES_LIST = [0, 3, 5]

# Fixed params
INITIAL_QTY = 1
MAX_LEVELS = 1       # funded tier 1: depth 1
MAX_CONTRACT_SIZE = 2  # funded tier 1: 2 minis
TICK_SIZE = 0.25
COMMISSION_PER_RT_MINI = 4.00  # $4.00 per round-turn mini contract


# ---------------------------------------------------------------------------
#  Metrics computation
# ---------------------------------------------------------------------------
def compute_commission(cycle_depth: int, initial_qty: int) -> float:
    """Compute commission for a cycle.

    A cycle has: seed (initial_qty) + depth adds + flatten.
    Total round-trip contracts = 2 * total_position_at_exit.
    But simpler: each contract enters once and exits once = 1 RT each.
    Total contracts in cycle = initial_qty * 2^depth (from math doc: Q(k) = q0 * 2^k)
    But capped by max_contract_size. Since we're at depth 1 max with MCS=2:
    depth 0: 1 contract RT -> $4
    depth 1: 2 contracts RT -> $8
    """
    # Position at exit = initial_qty * 2^depth, capped at MAX_CONTRACT_SIZE
    pos = min(initial_qty * (2 ** cycle_depth), MAX_CONTRACT_SIZE)
    return pos * COMMISSION_PER_RT_MINI


def compute_metrics(cycles: list, config: dict) -> dict:
    """Compute sweep metrics from cycle records."""
    if not cycles:
        return {
            **config,
            "cycle_count": 0,
            "win_count": 0,
            "loss_count": 0,
            "win_rate": 0.0,
            "gross_er": 0.0,
            "net_er": 0.0,
            "sigma": 0.0,
            "max_consec_losses": 0,
            "p_pass_eval": 0.0,
            "p_pass_funded": 0.0,
            "prop_score": 0.0,
            "kelly_r": 0.0,
            "total_gross_pnl_ticks": 0.0,
            "total_net_pnl_dollars": 0.0,
        }

    # Per-cycle P&L in dollars (net of commission)
    pnl_gross = []
    pnl_net = []
    for c in cycles:
        gross_dollars = c.pnl_ticks * 5.0  # $5/tick for NQ mini
        comm = compute_commission(c.depth, INITIAL_QTY)
        net_dollars = gross_dollars - comm
        pnl_gross.append(gross_dollars)
        pnl_net.append(net_dollars)

    n = len(cycles)
    gross_er = sum(pnl_gross) / n
    net_er = sum(pnl_net) / n

    # Sigma (std dev of net cycle P&L)
    if n > 1:
        mean = net_er
        variance = sum((p - mean) ** 2 for p in pnl_net) / (n - 1)
        sigma = math.sqrt(variance)
    else:
        sigma = 0.0

    # Win/loss counts (net)
    wins = sum(1 for p in pnl_net if p >= 0)
    losses = n - wins

    # Max consecutive losses
    max_consec = 0
    consec = 0
    for p in pnl_net:
        if p < 0:
            consec += 1
            max_consec = max(max_consec, consec)
        else:
            consec = 0

    # P_pass (Gambler's Ruin with drift)
    # P_pass = (1 - exp(-2*E[R]*D/sigma^2)) / (1 - exp(-2*E[R]*(D+T)/sigma^2))
    # D = drawdown limit, T = profit target
    D_eval = 2000.0
    T_eval = 3000.0
    D_funded = 2000.0
    T_funded = 1000.0  # first scaling tier target

    p_pass_eval = 0.0
    p_pass_funded = 0.0
    prop_score = 0.0
    kelly_r = 0.0

    if sigma > 0 and net_er != 0:
        sig2 = sigma ** 2

        # P_pass eval
        try:
            exp_num = math.exp(-2.0 * net_er * D_eval / sig2)
            exp_den = math.exp(-2.0 * net_er * (D_eval + T_eval) / sig2)
            if abs(1.0 - exp_den) > 1e-12:
                p_pass_eval = (1.0 - exp_num) / (1.0 - exp_den)
                p_pass_eval = max(0.0, min(1.0, p_pass_eval))
        except OverflowError:
            p_pass_eval = 1.0 if net_er > 0 else 0.0

        # P_pass funded
        try:
            exp_num = math.exp(-2.0 * net_er * D_funded / sig2)
            exp_den = math.exp(-2.0 * net_er * (D_funded + T_funded) / sig2)
            if abs(1.0 - exp_den) > 1e-12:
                p_pass_funded = (1.0 - exp_num) / (1.0 - exp_den)
                p_pass_funded = max(0.0, min(1.0, p_pass_funded))
        except OverflowError:
            p_pass_funded = 1.0 if net_er > 0 else 0.0

        # PropScore = E[R]/sigma * sqrt(D/T)  (using eval params)
        prop_score = (net_er / sigma) * math.sqrt(D_eval / T_eval)

        # Fractional Kelly: r* = alpha * D * E[R] / sigma^2, alpha=0.2
        kelly_r = 0.2 * D_eval * net_er / sig2

    total_gross_ticks = sum(c.pnl_ticks for c in cycles)
    total_net_dollars = sum(pnl_net)

    return {
        **config,
        "cycle_count": n,
        "win_count": wins,
        "loss_count": losses,
        "win_rate": wins / n if n > 0 else 0.0,
        "gross_er": round(gross_er, 2),
        "net_er": round(net_er, 2),
        "sigma": round(sigma, 2),
        "max_consec_losses": max_consec,
        "p_pass_eval": round(p_pass_eval, 6),
        "p_pass_funded": round(p_pass_funded, 6),
        "prop_score": round(prop_score, 6),
        "kelly_r": round(kelly_r, 6),
        "total_gross_pnl_ticks": round(total_gross_ticks, 2),
        "total_net_pnl_dollars": round(total_net_dollars, 2),
    }


# ---------------------------------------------------------------------------
#  Main sweep
# ---------------------------------------------------------------------------
def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="LP Sweep — 108-config parameter sweep")
    parser.add_argument("--bar-file", type=str,
                        default=r"C:\Projects\pipeline\stages\01-data\data\bar_data\tick\NQ_BarData_1tick_rot_P1.csv")
    parser.add_argument("--output-dir", type=str,
                        default=r"C:\Projects\pipeline\shared\archetypes\rotational\docs")
    args = parser.parse_args()

    # Load bars once
    print(f"Loading bars from {args.bar_file}...")
    t0 = time.time()
    bars = load_bars(args.bar_file)
    t_load = time.time() - t0
    print(f"Loaded {len(bars)} bars in {t_load:.1f}s")

    # Generate configs
    configs = []
    for sd, hs, mf in product(STEP_DISTS, HARD_STOPS, MAX_FADES_LIST):
        configs.append({
            "step_dist": sd,
            "hard_stop": hs,
            "max_fades": mf,
        })

    print(f"Running {len(configs)} configurations...")
    results = []

    for idx, cfg in enumerate(configs):
        t1 = time.time()

        sim = LPSimulator(
            step_dist=cfg["step_dist"],
            initial_qty=INITIAL_QTY,
            max_levels=MAX_LEVELS,
            max_contract_size=MAX_CONTRACT_SIZE,
            hard_stop=cfg["hard_stop"],
            max_fades=cfg["max_fades"],
            tick_size=TICK_SIZE,
        )
        sim.run(bars)

        metrics = compute_metrics(sim.cycles, cfg)
        results.append(metrics)

        elapsed = time.time() - t1
        print(f"  [{idx+1:3d}/{len(configs)}] SD={cfg['step_dist']:5.1f} "
              f"HS={cfg['hard_stop']:5.0f} MF={cfg['max_fades']:1d} -> "
              f"{metrics['cycle_count']:5d} cycles, "
              f"E[R]=${metrics['net_er']:7.2f}, "
              f"PropScore={metrics['prop_score']:8.4f}  "
              f"({elapsed:.1f}s)")

    # Sort by PropScore descending
    results.sort(key=lambda r: r["prop_score"], reverse=True)

    # Write results
    out_path = Path(args.output_dir) / "sweep_results.csv"
    fieldnames = [
        "step_dist", "hard_stop", "max_fades",
        "cycle_count", "win_count", "loss_count", "win_rate",
        "gross_er", "net_er", "sigma", "max_consec_losses",
        "p_pass_eval", "p_pass_funded", "prop_score", "kelly_r",
        "total_gross_pnl_ticks", "total_net_pnl_dollars",
    ]
    with open(out_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in results:
            w.writerow({k: r[k] for k in fieldnames})

    print(f"\nResults written to {out_path}")
    print(f"\nTop 10 by PropScore:")
    print(f"{'SD':>5} {'HS':>5} {'MF':>3} {'Cycles':>7} {'WinRate':>8} "
          f"{'E[R]':>8} {'Sigma':>8} {'PropScore':>10} {'P_pass_E':>9} {'P_pass_F':>9}")
    print("-" * 85)
    for r in results[:10]:
        print(f"{r['step_dist']:5.0f} {r['hard_stop']:5.0f} {r['max_fades']:3d} "
              f"{r['cycle_count']:7d} {r['win_rate']:8.1%} "
              f"{r['net_er']:8.2f} {r['sigma']:8.2f} {r['prop_score']:10.4f} "
              f"{r['p_pass_eval']:9.4f} {r['p_pass_funded']:9.4f}")

    total_time = time.time() - t0
    print(f"\nTotal time: {total_time:.0f}s ({total_time/60:.1f}m)")


if __name__ == "__main__":
    main()
