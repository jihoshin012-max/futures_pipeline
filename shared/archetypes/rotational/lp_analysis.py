# archetype: rotational
"""LP Analysis — post-processing on sweep cycle data.

Reads sweep_all_cycles.csv and produces:
1. 30-minute block analysis: metrics per time block per config
2. Regime analysis: rotation vs trend breakdown by cycle outcome
3. Top config deep-dive with both views combined

Usage:
    python lp_analysis.py [--cycles-file PATH] [--results-file PATH] [--output-dir PATH]
"""

from __future__ import annotations

import csv
import math
from collections import defaultdict
from pathlib import Path

COMMISSION_PER_RT_MINI = 3.50
TICK_VALUE = 5.0  # $5 per tick for NQ mini


# ---------------------------------------------------------------------------
#  Time block definitions
# ---------------------------------------------------------------------------
TIME_BLOCKS = [
    ("09:30-10:00", 9*3600+30*60, 10*3600),
    ("10:00-10:30", 10*3600, 10*3600+30*60),
    ("10:30-11:00", 10*3600+30*60, 11*3600),
    ("11:00-11:30", 11*3600, 11*3600+30*60),
    ("11:30-12:00", 11*3600+30*60, 12*3600),
    ("12:00-12:30", 12*3600, 12*3600+30*60),
    ("12:30-13:00", 12*3600+30*60, 13*3600),
    ("13:00-13:30", 13*3600, 13*3600+30*60),
    ("13:30-14:00", 13*3600+30*60, 14*3600),
    ("14:00-14:30", 14*3600, 14*3600+30*60),
    ("14:30-15:00", 14*3600+30*60, 15*3600),
    ("15:00-15:30", 15*3600, 15*3600+30*60),
    ("15:30-15:50", 15*3600+30*60, 15*3600+50*60),
]


def parse_time_sec(dt_str: str) -> int:
    """Extract seconds since midnight from 'YYYY-MM-DD HH:MM:SS'."""
    time_part = dt_str.split(" ")[1] if " " in dt_str else dt_str
    parts = time_part.split(":")
    return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])


def get_time_block(dt_str: str) -> str:
    """Return the time block label for a datetime string."""
    sec = parse_time_sec(dt_str)
    for label, start, end in TIME_BLOCKS:
        if start <= sec < end:
            return label
    return "outside_rth"


def compute_commission(depth: int, mcs: int) -> float:
    pos = min(1 * (2 ** depth), mcs)
    return pos * COMMISSION_PER_RT_MINI


