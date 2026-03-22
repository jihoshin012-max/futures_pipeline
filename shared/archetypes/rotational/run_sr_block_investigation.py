# archetype: rotational
# STATUS: ONE-TIME
# PURPOSE: SR-block watch price reset investigation
# LAST RUN: 2026-03

"""SR-block watch price reset investigation for daily-flatten trading.

Follow-up to seed optimization investigation. Tests whether resetting the watch
price during SpeedRead blocks improves seed quality.

Baseline: Variant D + SeedDist=15 (RTH-only, 9:30 watch price, NPF~1.361).
Only the SR-block watch price behavior varies.

Variants:
  D (baseline): Watch price stays fixed during SR block
  D+F: Reset watch price once when SR crosses above 48
  D+G: Reset watch price on each completed 250-tick bar during SR block

Steps:
  --step 1: Test F and G against baseline D
  --step 2: Sensitivity analysis (conditional on >=5% NPF diff)
  --step 3: Recommendation

Usage:
    python run_sr_block_investigation.py --step 1
    python run_sr_block_investigation.py --step 2
    python run_sr_block_investigation.py --step 3
    python run_sr_block_investigation.py --step all
"""

import sys
import json
import time
import argparse
import datetime as dt_mod
from pathlib import Path

import numpy as np
import pandas as pd

_REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from shared.data_loader import load_bars

# ---------------------------------------------------------------------------
# Constants (all FROZEN from prior investigation)
# ---------------------------------------------------------------------------

_P1_START = dt_mod.date(2025, 9, 21)
_P1_END = dt_mod.date(2025, 12, 14)
_P1_MID = _P1_START + (_P1_END - _P1_START) / 2

EXCLUDE_HOURS = {1, 19, 20}

FLATTEN_TOD = 16 * 3600   # 16:00 ET
RESUME_TOD = 18 * 3600    # 18:00 ET
RTH_OPEN_TOD = 9 * 3600 + 30 * 60  # 09:30 ET

TICK_SIZE = 0.25
COST_TICKS = 1
STEP_DIST = 25.0
SEED_DIST = 15.0
FLATTEN_CAP = 2
MAX_LEVELS = 1
MAX_CS = 8
INIT_QTY = 1
SEED_SR_THRESH = 48.0
REV_SR_THRESH = 48.0

_1TICK_PATH = "stages/01-data/data/bar_data/tick/NQ_BarData_1tick_rot_P1.csv"
_250TICK_PATH = "stages/01-data/data/bar_data/tick/NQ_BarData_250tick_rot_P1.csv"
_SR_PARQUET = Path(__file__).parent / "speedread_results" / "speedread_250tick.parquet"
_OUTPUT_DIR = Path(__file__).parent / "sr_block_results"

_IDLE = -2
_PRE_RTH = -3
_WATCHING = -1
_LONG = 1
_SHORT = 2


# ---------------------------------------------------------------------------
# Cycle finalization helper
# ---------------------------------------------------------------------------

def _finalize_cycle(cycle_trades, cycle_id, cycle_start, end_bar, state, price,
                    tick_size=TICK_SIZE):
    direction = "Long" if state == _LONG else "Short"
    entries = [t for t in cycle_trades if t["action"] in ("SEED", "REVERSAL", "ADD")]
    total_qty = sum(t["qty"] for t in entries)
    wavg = (sum(t["price"] * t["qty"] for t in entries) / total_qty) if total_qty else price
    if direction == "Long":
        gross = (price - wavg) / tick_size * total_qty
    else:
        gross = (wavg - price) / tick_size * total_qty
    total_cost = sum(t["cost_ticks"] for t in cycle_trades)
    net = gross - total_cost
    adds = [t for t in entries if t["action"] == "ADD"]
    max_pos, rq = 0, 0
    for t in cycle_trades:
        if t["action"] == "FLATTEN":
            rq = 0
        elif t["action"] in ("SEED", "REVERSAL", "ADD"):
            rq += t["qty"]
            max_pos = max(max_pos, rq)
    max_level = max((t["level"] for t in entries), default=0)
    return {
        "cycle_id": cycle_id, "start_bar": cycle_start, "end_bar": end_bar,
        "direction": direction, "duration_bars": end_bar - cycle_start + 1,
        "entry_price": round(entries[0]["price"], 4) if entries else price,
        "exit_price": round(price, 4), "avg_entry_price": round(wavg, 4),
        "adds_count": len(adds), "max_level_reached": max_level,
        "max_position_qty": max_pos,
        "gross_pnl_ticks": round(gross, 4), "net_pnl_ticks": round(net, 4),
        "exit_reason": "",
    }


# ---------------------------------------------------------------------------
# Core simulation: Variant D + optional SR-block watch price resets (F/G)
# ---------------------------------------------------------------------------

