# archetype: rotational
"""Frozen-anchor structural verification — 3 configs on P1 1-tick data.

Runs before the full sweep as a go/no-go gate:
  1. V11_CHECK: cycle count comparison vs V1.1 A_SD25 (4,856)
  2. FRACTAL_CHECK_R04: success rate by add count (ratio 0.4)
  3. FRACTAL_CHECK_R025: success rate by add count (ratio 0.25)

Usage:
    cd stages/04-backtest/rotational
    python run_fa_verification.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from config_schema import FrozenAnchorConfig
from rotation_simulator import run_frozen_anchor_simulation

# ---------------------------------------------------------------------------
# Constants (same as run_sweep.py)
# ---------------------------------------------------------------------------
TICK_SIZE = 0.25

_TICK_DIR = _SCRIPT_DIR.parents[1] / "01-data" / "data" / "bar_data" / "tick"
P1_DATA_PATH = _TICK_DIR / "NQ_BarData_1tick_rot_P1.csv"

P1_START = pd.Timestamp("2025-09-21")
P1_END = pd.Timestamp("2025-12-17")
RTH_START_SEC = 9 * 3600 + 30 * 60
RTH_END_SEC = 16 * 3600 + 15 * 60

# V1.1 sweep reference
V11_A_SD25_CYCLES = 4856


# ---------------------------------------------------------------------------
# Data loading (same logic as run_sweep.load_p1_bars)
# ---------------------------------------------------------------------------
def load_p1_bars() -> pd.DataFrame:
    print(f"Loading P1 1-tick data from: {P1_DATA_PATH}")
    header = pd.read_csv(P1_DATA_PATH, nrows=0)
    header.columns = header.columns.str.strip()
    needed = ["Date", "Time", "Open", "High", "Low", "Last"]
    col_indices = [list(header.columns).index(c) for c in needed]
    df = pd.read_csv(P1_DATA_PATH, usecols=col_indices, dtype={
        "Open": "float32", "High": "float32", "Low": "float32", "Last": "float32",
    })
    df.columns = df.columns.str.strip()
    df["datetime"] = pd.to_datetime(df["Date"].str.strip() + " " + df["Time"].str.strip())
    df.drop(columns=["Date", "Time"], inplace=True)

    dates = df["datetime"].dt.normalize()
    df = df[(dates >= P1_START) & (dates <= P1_END)].copy()
    time_sec = df["datetime"].dt.hour * 3600 + df["datetime"].dt.minute * 60 + df["datetime"].dt.second
    df = df[(time_sec >= RTH_START_SEC) & (time_sec < RTH_END_SEC)].copy()
    df = df.reset_index(drop=True)

    trading_days = df["datetime"].dt.date.nunique()
    print(f"  Rows (RTH, P1): {len(df):,}")
    print(f"  Date range: {df['datetime'].iloc[0]} to {df['datetime'].iloc[-1]}")
    print(f"  Trading days: {trading_days}")
    return df


# ---------------------------------------------------------------------------
# Configs
# ---------------------------------------------------------------------------
CONFIGS = [
    FrozenAnchorConfig(
        config_id="V11_CHECK",
        step_dist=25.0,
        add_dist=25.0,
        max_adds=0,
        reversal_target=1.0,
        cost_ticks=0.0,
    ),
    FrozenAnchorConfig(
        config_id="FRACTAL_CHECK_R04",
        step_dist=25.0,
        add_dist=10.0,
        max_adds=2,
        reversal_target=1.0,
        cost_ticks=0.0,
    ),
    FrozenAnchorConfig(
        config_id="FRACTAL_CHECK_R025",
        step_dist=25.0,
        add_dist=6.25,
        max_adds=3,
        reversal_target=1.0,
        cost_ticks=0.0,
    ),
]

# Fractal predictions (from half-block completion curve)
FRACTAL_PRED = {0: 100.0, 1: 79.7, 2: 64.1, 3: 56.0}


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------
def success_rate_by_adds(cycles: pd.DataFrame) -> dict[int, dict]:
    """Compute success rate grouped by add_count."""
    result = {}
    for ac in sorted(cycles["add_count"].unique()):
        subset = cycles[cycles["add_count"] == ac]
        total = len(subset)
        successes = (subset["exit_type"] == "SUCCESS").sum()
        failures = (subset["exit_type"] == "FAILURE").sum()
        rate = successes / total * 100.0 if total > 0 else 0.0
        result[int(ac)] = {
            "total": total,
            "success": int(successes),
            "failure": int(failures),
            "rate": round(rate, 1),
        }
    return result


def run_config(cfg: FrozenAnchorConfig, bars: pd.DataFrame) -> dict:
    """Run one config and return summary dict."""
    print(f"\nRunning {cfg.config_id}...")
    t0 = time.time()
    result = run_frozen_anchor_simulation(cfg, bars, tick_size=TICK_SIZE)
    elapsed = time.time() - t0
    print(f"  Done in {elapsed:.1f}s")

    cycles = result.cycles
    inc = result.incomplete_cycles

    total = len(cycles)
    success_count = (cycles["exit_type"] == "SUCCESS").sum() if total > 0 else 0
    failure_count = (cycles["exit_type"] == "FAILURE").sum() if total > 0 else 0
    gross_pnl = cycles["pnl_ticks_gross"].sum() if total > 0 else 0.0
    incomplete_count = len(inc)

    print(f"  Cycles: {total}, S: {success_count}, F: {failure_count}, Inc: {incomplete_count}")
    print(f"  Gross PnL: {gross_pnl:,.1f} ticks")

    by_adds = success_rate_by_adds(cycles) if total > 0 else {}
    if by_adds:
        for ac, stats in by_adds.items():
            print(f"  Add {ac}: {stats['total']} cycles, {stats['rate']}% success")

    return {
        "config_id": cfg.config_id,
        "total_cycles": total,
        "success_count": int(success_count),
        "failure_count": int(failure_count),
        "incomplete_count": incomplete_count,
        "gross_pnl": round(float(gross_pnl), 1),
        "by_adds": by_adds,
        "elapsed_sec": round(elapsed, 1),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    bars = load_p1_bars()

    results = {}
    for cfg in CONFIGS:
        results[cfg.config_id] = run_config(cfg, bars)

    # --- Report ---
    print("\n" + "=" * 70)
    print("FROZEN-ANCHOR STRUCTURAL VERIFICATION REPORT")
    print("=" * 70)

    # 1. V1.1 comparison
    v11 = results["V11_CHECK"]
    delta_pct = abs(v11["total_cycles"] - V11_A_SD25_CYCLES) / V11_A_SD25_CYCLES * 100
    print(f"\n--- V1.1 Comparison (V11_CHECK vs A_SD25) ---")
    print(f"  Frozen-anchor cycles: {v11['total_cycles']}")
    print(f"  V1.1 A_SD25 cycles:   {V11_A_SD25_CYCLES}")
    print(f"  Delta:                 {delta_pct:.1f}%")
    if v11["total_cycles"] == V11_A_SD25_CYCLES:
        print("  Verdict: EXACT MATCH")
    elif delta_pct < 5:
        print("  Verdict: CLOSE MATCH (within 5%)")
    elif delta_pct < 20:
        print("  Verdict: BALLPARK (within 20%)")
    else:
        print("  *** WARNING: LARGE DIVERGENCE — investigate ***")

    # 2. Fractal completion table
    r04 = results["FRACTAL_CHECK_R04"]
    r025 = results["FRACTAL_CHECK_R025"]

    print(f"\n--- Fractal Completion Rate Comparison ---")
    print(f"{'Add Count':>10} | {'R04 Rate':>10} | {'R025 Rate':>10} | {'Fractal':>10} | {'D(R04)':>10} | {'D(R025)':>10}")
    print("-" * 70)

    stop_flag = False
    for ac in range(4):
        r04_rate = r04["by_adds"].get(ac, {}).get("rate", None)
        r025_rate = r025["by_adds"].get(ac, {}).get("rate", None)
        fractal = FRACTAL_PRED.get(ac, None)

        r04_str = f"{r04_rate:.1f}%" if r04_rate is not None else "n/a"
        r025_str = f"{r025_rate:.1f}%" if r025_rate is not None else "n/a"
        frac_str = f"~{fractal:.0f}%" if fractal is not None else "?"

        if r04_rate is not None and fractal is not None:
            d04 = round(r04_rate - fractal, 1)
            d04_str = f"{d04:+.1f}pp"
        else:
            d04 = None
            d04_str = "n/a"

        if r025_rate is not None and fractal is not None:
            d025 = round(r025_rate - fractal, 1)
            d025_str = f"{d025:+.1f}pp"
        else:
            d025 = None
            d025_str = "n/a"

        print(f"{ac:>10} | {r04_str:>10} | {r025_str:>10} | {frac_str:>10} | {d04_str:>10} | {d025_str:>10}")

        # Check stop condition: delta > 10pp at add counts 1 or 2
        if ac in (1, 2):
            if d04 is not None and abs(d04) > 10:
                print(f"  *** STOP: R04 delta at add {ac} exceeds 10pp ***")
                stop_flag = True
            if d025 is not None and abs(d025) > 10:
                print(f"  *** STOP: R025 delta at add {ac} exceeds 10pp ***")
                stop_flag = True

    # 3. Summary table
    print(f"\n--- Config Summary ---")
    print(f"{'Config':>25} | {'Cycles':>8} | {'Success':>8} | {'Failure':>8} | {'Inc':>5} | {'Gross PnL':>12} | {'Time':>6}")
    print("-" * 85)
    for cid in ["V11_CHECK", "FRACTAL_CHECK_R04", "FRACTAL_CHECK_R025"]:
        r = results[cid]
        print(f"{r['config_id']:>25} | {r['total_cycles']:>8} | {r['success_count']:>8} | "
              f"{r['failure_count']:>8} | {r['incomplete_count']:>5} | {r['gross_pnl']:>12,.1f} | "
              f"{r['elapsed_sec']:>5.0f}s")

    if stop_flag:
        print("\n*** STOP CONDITION MET ***")
        print("Distance-threshold proxy shows >10pp gap vs fractal predictions at critical add counts.")
        print("Do NOT proceed to full sweep. Review findings and consider Option 2 (real-time zig-zag).")
    else:
        print("\n*** ALL CHECKS PASS — proceed to full sweep ***")

    print()


if __name__ == "__main__":
    main()