# ---------------------------------------------------------------------------
#  Load cycle data
# ---------------------------------------------------------------------------
def load_cycles(filepath: str) -> list[dict]:
    """Load cycle data from sweep_all_cycles.csv."""
    cycles = []
    with open(filepath, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            row["config_id"] = int(row["config_id"])
            row["config_sd"] = float(row["config_sd"])
            row["config_hs"] = float(row["config_hs"])
            row["config_mcs"] = int(row["config_mcs"])
            row["depth"] = int(row["depth"])
            row["max_position"] = int(row["max_position"])
            row["pnl_ticks"] = float(row["pnl_ticks"])
            row["pnl_dollars"] = float(row["pnl_dollars"])
            row["bars_held"] = int(row["bars_held"])
            row["mfe_ticks"] = float(row["mfe_ticks"])
            row["mae_ticks"] = float(row["mae_ticks"])
            cycles.append(row)
    return cycles


def load_results(filepath: str) -> list[dict]:
    """Load sweep_results.csv."""
    results = []
    with open(filepath, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            for k in ["config_id", "cycle_count", "win_count", "loss_count",
                       "max_consec_losses", "depth_0_count", "depth_1_count",
                       "depth_2_count", "depth_3_count", "reversal_count",
                       "hard_stop_count", "eod_flatten_count", "max_contract_size", "max_levels"]:
                if k in row:
                    row[k] = int(row[k])
            for k in ["step_dist", "hard_stop", "max_loss_dollar", "mll_pct",
                       "win_rate", "gross_er", "net_er", "sigma",
                       "p_pass_eval", "p_pass_funded", "prop_score", "kelly_r",
                       "total_gross_pnl_ticks", "total_net_pnl_dollars"]:
                if k in row:
                    row[k] = float(row[k])
            results.append(row)
    return results


# ---------------------------------------------------------------------------
#  Analysis 1: 30-minute block breakdown
# ---------------------------------------------------------------------------
def analyze_time_blocks(cycles: list[dict], top_config_ids: list[int],
                        output_path: Path) -> None:
    """Compute metrics per 30-min block for top configs."""

    # Group cycles by config_id and time block
    blocks: dict[int, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for c in cycles:
        cid = c["config_id"]
        if cid not in top_config_ids:
            continue
        block = get_time_block(c["seed_dt"])
        if block != "outside_rth":
            blocks[cid][block].append(c)

    rows = []
    for cid in top_config_ids:
        if cid not in blocks:
            continue
        cfg_cycles = blocks[cid]
        # Get config info from first cycle
        sample = None
        for bl in cfg_cycles.values():
            if bl:
                sample = bl[0]
                break
        if not sample:
            continue

        sd = sample["config_sd"]
        hs = sample["config_hs"]
        mcs = sample["config_mcs"]
        label = sample["config_label"]

        for block_label, _, _ in TIME_BLOCKS:
            bc = cfg_cycles.get(block_label, [])
            if not bc:
                rows.append({
                    "config_id": cid, "label": label, "sd": sd, "hs": hs, "mcs": mcs,
                    "time_block": block_label, "cycle_count": 0,
                    "reversals": 0, "hard_stops": 0, "eod_flattens": 0,
                    "win_rate": 0.0, "net_er": 0.0, "total_net_pnl": 0.0,
                    "avg_depth": 0.0, "pct_d0": 0.0, "pct_d1_plus": 0.0,
                })
                continue

            n = len(bc)
            pnl_net = []
            for c in bc:
                gross = c["pnl_ticks"] * TICK_VALUE
                comm = compute_commission(c["depth"], mcs)
                pnl_net.append(gross - comm)

            wins = sum(1 for p in pnl_net if p >= 0)
            reversals = sum(1 for c in bc if c["exit_type"] == "REVERSAL")
            hard_stops = sum(1 for c in bc if c["exit_type"] == "HARD_STOP")
            eod_flattens = sum(1 for c in bc if c["exit_type"] == "EOD_FLATTEN")
            avg_depth = sum(c["depth"] for c in bc) / n
            d0 = sum(1 for c in bc if c["depth"] == 0)

            rows.append({
                "config_id": cid, "label": label, "sd": sd, "hs": hs, "mcs": mcs,
                "time_block": block_label, "cycle_count": n,
                "reversals": reversals, "hard_stops": hard_stops,
                "eod_flattens": eod_flattens,
                "win_rate": wins / n if n > 0 else 0.0,
                "net_er": sum(pnl_net) / n if n > 0 else 0.0,
                "total_net_pnl": sum(pnl_net),
                "avg_depth": avg_depth,
                "pct_d0": d0 / n if n > 0 else 0.0,
                "pct_d1_plus": (n - d0) / n if n > 0 else 0.0,
            })

    # Write
    fieldnames = [
        "config_id", "label", "sd", "hs", "mcs", "time_block",
        "cycle_count", "reversals", "hard_stops", "eod_flattens",
        "win_rate", "net_er", "total_net_pnl",
        "avg_depth", "pct_d0", "pct_d1_plus",
    ]
    with open(output_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            out = {}
            for k in fieldnames:
                v = r[k]
                if isinstance(v, float):
                    out[k] = f"{v:.2f}"
                else:
                    out[k] = v
            w.writerow(out)

    # Print summary
    print("\n=== 30-MINUTE BLOCK ANALYSIS ===")
    for cid in top_config_ids:
        cfg_rows = [r for r in rows if r["config_id"] == cid]
        if not cfg_rows:
            continue
        s = cfg_rows[0]
        print(f"\nConfig {cid}: {s['label']} SD={s['sd']} HS={s['hs']} MCS={s['mcs']}")
        print(f"  {'Block':<14} {'Cycles':>7} {'WinRate':>8} {'NetE[R]':>9} "
              f"{'TotalPnL':>10} {'Reversals':>9} {'Stops':>6} {'EOD':>4} {'AvgDepth':>8}")
        print("  " + "-" * 90)
        for r in cfg_rows:
            if r["cycle_count"] == 0:
                continue
            print(f"  {r['time_block']:<14} {r['cycle_count']:>7} "
                  f"{r['win_rate']:>8.1%} ${r['net_er']:>8.2f} "
                  f"${r['total_net_pnl']:>9.2f} "
                  f"{r['reversals']:>9} {r['hard_stops']:>6} {r['eod_flattens']:>4} "
                  f"{r['avg_depth']:>8.2f}")


# ---------------------------------------------------------------------------
#  Analysis 2: Regime classification by cycle outcome
# ---------------------------------------------------------------------------
def analyze_regime(cycles: list[dict], top_config_ids: list[int],
                   output_path: Path) -> None:
    """Classify cycles as rotational vs trending by outcome at each SD scale."""

    rows = []
    for cid in top_config_ids:
        cfg_cycles = [c for c in cycles if c["config_id"] == cid]
        if not cfg_cycles:
            continue

        sd = cfg_cycles[0]["config_sd"]
        hs = cfg_cycles[0]["config_hs"]
        mcs = cfg_cycles[0]["config_mcs"]
        label = cfg_cycles[0]["config_label"]
        n = len(cfg_cycles)

        # Classify each cycle
        categories = {
            "clean_rotation": [],      # REVERSAL at depth 0
            "martingale_save": [],      # REVERSAL at depth 1+
            "fast_trend": [],           # HARD_STOP at depth 0
            "trend_overcame": [],       # HARD_STOP at depth 1+
            "eod_incomplete": [],       # EOD_FLATTEN
            "data_end": [],             # DATA_END
        }

        for c in cfg_cycles:
            gross = c["pnl_ticks"] * TICK_VALUE
            comm = compute_commission(c["depth"], mcs)
            net = gross - comm

            entry = {**c, "net_pnl": net}

            if c["exit_type"] == "REVERSAL":
                if c["depth"] == 0:
                    categories["clean_rotation"].append(entry)
                else:
                    categories["martingale_save"].append(entry)
            elif c["exit_type"] == "HARD_STOP":
                if c["depth"] == 0:
                    categories["fast_trend"].append(entry)
                else:
                    categories["trend_overcame"].append(entry)
            elif c["exit_type"] == "EOD_FLATTEN":
                categories["eod_incomplete"].append(entry)
            else:
                categories["data_end"].append(entry)

        for cat_name, cat_cycles in categories.items():
            cn = len(cat_cycles)
            if cn == 0:
                rows.append({
                    "config_id": cid, "label": label, "sd": sd, "hs": hs, "mcs": mcs,
                    "regime": cat_name, "count": 0, "pct_of_total": 0.0,
                    "avg_net_pnl": 0.0, "total_net_pnl": 0.0,
                    "avg_mfe": 0.0, "avg_mae": 0.0,
                })
                continue

            pnls = [c["net_pnl"] for c in cat_cycles]
            rows.append({
                "config_id": cid, "label": label, "sd": sd, "hs": hs, "mcs": mcs,
                "regime": cat_name, "count": cn, "pct_of_total": cn / n,
                "avg_net_pnl": sum(pnls) / cn,
                "total_net_pnl": sum(pnls),
                "avg_mfe": sum(c["mfe_ticks"] for c in cat_cycles) / cn,
                "avg_mae": sum(c["mae_ticks"] for c in cat_cycles) / cn,
            })

    # Write
    fieldnames = [
        "config_id", "label", "sd", "hs", "mcs",
        "regime", "count", "pct_of_total",
        "avg_net_pnl", "total_net_pnl", "avg_mfe", "avg_mae",
    ]
    with open(output_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            out = {}
            for k in fieldnames:
                v = r[k]
                if isinstance(v, float):
                    out[k] = f"{v:.2f}"
                else:
                    out[k] = v
            w.writerow(out)

    # Print summary
    print("\n=== REGIME ANALYSIS (by cycle outcome at each SD scale) ===")
    for cid in top_config_ids:
        cfg_rows = [r for r in rows if r["config_id"] == cid]
        if not cfg_rows:
            continue
        s = cfg_rows[0]
        print(f"\nConfig {cid}: {s['label']} SD={s['sd']} HS={s['hs']} MCS={s['mcs']}")
        print(f"  {'Regime':<20} {'Count':>6} {'%Total':>7} {'AvgPnL':>9} "
              f"{'TotalPnL':>10} {'AvgMFE':>7} {'AvgMAE':>7}")
        print("  " + "-" * 75)
        for r in cfg_rows:
            if r["count"] == 0:
                continue
            print(f"  {r['regime']:<20} {r['count']:>6} {r['pct_of_total']:>7.1%} "
                  f"${r['avg_net_pnl']:>8.2f} ${r['total_net_pnl']:>9.2f} "
                  f"{r['avg_mfe']:>7.1f} {r['avg_mae']:>7.1f}")


# ---------------------------------------------------------------------------
#  Main
# ---------------------------------------------------------------------------
def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="LP Analysis — post-processing")
    parser.add_argument("--cycles-file", type=str,
                        default=r"C:\Projects\pipeline\shared\archetypes\rotational\docs\sweep_all_cycles.csv")
    parser.add_argument("--results-file", type=str,
                        default=r"C:\Projects\pipeline\shared\archetypes\rotational\docs\sweep_results.csv")
    parser.add_argument("--output-dir", type=str,
                        default=r"C:\Projects\pipeline\shared\archetypes\rotational\docs")
    parser.add_argument("--top-n", type=int, default=5,
                        help="Number of top configs per depth to analyze")
    args = parser.parse_args()

    out_dir = Path(args.output_dir)

    print("Loading sweep results...")
    results = load_results(args.results_file)

    # Get top N configs per depth by PropScore
    top_ids = []
    for label in ["depth_0", "depth_1", "depth_2", "depth_3"]:
        label_results = [r for r in results if r["label"] == label and r["prop_score"] > 0]
        label_results.sort(key=lambda r: r["prop_score"], reverse=True)
        for r in label_results[:args.top_n]:
            top_ids.append(r["config_id"])

    print(f"Analyzing top {len(top_ids)} configs across all depths...")
    print(f"Config IDs: {top_ids}")

    print(f"\nLoading cycle data from {args.cycles_file}...")
    cycles = load_cycles(args.cycles_file)
    print(f"Loaded {len(cycles)} cycles")

    # Run analyses
    analyze_time_blocks(cycles, top_ids, out_dir / "analysis_time_blocks.csv")
    analyze_regime(cycles, top_ids, out_dir / "analysis_regime.csv")

    print(f"\nOutput files:")
    print(f"  {out_dir / 'analysis_time_blocks.csv'}")
    print(f"  {out_dir / 'analysis_regime.csv'}")


if __name__ == "__main__":
    main()