def simulate(prices, tod_secs, sr_vals, dts, sr_idx_arr, bar_close_arr,
             sr_block_mode='none'):
    """Tick simulation with Variant D (RTH-only) + SR-block watch price resets.

    sr_block_mode:
      'none'          - Baseline D: watch price stays fixed during SR block
      'reset_on_clear' - Variant F: reset watch price once when SR crosses above 48
      'reset_on_bar'   - Variant G: reset watch price on each completed bar during block

    Returns dict with trade_records, cycle_records, total_sessions, wp_resets,
    and sr_block_episodes (list of episode dicts).
    """
    n = len(prices)
    seed_dist = SEED_DIST
    step_dist = STEP_DIST
    cost_ticks = COST_TICKS
    tick_size = TICK_SIZE
    seed_sr = SEED_SR_THRESH
    rev_sr = REV_SR_THRESH

    # State
    state = _IDLE
    watch_price = 0.0
    anchor = 0.0
    level = 0
    position_qty = 0
    avg_entry = 0.0
    cycle_id = 0
    cycle_start = 0
    session_id = 0

    # Session tracking
    prior_close = 0.0
    prior_high = 0.0
    prior_low = 1e9
    session_high = 0.0
    session_low = 1e9

    # SR-block state
    prev_bar_idx = -1       # previous 250-tick bar index
    sr_prev_below = False   # was previous bar's SR below threshold?
    wp_resets = 0

    # SR-block episode tracking
    in_sr_block = False
    block_start_tick = 0
    block_start_price = 0.0
    block_start_dt = None
    block_bars = 0
    block_max_disp = 0.0    # max |price - block_start_price| during block
    block_resets = 0
    sr_block_episodes = []

    trade_records = []
    cycle_records = []
    cycle_trades = []

    for i in range(n):
        price = prices[i]
        tod = tod_secs[i]
        sr = sr_vals[i]
        cur_bar_idx = sr_idx_arr[i]
        bar_changed = (cur_bar_idx != prev_bar_idx)

        # --- DEAD ZONE CHECK (16:00 <= tod < 18:00) ---
        if FLATTEN_TOD <= tod < RESUME_TOD:
            if state == _LONG or state == _SHORT:
                direction = "Long" if state == _LONG else "Short"
                ft = {"bar_idx": i, "datetime": dts[i], "action": "FLATTEN",
                      "direction": direction, "qty": position_qty, "price": price,
                      "level": level, "anchor": anchor,
                      "cost_ticks": cost_ticks * position_qty,
                      "cycle_id": cycle_id, "session_id": session_id,
                      "price_source": "tick"}
                trade_records.append(ft)
                cycle_trades.append(ft)
                cr = _finalize_cycle(cycle_trades, cycle_id, cycle_start, i,
                                     state, price, tick_size)
                cr["exit_reason"] = "daily_flatten"
                cr["session_id"] = session_id
                cycle_records.append(cr)
                cycle_trades = []
                position_qty = 0

            # End any active SR-block episode
            if in_sr_block:
                sr_block_episodes.append({
                    "session_id": session_id, "start_price": block_start_price,
                    "end_price": price, "bars": block_bars,
                    "max_displacement": block_max_disp, "resets": block_resets,
                    "start_dt": block_start_dt, "end_dt": dts[i],
                })
                in_sr_block = False

            if state != _IDLE:
                prior_close = price
                if session_high > 0:
                    prior_high = session_high
                if session_low < 1e9:
                    prior_low = session_low
                state = _IDLE
            continue

        # --- SESSION START (transition from IDLE) ---
        if state == _IDLE:
            session_id += 1
            session_high = price
            session_low = price
            # Variant D: always use RTH open
            state = _PRE_RTH
            sr_prev_below = False
            in_sr_block = False
            prev_bar_idx = cur_bar_idx
            continue

        # Update session high/low
        if price > session_high:
            session_high = price
        if price < session_low:
            session_low = price

        # --- PRE_RTH: wait for 09:30 ---
        if state == _PRE_RTH:
            if RTH_OPEN_TOD <= tod < FLATTEN_TOD:
                state = _WATCHING
                watch_price = price
                sr_prev_below = (sr < seed_sr)
                prev_bar_idx = cur_bar_idx
            else:
                prev_bar_idx = cur_bar_idx
            continue

        # --- WATCHING: seed detection with SR-block handling ---
        if state == _WATCHING:
            if watch_price == 0.0:
                watch_price = price
                prev_bar_idx = cur_bar_idx
                continue

            sr_below = sr < seed_sr

            # SR-block episode tracking
            if sr_below and not in_sr_block:
                # Entering a new SR-block episode
                in_sr_block = True
                block_start_tick = i
                block_start_price = price
                block_start_dt = dts[i]
                block_bars = 0
                block_max_disp = 0.0
                block_resets = 0

            if in_sr_block:
                disp = abs(price - block_start_price)
                if disp > block_max_disp:
                    block_max_disp = disp

            if not sr_below and in_sr_block:
                # SR-block episode ending
                sr_block_episodes.append({
                    "session_id": session_id, "start_price": block_start_price,
                    "end_price": price, "bars": block_bars,
                    "max_displacement": block_max_disp, "resets": block_resets,
                    "start_dt": block_start_dt, "end_dt": dts[i],
                })
                in_sr_block = False

            # --- Variant F: reset watch price when SR crosses above threshold ---
            if sr_block_mode == 'reset_on_clear':
                if bar_changed and sr_prev_below and not sr_below:
                    # Transition from <48 to >=48 — reset watch price
                    watch_price = price
                    wp_resets += 1
                    if in_sr_block:
                        block_resets += 1

            # --- Variant G: reset watch price on each completed bar during block ---
            elif sr_block_mode == 'reset_on_bar':
                if bar_changed and sr_below:
                    # New bar completed while SR is below threshold
                    watch_price = bar_close_arr[cur_bar_idx]
                    wp_resets += 1
                    block_bars += 1
                    if in_sr_block:
                        block_resets += 1
                elif bar_changed and sr_prev_below and not sr_below:
                    # SR just cleared after G resets — no extra reset needed,
                    # watch price is already fresh from the last bar reset.
                    # But we do note it in diagnostics.
                    pass

            # Update bar tracking
            if bar_changed:
                if sr_below and sr_block_mode != 'reset_on_bar':
                    # Track bars during block for diagnostics (non-G modes)
                    block_bars += 1
                sr_prev_below = sr_below
                prev_bar_idx = cur_bar_idx

            # Normal seed detection
            up_dist = price - watch_price
            down_dist = watch_price - price

            if up_dist >= seed_dist and sr >= seed_sr:
                cycle_id += 1
                state = _LONG
                anchor = price
                level = 0
                position_qty = INIT_QTY
                avg_entry = price
                cycle_start = i
                t = {"bar_idx": i, "datetime": dts[i], "action": "SEED",
                     "direction": "Long", "qty": INIT_QTY, "price": price,
                     "level": 0, "anchor": price,
                     "cost_ticks": cost_ticks * INIT_QTY,
                     "cycle_id": cycle_id, "session_id": session_id,
                     "price_source": "tick"}
                trade_records.append(t)
                cycle_trades = [t]
                # End any active SR-block episode (seed fired)
                if in_sr_block:
                    sr_block_episodes.append({
                        "session_id": session_id, "start_price": block_start_price,
                        "end_price": price, "bars": block_bars,
                        "max_displacement": block_max_disp, "resets": block_resets,
                        "start_dt": block_start_dt, "end_dt": dts[i],
                    })
                    in_sr_block = False
            elif down_dist >= seed_dist and sr >= seed_sr:
                cycle_id += 1
                state = _SHORT
                anchor = price
                level = 0
                position_qty = INIT_QTY
                avg_entry = price
                cycle_start = i
                t = {"bar_idx": i, "datetime": dts[i], "action": "SEED",
                     "direction": "Short", "qty": INIT_QTY, "price": price,
                     "level": 0, "anchor": price,
                     "cost_ticks": cost_ticks * INIT_QTY,
                     "cycle_id": cycle_id, "session_id": session_id,
                     "price_source": "tick"}
                trade_records.append(t)
                cycle_trades = [t]
                if in_sr_block:
                    sr_block_episodes.append({
                        "session_id": session_id, "start_price": block_start_price,
                        "end_price": price, "bars": block_bars,
                        "max_displacement": block_max_disp, "resets": block_resets,
                        "start_dt": block_start_dt, "end_dt": dts[i],
                    })
                    in_sr_block = False
            continue

        # --- POSITIONED (LONG or SHORT): rotation logic ---
        # (Update bar tracking even when positioned, for state continuity)
        if bar_changed:
            sr_prev_below = (sr < seed_sr)
            prev_bar_idx = cur_bar_idx

        distance = price - anchor
        if state == _LONG:
            in_favor = distance >= step_dist
            against = (-distance) >= step_dist
        else:
            in_favor = (-distance) >= step_dist
            against = distance >= step_dist

        if in_favor:
            direction = "Long" if state == _LONG else "Short"
            ft = {"bar_idx": i, "datetime": dts[i], "action": "FLATTEN",
                  "direction": direction, "qty": position_qty, "price": price,
                  "level": level, "anchor": anchor,
                  "cost_ticks": cost_ticks * position_qty,
                  "cycle_id": cycle_id, "session_id": session_id,
                  "price_source": "tick"}
            trade_records.append(ft)
            cycle_trades.append(ft)
            cr = _finalize_cycle(cycle_trades, cycle_id, cycle_start, i,
                                 state, price, tick_size)
            cr["session_id"] = session_id

            if sr >= rev_sr:
                cr["exit_reason"] = "reversal"
                cycle_records.append(cr)
                new_dir = "Short" if state == _LONG else "Long"
                cycle_id += 1
                state = _SHORT if state == _LONG else _LONG
                anchor = price
                level = 0
                position_qty = INIT_QTY
                avg_entry = price
                cycle_start = i
                rt = {"bar_idx": i, "datetime": dts[i], "action": "REVERSAL",
                      "direction": new_dir, "qty": INIT_QTY, "price": price,
                      "level": 0, "anchor": price,
                      "cost_ticks": cost_ticks * INIT_QTY,
                      "cycle_id": cycle_id, "session_id": session_id,
                      "price_source": "tick"}
                trade_records.append(rt)
                cycle_trades = [rt]
            else:
                cr["exit_reason"] = "reversal_sr_skip"
                cycle_records.append(cr)
                state = _WATCHING
                watch_price = price
                position_qty = 0
                cycle_trades = []
                # Reset SR-block state for the new WATCHING period
                sr_prev_below = (sr < seed_sr)
                in_sr_block = False

        elif against:
            if FLATTEN_CAP > 0 and position_qty >= FLATTEN_CAP:
                direction = "Long" if state == _LONG else "Short"
                ft = {"bar_idx": i, "datetime": dts[i], "action": "FLATTEN",
                      "direction": direction, "qty": position_qty, "price": price,
                      "level": level, "anchor": anchor,
                      "cost_ticks": cost_ticks * position_qty,
                      "cycle_id": cycle_id, "session_id": session_id,
                      "price_source": "tick"}
                trade_records.append(ft)
                cycle_trades.append(ft)
                cr = _finalize_cycle(cycle_trades, cycle_id, cycle_start, i,
                                     state, price, tick_size)
                cr["exit_reason"] = "flatten_reseed"
                cr["session_id"] = session_id
                cycle_records.append(cr)
                state = _WATCHING
                watch_price = price
                position_qty = 0
                cycle_trades = []
                sr_prev_below = (sr < seed_sr)
                in_sr_block = False
                continue

            # ADD
            proposed_qty = INIT_QTY * (2 ** level)
            if proposed_qty > MAX_CS or level >= MAX_LEVELS:
                proposed_qty = INIT_QTY
                next_level = 0
                level_at_add = 0
            else:
                next_level = level + 1
                level_at_add = level

            level = next_level
            anchor = price
            old_qty = position_qty
            position_qty += proposed_qty
            if position_qty > 0:
                avg_entry = (avg_entry * old_qty + price * proposed_qty) / position_qty

            direction = "Long" if state == _LONG else "Short"
            at = {"bar_idx": i, "datetime": dts[i], "action": "ADD",
                  "direction": direction, "qty": proposed_qty, "price": price,
                  "level": level_at_add, "anchor": price,
                  "cost_ticks": cost_ticks * proposed_qty,
                  "cycle_id": cycle_id, "session_id": session_id,
                  "price_source": "tick"}
            trade_records.append(at)
            cycle_trades.append(at)

    # Finalize open cycle at end of data
    if (state == _LONG or state == _SHORT) and cycle_trades:
        last_price = prices[-1]
        cr = _finalize_cycle(cycle_trades, cycle_id, cycle_start, n - 1,
                             state, last_price, tick_size)
        cr["exit_reason"] = "end_of_data"
        cr["session_id"] = session_id
        cycle_records.append(cr)

    # Close any open SR-block episode
    if in_sr_block:
        sr_block_episodes.append({
            "session_id": session_id, "start_price": block_start_price,
            "end_price": prices[-1], "bars": block_bars,
            "max_displacement": block_max_disp, "resets": block_resets,
            "start_dt": block_start_dt, "end_dt": dts[-1],
        })

    return {
        "trade_records": trade_records,
        "cycle_records": cycle_records,
        "total_sessions": session_id,
        "wp_resets": wp_resets,
        "sr_block_episodes": sr_block_episodes,
    }


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

