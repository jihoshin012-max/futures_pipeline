# archetype: zone_touch
"""Generate v3.2 replication reference and skipped CSVs for C++ gate.

Produces:
  - v32_replication_reference_P1.csv  (all P1 trades — ground truth for C++ matching)
  - v32_replication_skipped_P1.csv    (all qualifying signals skipped due to position overlap)

Uses the SAME scoring, waterfall, and simulation logic as stress_test_v32.py.
P1 data only. Gross PnL (no cost deduction).
"""

import json
import sys
import warnings
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd

# ════════════════════════════════════════════════════════════════════
# PATHS & CONSTANTS  (mirror stress_test_v32.py exactly)
# ════════════════════════════════════════════════════════════════════
BASE = Path(r"c:\Projects\pipeline")
DATA_DIR = BASE / "stages" / "01-data" / "output" / "zone_prep"
PARAM_DIR = BASE / "shared" / "archetypes" / "zone_touch" / "output"
OUT_DIR = PARAM_DIR
SIM_DIR = BASE / "shared" / "archetypes" / "zone_touch"
TICK = 0.25

# ── Import reusable functions from stress_test_v32 ──
sys.path.insert(0, str(SIM_DIR))
from stress_test_v32 import (
    compute_features,
    score_aeq,
    score_bzscore,
    build_waterfall,
    sim_trade_m2,
    M1_PARTIAL_CFG,
    M2_STOP_MULT,
    M2_STOP_FLOOR,
    M2_TARGET_MULT,
    M2_TCAP,
)
from zone_touch_simulator import run_multileg as _run_multileg


def simulate_with_full_log(m1_qual, m2_qual, bar_arr, n_bars):
    """Like stress_test_v32.simulate_all_trades but captures entry/exit prices,
    scores, zone metadata, and logs skipped signals."""

    all_qual = pd.concat([m1_qual, m2_qual], ignore_index=True)
    all_qual = all_qual.sort_values("RotBarIndex").reset_index(drop=True)

    bar_df = pd.DataFrame(bar_arr, columns=["Open", "High", "Low", "Last"])
    trades = []
    skipped = []
    in_trade_until = -1
    blocking_trade_rbi = -1  # RotBarIndex of the trade causing the block

    for _, row in all_qual.iterrows():
        rbi = int(row["RotBarIndex"])
        entry_bar = rbi + 1
        direction = 1 if "DEMAND" in str(row["TouchType"]) else -1
        zw = int(row.get("ZoneWidthTicks", 100))
        mode = row["mode"]
        dt_str = str(row.get("DateTime", ""))
        zone_type = "DEMAND" if direction == 1 else "SUPPLY"
        zone_tf = str(row.get("SourceLabel", ""))
        seq_count = int(row.get("TouchSequence", 1))
        s_aeq = float(row.get("score_aeq", 0))
        s_bz = float(row.get("score_bz", 0))

        # ── Skip: position overlap ──
        if entry_bar <= in_trade_until:
            skipped.append({
                "datetime": dt_str,
                "RotBarIndex": rbi,
                "mode": mode,
                "direction": direction,
                "zone_type": zone_type,
                "zone_tf": zone_tf,
                "seq_count": seq_count,
                "zone_width_ticks": zw,
                "score_aeq": round(s_aeq, 4),
                "score_bz": round(s_bz, 4),
                "skip_reason": "POSITION_OPEN",
                "blocking_trade_rbi": blocking_trade_rbi,
            })
            continue

        # ── Skip: entry bar out of range ──
        if entry_bar >= n_bars:
            skipped.append({
                "datetime": dt_str,
                "RotBarIndex": rbi,
                "mode": mode,
                "direction": direction,
                "zone_type": zone_type,
                "zone_tf": zone_tf,
                "seq_count": seq_count,
                "zone_width_ticks": zw,
                "score_aeq": round(s_aeq, 4),
                "score_bz": round(s_bz, 4),
                "skip_reason": "OUT_OF_BARS",
                "blocking_trade_rbi": -1,
            })
            continue

        entry_price = bar_arr[entry_bar, 0]  # Open of entry bar

        if mode == "M1":
            touch_row = pd.Series({
                "TouchPrice": entry_price,
                "ApproachDir": direction,
                "mode": "M1",
            })
            cfg = {"tick_size": TICK, "M1": dict(M1_PARTIAL_CFG)}
            result = _run_multileg(bar_df, touch_row, cfg, entry_bar)
            pnl_per_ct = result.pnl_ticks  # weighted PnL
            contracts = 3
            bars_held = result.bars_held
            exit_type = (result.leg_exit_reasons[-1]
                         if result.leg_exit_reasons else "?")
            # Compute effective exit price from weighted PnL
            exit_price = entry_price + direction * pnl_per_ct * TICK
        else:
            stop_t = max(round(M2_STOP_MULT * zw), M2_STOP_FLOOR)
            target_t = max(1, round(M2_TARGET_MULT * zw))
            result = sim_trade_m2(entry_bar, direction, stop_t, target_t,
                                  M2_TCAP, bar_arr, n_bars)
            if result is None:
                skipped.append({
                    "datetime": dt_str,
                    "RotBarIndex": rbi,
                    "mode": mode,
                    "direction": direction,
                    "zone_type": zone_type,
                    "zone_tf": zone_tf,
                    "seq_count": seq_count,
                    "zone_width_ticks": zw,
                    "score_aeq": round(s_aeq, 4),
                    "score_bz": round(s_bz, 4),
                    "skip_reason": "SIM_NONE",
                    "blocking_trade_rbi": -1,
                })
                continue
            pnl_per_ct = result["pnl"]
            if zw < 150:
                contracts = 3
            elif zw <= 250:
                contracts = 2
            else:
                contracts = 1
            bars_held = result["bars_held"]
            exit_type = result["exit_type"]
            exit_price = entry_price + direction * pnl_per_ct * TICK

        pnl_total = contracts * pnl_per_ct
        total_pnl_ticks = pnl_total  # gross — no cost

        trades.append({
            "datetime": dt_str,
            "RotBarIndex": rbi,
            "mode": mode,
            "direction": direction,
            "zone_type": zone_type,
            "zone_tf": zone_tf,
            "seq_count": seq_count,
            "zone_width_ticks": zw,
            "entry_price": round(entry_price, 2),
            "exit_price": round(exit_price, 2),
            "exit_type": exit_type,
            "contracts": contracts,
            "pnl_per_contract": round(pnl_per_ct, 4),
            "total_pnl_ticks": round(pnl_total, 4),
            "bars_held": bars_held,
            "score_aeq": round(s_aeq, 4),
            "score_bz": round(s_bz, 4),
        })
        blocking_trade_rbi = rbi
        in_trade_until = entry_bar + bars_held - 1

    return pd.DataFrame(trades), pd.DataFrame(skipped)


