# archetype: rotational
"""LP Stress Test — Monte Carlo, WR compression, slippage, Kelly, LucidFlex eval sim.

Reads cycle data from sweep_all_cycles.csv for the best config and runs:
1. Historical drawdown analysis
2. Serial correlation check
3. Bootstrap Monte Carlo (10K paths)
4. Reshuffling Monte Carlo (10K paths)
5. WR compression stress test
6. Slippage sensitivity
7. Kelly sizing
8. LucidFlex eval Monte Carlo (10K paths with trailing drawdown + consistency)

Usage:
    python lp_stress_test.py [--config-id 79] [--time-gate] [--output-dir PATH]
"""

from __future__ import annotations

import csv
import math
import random
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

TICK_VALUE = 5.0  # $5/tick NQ mini
COMMISSION_PER_RT = 3.50
MLL = 2000.0
EVAL_TARGET = 3000.0
INITIAL_TRAIL_BALANCE = 52100.0
STARTING_BALANCE = 50000.0

# Time gate: exclude these blocks (seed_dt seconds)
BAD_BLOCKS = [
    (9*3600+30*60, 10*3600),      # 09:30-10:00
    (12*3600+30*60, 13*3600),     # 12:30-13:00
    (13*3600+30*60, 14*3600),     # 13:30-14:00
]


def parse_time_sec(dt: str) -> int:
    t = dt.split(" ")[1]
    p = t.split(":")
    return int(p[0]) * 3600 + int(p[1]) * 60 + int(p[2])


def parse_date(dt: str) -> str:
    return dt.split(" ")[0]


def in_bad_block(dt: str) -> bool:
    s = parse_time_sec(dt)
    for start, end in BAD_BLOCKS:
        if start <= s < end:
            return True
    return False


def compute_net_pnl(pnl_ticks: float, depth: int, mcs: int) -> float:
    pos = min(1 * (2 ** depth), mcs)
    gross = pnl_ticks * TICK_VALUE
    comm = pos * COMMISSION_PER_RT
    return gross - comm


# ---------------------------------------------------------------------------
#  Load cycle data
# ---------------------------------------------------------------------------
def load_cycles(filepath: str, config_id: int, time_gate: bool) -> list[dict]:
    cycles = []
    with open(filepath) as f:
        for row in csv.DictReader(f):
            if int(row["config_id"]) != config_id:
                continue
            if time_gate and in_bad_block(row["seed_dt"]):
                continue
            row["depth"] = int(row["depth"])
            row["max_position"] = int(row["max_position"])
            row["pnl_ticks"] = float(row["pnl_ticks"])
            row["config_mcs"] = int(row["config_mcs"])
            row["net_pnl"] = compute_net_pnl(row["pnl_ticks"], row["depth"], row["config_mcs"])
            row["date"] = parse_date(row["seed_dt"])
            cycles.append(row)
    return cycles