def analyze(sim_result, label, exclude_hours=EXCLUDE_HOURS):
    """Compute summary statistics from simulation results."""
    trade_records = sim_result["trade_records"]
    cycle_records = sim_result["cycle_records"]
    total_sessions = sim_result["total_sessions"]

    if not cycle_records:
        return None

    trades_df = pd.DataFrame(trade_records)
    cycles_df = pd.DataFrame(cycle_records)

    # Post-hoc hour filter
    entry_trades = trades_df[trades_df["action"].isin(["SEED", "REVERSAL"])]
    ce = entry_trades.groupby("cycle_id")["datetime"].first().reset_index()
    ce.columns = ["cycle_id", "entry_dt"]
    cycles_df = cycles_df.merge(ce, on="cycle_id", how="left")
    cycles_df["hour"] = pd.to_datetime(cycles_df["entry_dt"]).dt.hour
    cf = cycles_df[~cycles_df["hour"].isin(exclude_hours)].copy()

    if len(cf) == 0:
        return None

    valid_ids = set(cf["cycle_id"])
    tf = trades_df[trades_df["cycle_id"].isin(valid_ids)]
    cc = tf.groupby("cycle_id")["cost_ticks"].sum()
    cf["cost"] = cf["cycle_id"].map(cc).fillna(0)
    cf["net_1t"] = cf["gross_pnl_ticks"] - cf["cost"]

    nn = len(cf)
    gw = cf[cf["gross_pnl_ticks"] > 0]["gross_pnl_ticks"].sum()
    gl = abs(cf[cf["gross_pnl_ticks"] <= 0]["gross_pnl_ticks"].sum())
    gpf = gw / gl if gl else 0

    nw = cf[cf["net_1t"] > 0]["net_1t"].sum()
    nl = abs(cf[cf["net_1t"] <= 0]["net_1t"].sum())
    npf = nw / nl if nl else 0

    net_pnl = cf["net_1t"].sum()

    all_sids = range(1, total_sessions + 1)
    session_pnl_raw = cf.groupby("session_id")["net_1t"].sum()
    session_pnl = session_pnl_raw.reindex(all_sids, fill_value=0.0)

    cycles_per_session = cf.groupby("session_id").size().reindex(all_sids, fill_value=0)
    mean_cycles = cycles_per_session.mean()

    mean_daily = session_pnl.mean()
    std_daily = session_pnl.std()
    session_win_pct = (session_pnl > 0).mean()

    pvals = session_pnl.values
    if len(pvals) >= 5:
        p10, p25, p50, p75, p90 = np.percentile(pvals, [10, 25, 50, 75, 90])
    else:
        p10 = p25 = p50 = p75 = p90 = 0.0

    # Seed accuracy
    first_actions = trades_df.groupby("cycle_id")["action"].first()
    seed_cids = first_actions[first_actions == "SEED"].index
    seed_cf = cf[cf["cycle_id"].isin(seed_cids)]
    seed_accuracy = (seed_cf["gross_pnl_ticks"] > 0).mean() if len(seed_cf) > 0 else 0

    # SR-block diagnostics
    episodes = sim_result["sr_block_episodes"]
    n_episodes = len(episodes)
    episodes_per_session = n_episodes / total_sessions if total_sessions > 0 else 0
    mean_block_bars = np.mean([e["bars"] for e in episodes]) if episodes else 0
    mean_block_disp = np.mean([e["max_displacement"] for e in episodes]) if episodes else 0

    # Mean block duration in seconds
    block_durations = []
    for e in episodes:
        try:
            dt_start = pd.Timestamp(e["start_dt"])
            dt_end = pd.Timestamp(e["end_dt"])
            dur = (dt_end - dt_start).total_seconds()
            if dur >= 0:
                block_durations.append(dur)
        except Exception:
            pass
    mean_block_sec = np.mean(block_durations) if block_durations else 0

    resets_per_session = sim_result["wp_resets"] / total_sessions if total_sessions > 0 else 0

    return {
        "label": label,
        "cycles": nn,
        "gpf": round(gpf, 4),
        "npf_1t": round(npf, 4),
        "net_pnl": int(net_pnl),
        "sessions": total_sessions,
        "mean_daily": round(mean_daily, 1),
        "std_daily": round(std_daily, 1),
        "session_win_pct": round(session_win_pct, 4),
        "cycles_per_session": round(mean_cycles, 1),
        "seed_accuracy": round(seed_accuracy, 4),
        "p10": round(p10, 1), "p25": round(p25, 1), "p50": round(p50, 1),
        "p75": round(p75, 1), "p90": round(p90, 1),
        "sr_block_episodes": n_episodes,
        "episodes_per_session": round(episodes_per_session, 1),
        "mean_block_bars": round(mean_block_bars, 1),
        "mean_block_sec": round(mean_block_sec, 1),
        "mean_block_displacement": round(mean_block_disp, 2),
        "wp_resets": sim_result["wp_resets"],
        "resets_per_session": round(resets_per_session, 1),
        "session_pnl": session_pnl.to_dict(),
    }


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_data():
    """Load P1a tick data, SpeedRead, bar close prices, and sr_idx mapping."""
    print("Loading tick data (P1a)...")
    t0 = time.time()
    tick_bars = load_bars(str(_REPO / _1TICK_PATH))
    tick_p1a = tick_bars[tick_bars["datetime"].dt.date <= _P1_MID].reset_index(drop=True)
    print(f"  P1a ticks: {len(tick_p1a):,} rows in {time.time() - t0:.1f}s")

    prices = tick_p1a["Last"].values.astype(np.float64)
    dts = tick_p1a["datetime"].values
    hours = tick_p1a["datetime"].dt.hour.values.astype(np.int32)
    minutes = tick_p1a["datetime"].dt.minute.values.astype(np.int32)
    seconds = tick_p1a["datetime"].dt.second.values.astype(np.int32)
    tod_secs = hours * 3600 + minutes * 60 + seconds

    # SpeedRead and bar mapping
    print("Loading SpeedRead + 250-tick bar close prices...")
    sr_df = pd.read_parquet(_SR_PARQUET)
    sr_ts = pd.to_datetime(sr_df["datetime"]).values.astype("int64") // 10**9
    sr_comp = sr_df["speedread_composite"].values.astype(np.float64)
    sr_comp = np.nan_to_num(sr_comp, nan=-1.0)

    # 250-tick bar close prices (aligned with SR parquet)
    ohlc = load_bars(str(_REPO / _250TICK_PATH))
    bar_close = ohlc["Last"].values.astype(np.float64)

    # Map ticks to 250-tick bar indices
    tick_ts = tick_p1a["datetime"].values.astype("int64") // 10**9
    sr_idx = np.clip(np.searchsorted(sr_ts, tick_ts, side="right") - 1, 0, len(sr_df) - 1)
    tick_sr = sr_comp[sr_idx]

    print(f"  SpeedRead mapped. Valid: {(tick_sr >= 0).sum():,} / {len(tick_sr):,}")
    print(f"  250-tick bars: {len(bar_close):,}")

    first_dt = tick_p1a["datetime"].iloc[0]
    last_dt = tick_p1a["datetime"].iloc[-1]
    print(f"  Date range: {first_dt} to {last_dt}")
    print(f"  Load complete in {time.time() - t0:.1f}s")

    return prices, tod_secs, tick_sr, dts, sr_idx, bar_close


