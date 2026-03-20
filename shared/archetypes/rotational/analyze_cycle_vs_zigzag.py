# archetype: rotational
"""Cycle Distance vs Zigzag Swing Validation.

Runs the base rotation config (V1.1, SD=25, cap=2, ML=1, walking anchor) on
full P1 with daily flattens, RTH only, NO SpeedRead filter.  Computes per-cycle
MFE/MAE/gross distance and compares with zigzag swing distributions.

Outputs:
  - cycle_distances_full_p1_rth.parquet   (cycle-level data)
  - cycle_vs_zigzag_comparison.json       (all tables and metrics)
"""

import datetime as dt
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

_REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO))
from shared.data_loader import load_bars

OUT_DIR = Path(__file__).parent

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
P1_END = pd.Timestamp("2025-12-14 23:59:59")
P1A_END = pd.Timestamp("2025-11-02 23:59:59")

TICK_SIZE = 0.25
COST_TICKS = 1
STEP_DIST = 25.0
FLATTEN_CAP = 2
MAX_LEVELS = 1
MAX_CS = 8
INIT_QTY = 1

FLATTEN_TOD = 16 * 3600   # 16:00 ET
RESUME_TOD = 18 * 3600    # 18:00 ET
RTH_OPEN_TOD = 9 * 3600 + 30 * 60  # 09:30 ET

_IDLE = -2
_PRE_RTH = -3
_WATCHING = -1
_LONG = 1
_SHORT = 2

BLOCKS = [
    ("Open",      dt.time(9, 30),  dt.time(10, 0)),
    ("Morning",   dt.time(10, 0),  dt.time(11, 30)),
    ("Midday",    dt.time(11, 30), dt.time(13, 30)),
    ("Afternoon", dt.time(13, 30), dt.time(15, 0)),
    ("Close",     dt.time(15, 0),  dt.time(16, 0)),
]

BLOCK_HOURS = {
    "Open": 0.5, "Morning": 1.5, "Midday": 2.0,
    "Afternoon": 1.5, "Close": 1.0,
}


def assign_block(tod_sec: int) -> str:
    """Assign block from seconds-since-midnight (faster than dt.time)."""
    if 34200 <= tod_sec < 36000:
        return "Open"
    elif 36000 <= tod_sec < 41400:
        return "Morning"
    elif 41400 <= tod_sec < 48600:
        return "Midday"
    elif 48600 <= tod_sec < 54000:
        return "Afternoon"
    elif 54000 <= tod_sec < 57600:
        return "Close"
    return ""


# ---------------------------------------------------------------------------
# Simulation with MFE/MAE tracking
# ---------------------------------------------------------------------------