# ---------------------------------------------------------------------------
#  Step 1: Historical drawdown
# ---------------------------------------------------------------------------
def historical_drawdown(cycles: list[dict]) -> dict:
    pnls = [c["net_pnl"] for c in cycles]
    n = len(pnls)
    cum = np.cumsum(pnls)
    peak = np.maximum.accumulate(cum)
    dd = peak - cum

    max_dd = float(np.max(dd))
    max_dd_idx = int(np.argmax(dd))
    total_profit = float(cum[-1])

    # Max consecutive losses/wins
    max_consec_loss = 0
    max_consec_win = 0
    cl = 0
    cw = 0
    for p in pnls:
        if p < 0:
            cl += 1
            cw = 0
            max_consec_loss = max(max_consec_loss, cl)
        else:
            cw += 1
            cl = 0
            max_consec_win = max(max_consec_win, cw)

    # Longest drawdown in trades
    in_dd = False
    dd_start = 0
    longest_dd_trades = 0
    for i in range(n):
        if dd[i] > 0:
            if not in_dd:
                dd_start = i
                in_dd = True
        else:
            if in_dd:
                longest_dd_trades = max(longest_dd_trades, i - dd_start)
                in_dd = False
    if in_dd:
        longest_dd_trades = max(longest_dd_trades, n - dd_start)

    # Longest drawdown in days
    dates = [c["date"] for c in cycles]
    unique_dates = sorted(set(dates))
    date_to_idx = {d: i for i, d in enumerate(unique_dates)}

    dd_start_date = None
    longest_dd_days = 0
    in_dd = False
    for i in range(n):
        if dd[i] > 0:
            if not in_dd:
                dd_start_date = dates[i]
                in_dd = True
        else:
            if in_dd and dd_start_date:
                days = date_to_idx.get(dates[i], 0) - date_to_idx.get(dd_start_date, 0)
                longest_dd_days = max(longest_dd_days, days)
                in_dd = False
    if in_dd and dd_start_date:
        days = date_to_idx.get(dates[-1], 0) - date_to_idx.get(dd_start_date, 0)
        longest_dd_days = max(longest_dd_days, days)

    # DD recovery analysis (each DD > $500)
    recoveries = []
    in_dd = False
    dd_peak_val = 0.0
    dd_trough_val = 0.0
    dd_start_idx = 0
    for i in range(n):
        if dd[i] > 0:
            if not in_dd:
                dd_peak_val = float(cum[i - 1]) if i > 0 else 0.0
                dd_start_idx = i
                in_dd = True
            dd_trough_val = min(dd_trough_val, float(cum[i]))
        else:
            if in_dd:
                dd_size = dd_peak_val - dd_trough_val
                if dd_size > 500:
                    recoveries.append({
                        "peak": dd_peak_val,
                        "trough": dd_trough_val,
                        "dd_size": dd_size,
                        "recovery_trades": i - dd_start_idx,
                    })
                in_dd = False
                dd_trough_val = 0.0

    return {
        "total_profit": total_profit,
        "max_dd": max_dd,
        "profit_dd_ratio": total_profit / max_dd if max_dd > 0 else 0,
        "max_consec_losses": max_consec_loss,
        "max_consec_wins": max_consec_win,
        "longest_dd_trades": longest_dd_trades,
        "longest_dd_days": longest_dd_days,
        "recoveries": recoveries,
        "n_trades": n,
        "n_days": len(unique_dates),
    }


# ---------------------------------------------------------------------------
#  Step 2: Serial correlation
# ---------------------------------------------------------------------------
def serial_correlation(cycles: list[dict], max_lag: int = 5) -> list[dict]:
    pnls = np.array([c["net_pnl"] for c in cycles])
    n = len(pnls)
    mean = np.mean(pnls)
    denom = np.sum((pnls - mean) ** 2)
    threshold = 2.0 / math.sqrt(n)

    results = []
    for lag in range(1, max_lag + 1):
        if lag >= n:
            break
        numer = np.sum((pnls[:-lag] - mean) * (pnls[lag:] - mean))
        r = numer / denom if denom > 0 else 0
        results.append({
            "lag": lag,
            "autocorrelation": round(float(r), 4),
            "significant": abs(r) > threshold,
            "threshold": round(threshold, 4),
        })
    return results


# ---------------------------------------------------------------------------
#  Step 3: Bootstrap Monte Carlo
# ---------------------------------------------------------------------------
def bootstrap_mc(cycles: list[dict], n_paths: int = 10000) -> dict:
    pnls = np.array([c["net_pnl"] for c in cycles])
    n = len(pnls)

    max_dds = np.empty(n_paths)
    total_profits = np.empty(n_paths)

    for p in range(n_paths):
        path = np.random.choice(pnls, size=n, replace=True)
        cum = np.cumsum(path)
        peak = np.maximum.accumulate(cum)
        dd = peak - cum
        max_dds[p] = np.max(dd)
        total_profits[p] = cum[-1]

    dd_pcts = np.percentile(max_dds, [50, 75, 90, 95, 99])
    profit_pcts = np.percentile(total_profits, [5, 25, 50, 75, 95])

    # Ruin probability
    ruin_thresholds = [1000, 1500, 2000, 2500, 3000]
    ruin_probs = {t: float(np.mean(max_dds >= t)) for t in ruin_thresholds}

    return {
        "dd_50": float(dd_pcts[0]),
        "dd_75": float(dd_pcts[1]),
        "dd_90": float(dd_pcts[2]),
        "dd_95": float(dd_pcts[3]),
        "dd_99": float(dd_pcts[4]),
        "dd_worst": float(np.max(max_dds)),
        "profit_5": float(profit_pcts[0]),
        "profit_25": float(profit_pcts[1]),
        "profit_50": float(profit_pcts[2]),
        "profit_75": float(profit_pcts[3]),
        "profit_95": float(profit_pcts[4]),
        "ruin_probs": ruin_probs,
    }