# ---------------------------------------------------------------------------
# Step 1: Test F and G against baseline D
# ---------------------------------------------------------------------------

def step1(prices, tod_secs, sr_vals, dts, sr_idx, bar_close):
    print("\n" + "=" * 70)
    print("STEP 1: Test F and G Against Baseline D (P1a)")
    print("  Baseline: Variant D + SeedDist=15 (RTH-only, 9:30 watch price)")
    print("  All rotation params frozen.")
    print("=" * 70)

    configs = [
        ("D (baseline)", "none"),
        ("D+F (reset on SR clear)", "reset_on_clear"),
        ("D+G (reset on each bar)", "reset_on_bar"),
    ]

    results = []
    for name, mode in configs:
        t0 = time.time()
        sim = simulate(prices, tod_secs, sr_vals, dts, sr_idx, bar_close,
                       sr_block_mode=mode)
        elapsed = time.time() - t0
        r = analyze(sim, name)
        if r is None:
            print(f"  {name}: no valid cycles")
            continue
        results.append(r)
        print(f"\n--- {name} ({elapsed:.1f}s) ---")
        print(f"  Cycles: {r['cycles']}, Net PF: {r['npf_1t']:.4f}, "
              f"Net PnL: {r['net_pnl']:+,}, Daily: {r['mean_daily']:+.1f}")
        print(f"  Session Win%: {r['session_win_pct']:.1%}, "
              f"Seed Accuracy: {r['seed_accuracy']:.1%}")
        print(f"  SR-block episodes: {r['sr_block_episodes']} "
              f"({r['episodes_per_session']:.1f}/session)")
        print(f"  Mean block duration: {r['mean_block_bars']:.1f} bars, "
              f"{r['mean_block_sec']:.1f}s")
        print(f"  Mean price displacement during blocks: "
              f"{r['mean_block_displacement']:.2f} pts")
        print(f"  Watch price resets: {r['wp_resets']} "
              f"({r['resets_per_session']:.1f}/session)")

    if not results:
        print("  ERROR: No valid results.")
        return None

    # Comparison table
    print(f"\n{'='*80}")
    print(f"{'Config':<28} {'Cyc':>5} {'NPF':>6} {'NetPnL':>8} {'DailyM':>7} "
          f"{'SessW%':>6} {'SeedAcc':>7} {'Eps/S':>5} {'Resets/S':>8}")
    print("-" * 80)
    for r in results:
        print(f"{r['label']:<28} {r['cycles']:>5} {r['npf_1t']:>6.3f} "
              f"{r['net_pnl']:>+8,} {r['mean_daily']:>+7.1f} "
              f"{r['session_win_pct']:>6.1%} {r['seed_accuracy']:>7.1%} "
              f"{r['episodes_per_session']:>5.1f} {r['resets_per_session']:>8.1f}")
    print(f"{'='*80}")

    _save_result("step1_results.json", results)

    # Kill condition: fewer than 5 SR-block episodes during RTH
    baseline = results[0]
    if baseline["sr_block_episodes"] < 5:
        print(f"\n  *** KILL CONDITION: Only {baseline['sr_block_episodes']} SR-block "
              f"episodes during RTH. ***")
        print(f"  Stale watch price problem too rare to optimize. Baseline D is the answer.")
        return {"kill": True, "results": results, "kill_reason": "too_few_episodes"}

    # Check NPF differences
    baseline_npf = baseline["npf_1t"]
    for r in results[1:]:
        diff_pct = (r["npf_1t"] - baseline_npf) / baseline_npf * 100
        print(f"  {r['label']}: NPF diff from baseline = {diff_pct:+.1f}%")

    # Check for positive improvement (not just any difference)
    best_variant = max(results[1:], key=lambda x: x["npf_1t"])
    best_diff = (best_variant["npf_1t"] - baseline_npf) / baseline_npf * 100
    print(f"  Best variant improvement: {best_diff:+.1f}%")

    if best_diff < 5:
        print(f"\n  No variant improved NPF by >=5%. Step 2 sensitivity analysis skipped.")
        return {"kill": False, "skip_step2": True, "results": results}

    return {"kill": False, "skip_step2": False, "results": results}


