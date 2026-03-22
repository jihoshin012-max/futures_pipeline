# archetype: rotational
# STATUS: ONE-TIME
# PURPOSE: Phase 2 risk mitigation (adaptive stop, daily loss)
# LAST RUN: 2026-03

"""Phase 2 Step 4: Risk Mitigation.

4A: Adaptive cycle stop (MAE > N * rolling zigzag std)
4B: Max daily loss stop
4C: Max cap-walks per cycle

Evaluate by tail-risk reduction vs mean PnL cost.

Usage:
    python run_phase2_risk.py
"""

import sys
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

_REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from run_seed_investigation import simulate_daily_flatten, load_data, FLATTEN_TOD
from run_phase1_sweep import (build_zigzag_lookup, make_adaptive_lookup,
                               analyze_step2, _OUTPUT_DIR)


def main():
    print("Loading tick data WITH SpeedRead...")
    prices, tod_secs, sr_vals, dts = load_data(period='full_p1', use_speedread=True)
    zz_lookup = build_zigzag_lookup()
    adaptive = make_adaptive_lookup(zz_lookup, 5, 2)  # P90, P75

    SEED_START = 10 * 3600

    # Pre-compute rolling 50-tick SR average
    cs = np.cumsum(np.insert(sr_vals, 0, 0))
    w = 50
    sr_roll50 = np.empty_like(sr_vals)
    sr_roll50[:w] = cs[1:w+1] / np.arange(1, w+1)
    sr_roll50[w:] = (cs[w+1:] - cs[1:len(sr_vals)-w+1]) / w

    # Run baseline with Roll50 SR>=48
    print("Running baseline (Roll50 SR>=48)...")
    sim_base = simulate_daily_flatten(
        prices, tod_secs, sr_roll50, dts,
        seed_dist=15.0, step_dist=25.0, add_dist=25.0,
        flatten_reseed_cap=2, max_levels=1,
        seed_sr_thresh=48.0, rev_sr_thresh=48.0,
        watch_mode='rth_open', cap_action='walk',
        seed_start_tod=SEED_START,
        adaptive_lookup=adaptive,
    )
    r_base = analyze_step2(sim_base, "Roll50_SR>=48_baseline")

    # Build cycle data
    cycles = pd.DataFrame(sim_base["cycle_records"])
    trades = pd.DataFrame(sim_base["trade_records"])

    entry_trades = trades[trades["action"].isin(["SEED", "REVERSAL"])]
    ce = entry_trades.groupby("cycle_id")["datetime"].first().reset_index()
    ce.columns = ["cycle_id", "entry_dt"]
    cycles = cycles.merge(ce, on="cycle_id", how="left")
    cycles["hour"] = pd.to_datetime(cycles["entry_dt"]).dt.hour
    cycles = cycles[~cycles["hour"].isin({1, 19, 20})].copy()

    valid_ids = set(cycles["cycle_id"])
    cc = trades[trades["cycle_id"].isin(valid_ids)].groupby("cycle_id")["cost_ticks"].sum()
    cycles["cost"] = cycles["cycle_id"].map(cc).fillna(0)
    cycles["net_1t"] = cycles["gross_pnl_ticks"] - cycles["cost"]
    cycles = cycles.reset_index(drop=True)

    session_pnl_base = cycles.groupby("session_id")["net_1t"].sum()
    worst_day_base = session_pnl_base.min()

    # Rotation std per cycle
    swing_lens = zz_lookup["swing_lens"]
    WINDOW = 200
    n_pts = len(swing_lens) - WINDOW
    zz_stds = np.empty(n_pts, dtype=np.float64)
    for j in range(n_pts):
        idx = WINDOW + j
        zz_stds[j] = swing_lens[idx - WINDOW:idx].std()

    zz_ts = zz_lookup["pct_ts"][:n_pts]
    cycle_entry_ts = pd.to_datetime(cycles["entry_dt"]).values.astype("int64")
    zz_idx = np.searchsorted(zz_ts, cycle_entry_ts, side="right") - 1
    zz_idx = np.clip(zz_idx, 0, n_pts - 1)
    cycles["rot_std"] = zz_stds[zz_idx]

    # Cap-walks per cycle
    cw_counts = trades[trades["action"] == "CAP_WALK"].groupby("cycle_id").size()
    cycles["cw_count"] = cycles["cycle_id"].map(cw_counts).fillna(0).astype(int)

    total_sessions = sim_base["total_sessions"]

    print(f"Baseline: {len(cycles)} cycles, NPF={r_base['npf_1t']:.4f}, "
          f"PnL={r_base['net_pnl']:+.0f}, worst day={worst_day_base:+.0f}")

    print("\n" + "=" * 72)
    print("PHASE 2 STEP 4: Risk Mitigation")
    print("=" * 72)

    # ===================================================================
    # 4A: Adaptive Cycle Stop (MAE > N * rolling_std)
    # ===================================================================
    print("\n--- 4A: Adaptive Cycle Stop ---")
    hdr = f"  {'N_sigma':>8} {'Stopped':>8} {'NPF':>7} {'NetPnL':>9} {'WorstDay':>10} {'MaxLoss':>9}"
    print(hdr)
    print(f"  {'-' * 55}")

    results_4a = []
    for n_sig in [1.5, 2.0, 2.5, 3.0, None]:
        c = cycles.copy()
        if n_sig is not None:
            threshold = n_sig * c["rot_std"]
            stopped_mask = c["mae"] > threshold
            # Cap loss at stop threshold
            stop_loss = -(threshold / 0.25 * c["max_position_qty"])
            improve_mask = stopped_mask & (stop_loss > c["net_1t"])
            c.loc[improve_mask, "net_1t"] = stop_loss[improve_mask]
            n_stopped = stopped_mask.sum()
            label = f"{n_sig:.1f}s"
        else:
            n_stopped = 0
            label = "none"

        gw = c.loc[c["net_1t"] > 0, "net_1t"].sum()
        gl = abs(c.loc[c["net_1t"] <= 0, "net_1t"].sum())
        npf = gw / gl if gl > 0 else 0
        net = c["net_1t"].sum()
        sp = c.groupby("session_id")["net_1t"].sum()
        worst = sp.min()
        max_loss = c["net_1t"].min()
        results_4a.append({"n_sigma": n_sig, "stopped": int(n_stopped), "npf": round(npf, 4),
                           "net_pnl": round(float(net), 1), "worst_day": round(float(worst), 1),
                           "max_loss": round(float(max_loss), 1)})
        print(f"  {label:>8} {n_stopped:>8} {npf:>7.4f} {net:>+9.0f} {worst:>+10.0f} {max_loss:>+9.0f}")

    # ===================================================================
    # 4B: Max Daily Loss Stop
    # ===================================================================
    print("\n--- 4B: Max Daily Loss Stop ---")
    hdr = f"  {'Max_Loss':>8} {'Sess_Stop':>9} {'NPF':>7} {'NetPnL':>9} {'WorstDay':>10} {'Forfeit':>8}"
    print(hdr)
    print(f"  {'-' * 55}")

    results_4b = []
    for max_daily in [100, 150, 200, 250, None]:
        c = cycles.copy()
        if max_daily is not None:
            keep_mask = np.ones(len(c), dtype=bool)
            for sid in c["session_id"].unique():
                sess_mask = c["session_id"] == sid
                sess_idx = c.index[sess_mask]
                running = 0.0
                stopped = False
                for idx in sess_idx:
                    if stopped:
                        keep_mask[idx] = False
                    else:
                        running += c.loc[idx, "net_1t"]
                        if running < -max_daily:
                            stopped = True
            forfeited = int((~keep_mask).sum())
            sessions_stopped = 0
            for sid in c["session_id"].unique():
                if not keep_mask[c["session_id"] == sid].all():
                    sessions_stopped += 1
            c = c[keep_mask].copy()
            label = f"-{max_daily}t"
        else:
            forfeited = 0
            sessions_stopped = 0
            label = "none"

        gw = c.loc[c["net_1t"] > 0, "net_1t"].sum()
        gl = abs(c.loc[c["net_1t"] <= 0, "net_1t"].sum())
        npf = gw / gl if gl > 0 else 0
        net = c["net_1t"].sum()
        sp = c.groupby("session_id")["net_1t"].sum()
        sp_full = sp.reindex(range(1, total_sessions + 1), fill_value=0.0)
        worst = sp_full.min()
        results_4b.append({"max_daily": max_daily, "sessions_stopped": sessions_stopped,
                           "npf": round(npf, 4), "net_pnl": round(float(net), 1),
                           "worst_day": round(float(worst), 1), "forfeited": forfeited})
        print(f"  {label:>8} {sessions_stopped:>9} {npf:>7.4f} {net:>+9.0f} {worst:>+10.0f} {forfeited:>8}")

    # ===================================================================
    # 4C: Max Cap-Walks Per Cycle
    # ===================================================================
    print("\n--- 4C: Max Cap-Walks Per Cycle ---")

    print("  Cap-walk distribution:")
    for n in range(6):
        cnt = (cycles["cw_count"] == n).sum()
        mean_pnl = cycles.loc[cycles["cw_count"] == n, "net_1t"].mean() if cnt > 0 else 0
        print(f"    CW={n}: {cnt:>5} cycles, mean PnL={mean_pnl:+.1f}")
    cnt_5p = (cycles["cw_count"] >= 5).sum()
    mean_5p = cycles.loc[cycles["cw_count"] >= 5, "net_1t"].mean() if cnt_5p > 0 else 0
    print(f"    CW>=5: {cnt_5p:>4} cycles, mean PnL={mean_5p:+.1f}")

    hdr = f"\n  {'Max_CW':>8} {'Stopped':>8} {'NPF':>7} {'NetPnL':>9} {'WorstDay':>10} {'MaxLoss':>9}"
    print(hdr)
    print(f"  {'-' * 55}")

    results_4c = []
    for max_cw in [2, 3, 4, 5, None]:
        c = cycles.copy()
        if max_cw is not None:
            stopped_mask = c["cw_count"] > max_cw
            n_stopped = int(stopped_mask.sum())
            c = c[~stopped_mask].copy()
            label = str(max_cw)
        else:
            n_stopped = 0
            label = "none"

        gw = c.loc[c["net_1t"] > 0, "net_1t"].sum()
        gl = abs(c.loc[c["net_1t"] <= 0, "net_1t"].sum())
        npf = gw / gl if gl > 0 else 0
        net = c["net_1t"].sum()
        sp = c.groupby("session_id")["net_1t"].sum()
        sp_full = sp.reindex(range(1, total_sessions + 1), fill_value=0.0)
        worst = sp_full.min()
        max_loss = c["net_1t"].min() if len(c) > 0 else 0
        results_4c.append({"max_cw": max_cw, "stopped": n_stopped, "npf": round(npf, 4),
                           "net_pnl": round(float(net), 1), "worst_day": round(float(worst), 1),
                           "max_loss": round(float(max_loss), 1)})
        print(f"  {label:>8} {n_stopped:>8} {npf:>7.4f} {net:>+9.0f} {worst:>+10.0f} {max_loss:>+9.0f}")

    # ===================================================================
    # Summary
    # ===================================================================
    print("\n" + "=" * 72)
    print("STEP 4 SUMMARY")
    print("=" * 72)

    base_npf = r_base["npf_1t"]
    base_pnl = r_base["net_pnl"]
    print(f"\n  Baseline: NPF={base_npf:.4f}, PnL={base_pnl:+.0f}, worst day={worst_day_base:+.0f}")

    # Best from each (by worst-day improvement)
    base_wd = float(worst_day_base)
    for name, results_list, key_name in [
        ("4A", results_4a, "n_sigma"),
        ("4B", results_4b, "max_daily"),
        ("4C", results_4c, "max_cw"),
    ]:
        # Exclude baseline (None)
        filtered = [r for r in results_list if r[key_name] is not None]
        if not filtered:
            continue
        best_wd = min(filtered, key=lambda x: abs(x["worst_day"]))
        best_npf = max(filtered, key=lambda x: x["npf"])
        wd_improvement = (1 - abs(best_wd["worst_day"]) / abs(base_wd)) * 100 if base_wd != 0 else 0
        npf_cost = (best_wd["npf"] - base_npf) / base_npf * 100

        print(f"\n  {name}: Best tail-risk: {key_name}={best_wd[key_name]} "
              f"-> worst day={best_wd['worst_day']:+.0f} "
              f"(improvement={wd_improvement:+.1f}%, NPF cost={npf_cost:+.1f}%)")

    # Save all
    all_results = {
        "4a": results_4a, "4b": results_4b, "4c": results_4c,
        "baseline": {"npf": base_npf, "net_pnl": base_pnl,
                     "worst_day": float(worst_day_base)},
    }
    out_path = _OUTPUT_DIR / "phase2_step4_risk_results.json"
    out_path.write_text(json.dumps(all_results, indent=2, default=str))
    print(f"\n  Saved: {out_path}")


if __name__ == "__main__":
    main()