# ---------------------------------------------------------------------------
#  Step 4: Reshuffling Monte Carlo
# ---------------------------------------------------------------------------
def reshuffling_mc(cycles: list[dict], n_paths: int = 10000) -> dict:
    pnls = np.array([c["net_pnl"] for c in cycles])
    n = len(pnls)
    historical_cum = np.cumsum(pnls)
    historical_peak = np.maximum.accumulate(historical_cum)
    historical_dd = float(np.max(historical_peak - historical_cum))

    max_dds = np.empty(n_paths)
    for p in range(n_paths):
        shuffled = pnls.copy()
        np.random.shuffle(shuffled)
        cum = np.cumsum(shuffled)
        peak = np.maximum.accumulate(cum)
        dd = peak - cum
        max_dds[p] = np.max(dd)

    dd_pcts = np.percentile(max_dds, [50, 75, 90, 95, 99])
    hist_pctile = float(np.mean(max_dds <= historical_dd)) * 100

    return {
        "dd_50": float(dd_pcts[0]),
        "dd_75": float(dd_pcts[1]),
        "dd_90": float(dd_pcts[2]),
        "dd_95": float(dd_pcts[3]),
        "dd_99": float(dd_pcts[4]),
        "dd_worst": float(np.max(max_dds)),
        "historical_dd": historical_dd,
        "historical_percentile": hist_pctile,
    }


# ---------------------------------------------------------------------------
#  Step 5: WR compression
# ---------------------------------------------------------------------------
def wr_compression(cycles: list[dict], n_iter: int = 1000) -> list[dict]:
    pnls = np.array([c["net_pnl"] for c in cycles])
    n = len(pnls)
    wins = pnls >= 0
    win_indices = np.where(wins)[0]
    n_wins = len(win_indices)
    mean_loss = float(np.mean(pnls[~wins])) if np.any(~wins) else -100.0

    results = []
    for reduction_pct in [0, 2, 5, 8, 10, 15]:
        n_convert = int(n_wins * reduction_pct / 100)
        median_pfs = []
        dd_95s = []

        for _ in range(n_iter):
            degraded = pnls.copy()
            if n_convert > 0:
                convert_idx = np.random.choice(win_indices, size=n_convert, replace=False)
                degraded[convert_idx] = mean_loss

            # PF
            gross_wins = float(np.sum(degraded[degraded >= 0]))
            gross_losses = float(abs(np.sum(degraded[degraded < 0])))
            pf = gross_wins / gross_losses if gross_losses > 0 else 999

            # DD
            cum = np.cumsum(degraded)
            peak = np.maximum.accumulate(cum)
            dd = peak - cum
            max_dd = float(np.max(dd))

            median_pfs.append(pf)
            dd_95s.append(max_dd)

        results.append({
            "reduction_pct": reduction_pct,
            "effective_wr": float(np.mean(pnls >= 0)) * (1 - reduction_pct / 100),
            "median_pf": float(np.median(median_pfs)),
            "dd_95": float(np.percentile(dd_95s, 95)),
        })

    return results


# ---------------------------------------------------------------------------
#  Step 6: Slippage sensitivity
# ---------------------------------------------------------------------------
def slippage_sensitivity(cycles: list[dict]) -> list[dict]:
    results = []
    for slip_ticks in [0, 1, 2, 3, 4, 6]:
        pnls = []
        for c in cycles:
            pos = min(1 * (2 ** c["depth"]), c["config_mcs"])
            gross = c["pnl_ticks"] * TICK_VALUE
            comm = pos * COMMISSION_PER_RT
            slip_cost = pos * slip_ticks * TICK_VALUE
            pnls.append(gross - comm - slip_cost)

        pnls = np.array(pnls)
        gross_wins = float(np.sum(pnls[pnls >= 0]))
        gross_losses = float(abs(np.sum(pnls[pnls < 0])))
        pf = gross_wins / gross_losses if gross_losses > 0 else 999

        cum = np.cumsum(pnls)
        peak = np.maximum.accumulate(cum)
        dd = peak - cum

        results.append({
            "slippage_ticks_rt": slip_ticks,
            "pf": round(pf, 2),
            "net_er": round(float(np.mean(pnls)), 2),
            "total_pnl": round(float(np.sum(pnls)), 2),
            "max_dd": round(float(np.max(dd)), 2),
        })

    return results


