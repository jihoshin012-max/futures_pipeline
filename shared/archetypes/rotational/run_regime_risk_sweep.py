# archetype: rotational
# STATUS: ONE-TIME
# PURPOSE: Regime-adaptive risk sweep using ZZ regime
# LAST RUN: 2026-03

"""Regime-Adaptive Risk Sweep — ZZ regime for dynamic risk mitigation.

Tests variations of using the rolling zigzag regime to adjust risk parameters
when the position is against you, instead of fixed thresholds.

Hypotheses tested:
  H1: Regime-scaled 4C — max_cap_walks varies with P90/P50 ratio (volatility expansion)
  H2: Regime-scaled adverse stop — flatten when MAE > N * current_P90 (instead of N * std)
  H3: ZZ-P50 scaled adverse stop — tighter stop when median swing is small (compressed regime)
  H4: Conditional cap reduction — drop position_cap to 1 when P90/P50 > threshold (fat tails)
  H5: Regime gate on adds — skip add if current P90 > entry P90 * factor (regime shifted against you)

All tests on P1 data with the final V1.4 config as baseline.

Usage:
    python run_regime_risk_sweep.py
"""

import sys
import json
import time
import copy
import datetime as dt_mod
from pathlib import Path

import numpy as np
import pandas as pd

_REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from shared.data_loader import load_bars
from run_seed_investigation import (
    simulate_daily_flatten, load_data, _finalize_cycle,
    COST_TICKS, TICK_SIZE, RTH_OPEN_TOD, FLATTEN_TOD, RESUME_TOD,
    _P1_START, _P1_END, FLATTEN_CAP, MAX_LEVELS, INIT_QTY,
    _IDLE, _PRE_RTH, _WATCHING, _LONG, _SHORT, MAX_CS, REV_SR_THRESH,
)
from run_phase1_sweep import (
    build_zigzag_lookup, make_adaptive_lookup, make_std_lookup, analyze_step2,
)
from run_p2a_validation import SEED_DIST, SEED_START, SR_THRESHOLD, EXCLUDE_HOURS

_OUTPUT_DIR = Path(__file__).parent / "phase1_results"

MAX_CAP_WALKS_BASELINE = 2


# ---------------------------------------------------------------------------
# Extended simulator: adds regime-aware risk parameters
# ---------------------------------------------------------------------------