# ---------------------------------------------------------------------------
# Step 2: Sensitivity analysis
# ---------------------------------------------------------------------------

def step2():
    """Session-by-session comparison of best variant vs baseline."""
    print("\n" + "=" * 70)
    print("STEP 2: Sensitivity Analysis")
    print("=" * 70)

    results = _load_result("step1_results.json")
    if results is None:
        print("  ERROR: Step 1 results not found.")
        return None

    baseline = results[0]
    baseline_npf = baseline["npf_1t"]

    # Find best non-baseline variant
    best = max(results[1:], key=lambda x: x["npf_1t"])
    diff_pct = (best["npf_1t"] - baseline_npf) / baseline_npf * 100

    if diff_pct < 5:
        print(f"  Best variant ({best['label']}) improved NPF by only {diff_pct:+.1f}% (<5%).")
        print(f"  Sensitivity analysis not warranted.")
        return {"robust": False, "reason": "insufficient_improvement"}

    print(f"  Comparing: {best['label']} (NPF={best['npf_1t']:.4f}) vs "
          f"{baseline['label']} (NPF={baseline_npf:.4f})")
    print(f"  NPF improvement: {diff_pct:+.1f}%")

    # Session-by-session comparison
    base_pnl = baseline["session_pnl"]
    best_pnl = best["session_pnl"]

    all_sids = sorted(set(base_pnl.keys()) | set(best_pnl.keys()))
    diffs = {}
    for sid in all_sids:
        bp = base_pnl.get(sid, 0)
        vp = best_pnl.get(sid, 0)
        # Handle both string and int keys from JSON
        if isinstance(bp, str):
            bp = float(bp)
        if isinstance(vp, str):
            vp = float(vp)
        diffs[sid] = vp - bp

    improved = sum(1 for d in diffs.values() if d > 0)
    worsened = sum(1 for d in diffs.values() if d < 0)
    unchanged = sum(1 for d in diffs.values() if d == 0)

    print(f"\n  Session-by-session comparison ({len(all_sids)} sessions):")
    print(f"    Improved:  {improved}")
    print(f"    Worsened:  {worsened}")
    print(f"    Unchanged: {unchanged}")

    # Top 5 improvements and worst 5
    sorted_diffs = sorted(diffs.items(), key=lambda x: x[1], reverse=True)

    print(f"\n  5 sessions with LARGEST improvement (variant - baseline):")
    for sid, d in sorted_diffs[:5]:
        bp = base_pnl.get(sid, 0)
        vp = best_pnl.get(sid, 0)
        print(f"    Session {sid}: {d:+.1f} ticks "
              f"(baseline={bp:+.1f}, variant={vp:+.1f})")

    print(f"\n  5 sessions with LARGEST worsening (variant - baseline):")
    for sid, d in sorted_diffs[-5:]:
        bp = base_pnl.get(sid, 0)
        vp = best_pnl.get(sid, 0)
        print(f"    Session {sid}: {d:+.1f} ticks "
              f"(baseline={bp:+.1f}, variant={vp:+.1f})")

    # Robustness check: is improvement driven by <=3 sessions?
    total_improvement = sum(d for d in diffs.values() if d > 0)
    top3_improvement = sum(d for _, d in sorted_diffs[:3] if d > 0)
    top3_pct = (top3_improvement / total_improvement * 100) if total_improvement > 0 else 100

    print(f"\n  Total positive diff: {total_improvement:+.1f} ticks")
    print(f"  Top 3 sessions contribute: {top3_improvement:+.1f} ticks ({top3_pct:.1f}%)")

    robust = top3_pct < 80  # not driven by just 3 sessions
    print(f"\n  Robustness: {'ROBUST' if robust else 'CONCENTRATED'} "
          f"(top 3 = {top3_pct:.1f}% of improvement)")

    if not robust:
        print(f"  *** KILL CONDITION: Improvement concentrated in <=3 sessions. ***")
        print(f"  Not robust. Stick with baseline.")

    _save_result("step2_sensitivity.json", {
        "baseline": baseline["label"],
        "variant": best["label"],
        "diff_pct": round(diff_pct, 2),
        "improved": improved,
        "worsened": worsened,
        "unchanged": unchanged,
        "total_improvement": round(total_improvement, 1),
        "top3_pct": round(top3_pct, 1),
        "robust": robust,
    })

    return {"robust": robust}