def main():
    print("=" * 60)
    print("GENERATE v3.2 REPLICATION REFERENCE CSVs (P1 only)")
    print("=" * 60)

    # ── Load bar data (P1 only) ──
    print("\n[1/5] Loading P1 bar data...")
    bar_p1 = pd.read_csv(DATA_DIR / "NQ_bardata_P1.csv")
    bar_p1.columns = bar_p1.columns.str.strip()
    bar_arr = bar_p1[["Open", "High", "Low", "Last"]].to_numpy(np.float64)
    bar_atr = bar_p1["ATR"].to_numpy(np.float64)
    n_bars = len(bar_arr)
    print(f"  P1 bars: {n_bars}")

    # ── Load touch data (P1) ──
    print("[2/5] Loading P1 touch data...")
    p1a = pd.read_csv(DATA_DIR / "NQ_merged_P1a.csv")
    p1b = pd.read_csv(DATA_DIR / "NQ_merged_P1b.csv")
    p1a = p1a[p1a["RotBarIndex"] >= 0].reset_index(drop=True)
    p1b = p1b[p1b["RotBarIndex"] >= 0].reset_index(drop=True)
    p1_all = pd.concat([p1a, p1b], ignore_index=True)
    print(f"  P1 touches: {len(p1_all)}")

    # ── Compute features ──
    print("[3/5] Computing features + scoring...")
    p1_feat = compute_features(p1_all, bar_arr, bar_atr, n_bars, "P1")

    # P1 B-ZScore: use pre-scored CSV (same as stress_test_v32.py)
    p1_bz_csv = pd.read_csv(
        PARAM_DIR / "p1_scored_touches_bzscore_v32.csv",
        usecols=["BarIndex", "TouchType", "SourceLabel", "Score_BZScore"])
    p1_feat["_jk"] = (p1_feat["BarIndex"].astype(str) + "|" +
                       p1_feat["TouchType"] + "|" + p1_feat["SourceLabel"])
    p1_bz_csv["_jk"] = (p1_bz_csv["BarIndex"].astype(str) + "|" +
                          p1_bz_csv["TouchType"] + "|" +
                          p1_bz_csv["SourceLabel"])
    bz_map = p1_bz_csv.drop_duplicates("_jk").set_index("_jk")["Score_BZScore"]
    p1_prescored = p1_feat["_jk"].map(bz_map).values
    p1_prescored = np.where(pd.isna(p1_prescored), 0.0, p1_prescored)
    p1_feat.drop(columns=["_jk"], inplace=True)

    # ── Build waterfall (scores get attached to qualifying DataFrames) ──
    print("[4/5] Building waterfall + simulating trades...")
    m1_p1, m2_p1 = build_waterfall(p1_feat, "P1", prescored_bz=p1_prescored)

    # Attach scores to qualifying rows for the log
    # build_waterfall already sets score_aeq and score_bz on both DataFrames
    # (via score_aeq() and the prescored path)

    # ── Simulate with full logging ──
    trades_df, skipped_df = simulate_with_full_log(
        m1_p1, m2_p1, bar_arr, n_bars)

    # ── Summary ──
    n_m1 = (trades_df["mode"] == "M1").sum() if len(trades_df) > 0 else 0
    n_m2 = (trades_df["mode"] == "M2").sum() if len(trades_df) > 0 else 0
    n_skip = len(skipped_df)
    n_pos_open = (skipped_df["skip_reason"] == "POSITION_OPEN").sum() if n_skip > 0 else 0

    print(f"\n  Trades:  {len(trades_df)} total (M1={n_m1}, M2={n_m2})")
    print(f"  Skipped: {n_skip} total (POSITION_OPEN={n_pos_open})")

    # Quick PF check (gross, no cost — matches stress_test expected)
    if len(trades_df) > 0:
        gp = trades_df.loc[trades_df["total_pnl_ticks"] > 0, "total_pnl_ticks"].sum()
        gl = trades_df.loc[trades_df["total_pnl_ticks"] < 0, "total_pnl_ticks"].abs().sum()
        pf = gp / gl if gl > 0 else float("inf")
        print(f"  Gross PF (no cost): {pf:.2f}")

    # ── Save ──
    print("\n[5/5] Saving CSVs...")
    ref_path = OUT_DIR / "v32_replication_reference_P1.csv"
    skip_path = OUT_DIR / "v32_replication_skipped_P1.csv"
    trades_df.to_csv(ref_path, index=False)
    skipped_df.to_csv(skip_path, index=False)
    print(f"  -> {ref_path}")
    print(f"  -> {skip_path}")
    print("\nDone.")


if __name__ == "__main__":
    main()