def simulate_regime_risk(prices, tod_secs, sr_vals, dts,
                         adaptive_lookup, std_lookup,
                         # Regime risk params
                         adverse_p90_mult=None,      # H2: flatten when MAE > mult * current_P90
                         adverse_p50_mult=None,      # H3: flatten when MAE > mult * current_P50
                         regime_cap_walks=None,       # H1: dict mapping P90/P50 ratio bands to max_cw
                         cap_reduction_ratio=None,    # H4: reduce cap to 1 when P90/P50 > ratio
                         add_regime_gate=None,        # H5: skip add if current_P90 > entry_P90 * factor
                         # Standard params
                         max_cap_walks=MAX_CAP_WALKS_BASELINE,
                         max_adverse_sigma=None,
                         ):
    """Extended simulator with regime-aware risk controls.

    Wraps simulate_daily_flatten but adds custom risk checks via a
    tick-level loop that reads ZZ percentiles from the adaptive lookup.
    """
    # For H2/H3/H4/H5 we need per-tick access to ZZ percentiles.
    # The adaptive lookup has timestamps + sd_values (P90) + ad_values (P75).
    # We also need P50 — build it from the zigzag lookup.
    # For simplicity, we'll run the standard sim for baseline scenarios
    # and a custom loop for regime-aware ones.

    needs_custom = any([adverse_p90_mult, adverse_p50_mult,
                        regime_cap_walks, cap_reduction_ratio, add_regime_gate])

    if not needs_custom:
        # Standard simulation
        return simulate_daily_flatten(
            prices, tod_secs, sr_vals, dts,
            seed_dist=SEED_DIST, step_dist=25.0, add_dist=25.0,
            flatten_reseed_cap=FLATTEN_CAP, max_levels=MAX_LEVELS,
            seed_sr_thresh=SR_THRESHOLD, rev_sr_thresh=SR_THRESHOLD,
            watch_mode='rth_open', cap_action='walk',
            seed_start_tod=SEED_START,
            adaptive_lookup=adaptive_lookup,
            max_adverse_sigma=max_adverse_sigma,
            max_cap_walks=max_cap_walks,
            std_lookup=std_lookup,
        )

    # --- Custom loop with regime-aware risk ---
    # This is a modified copy of simulate_daily_flatten with added checks.

    seed_dist = SEED_DIST
    step_dist = 25.0
    add_dist = 25.0
    flatten_reseed_cap = FLATTEN_CAP
    max_levels = MAX_LEVELS
    cost_ticks = COST_TICKS
    tick_size = TICK_SIZE
    seed_sr_thresh = SR_THRESHOLD
    rev_sr_thresh = SR_THRESHOLD
    cap_action = 'walk'
    seed_start_tod = SEED_START

    n = len(prices)
    current_sd = step_dist
    current_ad = add_dist
    current_seed = seed_dist

    _adapt_ts = adaptive_lookup['timestamps']
    _adapt_sd = adaptive_lookup['sd_values']  # P90
    _adapt_ad = adaptive_lookup['ad_values']  # P75
    _std_ts = std_lookup['timestamps']
    _std_vals = std_lookup['std_values']

    # Build P50 lookup from the same zigzag data
    # We'll derive it from adaptive: P50 ≈ P75 * 0.75 / 0.667 ... no, need real data.
    # Actually the adaptive lookup only has P90 and P75. For P50 we need to build it.
    # Let's use the std: P50 ≈ P90 - 1.28 * std (normal approx) — rough but workable.
    # Better: use P75 as the "moderate" reference and P90 as "extreme".
    # For H1/H4: P90/P75 ratio is actually more stable to compute than P90/P50.
    # Let's use P90/P75 as the regime ratio instead.

    current_std = 0.0
    stops_4a = 0
    stops_4c = 0
    stops_regime = 0

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

    cycle_entry_price = 0.0
    cycle_mfe = 0.0
    cycle_mae = 0.0
    cycle_cap_walks = 0
    cycle_entry_p90 = 0.0  # P90 at cycle entry (for H5)

    prior_close = 0.0
    prior_high = 0.0
    prior_low = 1e9
    session_high = 0.0
    session_low = 1e9
    prev_side = 0
    wp_resets = 0

    trade_records = []
    cycle_records = []
    cycle_trades = []

    def _read_adaptive(tick_idx):
        """Read current P90, P75 from adaptive lookup."""
        ts_val = dts[tick_idx].astype('int64')
        aidx = np.searchsorted(_adapt_ts, ts_val, side='right') - 1
        if aidx >= 0:
            p90 = max(float(_adapt_sd[aidx]), 10.0)
            p75 = max(float(_adapt_ad[aidx]), 10.0)
        else:
            p90 = step_dist
            p75 = add_dist
        return p90, p75

    def _read_std(tick_idx):
        ts_val = dts[tick_idx].astype('int64')
        sidx = np.searchsorted(_std_ts, ts_val, side='right') - 1
        if sidx >= 0:
            return float(_std_vals[sidx])
        return 0.0

    def _get_effective_max_cw(p90, p75):
        """H1: regime-scaled cap-walks."""
        if regime_cap_walks is None:
            return max_cap_walks
        ratio = p90 / p75 if p75 > 0 else 1.0
        # regime_cap_walks is list of (ratio_threshold, max_cw) sorted ascending
        for thresh, mcw in regime_cap_walks:
            if ratio <= thresh:
                return mcw
        return regime_cap_walks[-1][1]  # highest band

    def _get_effective_cap(p90, p75):
        """H4: reduce position cap when tails are fat."""
        if cap_reduction_ratio is None:
            return flatten_reseed_cap
        ratio = p90 / p75 if p75 > 0 else 1.0
        if ratio > cap_reduction_ratio:
            return 1  # single contract only
        return flatten_reseed_cap

    def _flatten_and_record(i, price, reason):
        nonlocal state, watch_price, position_qty, cycle_trades, prev_side
        nonlocal stops_regime, stops_4c, stops_4a
        nonlocal cycle_mfe, cycle_mae, cycle_cap_walks

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
        cr["exit_reason"] = reason
        cr["session_id"] = session_id
        cr["mfe"] = round(cycle_mfe, 4)
        cr["mae"] = round(cycle_mae, 4)
        cr["cycle_cap_walks"] = cycle_cap_walks
        cr["stepdist_used"] = round(current_sd, 4)
        cr["adddist_used"] = round(current_ad, 4)
        cycle_records.append(cr)

        if 'regime' in reason:
            stops_regime += 1
        elif '4c' in reason:
            stops_4c += 1
        elif '4a' in reason:
            stops_4a += 1

        state = _WATCHING
        watch_price = price
        position_qty = 0
        cycle_trades = []
        prev_side = 0

    for i in range(n):
        price = prices[i]
        tod = tod_secs[i]
        sr = sr_vals[i]

        # --- DEAD ZONE ---
        effective_flatten = FLATTEN_TOD
        if effective_flatten <= tod < RESUME_TOD:
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
                cr["mfe"] = round(cycle_mfe, 4)
                cr["mae"] = round(cycle_mae, 4)
                cr["cycle_cap_walks"] = cycle_cap_walks
                cr["stepdist_used"] = round(current_sd, 4)
                cr["adddist_used"] = round(current_ad, 4)
                cycle_records.append(cr)
                cycle_trades = []
                position_qty = 0

            if state != _IDLE:
                prior_close = price
                state = _IDLE
            continue

        # --- SESSION START ---
        if state == _IDLE:
            if tod >= RESUME_TOD or (tod < effective_flatten):
                session_id += 1
                session_high = 0.0
                session_low = 1e9
                state = _WATCHING
                # rth_open watch mode
                if seed_start_tod is not None:
                    if tod < seed_start_tod:
                        state = _PRE_RTH
                        continue
                watch_price = price
                prev_side = 0
            continue

        # --- PRE-RTH ---
        if state == _PRE_RTH:
            if tod >= seed_start_tod and tod < effective_flatten:
                state = _WATCHING
                watch_price = price
                prev_side = 0
            continue

        # --- WATCHING: SEED detection ---
        if state == _WATCHING:
            if watch_price == 0.0:
                watch_price = price
                continue

            dist = price - watch_price
            if abs(dist) >= current_seed:
                if sr < seed_sr_thresh:
                    continue

                # Read adaptive params
                p90, p75 = _read_adaptive(i)
                current_sd = p90
                current_ad = min(p75, p90)
                current_seed = current_sd
                current_std = _read_std(i)

                seed_dir = _LONG if dist > 0 else _SHORT
                direction = "Long" if seed_dir == _LONG else "Short"
                cycle_id += 1
                cycle_start = i
                cycle_mfe = 0.0
                cycle_mae = 0.0
                cycle_cap_walks = 0
                cycle_entry_price = price
                cycle_entry_p90 = p90

                state = seed_dir
                anchor = price
                level = 0
                position_qty = INIT_QTY
                avg_entry = price
                watch_price = 0.0

                t = {"bar_idx": i, "datetime": dts[i], "action": "SEED",
                     "direction": direction, "qty": INIT_QTY, "price": price,
                     "level": 0, "anchor": price,
                     "cost_ticks": cost_ticks * INIT_QTY,
                     "cycle_id": cycle_id, "session_id": session_id,
                     "price_source": "tick"}
                trade_records.append(t)
                cycle_trades = [t]
            continue

        # --- POSITIONED ---
        excursion = (price - cycle_entry_price) if state == _LONG else (cycle_entry_price - price)
        if excursion > cycle_mfe:
            cycle_mfe = excursion
        if -excursion > cycle_mae:
            cycle_mae = -excursion

        # Read current regime
        cur_p90, cur_p75 = _read_adaptive(i)

        # --- H2: Regime-scaled adverse stop (P90-based) ---
        if adverse_p90_mult is not None:
            adverse_from_entry = max(0.0, -excursion)
            if adverse_from_entry > adverse_p90_mult * cur_p90:
                _flatten_and_record(i, price, "stop_regime_p90")
                continue

        # --- H3: Regime-scaled adverse stop (P75-based, proxy for P50) ---
        if adverse_p50_mult is not None:
            adverse_from_entry = max(0.0, -excursion)
            if adverse_from_entry > adverse_p50_mult * cur_p75:
                _flatten_and_record(i, price, "stop_regime_p75")
                continue

        # --- Standard 4A stop ---
        if max_adverse_sigma is not None and current_std > 0:
            adverse_from_entry = max(0.0, -excursion)
            if adverse_from_entry > max_adverse_sigma * current_std:
                _flatten_and_record(i, price, "stop_4a")
                continue

        distance = price - anchor
        if state == _LONG:
            in_favor = distance >= current_sd
            adverse = -distance
        else:
            in_favor = (-distance) >= current_sd
            adverse = distance

        add_triggered = adverse >= current_ad
        capwalk_triggered = adverse >= current_sd

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

            if sr >= rev_sr_thresh:
                cr["exit_reason"] = "reversal"
                cr["mfe"] = round(cycle_mfe, 4)
                cr["mae"] = round(cycle_mae, 4)
                cr["cycle_cap_walks"] = cycle_cap_walks
                cr["stepdist_used"] = round(current_sd, 4)
                cr["adddist_used"] = round(current_ad, 4)
                cycle_records.append(cr)

                # Read fresh adaptive for new cycle
                p90, p75 = _read_adaptive(i)
                current_sd = p90
                current_ad = min(p75, p90)
                current_seed = current_sd
                current_std = _read_std(i)

                new_state = _SHORT if state == _LONG else _LONG
                new_dir = "Short" if state == _LONG else "Long"
                cycle_id += 1
                cycle_start = i
                cycle_mfe = 0.0
                cycle_mae = 0.0
                cycle_cap_walks = 0
                cycle_entry_price = price
                cycle_entry_p90 = p90
                state = new_state
                anchor = price
                level = 0
                position_qty = INIT_QTY
                avg_entry = price

                t = {"bar_idx": i, "datetime": dts[i], "action": "REVERSAL",
                     "direction": new_dir, "qty": INIT_QTY, "price": price,
                     "level": 0, "anchor": price,
                     "cost_ticks": cost_ticks * INIT_QTY,
                     "cycle_id": cycle_id, "session_id": session_id,
                     "price_source": "tick"}
                trade_records.append(t)
                cycle_trades = [t]
            else:
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
            eff_cap = _get_effective_cap(cur_p90, cur_p75)
            at_cap = eff_cap > 0 and position_qty >= eff_cap

            if at_cap and capwalk_triggered:
                # Cap-walk
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

                # H1: regime-adaptive max cap-walks
                eff_max_cw = _get_effective_max_cw(cur_p90, cur_p75)
                if eff_max_cw is not None and cycle_cap_walks > eff_max_cw:
                    _flatten_and_record(i, price, "stop_4c_regime")
                    continue

                # Standard 4C
                if max_cap_walks is not None and cycle_cap_walks > max_cap_walks:
                    _flatten_and_record(i, price, "stop_4c")
                    continue

            elif not at_cap and add_triggered:
                # H5: skip add if regime shifted against you
                if add_regime_gate is not None and cycle_entry_p90 > 0:
                    if cur_p90 > cycle_entry_p90 * add_regime_gate:
                        # Regime expanded — skip this add, just walk anchor
                        anchor = price
                        continue

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

    # Finalize open cycle
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
        "stops_regime": stops_regime,
    }