# ---------------------------------------------------------------------------
# Step 3: Recommendation
# ---------------------------------------------------------------------------

def step3():
    print("\n" + "=" * 70)
    print("STEP 3: Recommendation")
    print("=" * 70)

    s1 = _load_result("step1_results.json")
    s2 = _load_result("step2_sensitivity.json")

    if s1 is None:
        print("  ERROR: Step 1 results not found.")
        return

    baseline = s1[0]
    baseline_npf = baseline["npf_1t"]

    # Determine outcome
    adopt_variant = False
    adopted_label = None

    if s2 and s2.get("robust"):
        # Step 2 confirmed robust improvement
        best = max(s1[1:], key=lambda x: x["npf_1t"])
        diff_pct = (best["npf_1t"] - baseline_npf) / baseline_npf * 100
        if diff_pct >= 5:
            adopt_variant = True
            adopted_label = best["label"]
            print(f"  ADOPTING: {adopted_label}")
            print(f"  Reason: NPF improvement {diff_pct:+.1f}% and robust across sessions.")
    elif s2 and not s2.get("robust"):
        print(f"  Step 2 found improvement not robust. Keeping baseline.")
    else:
        # No Step 2 (either skipped or not run)
        best = max(s1[1:], key=lambda x: x["npf_1t"])
        diff_pct = (best["npf_1t"] - baseline_npf) / baseline_npf * 100
        if diff_pct < 5:
            print(f"  No variant improved NPF by >=5% ({diff_pct:+.1f}%). Keeping baseline.")
        else:
            print(f"  Step 2 not run but >=5% improvement found. Run Step 2 to confirm.")

    # Determine SR-block behavior
    if adopt_variant and "F" in adopted_label:
        sr_block_behavior = "reset_on_clear (Variant F: reset watch price when SR crosses above 48)"
    elif adopt_variant and "G" in adopted_label:
        sr_block_behavior = "reset_on_bar (Variant G: reset watch price on each bar during SR block)"
    else:
        sr_block_behavior = "none (watch price stays fixed during SR block)"

    # Final frozen config
    print(f"\n--- Final Frozen Config for P1b Validation ---")
    print(f"  | {'Parameter':<32} | {'Value':<48} |")
    print(f"  |{'-'*34}|{'-'*50}|")
    params = [
        ("StepDist (rotation)", "25"),
        ("SeedDist", "15"),
        ("Watch price", "First tick at/after 09:30 ET"),
        ("SR block behavior", sr_block_behavior),
        ("Position cap (flatten_reseed)", "2"),
        ("Max levels (ML)", "1"),
        ("Max contract size", "8"),
        ("Initial qty", "1"),
        ("Seed SR threshold", "48"),
        ("Reversal SR threshold", "48"),
        ("Daily flatten", "16:00 ET"),
        ("Anchor mode", "Walking"),
        ("cost_ticks", "1"),
    ]
    for k, v in params:
        print(f"  | {k:<32} | {v:<48} |")

    print(f"\n  *** DO NOT RUN P1b. Recommendation only. ***")

    # Progression from prior investigation
    print(f"\n--- Full Progression ---")
    print(f"  {'Config':<50} {'NPF':>6} {'NetPnL':>8}")
    print(f"  {'-'*70}")
    print(f"  {'Continuous (no flatten, no SR)':50} {'~1.14':>6} {'~+14,527':>8}")
    print(f"  {'Daily-flatten + SD=25 (baseline from Step 1)':50} {'1.243':>6} {'+15,330':>8}")
    print(f"  {'Daily-flatten + SD=15':50} {'1.267':>6} {'+19,024':>8}")
    print(f"  {'Daily-flatten + SD=15 + RTH-only (Variant D)':50} "
          f"{baseline_npf:>6.3f} {baseline['net_pnl']:>+8,}")
    if adopt_variant:
        best = max(s1[1:], key=lambda x: x["npf_1t"])
        print(f"  {'Daily-flatten + SD=15 + RTH + ' + adopted_label:50} "
              f"{best['npf_1t']:>6.3f} {best['net_pnl']:>+8,}")

    _save_result("step3_recommendation.json", {
        "adopted": adopt_variant,
        "adopted_label": adopted_label,
        "sr_block_behavior": sr_block_behavior,
        "baseline_npf": baseline_npf,
    })


# ---------------------------------------------------------------------------
# File I/O helpers
# ---------------------------------------------------------------------------

def _save_result(filename, data):
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = _OUTPUT_DIR / filename
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)
    print(f"  Saved: {path}")


def _load_result(filename):
    path = _OUTPUT_DIR / filename
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="SR-block watch price reset investigation")
    parser.add_argument("--step", required=True, help="Step: 1, 2, 3, or all")
    args = parser.parse_args()

    step = args.step.lower()

    if step in ("1", "all"):
        data = load_data()
        r1 = step1(*data)

        if step == "1":
            return

        if r1 and r1.get("kill"):
            print(f"\nKILL: {r1.get('kill_reason', 'unknown')}. Skipping Step 2.")
            step3()
            return

        if r1 and r1.get("skip_step2"):
            print(f"\nNo variant improved NPF by >=5%. Skipping Step 2.")
            step3()
            return

        step2()
        step3()

    elif step == "2":
        step2()
    elif step == "3":
        step3()
    else:
        print(f"Unknown step: {args.step}. Use 1, 2, 3, or all.")
        sys.exit(1)


if __name__ == "__main__":
    main()