def simulate_with_mfe_mae(prices, tod_secs, dts,
                          seed_dist=25.0, step_dist=STEP_DIST,
                          flatten_reseed_cap=FLATTEN_CAP,
                          max_levels=MAX_LEVELS,
                          cost_ticks=COST_TICKS, tick_size=TICK_SIZE):
    """Tick simulation: daily flatten, RTH-open watch, NO SpeedRead filter.

    Tracks per-cycle MFE/MAE in points from entry_price.
    Returns cycle_records list.
    """
    n = len(prices)

    state = _IDLE
    watch_price = 0.0
    anchor = 0.0
    level = 0
    position_qty = 0
    avg_entry = 0.0
    entry_price = 0.0
    cycle_id = 0
    cycle_start = 0
    session_id = 0

    # MFE/MAE tracking (in points, from entry_price)
    mfe_pts = 0.0
    mae_pts = 0.0
    adds_count = 0
    cap_walks = 0

    cycle_records = []

    # Track cycle trades for gross PnL computation
    trade_entries = []  # list of (price, qty)

    def _finalize(exit_price, end_bar, exit_reason):
        nonlocal cycle_id
        direction = "Long" if state == _LONG else "Short"
        total_qty = sum(q for _, q in trade_entries)
        wavg = (sum(p * q for p, q in trade_entries) / total_qty) if total_qty else exit_price
        if direction == "Long":
            gross = (exit_price - wavg) / tick_size * total_qty
        else:
            gross = (wavg - exit_price) / tick_size * total_qty
        n_actions = 1 + adds_count  # entry + adds
        total_cost = cost_ticks * (total_qty + total_qty)  # entry cost + exit cost
        # More precise: each trade action costs cost_ticks * qty
        total_cost = 0
        for _, q in trade_entries:
            total_cost += cost_ticks * q
        total_cost += cost_ticks * total_qty  # flatten cost

        return {
            "cycle_id": cycle_id,
            "start_bar": cycle_start,
            "end_bar": end_bar,
            "direction": direction,
            "entry_price": round(entry_price, 4),
            "exit_price": round(exit_price, 4),
            "avg_entry_price": round(wavg, 4),
            "gross_distance_pts": round(abs(exit_price - entry_price), 4),
            "gross_pnl_ticks": round(gross, 4),
            "net_pnl_ticks": round(gross - total_cost, 4),
            "mfe_pts": round(mfe_pts, 4),
            "mae_pts": round(mae_pts, 4),
            "adds_count": adds_count,
            "cap_walks": cap_walks,
            "max_position_qty": max(q for _, q in trade_entries) if trade_entries else 0,
            "total_qty": total_qty,
            "exit_reason": exit_reason,
            "session_id": session_id,
            "entry_tod_sec": int(tod_secs[cycle_start]),
            "entry_dt": dts[cycle_start],
        }

    for i in range(n):
        price = prices[i]
        tod = tod_secs[i]

        # --- DEAD ZONE (16:00-18:00) ---
        if FLATTEN_TOD <= tod < RESUME_TOD:
            if state == _LONG or state == _SHORT:
                cr = _finalize(price, i, "daily_flatten")
                cycle_records.append(cr)
                position_qty = 0
                trade_entries = []
            if state != _IDLE:
                state = _IDLE
            continue

        # --- SESSION START ---
        if state == _IDLE:
            session_id += 1
            # Watch mode = rth_open: wait for 09:30
            state = _PRE_RTH
            continue

        # --- PRE_RTH: wait for 09:30 ---
        if state == _PRE_RTH:
            if RTH_OPEN_TOD <= tod < FLATTEN_TOD:
                state = _WATCHING
                watch_price = price
            continue

        # --- WATCHING: seed detection (no SR filter) ---
        if state == _WATCHING:
            if watch_price == 0.0:
                watch_price = price
                continue

            up_dist = price - watch_price
            down_dist = watch_price - price

            if up_dist >= seed_dist:
                cycle_id += 1
                state = _LONG
                anchor = price
                entry_price = price
                level = 0
                position_qty = INIT_QTY
                avg_entry = price
                cycle_start = i
                mfe_pts = 0.0
                mae_pts = 0.0
                adds_count = 0
                cap_walks = 0
                trade_entries = [(price, INIT_QTY)]
            elif down_dist >= seed_dist:
                cycle_id += 1
                state = _SHORT
                anchor = price
                entry_price = price
                level = 0
                position_qty = INIT_QTY
                avg_entry = price
                cycle_start = i
                mfe_pts = 0.0
                mae_pts = 0.0
                adds_count = 0
                cap_walks = 0
                trade_entries = [(price, INIT_QTY)]
            continue

        # --- POSITIONED: update MFE/MAE ---
        if state == _LONG:
            excursion = price - entry_price
        else:
            excursion = entry_price - price

        if excursion > mfe_pts:
            mfe_pts = excursion
        if excursion < 0 and abs(excursion) > mae_pts:
            mae_pts = abs(excursion)

        # --- Rotation logic ---
        distance = price - anchor
        if state == _LONG:
            in_favor = distance >= step_dist
            against = (-distance) >= step_dist
        else:
            in_favor = (-distance) >= step_dist
            against = distance >= step_dist

        if in_favor:
            # Reversal: flatten + enter opposite (no SR gate)
            cr = _finalize(price, i, "reversal")
            cycle_records.append(cr)

            # Start new cycle in opposite direction
            cycle_id += 1
            state = _SHORT if state == _LONG else _LONG
            anchor = price
            entry_price = price
            level = 0
            position_qty = INIT_QTY
            avg_entry = price
            cycle_start = i
            mfe_pts = 0.0
            mae_pts = 0.0
            adds_count = 0
            cap_walks = 0
            trade_entries = [(price, INIT_QTY)]

        elif against:
            # Check flatten-reseed cap
            if flatten_reseed_cap > 0 and position_qty >= flatten_reseed_cap:
                cr = _finalize(price, i, "flatten_reseed")
                cycle_records.append(cr)

                state = _WATCHING
                watch_price = price
                position_qty = 0
                trade_entries = []
                continue

            # ADD (walking anchor mode)
            proposed_qty = INIT_QTY * (2 ** level)
            if proposed_qty > MAX_CS or level >= max_levels:
                proposed_qty = INIT_QTY
                cap_walks += 1
                level = 0
            else:
                level += 1

            anchor = price
            old_qty = position_qty
            position_qty += proposed_qty
            avg_entry = (avg_entry * old_qty + price * proposed_qty) / position_qty
            trade_entries.append((price, proposed_qty))
            adds_count += 1

    # Finalize open cycle
    if (state == _LONG or state == _SHORT) and trade_entries:
        cr = _finalize(prices[-1], n - 1, "end_of_data")
        cycle_records.append(cr)

    return cycle_records, session_id


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    t0_total = time.time()

    # ------------------------------------------------------------------
    # Load 1-tick data (full P1)
    # ------------------------------------------------------------------
    print("Loading NQ 1-tick P1 data (this takes ~2 min)...")
    t0 = time.time()
    tick_bars = load_bars(str(_REPO / "stages/01-data/data/bar_data/tick/NQ_BarData_1tick_rot_P1.csv"))
    tick_bars = tick_bars[tick_bars["datetime"] <= P1_END].reset_index(drop=True)
    print(f"  Loaded {len(tick_bars):,} ticks in {time.time()-t0:.1f}s")
    print(f"  Range: {tick_bars['datetime'].iloc[0]} to {tick_bars['datetime'].iloc[-1]}")

    prices = tick_bars["Last"].values.astype(np.float64)
    dts = tick_bars["datetime"].values
    h = tick_bars["datetime"].dt.hour.values.astype(np.int32)
    m = tick_bars["datetime"].dt.minute.values.astype(np.int32)
    s = tick_bars["datetime"].dt.second.values.astype(np.int32)
    tod_secs = h * 3600 + m * 60 + s

    # ------------------------------------------------------------------
    # Run simulation
    # ------------------------------------------------------------------
    print("\nRunning simulation (SD=25, cap=2, ML=1, no SR, rth_open watch, daily flatten)...")
    t0 = time.time()
    cycle_records, n_sessions = simulate_with_mfe_mae(prices, tod_secs, dts)
    print(f"  Completed in {time.time()-t0:.1f}s")
    print(f"  Cycles: {len(cycle_records):,}  |  Sessions: {n_sessions}")

    cycles = pd.DataFrame(cycle_records)

    # Assign block and period
    cycles["block"] = cycles["entry_tod_sec"].apply(assign_block)
    cycles["period"] = np.where(
        pd.to_datetime(cycles["entry_dt"]) <= P1A_END, "P1a", "P1b"
    )

    # Entry type
    first_cycle_per_session = cycles.groupby("session_id")["cycle_id"].min()
    seed_ids = set(first_cycle_per_session.values)
    # Also any cycle after a flatten_reseed is a seed
    fr_ids = set(cycles[cycles["exit_reason"] == "flatten_reseed"]["cycle_id"].values)
    cycles["entry_type"] = "reversal"
    cycles.loc[cycles["cycle_id"].isin(seed_ids), "entry_type"] = "seed"
    # After flatten_reseed, next cycle is also a seed
    for frid in fr_ids:
        fr_row = cycles[cycles["cycle_id"] == frid]
        if len(fr_row) > 0:
            sid = fr_row["session_id"].iloc[0]
            next_mask = (cycles["cycle_id"] == frid + 1) & (cycles["session_id"] == sid)
            cycles.loc[next_mask, "entry_type"] = "seed"

    # Clean/messy classification
    cycles["is_clean"] = (cycles["adds_count"] == 0) & (cycles["cap_walks"] == 0)

    # RTH only — filter to blocks
    rth_cycles = cycles[cycles["block"] != ""].copy()
    print(f"  RTH cycles: {len(rth_cycles):,}")

    # ------------------------------------------------------------------
    # Save parquet
    # ------------------------------------------------------------------
    parquet_path = OUT_DIR / "cycle_distances_full_p1_rth.parquet"
    rth_cycles.to_parquet(parquet_path, index=False)
    print(f"  Saved: {parquet_path.name}")

    # ------------------------------------------------------------------
    # Load zigzag data for comparison
    # ------------------------------------------------------------------
    print("\nLoading zigzag swing data...")
    zz_swings = pd.read_csv(OUT_DIR / "rth_swings_by_block.csv")
    print(f"  Zigzag RTH swings: {len(zz_swings):,}")

    # ------------------------------------------------------------------
    # Part B1: Cycle MFE distribution
    # ------------------------------------------------------------------
    print("\n" + "=" * 110)
    print("PART B1: CYCLE MFE vs ZIGZAG SWING DISTRIBUTION")
    print("-" * 110)

    pcts = [50, 75, 80, 85, 90, 95]
    zz_vals = zz_swings["swing_size_pts"].values
    mfe_vals = rth_cycles["mfe_pts"].values

    print(f"{'Metric':<10} {'Zigzag (RTH)':>14} {'Cycle MFE':>14} {'Delta':>10}")
    print("-" * 50)
    print(f"{'Count':<10} {len(zz_vals):>14,} {len(mfe_vals):>14,}")
    print(f"{'Mean':<10} {np.mean(zz_vals):>14.2f} {np.mean(mfe_vals):>14.2f} "
          f"{np.mean(mfe_vals) - np.mean(zz_vals):>+10.2f}")
    for p in pcts:
        zv = np.percentile(zz_vals, p)
        mv = np.percentile(mfe_vals, p)
        label = f"P{p}"
        print(f"{label:<10} {zv:>14.2f} {mv:>14.2f} {mv - zv:>+10.2f}")
    print(f"{'Max':<10} {np.max(zz_vals):>14.2f} {np.max(mfe_vals):>14.2f}")

    # ------------------------------------------------------------------
    # Part B2: Cycle MAE distribution
    # ------------------------------------------------------------------
    print("\n" + "=" * 110)
    print("PART B2: CYCLE MAE DISTRIBUTION")
    print("-" * 110)
    mae_vals = rth_cycles["mae_pts"].values
    print(f"{'Metric':<10} {'Cycle MAE':>14}")
    print("-" * 30)
    print(f"{'Count':<10} {len(mae_vals):>14,}")
    print(f"{'Mean':<10} {np.mean(mae_vals):>14.2f}")
    for p in pcts:
        print(f"{'P'+str(p):<10} {np.percentile(mae_vals, p):>14.2f}")
    print(f"{'Max':<10} {np.max(mae_vals):>14.2f}")

    # ------------------------------------------------------------------
    # Part B3: Gross distance — clean vs messy
    # ------------------------------------------------------------------
    print("\n" + "=" * 110)
    print("PART B3: CYCLE GROSS DISTANCE (|exit - entry|)")
    print("-" * 110)

    clean = rth_cycles[rth_cycles["is_clean"]]
    messy = rth_cycles[~rth_cycles["is_clean"]]
    print(f"  Clean cycles (no adds/cap walks): {len(clean):,}")
    print(f"  Messy cycles (1+ adds/cap walks): {len(messy):,}")

    if len(clean) > 0:
        cd = clean["gross_distance_pts"].values
        print(f"\n  CLEAN: gross distance stats")
        print(f"    Mean:   {np.mean(cd):.2f}")
        print(f"    Median: {np.median(cd):.2f}")
        print(f"    Min:    {np.min(cd):.2f}")
        print(f"    Max:    {np.max(cd):.2f}")
        print(f"    ==25.0: {(cd == 25.0).sum()} ({(cd == 25.0).mean()*100:.1f}%)")
        print(f"    >=24.5: {(cd >= 24.5).sum()} ({(cd >= 24.5).mean()*100:.1f}%)")
        # Check exit reasons
        print(f"    Exit reasons: {clean['exit_reason'].value_counts().to_dict()}")

    if len(messy) > 0:
        md = messy["gross_distance_pts"].values
        print(f"\n  MESSY: gross distance stats")
        print(f"    Mean:   {np.mean(md):.2f}")
        print(f"    Median: {np.median(md):.2f}")
        for p in [25, 50, 75, 90]:
            print(f"    P{p}:    {np.percentile(md, p):.2f}")
        print(f"    Max:    {np.max(md):.2f}")
        print(f"    Exit reasons: {messy['exit_reason'].value_counts().to_dict()}")

    # ------------------------------------------------------------------
    # Part B4: Block-level comparison
    # ------------------------------------------------------------------
    print("\n" + "=" * 110)
    print("PART B4: BLOCK-LEVEL COMPARISON")
    print("-" * 110)

    block_names = ["Open", "Morning", "Midday", "Afternoon", "Close"]

    print(f"{'Block':<12} {'ZZ Med':>7} {'ZZ P90':>7} {'MFE Med':>8} {'MFE P90':>8} "
          f"{'Cycles':>7} {'ZZ Sw/Hr':>9} {'Cyc/Hr':>8}")
    print("-" * 110)

    block_stats = {}
    for bname in block_names:
        zz_b = zz_swings[zz_swings["block"] == bname]["swing_size_pts"].values
        cy_b = rth_cycles[rth_cycles["block"] == bname]
        mfe_b = cy_b["mfe_pts"].values

        total_hours = BLOCK_HOURS[bname] * n_sessions
        zz_sph = len(zz_b) / total_hours if total_hours > 0 else 0
        cy_ph = len(cy_b) / total_hours if total_hours > 0 else 0

        stats = {
            "zz_median": round(float(np.median(zz_b)), 2) if len(zz_b) > 0 else 0,
            "zz_p90": round(float(np.percentile(zz_b, 90)), 2) if len(zz_b) > 0 else 0,
            "mfe_median": round(float(np.median(mfe_b)), 2) if len(mfe_b) > 0 else 0,
            "mfe_p90": round(float(np.percentile(mfe_b, 90)), 2) if len(mfe_b) > 0 else 0,
            "cycles": int(len(cy_b)),
            "zz_swings_per_hour": round(zz_sph, 1),
            "cycles_per_hour": round(cy_ph, 1),
        }
        block_stats[bname] = stats

        print(f"{bname:<12} {stats['zz_median']:>7.1f} {stats['zz_p90']:>7.1f} "
              f"{stats['mfe_median']:>8.1f} {stats['mfe_p90']:>8.1f} "
              f"{stats['cycles']:>7,} {stats['zz_swings_per_hour']:>9.1f} "
              f"{stats['cycles_per_hour']:>8.1f}")

    # ------------------------------------------------------------------
    # Part C1: Rolling zigzag stats
    # ------------------------------------------------------------------
    print("\n" + "=" * 110)
    print("PART C: CORRELATION ANALYSIS")
    print("-" * 110)

    # Rolling zigzag P50/P85/P90 over 200-swing window
    zz_sorted = zz_swings.sort_values("swing_start_time").reset_index(drop=True)
    window = 200
    rolling_p50 = []
    rolling_p85 = []
    rolling_p90 = []
    rolling_times = []

    sizes_arr = zz_sorted["swing_size_pts"].values
    times_arr = pd.to_datetime(zz_sorted["swing_start_time"]).values

    for j in range(window, len(sizes_arr)):
        w = sizes_arr[j - window:j]
        rolling_p50.append(np.percentile(w, 50))
        rolling_p85.append(np.percentile(w, 85))
        rolling_p90.append(np.percentile(w, 90))
        rolling_times.append(times_arr[j])

    rolling_p50 = np.array(rolling_p50)
    rolling_p85 = np.array(rolling_p85)
    rolling_p90 = np.array(rolling_p90)
    rolling_times = np.array(rolling_times)

    # Report rolling stats at key dates
    print(f"\n  Rolling ZZ stats (200-swing window) at key dates:")
    key_dates = [
        pd.Timestamp("2025-10-01"),
        pd.Timestamp("2025-10-15"),
        pd.Timestamp("2025-11-01"),
        pd.Timestamp("2025-11-15"),
        pd.Timestamp("2025-12-01"),
        pd.Timestamp("2025-12-14"),
    ]
    for kd in key_dates:
        mask = rolling_times <= np.datetime64(kd)
        if mask.any():
            idx = mask.sum() - 1
            print(f"    {kd.strftime('%Y-%m-%d')}: P50={rolling_p50[idx]:.1f} "
                  f"P85={rolling_p85[idx]:.1f} P90={rolling_p90[idx]:.1f}")

    # P1a vs P1b rolling averages
    p1a_mask = rolling_times <= np.datetime64(P1A_END)
    p1b_mask = ~p1a_mask
    if p1a_mask.any():
        print(f"\n  P1a avg rolling: P50={rolling_p50[p1a_mask].mean():.1f} "
              f"P85={rolling_p85[p1a_mask].mean():.1f} P90={rolling_p90[p1a_mask].mean():.1f}")
    if p1b_mask.any():
        print(f"  P1b avg rolling: P50={rolling_p50[p1b_mask].mean():.1f} "
              f"P85={rolling_p85[p1b_mask].mean():.1f} P90={rolling_p90[p1b_mask].mean():.1f}")

    # ------------------------------------------------------------------
    # Part C3: Cycle MFE vs recent zigzag (Spearman)
    # ------------------------------------------------------------------
    # For each cycle, find the most recent zigzag swing size at entry time
    print(f"\n  Computing cycle-to-zigzag correlation...")
    from scipy.stats import spearmanr

    cycle_entry_times = pd.to_datetime(rth_cycles["entry_dt"]).values
    zz_times_sorted = times_arr  # already sorted
    zz_sizes_sorted = sizes_arr

    recent_zz = np.full(len(rth_cycles), np.nan)
    rolling_p85_at_entry = np.full(len(rth_cycles), np.nan)
    rolling_p90_at_entry = np.full(len(rth_cycles), np.nan)

    for ci in range(len(rth_cycles)):
        et = cycle_entry_times[ci]
        idx = np.searchsorted(zz_times_sorted, et, side="right") - 1
        if 0 <= idx < len(zz_sizes_sorted):
            recent_zz[ci] = zz_sizes_sorted[idx]
        # Rolling stats
        ri = np.searchsorted(rolling_times, et, side="right") - 1
        if 0 <= ri < len(rolling_p85):
            rolling_p85_at_entry[ci] = rolling_p85[ri]
            rolling_p90_at_entry[ci] = rolling_p90[ri]

    mfe_arr = rth_cycles["mfe_pts"].values
    valid = ~np.isnan(recent_zz) & ~np.isnan(mfe_arr)
    if valid.sum() > 30:
        rho, pval = spearmanr(recent_zz[valid], mfe_arr[valid])
        print(f"  Spearman(recent_zz, cycle_mfe): rho={rho:.4f}, p={pval:.2e}, n={valid.sum():,}")

    # Part C1: Does cycle perform better when SD=25 is closer to rolling P85?
    valid2 = ~np.isnan(rolling_p85_at_entry) & ~np.isnan(mfe_arr)
    if valid2.sum() > 30:
        gap = 25.0 - rolling_p85_at_entry[valid2]
        gross_pnl = rth_cycles["gross_pnl_ticks"].values[valid2]
        rho2, pval2 = spearmanr(gap, gross_pnl)
        print(f"  Spearman(SD_minus_rolling_P85, gross_pnl): rho={rho2:.4f}, p={pval2:.2e}")

        # Bin by gap to see pattern
        gap_bins = pd.qcut(gap, 4, labels=["Q1 (SD>>P85)", "Q2", "Q3", "Q4 (SD~P85)"])
        binned = pd.DataFrame({"gap_bin": gap_bins, "gross_pnl": gross_pnl, "mfe": mfe_arr[valid2]})
        print(f"\n  Cycle performance by SD-vs-rolling_P85 quartile:")
        for gbin in ["Q1 (SD>>P85)", "Q2", "Q3", "Q4 (SD~P85)"]:
            sub = binned[binned["gap_bin"] == gbin]
            if len(sub) > 0:
                win_rate = (sub["gross_pnl"] > 0).mean()
                print(f"    {gbin}: n={len(sub):,}, mean_pnl={sub['gross_pnl'].mean():.1f}, "
                      f"win_rate={win_rate:.1%}, mean_mfe={sub['mfe'].mean():.1f}")

    # ------------------------------------------------------------------
    # Part D: Key Questions
    # ------------------------------------------------------------------
    print("\n" + "=" * 110)
    print("PART D: KEY QUESTIONS")
    print("=" * 110)

    # D4: Zigzag settings
    print("\nD4. ZIGZAG SETTINGS:")
    print("  Reversal amount: 5.25 pts (21 ticks)")
    print("  Bar type: 250-tick bars")
    print("  Study: Sierra Chart Zig Zag (standard)")
    print("  Minimum swing = 5.25 pts = reversal amount")
    print("  (All swings >= 5.25 pts, no swings below this threshold)")

    # D3: Block ranking comparison
    print("\nD3. BLOCK RANKING COMPARISON (cycles/hr vs swings/hr):")
    zz_rank = sorted(block_stats.items(), key=lambda x: x[1]["zz_swings_per_hour"], reverse=True)
    cy_rank = sorted(block_stats.items(), key=lambda x: x[1]["cycles_per_hour"], reverse=True)
    print(f"  {'Rank':<5} {'By ZZ Sw/Hr':<20} {'By Cycles/Hr':<20}")
    for i in range(len(block_names)):
        print(f"  {i+1:<5} {zz_rank[i][0]:<14} ({zz_rank[i][1]['zz_swings_per_hour']:.0f})"
              f"   {cy_rank[i][0]:<14} ({cy_rank[i][1]['cycles_per_hour']:.1f})")

    # ------------------------------------------------------------------
    # Regime split for cycles
    # ------------------------------------------------------------------
    print("\n" + "=" * 110)
    print("REGIME COMPARISON: CYCLES (P1a vs P1b)")
    print("-" * 110)
    print(f"{'Block':<12} | {'--- P1a ---':^30} | {'--- P1b ---':^30}")
    print(f"{'':12} | {'Cycles':>7} {'MFE Med':>8} {'MFE P90':>8} "
          f"| {'Cycles':>7} {'MFE Med':>8} {'MFE P90':>8}")
    print("-" * 90)

    regime_stats = {}
    for bname in block_names:
        regime_stats[bname] = {}
        for period in ["P1a", "P1b"]:
            cy_bp = rth_cycles[(rth_cycles["block"] == bname) & (rth_cycles["period"] == period)]
            mfe_bp = cy_bp["mfe_pts"].values
            regime_stats[bname][period] = {
                "cycles": int(len(cy_bp)),
                "mfe_median": round(float(np.median(mfe_bp)), 2) if len(mfe_bp) > 0 else 0,
                "mfe_p90": round(float(np.percentile(mfe_bp, 90)), 2) if len(mfe_bp) > 0 else 0,
            }

        p1a = regime_stats[bname]["P1a"]
        p1b = regime_stats[bname]["P1b"]
        print(f"{bname:<12} | {p1a['cycles']:>7} {p1a['mfe_median']:>8.1f} {p1a['mfe_p90']:>8.1f} "
              f"| {p1b['cycles']:>7} {p1b['mfe_median']:>8.1f} {p1b['mfe_p90']:>8.1f}")

    # ------------------------------------------------------------------
    # Build JSON output
    # ------------------------------------------------------------------
    def pct_dict(arr, pcts=[50, 75, 80, 85, 90, 95]):
        if len(arr) == 0:
            return {}
        return {
            "count": int(len(arr)),
            "mean": round(float(np.mean(arr)), 2),
            **{f"p{p}": round(float(np.percentile(arr, p)), 2) for p in pcts},
            "max": round(float(np.max(arr)), 2),
        }

    output = {
        "config": {
            "step_dist": STEP_DIST,
            "seed_dist": STEP_DIST,
            "flatten_reseed_cap": FLATTEN_CAP,
            "max_levels": MAX_LEVELS,
            "speedread_filter": "DISABLED",
            "watch_mode": "rth_open",
            "daily_flatten": "16:00 ET",
            "cost_ticks": COST_TICKS,
            "data": "NQ 1-tick P1 (Sep 21 – Dec 14, 2025)",
        },
        "zigzag_settings": {
            "reversal_amount_pts": 5.25,
            "reversal_amount_ticks": 21,
            "bar_type": "250-tick",
            "study": "Sierra Chart Zig Zag",
        },
        "totals": {
            "rth_cycles": int(len(rth_cycles)),
            "rth_zz_swings": int(len(zz_swings)),
            "sessions": n_sessions,
        },
        "B1_mfe_distribution": pct_dict(mfe_vals),
        "B1_zigzag_distribution": pct_dict(zz_vals),
        "B2_mae_distribution": pct_dict(mae_vals),
        "B3_clean_cycles": {
            "count": int(len(clean)),
            "gross_distance": pct_dict(clean["gross_distance_pts"].values) if len(clean) > 0 else {},
        },
        "B3_messy_cycles": {
            "count": int(len(messy)),
            "gross_distance": pct_dict(messy["gross_distance_pts"].values) if len(messy) > 0 else {},
        },
        "B4_block_comparison": block_stats,
        "regime_comparison": regime_stats,
    }

    json_path = OUT_DIR / "cycle_vs_zigzag_comparison.json"
    with open(json_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\n  Saved: {json_path.name}")

    print(f"\nTotal elapsed: {time.time()-t0_total:.1f}s")
    print("Done.")


if __name__ == "__main__":
    main()