# ---------------------------------------------------------------------------
# Analysis helper
# ---------------------------------------------------------------------------

def analyze_sim(sim, label):
    """Compute key metrics from simulation output."""
    trades = pd.DataFrame(sim['trade_records'])
    cycles = pd.DataFrame(sim['cycle_records'])
    if len(cycles) == 0:
        return None

    entry_trades = trades[trades['action'].isin(['SEED', 'REVERSAL'])]
    ce = entry_trades.groupby('cycle_id')['datetime'].first().reset_index()
    ce.columns = ['cycle_id', 'entry_dt']
    cycles = cycles.merge(ce, on='cycle_id', how='left')
    cycles['hour'] = pd.to_datetime(cycles['entry_dt']).dt.hour
    cf = cycles[~cycles['hour'].isin(EXCLUDE_HOURS)].copy()
    if len(cf) == 0:
        return None

    valid_ids = set(cf['cycle_id'])
    tf = trades[trades['cycle_id'].isin(valid_ids)]
    cc = tf.groupby('cycle_id')['cost_ticks'].sum()
    cf['cost'] = cf['cycle_id'].map(cc).fillna(0)
    cf['net_1t'] = cf['gross_pnl_ticks'] - cf['cost']

    session_pnl = cf.groupby('session_id')['net_1t'].sum()
    all_sids = range(1, sim['total_sessions'] + 1)
    spnl = session_pnl.reindex(all_sids, fill_value=0.0)

    pnl = spnl.values
    gross_w = cf.loc[cf['gross_pnl_ticks'] > 0, 'gross_pnl_ticks'].sum()
    gross_l = abs(cf.loc[cf['gross_pnl_ticks'] <= 0, 'gross_pnl_ticks'].sum())
    gpf = gross_w / gross_l if gross_l > 0 else 0

    net_w = cf.loc[cf['net_1t'] > 0, 'net_1t'].sum()
    net_l = abs(cf.loc[cf['net_1t'] <= 0, 'net_1t'].sum())
    npf = net_w / net_l if net_l > 0 else 0

    cum = np.cumsum(pnl)
    running_max = np.maximum.accumulate(cum)
    dd = cum - running_max
    max_dd = float(dd.min())

    stopped_4c = len(cf[cf['exit_reason'].str.contains('4c', na=False)])
    stopped_regime = len(cf[cf['exit_reason'].str.contains('regime', na=False)])

    return {
        'label': label,
        'cycles': len(cf),
        'sessions': len(spnl),
        'gpf': round(gpf, 4),
        'npf': round(npf, 4),
        'net_pnl': round(float(pnl.sum()), 1),
        'mean_daily': round(float(pnl.mean()), 1),
        'std_daily': round(float(pnl.std()), 1),
        'sharpe': round(float(pnl.mean() / pnl.std()), 4) if pnl.std() > 0 else 0,
        'session_win_pct': round(float((pnl > 0).mean()), 4),
        'worst_day': round(float(pnl.min()), 1),
        'max_dd': round(max_dd, 1),
        'max_cycle_loss': round(float(cf['net_1t'].min()), 1),
        'stopped_4c': stopped_4c,
        'stopped_regime': stopped_regime,
        'cap_walks': sim.get('cap_walks', 0),
        'clean_pct': round(float((cf['adds_count'] == 0).mean()), 4) if 'adds_count' in cf.columns else 0,
    }