# ---------------------------------------------------------------------------
#  Step 7: Kelly sizing
# ---------------------------------------------------------------------------
def kelly_sizing(cycles: list[dict]) -> dict:
    pnls = np.array([c["net_pnl"] for c in cycles])
    wins = pnls[pnls >= 0]
    losses = pnls[pnls < 0]

    wr = len(wins) / len(pnls) if len(pnls) > 0 else 0
    avg_win = float(np.mean(wins)) if len(wins) > 0 else 0
    avg_loss = float(abs(np.mean(losses))) if len(losses) > 0 else 1

    wl_ratio = avg_win / avg_loss if avg_loss > 0 else 999
    kelly = wr - (1 - wr) / wl_ratio if wl_ratio > 0 else 0

    return {
        "win_rate": round(wr, 4),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "wl_ratio": round(wl_ratio, 2),
        "full_kelly": round(kelly, 4),
        "half_kelly": round(kelly / 2, 4),
        "quarter_kelly": round(kelly / 4, 4),
    }


# ---------------------------------------------------------------------------
#  Step 8: LucidFlex eval Monte Carlo
# ---------------------------------------------------------------------------
def lucidflex_eval_mc(cycles: list[dict], n_paths: int = 10000) -> dict:
    """Simulate eval attempts under actual LucidFlex rules.

    Rules:
    - Starting balance: $50,000
    - MLL: $2,000 trailing EOD (simplified: trail on each trade, not EOD)
    - Profit target: $3,000
    - Consistency: largest single-day profit <= 50% of total profit
    - No time limit
    """
    # Group cycles by date for daily P&L
    daily_cycles = defaultdict(list)
    for c in cycles:
        daily_cycles[c["date"]].append(c["net_pnl"])

    dates = sorted(daily_cycles.keys())
    daily_pnls = [(d, daily_cycles[d]) for d in dates]

    passes = 0
    days_to_pass = []
    failures = 0

    for _ in range(n_paths):
        # Resample days with replacement
        sampled_days = [daily_pnls[random.randint(0, len(daily_pnls) - 1)] for _ in range(250)]

        balance = STARTING_BALANCE
        hwm = balance
        mll = balance - MLL
        cum_profit = 0.0
        max_day_profit = 0.0
        passed = False
        day_count = 0

        for date, day_trades in sampled_days:
            day_count += 1
            day_pnl = sum(day_trades)
            balance += day_pnl
            cum_profit += day_pnl

            if day_pnl > max_day_profit:
                max_day_profit = day_pnl

            # Update trailing MLL (EOD)
            if balance > hwm:
                hwm = balance
                mll = hwm - MLL

            # Check MLL breach
            if balance <= mll:
                failures += 1
                break

            # Check profit target + consistency
            if cum_profit >= EVAL_TARGET:
                if max_day_profit <= cum_profit * 0.52:  # 50% with cushion
                    passes += 1
                    days_to_pass.append(day_count)
                    passed = True
                    break
                # If consistency fails, keep trading

        if not passed and balance > mll:
            failures += 1  # ran out of days without passing

    pass_rate = passes / n_paths
    median_days = float(np.median(days_to_pass)) if days_to_pass else 0
    p25_days = float(np.percentile(days_to_pass, 25)) if days_to_pass else 0
    p75_days = float(np.percentile(days_to_pass, 75)) if days_to_pass else 0

    return {
        "pass_rate": round(pass_rate, 4),
        "failure_rate": round(failures / n_paths, 4),
        "median_days_to_pass": round(median_days, 1),
        "p25_days": round(p25_days, 1),
        "p75_days": round(p75_days, 1),
        "n_passed": passes,
        "n_failed": failures,
    }


