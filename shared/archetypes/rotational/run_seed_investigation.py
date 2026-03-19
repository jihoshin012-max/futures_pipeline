# archetype: rotational
"""Seed optimization investigation for daily-flatten trading.

Investigates optimal seed mechanics when daily flatten at 16:00 ET is modeled.
The validated rotation config (SD=25, ML=1, cap=2, SpeedRead>=48) is FROZEN.
Only seed parameters vary: seed distance, seed SpeedRead threshold, watch price mode.

Steps:
  --step 1: Baseline with daily flattens (kill if net PF < 0.95)
  --step 2: Seed distance sweep + SpeedRead seed threshold sub-sweep
  --step 3: Watch price placement (conditional on Step 2)
  --step 4: Summary and recommendation

Usage:
    python run_seed_investigation.py --step 1
    python run_seed_investigation.py --step 2
    python run_seed_investigation.py --step 3
    python run_seed_investigation.py --step 4
    python run_seed_investigation.py --step all
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
# Constants
# ---------------------------------------------------------------------------

_P1_START = dt_mod.date(2025, 9, 21)
_P1_END = dt_mod.date(2025, 12, 14)
_P1_MID = _P1_START + (_P1_END - _P1_START) / 2  # ~Nov 2

EXCLUDE_HOURS = {1, 19, 20}

# Session boundaries (seconds since midnight, ET)
FLATTEN_TOD = 16 * 3600   # 16:00:00 = 57600
RESUME_TOD = 18 * 3600    # 18:00:00 = 64800
RTH_OPEN_TOD = 9 * 3600 + 30 * 60  # 09:30:00 = 34200

# Frozen rotation params (from instruments.md and validated config)
TICK_SIZE = 0.25
COST_TICKS = 1
STEP_DIST = 25.0        # rotation distance — FROZEN
FLATTEN_CAP = 2         # flatten_reseed_cap — FROZEN
MAX_LEVELS = 1           # max martingale levels — FROZEN
MAX_CS = 8               # max contract size — FROZEN
INIT_QTY = 1             # initial quantity — FROZEN
REV_SR_THRESH = 48.0     # reversal SpeedRead threshold — FROZEN

# Data paths
_1TICK_PATH = "stages/01-data/data/bar_data/tick/NQ_BarData_1tick_rot_P1.csv"
_250TICK_PATH = "stages/01-data/data/bar_data/tick/NQ_BarData_250tick_rot_P1.csv"
_SR_PARQUET = Path(__file__).parent / "speedread_results" / "speedread_250tick.parquet"
_OUTPUT_DIR = Path(__file__).parent / "seed_investigation_results"

# State constants
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
    """Compute cycle summary record from trade list."""
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
        "exit_reason": "",  # caller fills
    }


# ---------------------------------------------------------------------------
# Core simulation with daily flatten
# ---------------------------------------------------------------------------

def simulate_daily_flatten(prices, tod_secs, sr_vals, dts,
                           seed_dist=25.0, step_dist=STEP_DIST,
                           add_dist=None,
                           flatten_reseed_cap=FLATTEN_CAP,
                           max_levels=MAX_LEVELS,
                           seed_sr_thresh=48.0, rev_sr_thresh=REV_SR_THRESH,
                           watch_mode='current', reset_on_reversal=False,
                           cost_ticks=COST_TICKS, tick_size=TICK_SIZE,
                           session_window_end=None,
                           cap_action='walk',
                           adaptive_lookup=None,
                           seed_start_tod=None,
                           max_adverse_sigma=None,
                           max_cap_walks=None,
                           std_lookup=None):
    """Tick simulation with daily flatten at 16:00 ET, fresh seed at 18:00 ET.

    Three distance triggers (all measured from current anchor):
    - add_dist: price moves add_dist AGAINST → add 1 contract (if below cap)
    - step_dist: price moves step_dist IN FAVOR → flatten and reverse
    - step_dist: price moves step_dist AGAINST when at cap → walk anchor (cap_action='walk')
      or flatten-reseed (cap_action='flatten_reseed', V1.1 compat)

    SpeedRead filter is applied in real-time:
    - Seeds only fire when sr >= seed_sr_thresh
    - Reversals enter opposite only when sr >= rev_sr_thresh; otherwise flatten to WATCHING

    Watch price modes:
    - 'current': first tick at/after 18:00
    - 'prior_close': last price before 16:00 flatten
    - 'prior_midpoint': (session_high + session_low) / 2 from prior session
    - 'rth_open': first tick at/after 09:30 ET (no trading in overnight session)

    reset_on_reversal (variant E): if True, watch price resets when price crosses through it.

    session_window_end: TOD in seconds (e.g. 11*3600+30*60 for 11:30).
        When reached, flatten if positioned, full state reset, no new entries until next session.
        None = no early window (trades until 16:00 flatten).

    cap_action: 'walk' (Phase 1 default — walk anchor at cap) or
                'flatten_reseed' (V1.1 compat — flatten all and go to WATCHING).

    adaptive_lookup: dict with 'timestamps' (int64 ns), 'sd_values', 'ad_values'.
        When provided, step_dist/add_dist/seed_dist are read from this lookup at each
        cycle entry (SEED/REVERSAL). SeedDist = StepDist (coupled). Floor = 10 pts.

    seed_start_tod: TOD in seconds for earliest seed acceptance (e.g. 10*3600 for 10:00).
        Only applies to watch_mode='rth_open'. None = use RTH_OPEN_TOD (09:30).

    max_adverse_sigma: If set, flatten cycle when adverse excursion from entry exceeds
        max_adverse_sigma * rolling_zigzag_std. Cycle resets to WATCHING with new watch price.

    max_cap_walks: If set, flatten cycle when cap-walk count within the cycle exceeds
        this limit. Same reset behavior as max_adverse_sigma.

    std_lookup: dict with 'timestamps' (int64 ns) and 'std_values' (float64).
        Rolling 200-swing zigzag std, same buffer as adaptive_lookup. Required for 4A stop.

    Returns dict with trade_records, cycle_records, total_sessions, wp_resets, cap_walks.
    """
    if add_dist is None:
        add_dist = step_dist

    # Effective session end: early window or regular 16:00 flatten
    effective_flatten = session_window_end if session_window_end is not None else FLATTEN_TOD

    n = len(prices)

    # Current distances (may be updated by adaptive_lookup)
    current_sd = step_dist
    current_ad = add_dist
    current_seed = seed_dist

    # Adaptive lookup arrays (for bisect)
    _adapt_ts = adaptive_lookup['timestamps'] if adaptive_lookup else None
    _adapt_sd = adaptive_lookup['sd_values'] if adaptive_lookup else None
    _adapt_ad = adaptive_lookup['ad_values'] if adaptive_lookup else None

    # Std lookup arrays (for 4A stop)
    _std_ts = std_lookup['timestamps'] if std_lookup else None
    _std_vals = std_lookup['std_values'] if std_lookup else None
    current_std = 0.0
    stops_4a = 0
    stops_4c = 0

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
    cap_walks = 0

    # Per-cycle tracking (MFE/MAE, cap-walks, distances used)
    cycle_entry_price = 0.0
    cycle_mfe = 0.0
    cycle_mae = 0.0
    cycle_cap_walks = 0

    # Session tracking for watch price variants
    prior_close = 0.0
    prior_high = 0.0
    prior_low = 1e9
    session_high = 0.0
    session_low = 1e9

    # Variant E state
    prev_side = 0  # 1=above watch, -1=below, 0=at/initial
    wp_resets = 0

    trade_records = []
    cycle_records = []
    cycle_trades = []

    for i in range(n):
        price = prices[i]
        tod = tod_secs[i]
        sr = sr_vals[i]

        # --- DEAD ZONE CHECK (effective_flatten <= tod < 18:00) ---
        if effective_flatten <= tod < RESUME_TOD:
            if state == _LONG or state == _SHORT:
                # Force daily flatten
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
                cr["mfe"] = round(cycle_mfe, 4)
                cr["mae"] = round(cycle_mae, 4)
                cr["cycle_cap_walks"] = cycle_cap_walks
                cr["stepdist_used"] = round(current_sd, 4)
                cr["adddist_used"] = round(current_ad, 4)
                cycle_records.append(cr)
                cycle_trades = []
                position_qty = 0

            if state != _IDLE:
                # Store session stats for watch price variants B/C
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

            if watch_mode == 'rth_open':
                state = _PRE_RTH
            else:
                state = _WATCHING
                if watch_mode == 'prior_close' and prior_close > 0:
                    watch_price = prior_close
                elif watch_mode == 'prior_midpoint' and prior_high > 0 and prior_low < 1e9:
                    watch_price = (prior_high + prior_low) / 2
                else:
                    watch_price = price  # 'current' or fallback
                prev_side = 0
            continue

        # Update session high/low
        if price > session_high:
            session_high = price
        if price < session_low:
            session_low = price

        # --- PRE_RTH: variant D waits for seed_start_tod (default 09:30) ---
        # Must check tod < FLATTEN_TOD to avoid triggering during evening
        # session (18:00-23:59 has tod > RTH_OPEN_TOD but is pre-RTH)
        _start_tod = seed_start_tod if seed_start_tod is not None else RTH_OPEN_TOD
        if state == _PRE_RTH:
            if _start_tod <= tod < FLATTEN_TOD:
                state = _WATCHING
                watch_price = price
                prev_side = 0
            continue

        # --- WATCHING: seed detection ---
        if state == _WATCHING:
            if watch_price == 0.0:
                watch_price = price
                continue

            # Variant E: reset on reversal through watch price
            if reset_on_reversal:
                cur_side = 1 if price > watch_price else (-1 if price < watch_price else 0)
                if prev_side != 0 and cur_side != 0 and cur_side != prev_side:
                    # Price crossed through watch price — reset
                    watch_price = price
                    prev_side = cur_side
                    wp_resets += 1
                    continue
                if cur_side != 0:
                    prev_side = cur_side

            up_dist = price - watch_price
            down_dist = watch_price - price

            if up_dist >= current_seed and sr >= seed_sr_thresh:
                # Adaptive lookup at cycle entry
                if _adapt_ts is not None:
                    _aidx = np.searchsorted(_adapt_ts, dts[i].astype('int64'), side='right') - 1
                    if _aidx >= 0:
                        current_sd = max(_adapt_sd[_aidx], 10.0)
                        current_ad = max(_adapt_ad[_aidx], 10.0)
                        current_seed = current_sd  # SeedDist = StepDist (coupled)
                if _std_ts is not None:
                    _sidx = np.searchsorted(_std_ts, dts[i].astype('int64'), side='right') - 1
                    if _sidx >= 0:
                        current_std = _std_vals[_sidx]
                # Seed Long
                cycle_id += 1
                state = _LONG
                anchor = price
                level = 0
                position_qty = INIT_QTY
                avg_entry = price
                cycle_start = i
                cycle_entry_price = price
                cycle_mfe = 0.0
                cycle_mae = 0.0
                cycle_cap_walks = 0
                t = {"bar_idx": i, "datetime": dts[i], "action": "SEED",
                     "direction": "Long", "qty": INIT_QTY, "price": price,
                     "level": 0, "anchor": price,
                     "cost_ticks": cost_ticks * INIT_QTY,
                     "cycle_id": cycle_id, "session_id": session_id,
                     "price_source": "tick"}
                trade_records.append(t)
                cycle_trades = [t]
            elif down_dist >= current_seed and sr >= seed_sr_thresh:
                # Adaptive lookup at cycle entry
                if _adapt_ts is not None:
                    _aidx = np.searchsorted(_adapt_ts, dts[i].astype('int64'), side='right') - 1
                    if _aidx >= 0:
                        current_sd = max(_adapt_sd[_aidx], 10.0)
                        current_ad = max(_adapt_ad[_aidx], 10.0)
                        current_seed = current_sd
                if _std_ts is not None:
                    _sidx = np.searchsorted(_std_ts, dts[i].astype('int64'), side='right') - 1
                    if _sidx >= 0:
                        current_std = _std_vals[_sidx]
                # Seed Short
                cycle_id += 1
                state = _SHORT
                anchor = price
                level = 0
                position_qty = INIT_QTY
                avg_entry = price
                cycle_start = i
                cycle_entry_price = price
                cycle_mfe = 0.0
                cycle_mae = 0.0
                cycle_cap_walks = 0
                t = {"bar_idx": i, "datetime": dts[i], "action": "SEED",
                     "direction": "Short", "qty": INIT_QTY, "price": price,
                     "level": 0, "anchor": price,
                     "cost_ticks": cost_ticks * INIT_QTY,
                     "cycle_id": cycle_id, "session_id": session_id,
                     "price_source": "tick"}
                trade_records.append(t)
                cycle_trades = [t]
            continue

        # --- POSITIONED (LONG or SHORT): rotation logic ---

        # MFE/MAE tracking (points from cycle entry price)
        excursion = (price - cycle_entry_price) if state == _LONG else (cycle_entry_price - price)
        if excursion > cycle_mfe:
            cycle_mfe = excursion
        if -excursion > cycle_mae:
            cycle_mae = -excursion

        # --- STOP CHECK: 4A (max adverse sigma) ---
        if max_adverse_sigma is not None and current_std > 0:
            adverse_from_entry = max(0.0, -excursion)
            if adverse_from_entry > max_adverse_sigma * current_std:
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
                cr["exit_reason"] = "stop_4a"
                cr["session_id"] = session_id
                cr["mfe"] = round(cycle_mfe, 4)
                cr["mae"] = round(cycle_mae, 4)
                cr["cycle_cap_walks"] = cycle_cap_walks
                cr["stepdist_used"] = round(current_sd, 4)
                cr["adddist_used"] = round(current_ad, 4)
                cycle_records.append(cr)
                stops_4a += 1
                state = _WATCHING
                watch_price = price
                position_qty = 0
                cycle_trades = []
                prev_side = 0
                continue

        distance = price - anchor
        if state == _LONG:
            in_favor = distance >= current_sd
            adverse = -distance  # positive when price below anchor
        else:  # _SHORT
            in_favor = (-distance) >= current_sd
            adverse = distance   # positive when price above anchor

        add_triggered = adverse >= current_ad
        capwalk_triggered = adverse >= current_sd

        if in_favor:
            direction = "Long" if state == _LONG else "Short"

            # Flatten current position
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

            if sr >= rev_sr_thresh:
                # Full reversal: enter opposite direction
                cr["exit_reason"] = "reversal"
                cr["mfe"] = round(cycle_mfe, 4)
                cr["mae"] = round(cycle_mae, 4)
                cr["cycle_cap_walks"] = cycle_cap_walks
                cr["stepdist_used"] = round(current_sd, 4)
                cr["adddist_used"] = round(current_ad, 4)
                cycle_records.append(cr)

                # Adaptive lookup at cycle entry
                if _adapt_ts is not None:
                    _aidx = np.searchsorted(_adapt_ts, dts[i].astype('int64'), side='right') - 1
                    if _aidx >= 0:
                        current_sd = max(_adapt_sd[_aidx], 10.0)
                        current_ad = max(_adapt_ad[_aidx], 10.0)
                        current_seed = current_sd
                if _std_ts is not None:
                    _sidx = np.searchsorted(_std_ts, dts[i].astype('int64'), side='right') - 1
                    if _sidx >= 0:
                        current_std = _std_vals[_sidx]

                new_dir = "Short" if state == _LONG else "Long"
                cycle_id += 1
                state = _SHORT if state == _LONG else _LONG
                anchor = price
                level = 0
                position_qty = INIT_QTY
                avg_entry = price
                cycle_start = i
                cycle_entry_price = price
                cycle_mfe = 0.0
                cycle_mae = 0.0
                cycle_cap_walks = 0
                rt = {"bar_idx": i, "datetime": dts[i], "action": "REVERSAL",
                      "direction": new_dir, "qty": INIT_QTY, "price": price,
                      "level": 0, "anchor": price,
                      "cost_ticks": cost_ticks * INIT_QTY,
                      "cycle_id": cycle_id, "session_id": session_id,
                      "price_source": "tick"}
                trade_records.append(rt)
                cycle_trades = [rt]
            else:
                # SR too low for reversal entry: flatten only, go to WATCHING
                cr["exit_reason"] = "reversal_sr_skip"
                cr["mfe"] = round(cycle_mfe, 4)
                cr["mae"] = round(cycle_mae, 4)
                cr["cycle_cap_walks"] = cycle_cap_walks
                cr["stepdist_used"] = round(current_sd, 4)
                cr["adddist_used"] = round(current_ad, 4)
                cycle_records.append(cr)

                state = _WATCHING
                watch_price = price
                position_qty = 0
                cycle_trades = []
                prev_side = 0

        elif add_triggered or capwalk_triggered:
            at_cap = flatten_reseed_cap > 0 and position_qty >= flatten_reseed_cap

            if at_cap and capwalk_triggered:
                # At position cap and price moved step_dist against
                if cap_action == 'flatten_reseed':
                    # V1.1 compat: flatten all, go to WATCHING
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
                    cr["mfe"] = round(cycle_mfe, 4)
                    cr["mae"] = round(cycle_mae, 4)
                    cr["cycle_cap_walks"] = cycle_cap_walks
                    cr["stepdist_used"] = round(current_sd, 4)
                    cr["adddist_used"] = round(current_ad, 4)
                    cycle_records.append(cr)

                    state = _WATCHING
                    watch_price = price
                    position_qty = 0
                    cycle_trades = []
                    prev_side = 0
                else:
                    # Phase 1: walk anchor only, keep position
                    direction = "Long" if state == _LONG else "Short"
                    cw = {"bar_idx": i, "datetime": dts[i], "action": "CAP_WALK",
                          "direction": direction, "qty": 0, "price": price,
                          "level": level, "anchor": price,
                          "cost_ticks": 0,
                          "cycle_id": cycle_id, "session_id": session_id,
                          "price_source": "tick"}
                    trade_records.append(cw)
                    cycle_trades.append(cw)
                    anchor = price
                    cap_walks += 1
                    cycle_cap_walks += 1

                    # --- STOP CHECK: 4C (max cap-walks) ---
                    if max_cap_walks is not None and cycle_cap_walks > max_cap_walks:
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
                        cr["exit_reason"] = "stop_4c"
                        cr["session_id"] = session_id
                        cr["mfe"] = round(cycle_mfe, 4)
                        cr["mae"] = round(cycle_mae, 4)
                        cr["cycle_cap_walks"] = cycle_cap_walks
                        cr["stepdist_used"] = round(current_sd, 4)
                        cr["adddist_used"] = round(current_ad, 4)
                        cycle_records.append(cr)
                        stops_4c += 1
                        state = _WATCHING
                        watch_price = price
                        position_qty = 0
                        cycle_trades = []
                        prev_side = 0

            elif not at_cap and add_triggered:
                # ADD: price moved add_dist against, below cap
                proposed_qty = INIT_QTY * (2 ** level)
                if proposed_qty > MAX_CS or level >= max_levels:
                    proposed_qty = INIT_QTY
                    next_level = 0
                    level_at_add = 0
                else:
                    next_level = level + 1
                    level_at_add = level

                level = next_level
                anchor = price  # walking mode
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
            # else: at cap but only add_triggered (not capwalk_triggered) → do nothing

    # Finalize any open cycle at end of data
    if (state == _LONG or state == _SHORT) and cycle_trades:
        last_price = prices[-1]
        cr = _finalize_cycle(cycle_trades, cycle_id, cycle_start, n - 1,
                             state, last_price, tick_size)
        cr["exit_reason"] = "end_of_data"
        cr["session_id"] = session_id
        cr["mfe"] = round(cycle_mfe, 4)
        cr["mae"] = round(cycle_mae, 4)
        cr["cycle_cap_walks"] = cycle_cap_walks
        cr["stepdist_used"] = round(current_sd, 4)
        cr["adddist_used"] = round(current_ad, 4)
        cycle_records.append(cr)

    return {
        "trade_records": trade_records,
        "cycle_records": cycle_records,
        "total_sessions": session_id,
        "wp_resets": wp_resets,
        "cap_walks": cap_walks,
        "stops_4a": stops_4a,
        "stops_4c": stops_4c,
    }


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

def analyze(sim_result, label, exclude_hours=EXCLUDE_HOURS):
    """Compute summary statistics from simulation results.

    Applies post-hoc hour filter (exclude hours {1, 19, 20}).
    Returns dict of metrics or None if no valid cycles.
    """
    trade_records = sim_result["trade_records"]
    cycle_records = sim_result["cycle_records"]
    total_sessions = sim_result["total_sessions"]

    if not cycle_records:
        return None

    trades_df = pd.DataFrame(trade_records)
    cycles_df = pd.DataFrame(cycle_records)

    # Post-hoc hour filter on cycle entry
    entry_trades = trades_df[trades_df["action"].isin(["SEED", "REVERSAL"])]
    ce = entry_trades.groupby("cycle_id")["datetime"].first().reset_index()
    ce.columns = ["cycle_id", "entry_dt"]
    cycles_df = cycles_df.merge(ce, on="cycle_id", how="left")
    cycles_df["hour"] = pd.to_datetime(cycles_df["entry_dt"]).dt.hour
    cf = cycles_df[~cycles_df["hour"].isin(exclude_hours)].copy()

    if len(cf) == 0:
        return None

    # Per-cycle cost at 1t
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

    # Per-session PnL (include zero-cycle sessions)
    session_pnl_raw = cf.groupby("session_id")["net_1t"].sum()
    all_sids = range(1, total_sessions + 1)
    session_pnl = session_pnl_raw.reindex(all_sids, fill_value=0.0)
    n_sessions = total_sessions

    cycles_per_session = cf.groupby("session_id").size().reindex(all_sids, fill_value=0)
    mean_cycles = cycles_per_session.mean()

    mean_daily = session_pnl.mean()
    std_daily = session_pnl.std()
    session_win_pct = (session_pnl > 0).mean()

    # Distribution
    pvals = session_pnl.values
    if len(pvals) >= 5:
        p10, p25, p50, p75, p90 = np.percentile(pvals, [10, 25, 50, 75, 90])
    else:
        p10 = p25 = p50 = p75 = p90 = 0.0

    # Worst 5 sessions
    worst5 = session_pnl.nsmallest(5)

    # Seed accuracy: % of seed-initiated cycles with positive gross PnL
    first_actions = trades_df.groupby("cycle_id")["action"].first()
    seed_cids = first_actions[first_actions == "SEED"].index
    seed_cf = cf[cf["cycle_id"].isin(seed_cids)]
    seed_accuracy = (seed_cf["gross_pnl_ticks"] > 0).mean() if len(seed_cf) > 0 else 0

    return {
        "label": label,
        "cycles": nn,
        "gpf": round(gpf, 4),
        "npf_1t": round(npf, 4),
        "net_pnl": int(net_pnl),
        "sessions": n_sessions,
        "mean_daily": round(mean_daily, 1),
        "std_daily": round(std_daily, 1),
        "session_win_pct": round(session_win_pct, 4),
        "cycles_per_session": round(mean_cycles, 1),
        "seed_accuracy": round(seed_accuracy, 4),
        "p10": round(p10, 1),
        "p25": round(p25, 1),
        "p50": round(p50, 1),
        "p75": round(p75, 1),
        "p90": round(p90, 1),
        "worst5": {str(k): round(v, 1) for k, v in worst5.items()},
    }


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_data(period='p1a', use_speedread=True):
    """Load tick data and optionally SpeedRead composite, return arrays for simulation.

    Args:
        period: 'p1a' (Sep 21 – ~Nov 2), 'full_p1' (Sep 21 – Dec 14), or 'p1b' (~Nov 2 – Dec 14).
        use_speedread: If False, returns dummy SR array (all 100.0, passes any threshold).
                       Set False for Phase 1 base economics (no SpeedRead filtering).
    """
    label = period.upper()
    print(f"Loading tick data ({label})...")
    t0 = time.time()
    tick_bars = load_bars(str(_REPO / _1TICK_PATH))

    if period == 'p1a':
        tick_data = tick_bars[tick_bars["datetime"].dt.date <= _P1_MID].reset_index(drop=True)
    elif period == 'p1b':
        tick_data = tick_bars[tick_bars["datetime"].dt.date > _P1_MID].reset_index(drop=True)
    elif period == 'full_p1':
        tick_data = tick_bars[(tick_bars["datetime"].dt.date >= _P1_START) &
                              (tick_bars["datetime"].dt.date <= _P1_END)].reset_index(drop=True)
    else:
        raise ValueError(f"Unknown period: {period}. Use 'p1a', 'p1b', or 'full_p1'.")

    print(f"  {label} ticks: {len(tick_data):,} rows in {time.time() - t0:.1f}s")

    # Extract arrays
    prices = tick_data["Last"].values.astype(np.float64)
    dts = tick_data["datetime"].values  # datetime64
    hours = tick_data["datetime"].dt.hour.values.astype(np.int32)
    minutes = tick_data["datetime"].dt.minute.values.astype(np.int32)
    seconds = tick_data["datetime"].dt.second.values.astype(np.int32)
    tod_secs = hours * 3600 + minutes * 60 + seconds

    if use_speedread:
        # SpeedRead mapping
        print("Loading SpeedRead composite...")
        sr_df = pd.read_parquet(_SR_PARQUET)
        sr_ts = pd.to_datetime(sr_df["datetime"]).values.astype("int64") // 10**9
        sr_comp = sr_df["speedread_composite"].values.astype(np.float64)

        tick_ts = tick_data["datetime"].values.astype("int64") // 10**9
        sr_idx = np.clip(np.searchsorted(sr_ts, tick_ts, side="right") - 1, 0, len(sr_df) - 1)
        tick_sr = sr_comp[sr_idx]
        # Replace NaN with -1 (below any threshold -> filtered out)
        tick_sr = np.nan_to_num(tick_sr, nan=-1.0)
        print(f"  SpeedRead mapped. Valid: {(tick_sr >= 0).sum():,} / {len(tick_sr):,}")
    else:
        # No SpeedRead filtering: all ticks pass any threshold
        tick_sr = np.full(len(prices), 100.0, dtype=np.float64)
        print("  SpeedRead DISABLED (all ticks pass threshold)")

    # Verify session boundaries: check for data in dead zone
    dead_mask = (tod_secs >= FLATTEN_TOD) & (tod_secs < RESUME_TOD)
    n_dead = dead_mask.sum()
    print(f"  Ticks in dead zone (16:00-18:00): {n_dead:,}")

    # Date range
    first_dt = tick_data["datetime"].iloc[0]
    last_dt = tick_data["datetime"].iloc[-1]
    print(f"  Date range: {first_dt} to {last_dt}")

    print(f"  Load complete in {time.time() - t0:.1f}s")
    return prices, tod_secs, tick_sr, dts


# ---------------------------------------------------------------------------
# Step 1: Baseline with daily flattens
# ---------------------------------------------------------------------------

def step1(prices, tod_secs, sr_vals, dts):
    """Establish daily-flatten baseline with validated config."""
    print("\n" + "=" * 70)
    print("STEP 1: Baseline With Daily Flattens (P1a)")
    print("  Config: FRC SD=25, cap=2, ML=1, SpeedRead>=48, cost_ticks=1")
    print("  Daily flatten at 16:00 ET, fresh seed at 18:00 ET")
    print("=" * 70)

    t0 = time.time()
    sim = simulate_daily_flatten(
        prices, tod_secs, sr_vals, dts,
        seed_dist=25.0, step_dist=STEP_DIST,
        seed_sr_thresh=48.0, rev_sr_thresh=REV_SR_THRESH,
        watch_mode='current', reset_on_reversal=False,
        cap_action='flatten_reseed',
    )
    elapsed = time.time() - t0
    print(f"  Simulation: {elapsed:.1f}s")

    r = analyze(sim, "Daily-flatten baseline (SD=25, SR>=48)")
    if r is None:
        print("  ERROR: No valid cycles. Check data and session boundaries.")
        return None

    # Print report
    print(f"\n--- Results ---")
    print(f"  Total completed cycles: {r['cycles']}")
    print(f"  Gross PF:               {r['gpf']:.4f}")
    print(f"  Net PF @1t:             {r['npf_1t']:.4f}")
    print(f"  Net PnL (ticks):        {r['net_pnl']:+,}")
    print(f"  Trading sessions:       {r['sessions']}")
    print(f"  Mean cycles/session:    {r['cycles_per_session']:.1f}")
    print(f"  Mean net PnL/session:   {r['mean_daily']:+.1f}")
    print(f"  StdDev daily PnL:       {r['std_daily']:.1f}")
    print(f"  Session win rate:       {r['session_win_pct']:.1%}")
    print(f"  Seed accuracy:          {r['seed_accuracy']:.1%}")

    print(f"\n  Per-session PnL distribution:")
    print(f"    P10:    {r['p10']:+.1f}")
    print(f"    P25:    {r['p25']:+.1f}")
    print(f"    Median: {r['p50']:+.1f}")
    print(f"    P75:    {r['p75']:+.1f}")
    print(f"    P90:    {r['p90']:+.1f}")

    print(f"\n  Worst 5 sessions:")
    for sid, pnl in r["worst5"].items():
        print(f"    Session {sid}: {pnl:+.1f} ticks")

    # Comparison with continuous baseline
    print(f"\n--- Comparison with Continuous Baseline ---")
    print(f"  Continuous (no flatten, no SR filter): net PF~1.14, ~+14,527 ticks")
    print(f"  Continuous (post-hoc SR>=48):          net PF~1.33, ~+20,045 ticks")
    print(f"  Daily-flatten + real-time SR>=48:      net PF={r['npf_1t']:.4f}, {r['net_pnl']:+,} ticks")

    if r['sessions'] > 0:
        continuous_daily = 14527 / r['sessions']  # approximate per-session
        daily_cost = continuous_daily - r['mean_daily']
        print(f"  Estimated daily-flatten cost: ~{daily_cost:+.1f} ticks/session")

    # Kill condition
    if r['npf_1t'] < 0.95:
        print(f"\n  *** KILL CONDITION: Net PF {r['npf_1t']:.4f} < 0.95 ***")
        print(f"  Strategy not viable for daily-flatten trading. STOPPING.")
        _save_result("step1_baseline.json", r)
        return False

    print(f"\n  PASS: Net PF {r['npf_1t']:.4f} >= 0.95. Proceeding to Step 2.")
    _save_result("step1_baseline.json", r)
    return r


# ---------------------------------------------------------------------------
# Step 2: Seed distance sweep + SpeedRead seed threshold sub-sweep
# ---------------------------------------------------------------------------

def step2(prices, tod_secs, sr_vals, dts):
    """Sweep seed distances and SpeedRead seed thresholds."""
    print("\n" + "=" * 70)
    print("STEP 2: Seed Distance Sweep (P1a)")
    print("  Rotation StepDist=25 FROZEN. Only seed distance varies.")
    print("  SpeedRead reversal threshold=48 FROZEN.")
    print("=" * 70)

    seed_dists = [10, 15, 20, 25, 30, 35]
    results = []

    hdr = (f"  {'SeedDist':>8} {'Cyc':>5} {'NPF':>6} {'NetPnL':>8} "
           f"{'DailyM':>7} {'DailySD':>7} {'SessW%':>6} {'SeedAcc':>7} {'Sec':>4}")
    print(f"\n{hdr}")
    print("  " + "-" * 75)

    for sd in seed_dists:
        t0 = time.time()
        sim = simulate_daily_flatten(
            prices, tod_secs, sr_vals, dts,
            seed_dist=float(sd), step_dist=STEP_DIST,
            seed_sr_thresh=48.0, rev_sr_thresh=REV_SR_THRESH,
            watch_mode='current', reset_on_reversal=False,
        )
        elapsed = time.time() - t0
        r = analyze(sim, f"SeedDist={sd}")
        if r is None:
            print(f"  {sd:>8} — no cycles —")
            continue
        results.append(r)
        mark = " <<<" if r["npf_1t"] == max(x["npf_1t"] for x in results) else ""
        print(f"  {sd:>8} {r['cycles']:>5} {r['npf_1t']:>6.3f} {r['net_pnl']:>+8,} "
              f"{r['mean_daily']:>+7.1f} {r['std_daily']:>7.1f} "
              f"{r['session_win_pct']:>6.1%} {r['seed_accuracy']:>7.1%} {elapsed:>4.0f}{mark}")

    if not results:
        print("  ERROR: No valid results from seed distance sweep.")
        return None

    # Check kill condition: all within ±3%?
    npfs = [r["npf_1t"] for r in results]
    npf_range = max(npfs) - min(npfs)
    npf_mid = (max(npfs) + min(npfs)) / 2
    pct_variation = (npf_range / npf_mid * 100) if npf_mid > 0 else 0

    print(f"\n  Net PF range: {min(npfs):.4f} to {max(npfs):.4f} "
          f"(variation: {pct_variation:.1f}%)")

    # Find best and top-2
    ranked = sorted(results, key=lambda x: x["npf_1t"], reverse=True)
    best_sd = int(ranked[0]["label"].split("=")[1])
    top2_sds = [int(r["label"].split("=")[1]) for r in ranked[:2]]
    print(f"  Best seed distance: {best_sd}")

    _save_result("step2_seed_sweep.json", results)

    # --- Sub-sweep: SpeedRead seed threshold ---
    print(f"\n--- Sub-sweep: SpeedRead Seed Threshold ---")
    print(f"  Testing seed SR thresholds: 48, 52, 55")
    print(f"  Reversal SR threshold=48 FROZEN.")
    print(f"  Using top-2 seed distances: {top2_sds}")

    sr_thresholds = [48, 52, 55]
    sr_results = []

    hdr2 = (f"  {'SeedDist':>8} {'SeedSR':>6} {'Cyc':>5} {'NPF':>6} {'NetPnL':>8} "
            f"{'DailyM':>7} {'SessW%':>6} {'SeedAcc':>7} {'Sec':>4}")
    print(f"\n{hdr2}")
    print("  " + "-" * 75)

    for sd in top2_sds:
        for sr_t in sr_thresholds:
            t0 = time.time()
            sim = simulate_daily_flatten(
                prices, tod_secs, sr_vals, dts,
                seed_dist=float(sd), step_dist=STEP_DIST,
                seed_sr_thresh=float(sr_t), rev_sr_thresh=REV_SR_THRESH,
                watch_mode='current', reset_on_reversal=False,
            )
            elapsed = time.time() - t0
            r = analyze(sim, f"SD={sd}_SR={sr_t}")
            if r is None:
                print(f"  {sd:>8} {sr_t:>6} — no cycles —")
                continue
            sr_results.append(r)
            print(f"  {sd:>8} {sr_t:>6} {r['cycles']:>5} {r['npf_1t']:>6.3f} "
                  f"{r['net_pnl']:>+8,} {r['mean_daily']:>+7.1f} "
                  f"{r['session_win_pct']:>6.1%} {r['seed_accuracy']:>7.1%} {elapsed:>4.0f}")

    _save_result("step2_sr_sweep.json", sr_results)

    # Combined kill condition
    all_results = results + sr_results
    all_npfs = [r["npf_1t"] for r in all_results]
    total_range = max(all_npfs) - min(all_npfs)
    total_mid = (max(all_npfs) + min(all_npfs)) / 2
    total_pct = (total_range / total_mid * 100) if total_mid > 0 else 0

    seed_only_pct = pct_variation
    sr_npfs = [r["npf_1t"] for r in sr_results] if sr_results else []
    sr_pct = 0
    if len(sr_npfs) >= 2:
        sr_range = max(sr_npfs) - min(sr_npfs)
        sr_mid = (max(sr_npfs) + min(sr_npfs)) / 2
        sr_pct = (sr_range / sr_mid * 100) if sr_mid > 0 else 0

    print(f"\n  Seed distance variation: {seed_only_pct:.1f}%")
    print(f"  SR threshold variation:  {sr_pct:.1f}%")

    kill_seed = seed_only_pct <= 6  # ±3% = 6% range
    kill_sr = sr_pct <= 6

    if kill_seed and kill_sr:
        print(f"\n  *** KILL CONDITION: All configs within ±3%. ***")
        print(f"  Seed optimization cannot meaningfully improve performance.")
        print(f"  Current config (SeedDist=25, SeedSR=48) is fine. Skip to Step 4.")
        return {"kill": True, "results": results, "sr_results": sr_results}

    # Find overall best
    best_overall = max(all_results, key=lambda x: x["npf_1t"])
    print(f"\n  Best overall: {best_overall['label']} (NPF={best_overall['npf_1t']:.4f})")
    print(f"  Proceeding to Step 3 with this config.")

    return {"kill": False, "results": results, "sr_results": sr_results,
            "best": best_overall}


# ---------------------------------------------------------------------------
# Step 3: Watch price placement
# ---------------------------------------------------------------------------

def step3(prices, tod_secs, sr_vals, dts):
    """Test watch price variants using best seed config from Step 2."""
    print("\n" + "=" * 70)
    print("STEP 3: Watch Price Placement (P1a)")
    print("=" * 70)

    # Load Step 2 results to get best config
    step2_seed = _load_result("step2_seed_sweep.json")
    step2_sr = _load_result("step2_sr_sweep.json")

    if step2_seed is None:
        print("  ERROR: Step 2 results not found. Run Step 2 first.")
        return None

    # Find best config
    all_r = step2_seed + (step2_sr or [])
    best = max(all_r, key=lambda x: x["npf_1t"])
    label = best["label"]

    # Parse seed_dist and seed_sr from label
    if "SD=" in label and "SR=" in label:
        parts = label.split("_")
        best_sd = float(parts[0].split("=")[1])
        best_sr = float(parts[1].split("=")[1])
    elif "SeedDist=" in label:
        best_sd = float(label.split("=")[1])
        best_sr = 48.0
    else:
        best_sd = 25.0
        best_sr = 48.0

    print(f"  Using best from Step 2: SeedDist={best_sd:.0f}, SeedSR={best_sr:.0f}")
    print(f"  Rotation StepDist=25, ML=1, cap=2, reversal SR>=48 — all FROZEN")

    # Define variants
    variants = [
        ("A: Current (baseline)", "current", False),
        ("B: Prior session close", "prior_close", False),
        ("C: Prior session midpoint", "prior_midpoint", False),
        ("D: First RTH price (9:30)", "rth_open", False),
        ("E: Reset on reversal (current)", "current", True),
    ]

    results = []
    hdr = (f"  {'Variant':<32} {'Cyc':>5} {'NPF':>6} {'NetPnL':>8} "
           f"{'DailyM':>7} {'SessW%':>6} {'SeedAcc':>7} {'Sec':>4}")
    print(f"\n{hdr}")
    print("  " + "-" * 85)

    best_ad = None  # best of A-D
    for name, wmode, ror in variants:
        t0 = time.time()
        sim = simulate_daily_flatten(
            prices, tod_secs, sr_vals, dts,
            seed_dist=best_sd, step_dist=STEP_DIST,
            seed_sr_thresh=best_sr, rev_sr_thresh=REV_SR_THRESH,
            watch_mode=wmode, reset_on_reversal=ror,
        )
        elapsed = time.time() - t0
        r = analyze(sim, name)
        if r is None:
            print(f"  {name:<32} — no cycles —")
            continue
        r["wp_resets"] = sim["wp_resets"]
        results.append(r)

        # Pre-RTH vs RTH seed counts
        trades_df = pd.DataFrame(sim["trade_records"])
        seeds = trades_df[trades_df["action"] == "SEED"]
        if len(seeds) > 0:
            seed_hours = pd.to_datetime(seeds["datetime"]).dt.hour
            # Pre-RTH: 18:00-9:29 (hours 18-23, 0-9)
            pre_rth = ((seed_hours >= 18) | (seed_hours < 9) |
                       ((seed_hours == 9) & (pd.to_datetime(seeds["datetime"]).dt.minute < 30)))
            n_pre = pre_rth.sum()
            n_rth = len(seeds) - n_pre
        else:
            n_pre = n_rth = 0

        r["seeds_pre_rth"] = int(n_pre)
        r["seeds_rth"] = int(n_rth)

        print(f"  {name:<32} {r['cycles']:>5} {r['npf_1t']:>6.3f} {r['net_pnl']:>+8,} "
              f"{r['mean_daily']:>+7.1f} {r['session_win_pct']:>6.1%} "
              f"{r['seed_accuracy']:>7.1%} {elapsed:>4.0f}"
              f"  [pre:{n_pre} rth:{n_rth}]")

        if not ror and (best_ad is None or r["npf_1t"] > best_ad["npf_1t"]):
            best_ad = r
            best_ad_mode = wmode

    # Test best(A-D) + variant E
    if best_ad is not None:
        combo_name = f"Best({best_ad['label'][:1]})+E"
        print(f"\n  Testing combination: {combo_name}")
        t0 = time.time()
        sim = simulate_daily_flatten(
            prices, tod_secs, sr_vals, dts,
            seed_dist=best_sd, step_dist=STEP_DIST,
            seed_sr_thresh=best_sr, rev_sr_thresh=REV_SR_THRESH,
            watch_mode=best_ad_mode, reset_on_reversal=True,
        )
        elapsed = time.time() - t0
        r = analyze(sim, combo_name)
        if r is not None:
            r["wp_resets"] = sim["wp_resets"]
            results.append(r)
            print(f"  {combo_name:<32} {r['cycles']:>5} {r['npf_1t']:>6.3f} "
                  f"{r['net_pnl']:>+8,} {r['mean_daily']:>+7.1f} "
                  f"{r['session_win_pct']:>6.1%} {r['seed_accuracy']:>7.1%} {elapsed:>4.0f}")

    # Variant E specific reporting
    print(f"\n  Variant E details:")
    for r in results:
        if "wp_resets" in r and r.get("wp_resets", 0) > 0:
            sessions = r.get("sessions", 1)
            resets_per_session = r["wp_resets"] / sessions if sessions > 0 else 0
            print(f"    {r['label']}: {r['wp_resets']} total resets "
                  f"({resets_per_session:.1f}/session)")

    _save_result("step3_watch_price.json", results)

    # Kill condition
    if len(results) >= 2:
        npfs = [r["npf_1t"] for r in results]
        npf_range = max(npfs) - min(npfs)
        npf_mid = (max(npfs) + min(npfs)) / 2
        pct = (npf_range / npf_mid * 100) if npf_mid > 0 else 0
        print(f"\n  Watch price variation: {pct:.1f}%")
        if pct <= 6:
            print(f"  *** KILL CONDITION: All variants within ±3%. ***")
            print(f"  Watch price placement doesn't matter. Use simplest (current baseline).")
        else:
            best_wp = max(results, key=lambda x: x["npf_1t"])
            print(f"  Best variant: {best_wp['label']} (NPF={best_wp['npf_1t']:.4f})")

    return results


# ---------------------------------------------------------------------------
# Step 4: Summary and recommendation
# ---------------------------------------------------------------------------

def step4():
    """Synthesize findings and recommend optimal seed configuration."""
    print("\n" + "=" * 70)
    print("STEP 4: Summary and Recommendation")
    print("=" * 70)

    s1 = _load_result("step1_baseline.json")
    s2_seed = _load_result("step2_seed_sweep.json")
    s2_sr = _load_result("step2_sr_sweep.json")
    s3 = _load_result("step3_watch_price.json")

    # Progression table
    print(f"\n{'Config':<50} {'NPF':>6} {'NetPnL':>8} {'DailySD':>7} {'SessW%':>6}")
    print("-" * 85)
    print(f"{'Continuous (no flatten, no SR)':50} {'~1.14':>6} {'~+14,527':>8} {'N/A':>7} {'N/A':>6}")
    print(f"{'Continuous (post-hoc SR>=48)':50} {'~1.33':>6} {'~+20,045':>8} {'N/A':>7} {'N/A':>6}")

    if s1:
        if isinstance(s1, dict) and "npf_1t" in s1:
            r = s1
        else:
            r = s1
        print(f"{'Daily-flatten + SD=25, SR>=48 (baseline)':50} "
              f"{r['npf_1t']:>6.3f} {r['net_pnl']:>+8,} "
              f"{r['std_daily']:>7.1f} {r['session_win_pct']:>6.1%}")

    # Best from seed sweep
    if s2_seed:
        best_seed = max(s2_seed, key=lambda x: x["npf_1t"])
        print(f"{'Daily-flatten + best SeedDist':50} "
              f"{best_seed['npf_1t']:>6.3f} {best_seed['net_pnl']:>+8,} "
              f"{best_seed['std_daily']:>7.1f} {best_seed['session_win_pct']:>6.1%}"
              f"  [{best_seed['label']}]")

    # Best from SR sweep
    if s2_sr:
        best_sr = max(s2_sr, key=lambda x: x["npf_1t"])
        print(f"{'Daily-flatten + best SeedDist + best SeedSR':50} "
              f"{best_sr['npf_1t']:>6.3f} {best_sr['net_pnl']:>+8,} "
              f"{best_sr['std_daily']:>7.1f} {best_sr['session_win_pct']:>6.1%}"
              f"  [{best_sr['label']}]")

    # Best from watch price
    if s3:
        best_wp = max(s3, key=lambda x: x["npf_1t"])
        print(f"{'Daily-flatten + best seed + best watch price':50} "
              f"{best_wp['npf_1t']:>6.3f} {best_wp['net_pnl']:>+8,} "
              f"{best_wp['std_daily']:>7.1f} {best_wp['session_win_pct']:>6.1%}"
              f"  [{best_wp['label']}]")

    # Quantify daily-flatten cost
    if s1 and isinstance(s1, dict) and "sessions" in s1 and s1["sessions"] > 0:
        continuous_per_day = 14527 / s1["sessions"]
        flatten_cost = continuous_per_day - s1["mean_daily"]
        print(f"\n--- Daily-Flatten Cost ---")
        print(f"  Continuous avg: ~{continuous_per_day:+.1f} ticks/session "
              f"(est from {s1['sessions']} sessions)")
        print(f"  Daily-flatten avg: {s1['mean_daily']:+.1f} ticks/session")
        print(f"  Cost of daily flatten: ~{flatten_cost:.1f} ticks/session")

    # P1b recommendation
    print(f"\n--- P1b Recommendation ---")

    # Find overall best across all steps
    candidates = []
    if s1 and isinstance(s1, dict):
        candidates.append(s1)
    if s2_seed:
        candidates.extend(s2_seed)
    if s2_sr:
        candidates.extend(s2_sr)
    if s3:
        candidates.extend(s3)

    if not candidates:
        print("  No valid results to recommend.")
        return

    best_overall = max(candidates, key=lambda x: x["npf_1t"])
    baseline_npf = s1["npf_1t"] if s1 and isinstance(s1, dict) else 0

    improvement = ((best_overall["npf_1t"] - baseline_npf) / baseline_npf * 100
                   if baseline_npf > 0 else 0)

    print(f"  Best config: {best_overall['label']}")
    print(f"  NPF improvement over baseline: {improvement:+.1f}%")

    if improvement >= 5:
        print(f"\n  RECOMMENDATION: Validate on P1b with frozen params:")

        # Parse best seed_dist and seed_sr from Step 2 results
        best_seed_dist = 25.0  # default
        best_seed_sr = 48.0
        all_step2 = (s2_seed or []) + (s2_sr or [])
        if all_step2:
            best_s2 = max(all_step2, key=lambda x: x["npf_1t"])
            lbl = best_s2["label"]
            if "SD=" in lbl and "SR=" in lbl:
                parts = lbl.split("_")
                best_seed_dist = float(parts[0].split("=")[1])
                best_seed_sr = float(parts[1].split("=")[1])
            elif "SeedDist=" in lbl:
                best_seed_dist = float(lbl.split("=")[1])

        # Determine watch price mode from best overall label
        label = best_overall["label"]
        watch_desc = "current (first tick at 18:00 ET)"
        if "RTH" in label or "rth" in label or "9:30" in label:
            watch_desc = "rth_open (first tick at/after 09:30 ET)"
        elif "Prior session close" in label:
            watch_desc = "prior_close (last price before 16:00 flatten)"
        elif "Prior session midpoint" in label:
            watch_desc = "prior_midpoint ((session_high + session_low) / 2)"
        reset_e = "Reset on reversal" in label

        print(f"    - Seed distance: {best_seed_dist:.0f}")
        print(f"    - Seed SpeedRead threshold: {best_seed_sr:.0f}")
        print(f"    - Watch price mode: {watch_desc}")
        print(f"    - Reset on reversal through watch price: {reset_e}")
        print(f"    - Rotation StepDist: 25 (FROZEN)")
        print(f"    - flatten_reseed_cap: 2 (FROZEN)")
        print(f"    - max_levels: 1 (FROZEN)")
        print(f"    - max_contract_size: 8 (FROZEN)")
        print(f"    - anchor_mode: walking (FROZEN)")
        print(f"    - SpeedRead reversal threshold: 48 (FROZEN)")
        print(f"    - cost_ticks: 1")
        print(f"    - Daily flatten: 16:00 ET")
        print(f"    - Session resume: 09:30 ET (RTH open)" if "rth" in watch_desc
              else f"    - Session resume: 18:00 ET")
        print(f"\n  *** DO NOT RUN P1b. Recommendation only. ***")
    else:
        print(f"\n  Improvement < 5% ({improvement:+.1f}%). Current config is adequate.")
        print(f"  No P1b validation needed for seed optimization.")


# ---------------------------------------------------------------------------
# File I/O helpers
# ---------------------------------------------------------------------------

def _save_result(filename, data):
    """Save result to JSON in output directory."""
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = _OUTPUT_DIR / filename
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)
    print(f"  Saved: {path}")


def _load_result(filename):
    """Load result from JSON. Returns None if not found."""
    path = _OUTPUT_DIR / filename
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Seed optimization investigation")
    parser.add_argument("--step", required=True,
                        help="Step to run: 1, 2, 3, 4, or all")
    args = parser.parse_args()

    step = args.step.lower()

    if step in ("1", "2", "3", "all"):
        data = load_data()

    if step == "1":
        step1(*data)
    elif step == "2":
        step2(*data)
    elif step == "3":
        step3(*data)
    elif step == "4":
        step4()
    elif step == "all":
        # Sequential execution with kill conditions
        r1 = step1(*data)
        if r1 is False:
            print("\nKILL: Step 1 failed. Investigation complete.")
            step4()
            return

        r2 = step2(*data)
        if r2 and r2.get("kill"):
            print("\nKILL: Step 2 shows no meaningful variation. Skipping Step 3.")
            step4()
            return

        step3(*data)
        step4()
    else:
        print(f"Unknown step: {args.step}. Use 1, 2, 3, 4, or all.")
        sys.exit(1)


if __name__ == "__main__":
    main()