# ---------------------------------------------------------------------------
# Main sweep
# ---------------------------------------------------------------------------

def main():
    t0 = time.time()
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("REGIME-ADAPTIVE RISK SWEEP — P1 Data")
    print("  V1.4 baseline + ZZ regime variations for risk mitigation")
    print("=" * 70)

    # Load data
    print("\nLoading P1 data...")
    prices, tod_secs, sr_raw, dts = load_data(period='full_p1', use_speedread=True)
    zz = build_zigzag_lookup()
    adaptive = make_adaptive_lookup(zz, 5, 2)
    std_lu = make_std_lookup(zz)

    w = 50
    cs = np.cumsum(np.insert(sr_raw, 0, 0))
    sr_roll50 = np.empty_like(sr_raw)
    sr_roll50[:w] = cs[1:w + 1] / np.arange(1, w + 1)
    sr_roll50[w:] = (cs[w + 1:] - cs[1:len(sr_raw) - w + 1]) / w

    results = []

    # ================================================================
    # BASELINE: V1.4 + 4C=2 (current final config)
    # ================================================================
    print("\n[0] BASELINE: V1.4 + 4C=2...")
    sim = simulate_regime_risk(
        prices, tod_secs, sr_roll50, dts, adaptive, std_lu,
        max_cap_walks=2,
    )
    r = analyze_sim(sim, "BASELINE (4C=2)")
    results.append(r)
    print(f"    NPF={r['npf']:.4f}  PnL={r['net_pnl']:+,.0f}  "
          f"MaxDD={r['max_dd']:,.0f}  Worst={r['worst_day']:,.0f}  "
          f"Stopped={r['stopped_4c']}")

    # Also run no-stops baseline
    print("\n[0b] BASELINE: No stops...")
    sim = simulate_regime_risk(
        prices, tod_secs, sr_roll50, dts, adaptive, std_lu,
        max_cap_walks=None,
    )
    r = analyze_sim(sim, "NO_STOPS")
    results.append(r)
    print(f"    NPF={r['npf']:.4f}  PnL={r['net_pnl']:+,.0f}  "
          f"MaxDD={r['max_dd']:,.0f}  Worst={r['worst_day']:,.0f}")

    # ================================================================
    # H1: Regime-scaled max cap-walks (P90/P75 ratio bands)
    # ================================================================
    print("\n--- H1: Regime-Scaled Cap-Walks (P90/P75 ratio) ---")
    h1_configs = [
        # (label, regime_cap_walks_bands, fallback_max_cw)
        ("H1a: tight=1, normal=2, wide=3",
         [(1.25, 1), (1.5, 2), (999, 3)], None),
        ("H1b: tight=1, normal=2",
         [(1.3, 1), (999, 2)], None),
        ("H1c: tight=1, normal=3",
         [(1.25, 1), (999, 3)], None),
        ("H1d: compressed=0(flat), normal=2, wide=3",
         [(1.15, 0), (1.4, 2), (999, 3)], None),
    ]
    for label, bands, fallback in h1_configs:
        print(f"  [{label}]...")
        sim = simulate_regime_risk(
            prices, tod_secs, sr_roll50, dts, adaptive, std_lu,
            regime_cap_walks=bands,
            max_cap_walks=None,  # H1 overrides
        )
        r = analyze_sim(sim, label)
        results.append(r)
        print(f"    NPF={r['npf']:.4f}  PnL={r['net_pnl']:+,.0f}  "
              f"MaxDD={r['max_dd']:,.0f}  Worst={r['worst_day']:,.0f}  "
              f"Stopped4C={r['stopped_4c']}  StoppedRegime={r['stopped_regime']}")

    # ================================================================
    # H2: Adverse stop scaled by current P90
    # ================================================================
    print("\n--- H2: Adverse Stop = N * P90 ---")
    for mult in [1.5, 2.0, 2.5, 3.0, 3.5]:
        label = f"H2: MAE > {mult}*P90"
        print(f"  [{label}]...")
        sim = simulate_regime_risk(
            prices, tod_secs, sr_roll50, dts, adaptive, std_lu,
            adverse_p90_mult=mult,
            max_cap_walks=2,  # Keep 4C as safety net
        )
        r = analyze_sim(sim, label)
        results.append(r)
        print(f"    NPF={r['npf']:.4f}  PnL={r['net_pnl']:+,.0f}  "
              f"MaxDD={r['max_dd']:,.0f}  Worst={r['worst_day']:,.0f}  "
              f"Stopped4C={r['stopped_4c']}  StoppedRegime={r['stopped_regime']}")

    # ================================================================
    # H3: Adverse stop scaled by current P75 (proxy for moderate swing)
    # ================================================================
    print("\n--- H3: Adverse Stop = N * P75 ---")
    for mult in [2.0, 2.5, 3.0, 3.5, 4.0]:
        label = f"H3: MAE > {mult}*P75"
        print(f"  [{label}]...")
        sim = simulate_regime_risk(
            prices, tod_secs, sr_roll50, dts, adaptive, std_lu,
            adverse_p50_mult=mult,
            max_cap_walks=2,
        )
        r = analyze_sim(sim, label)
        results.append(r)
        print(f"    NPF={r['npf']:.4f}  PnL={r['net_pnl']:+,.0f}  "
              f"MaxDD={r['max_dd']:,.0f}  Worst={r['worst_day']:,.0f}  "
              f"Stopped4C={r['stopped_4c']}  StoppedRegime={r['stopped_regime']}")

    # ================================================================
    # H4: Conditional cap reduction when tails are fat
    # ================================================================
    print("\n--- H4: Cap=1 when P90/P75 > threshold ---")
    for ratio in [1.2, 1.3, 1.4, 1.5]:
        label = f"H4: cap=1 when P90/P75>{ratio}"
        print(f"  [{label}]...")
        sim = simulate_regime_risk(
            prices, tod_secs, sr_roll50, dts, adaptive, std_lu,
            cap_reduction_ratio=ratio,
            max_cap_walks=2,
        )
        r = analyze_sim(sim, label)
        results.append(r)
        print(f"    NPF={r['npf']:.4f}  PnL={r['net_pnl']:+,.0f}  "
              f"MaxDD={r['max_dd']:,.0f}  Worst={r['worst_day']:,.0f}  "
              f"Stopped4C={r['stopped_4c']}  StoppedRegime={r['stopped_regime']}")

    # ================================================================
    # H5: Skip add if regime expanded against you
    # ================================================================
    print("\n--- H5: Skip add if P90 > entry_P90 * factor ---")
    for factor in [1.1, 1.2, 1.3, 1.5]:
        label = f"H5: skip add if P90>{factor}x entry"
        print(f"  [{label}]...")
        sim = simulate_regime_risk(
            prices, tod_secs, sr_roll50, dts, adaptive, std_lu,
            add_regime_gate=factor,
            max_cap_walks=2,
        )
        r = analyze_sim(sim, label)
        results.append(r)
        print(f"    NPF={r['npf']:.4f}  PnL={r['net_pnl']:+,.0f}  "
              f"MaxDD={r['max_dd']:,.0f}  Worst={r['worst_day']:,.0f}  "
              f"Stopped4C={r['stopped_4c']}  StoppedRegime={r['stopped_regime']}")

    # ================================================================
    # Summary
    # ================================================================
    print(f"\n{'=' * 100}")
    print(f"SWEEP RESULTS SUMMARY")
    print(f"{'=' * 100}")
    print(f"{'Label':<45} {'NPF':>7} {'PnL':>9} {'MaxDD':>8} {'Worst':>8} "
          f"{'Win%':>6} {'Sharpe':>7} {'St4C':>5} {'StReg':>5}")
    print(f"{'-' * 100}")

    baseline = results[0]
    for r in results:
        npf_delta = r['npf'] - baseline['npf']
        dd_delta = r['max_dd'] - baseline['max_dd']
        marker = ""
        if r['npf'] > baseline['npf'] and r['max_dd'] > baseline['max_dd']:
            marker = " ** BETTER NPF + DD"
        elif r['npf'] > baseline['npf']:
            marker = " * better NPF"
        elif r['max_dd'] > baseline['max_dd']:
            marker = " * better DD"

        print(f"{r['label']:<45} {r['npf']:>7.4f} {r['net_pnl']:>+9,.0f} "
              f"{r['max_dd']:>8,.0f} {r['worst_day']:>8,.0f} "
              f"{r['session_win_pct']:>6.1%} {r['sharpe']:>7.3f} "
              f"{r['stopped_4c']:>5} {r['stopped_regime']:>5}{marker}")

    # Save
    with open(_OUTPUT_DIR / "regime_risk_sweep.json", 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nSaved to {_OUTPUT_DIR / 'regime_risk_sweep.json'}")
    print(f"Total time: {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