# ---------------------------------------------------------------------------
#  Main
# ---------------------------------------------------------------------------
def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="LP Stress Test")
    parser.add_argument("--cycles-file", type=str,
                        default=r"C:\Projects\pipeline\shared\archetypes\rotational\docs\sweep_all_cycles.csv")
    parser.add_argument("--config-id", type=int, default=79)
    parser.add_argument("--time-gate", action="store_true", default=False)
    parser.add_argument("--output-dir", type=str,
                        default=r"C:\Projects\pipeline\shared\archetypes\rotational\docs")
    args = parser.parse_args()

    np.random.seed(42)
    random.seed(42)
    t0 = time.time()

    gate_label = "with time gate" if args.time_gate else "full RTH"
    print(f"Loading cycles for config {args.config_id} ({gate_label})...")
    cycles = load_cycles(args.cycles_file, args.config_id, args.time_gate)
    print(f"Loaded {len(cycles)} cycles")

    if not cycles:
        print("No cycles found. Check config_id.")
        return

    # === Step 1: Historical Drawdown ===
    print("\n=== STEP 1: HISTORICAL DRAWDOWN ===")
    hd = historical_drawdown(cycles)
    print(f"  Cycles: {hd['n_trades']}, Trading days: {hd['n_days']}")
    print(f"  Total profit: ${hd['total_profit']:.2f}")
    print(f"  Max drawdown: ${hd['max_dd']:.2f}")
    print(f"  Profit/DD ratio: {hd['profit_dd_ratio']:.2f}")
    print(f"  Max consecutive losses: {hd['max_consec_losses']}")
    print(f"  Max consecutive wins: {hd['max_consec_wins']}")
    print(f"  Longest DD: {hd['longest_dd_trades']} trades, {hd['longest_dd_days']} days")
    if hd['recoveries']:
        print(f"  Drawdowns > $500: {len(hd['recoveries'])}")
        for i, r in enumerate(hd['recoveries'][:5]):
            print(f"    DD#{i+1}: ${r['dd_size']:.0f} (peak ${r['peak']:.0f} -> trough ${r['trough']:.0f}, recovered in {r['recovery_trades']} trades)")

    # === Step 2: Serial Correlation ===
    print("\n=== STEP 2: SERIAL CORRELATION ===")
    sc = serial_correlation(cycles)
    for s in sc:
        flag = " ***" if s["significant"] else ""
        print(f"  Lag {s['lag']}: r={s['autocorrelation']:.4f} (threshold ±{s['threshold']:.4f}){flag}")

    # === Step 3: Bootstrap Monte Carlo ===
    print("\n=== STEP 3: BOOTSTRAP MONTE CARLO (10,000 paths) ===")
    t1 = time.time()
    bmc = bootstrap_mc(cycles, 10000)
    print(f"  ({time.time()-t1:.1f}s)")
    print(f"  Drawdown distribution:")
    print(f"    50th: ${bmc['dd_50']:.0f}")
    print(f"    75th: ${bmc['dd_75']:.0f}")
    print(f"    90th: ${bmc['dd_90']:.0f}")
    print(f"    95th: ${bmc['dd_95']:.0f}")
    print(f"    99th: ${bmc['dd_99']:.0f}")
    print(f"    Worst: ${bmc['dd_worst']:.0f}")
    print(f"  Profit distribution:")
    print(f"    5th: ${bmc['profit_5']:.0f}")
    print(f"    50th: ${bmc['profit_50']:.0f}")
    print(f"    95th: ${bmc['profit_95']:.0f}")
    print(f"  Ruin probability:")
    for threshold, prob in bmc["ruin_probs"].items():
        print(f"    DD >= ${threshold}: {prob:.1%}")

    # === Step 4: Reshuffling MC ===
    print("\n=== STEP 4: RESHUFFLING MONTE CARLO (10,000 paths) ===")
    t1 = time.time()
    rmc = reshuffling_mc(cycles, 10000)
    print(f"  ({time.time()-t1:.1f}s)")
    print(f"  Reshuffled DD distribution:")
    print(f"    50th: ${rmc['dd_50']:.0f}")
    print(f"    95th: ${rmc['dd_95']:.0f}")
    print(f"    99th: ${rmc['dd_99']:.0f}")
    print(f"  Historical DD: ${rmc['historical_dd']:.0f} (percentile: {rmc['historical_percentile']:.1f}%)")
    luck = "lucky" if rmc['historical_percentile'] < 30 else "average" if rmc['historical_percentile'] < 70 else "unlucky"
    print(f"  Sequence was: {luck}")

    # === Step 5: WR Compression ===
    print("\n=== STEP 5: WR COMPRESSION STRESS TEST ===")
    wrc = wr_compression(cycles)
    print(f"  {'Reduction':>10} {'Eff WR':>8} {'Med PF':>8} {'95th DD':>10}")
    print("  " + "-" * 40)
    for r in wrc:
        print(f"  {r['reduction_pct']:>9}% {r['effective_wr']:>8.1%} {r['median_pf']:>8.2f} ${r['dd_95']:>9.0f}")

    # === Step 6: Slippage ===
    print("\n=== STEP 6: SLIPPAGE SENSITIVITY ===")
    ss = slippage_sensitivity(cycles)
    print(f"  {'Slip(tks)':>10} {'PF':>8} {'Net E[R]':>10} {'Total PnL':>12} {'Max DD':>10}")
    print("  " + "-" * 55)
    for r in ss:
        print(f"  {r['slippage_ticks_rt']:>10} {r['pf']:>8.2f} ${r['net_er']:>9.2f} ${r['total_pnl']:>11.2f} ${r['max_dd']:>9.2f}")

    # === Step 7: Kelly ===
    print("\n=== STEP 7: KELLY SIZING ===")
    ks = kelly_sizing(cycles)
    print(f"  Win rate: {ks['win_rate']:.1%}")
    print(f"  Avg win: ${ks['avg_win']:.2f}, Avg loss: ${ks['avg_loss']:.2f}")
    print(f"  W/L ratio: {ks['wl_ratio']:.2f}")
    print(f"  Full Kelly: {ks['full_kelly']:.1%}")
    print(f"  Half Kelly: {ks['half_kelly']:.1%}")
    print(f"  Quarter Kelly: {ks['quarter_kelly']:.1%}")
    print(f"  Capital at 95th DD (bootstrap): ${bmc['dd_95']:.0f}")
    print(f"  Capital at 95th DD × 2 buffer: ${bmc['dd_95']*2:.0f}")

    # === Step 8: LucidFlex Eval MC ===
    print("\n=== STEP 8: LUCIDFLEX EVAL MONTE CARLO (10,000 paths) ===")
    t1 = time.time()
    emc = lucidflex_eval_mc(cycles, 10000)
    print(f"  ({time.time()-t1:.1f}s)")
    print(f"  Eval pass rate: {emc['pass_rate']:.1%}")
    print(f"  Failure rate: {emc['failure_rate']:.1%}")
    print(f"  Median days to pass: {emc['median_days_to_pass']:.0f}")
    print(f"  25th-75th days: {emc['p25_days']:.0f} - {emc['p75_days']:.0f}")
    print(f"  Passed: {emc['n_passed']}, Failed: {emc['n_failed']}")

    # === Summary ===
    total_time = time.time() - t0
    print(f"\nTotal time: {total_time:.0f}s")

    # Save results to CSV
    out_dir = Path(args.output_dir)
    out_path = out_dir / f"stress_test_config{args.config_id}{'_timegate' if args.time_gate else ''}.csv"
    with open(out_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["metric", "value"])
        w.writerow(["config_id", args.config_id])
        w.writerow(["time_gate", args.time_gate])
        w.writerow(["n_cycles", len(cycles)])
        w.writerow(["total_profit", f"{hd['total_profit']:.2f}"])
        w.writerow(["max_dd_historical", f"{hd['max_dd']:.2f}"])
        w.writerow(["profit_dd_ratio", f"{hd['profit_dd_ratio']:.2f}"])
        w.writerow(["max_consec_losses", hd['max_consec_losses']])
        w.writerow(["longest_dd_trades", hd['longest_dd_trades']])
        w.writerow(["longest_dd_days", hd['longest_dd_days']])
        for s in sc:
            w.writerow([f"autocorr_lag{s['lag']}", s['autocorrelation']])
        w.writerow(["bootstrap_dd_50", f"{bmc['dd_50']:.2f}"])
        w.writerow(["bootstrap_dd_75", f"{bmc['dd_75']:.2f}"])
        w.writerow(["bootstrap_dd_90", f"{bmc['dd_90']:.2f}"])
        w.writerow(["bootstrap_dd_95", f"{bmc['dd_95']:.2f}"])
        w.writerow(["bootstrap_dd_99", f"{bmc['dd_99']:.2f}"])
        w.writerow(["bootstrap_dd_worst", f"{bmc['dd_worst']:.2f}"])
        for t, p in bmc["ruin_probs"].items():
            w.writerow([f"ruin_prob_{t}", f"{p:.4f}"])
        w.writerow(["reshuffle_dd_95", f"{rmc['dd_95']:.2f}"])
        w.writerow(["reshuffle_historical_pctile", f"{rmc['historical_percentile']:.1f}"])
        w.writerow(["kelly_full", ks['full_kelly']])
        w.writerow(["kelly_half", ks['half_kelly']])
        w.writerow(["eval_pass_rate", emc['pass_rate']])
        w.writerow(["eval_median_days", emc['median_days_to_pass']])
        for r in wrc:
            w.writerow([f"wr_compress_{r['reduction_pct']}pct_pf", f"{r['median_pf']:.2f}"])
        for r in ss:
            w.writerow([f"slippage_{r['slippage_ticks_rt']}t_pf", f"{r['pf']:.2f}"])

    print(f"\nResults saved to {out_path}")


if __name__ == "__main__":
    main()
