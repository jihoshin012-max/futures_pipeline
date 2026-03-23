# archetype: zone_touch
"""
Throughput Optimization Analysis — Part 2 of 2.

Sections 8-12: adverse excursion exits, signal clustering,
dynamic T2 exit on new signal, hybrid strategies, combined summary.

Prerequisite: throughput_analysis_part1.md + Part 1 answer keys.

Usage:
    python throughput_analysis_part2.py
"""
import csv, json, sys, math, os
from collections import Counter, defaultdict
from datetime import datetime

# =========================================================================
#  Constants (same as Part 1)
# =========================================================================

TICK_SIZE = 0.25
COST_TICKS = 3.0
SCORE_THRESHOLD = 16.66
TF_MAX_MINUTES = 120
WTNT_SEQ_MAX = 5
LEG1_W, LEG2_W = 0.67, 0.33

KS_CONSEC = 3
KS_DAILY = -600.0
KS_WEEKLY = -1200.0

CT_LIMIT_TICKS = 5
CT_LIMIT_WINDOW = 20

BASE = 'C:/Projects/pipeline/stages'

TF_MINUTES = {'15m': 15, '30m': 30, '60m': 60, '90m': 90, '120m': 120,
              '240m': 240, '360m': 360, '480m': 480, '720m': 720}

with open(f'{BASE}/04-backtest/zone_touch/output/feature_config.json') as f:
    FCFG = json.load(f)
TREND_P33 = FCFG['trend_slope_p33']
TREND_P67 = FCFG['trend_slope_p67']

with open(f'{BASE}/04-backtest/zone_touch/output/scoring_model_acal.json') as f:
    MODEL = json.load(f)
WEIGHTS = MODEL['weights']
BIN_EDGES = MODEL['bin_edges']

# =========================================================================
#  Data loading (same as Part 1)
# =========================================================================

def load_bar_data(path):
    bars = []
    with open(path) as f:
        for row in csv.DictReader(f):
            r = {k.strip(): v.strip() for k, v in row.items()}
            o, h, l, c = float(r['Open']), float(r['High']), float(r['Low']), float(r['Last'])
            dt = r['Date'].split('.')[0] + ' ' + r['Time'].split('.')[0]
            bars.append((o, h, l, c, dt))
    return bars

def classify_trend(slope):
    if slope <= TREND_P33: return 'CT'
    if slope >= TREND_P67: return 'WT'
    return 'NT'

# P2 scoring
def bin_numeric(val, p33, p67, weight, is_nan=False):
    if is_nan: return 0.0
    if val <= p33: return weight
    if val >= p67: return 0.0
    return weight / 2.0

def score_f04(cascade, weight):
    if cascade == 'NO_PRIOR': return weight
    if cascade == 'PRIOR_HELD': return weight / 2.0
    return 0.0

def score_f01(tf_str, weight):
    if tf_str == '30m': return weight
    if tf_str == '480m': return 0.0
    if tf_str: return weight / 2.0
    return 0.0

print("Loading data...", file=sys.stderr)
P1_BARS = load_bar_data(f'{BASE}/01-data/output/zone_prep/NQ_bardata_P1.csv')
N_P1 = len(P1_BARS)
P2_BARS = load_bar_data(f'{BASE}/01-data/output/zone_prep/NQ_bardata_P2.csv')
N_P2 = len(P2_BARS)

def load_p1_touches():
    touches = []
    with open(f'{BASE}/04-backtest/zone_touch/output/p1_scored_touches_acal.csv') as f:
        for row in csv.DictReader(f): touches.append(row)
    return touches

def load_p2_touches():
    touches = []
    for fname in ['NQ_merged_P2a.csv', 'NQ_merged_P2b.csv']:
        with open(f'{BASE}/01-data/output/zone_prep/{fname}') as f:
            for row in csv.DictReader(f):
                if int(row['RotBarIndex']) >= 0: touches.append(row)
    touches.sort(key=lambda r: int(r['RotBarIndex']))
    return touches

P1_RAW = load_p1_touches()
P2_RAW = load_p2_touches()

# P2 zone history for scoring
p2_zone_history = {}
for t in P2_RAW:
    key = (t['ZoneTop'], t['ZoneBot'], t.get('SourceLabel', ''))
    p2_zone_history.setdefault(key, []).append(t)

def get_prior_pen_p2(touch):
    seq = int(touch['TouchSequence'])
    if seq <= 1: return None
    key = (touch['ZoneTop'], touch['ZoneBot'], touch.get('SourceLabel', ''))
    history = p2_zone_history.get(key, [])
    rbi = int(touch['RotBarIndex'])
    for prev in reversed(history):
        if int(prev['RotBarIndex']) >= rbi: continue
        if int(prev['TouchSequence']) == seq - 1:
            pen = prev.get('Penetration', '').strip()
            return float(pen) if pen else None
    return None

def score_p2_touch(touch):
    prior_pen = get_prior_pen_p2(touch)
    f10 = bin_numeric(0.0 if prior_pen is None else prior_pen,
                      BIN_EDGES['F10_PriorPenetration'][0],
                      BIN_EDGES['F10_PriorPenetration'][1],
                      WEIGHTS['F10_PriorPenetration'], prior_pen is None)
    f04 = score_f04(touch.get('CascadeState', '').strip(), WEIGHTS['F04_CascadeState'])
    f01 = score_f01(touch.get('SourceLabel', '').strip(), WEIGHTS['F01_Timeframe'])
    f21_str = touch.get('ZoneAgeBars', '').strip()
    f21 = bin_numeric(float(f21_str) if f21_str else 0.0,
                      BIN_EDGES['F21_ZoneAge'][0], BIN_EDGES['F21_ZoneAge'][1],
                      WEIGHTS['F21_ZoneAge'])
    return f10 + f04 + f01 + f21

# =========================================================================
#  Qualify touches
# =========================================================================

def qualify_touch(t, n_bars, score_fn=None):
    """Attach parsed fields to a qualifying touch. Returns True if qualifies."""
    tf = TF_MINUTES.get(t.get('SourceLabel', '').strip(), 999)
    if tf > TF_MAX_MINUTES: return False
    rbi_str = t.get('RotBarIndex', '').strip()
    if not rbi_str: return False
    rbi = int(rbi_str)
    if rbi < 0 or rbi + 1 >= n_bars: return False
    if score_fn:
        score = score_fn(t)
    else:
        score = float(t['score_acal'])
    if score < SCORE_THRESHOLD: return False
    t['_rbi'] = rbi
    t['_score'] = score
    ts_str = t.get('TrendSlope', '').strip()
    if not ts_str:
        tl = t.get('TrendLabel', 'NT').strip()
        t['_trend'] = tl if tl else 'NT'
        t['_trend_slope'] = 0.0
    else:
        t['_trend_slope'] = float(ts_str)
        t['_trend'] = classify_trend(float(ts_str))
    t['_direction'] = 1 if t['TouchType'].strip() == 'DEMAND_EDGE' else -1
    zw_str = t.get('ZoneWidthTicks', '').strip()
    t['_zw'] = float(zw_str) if zw_str else (float(t['ZoneTop']) - float(t['ZoneBot'])) / TICK_SIZE
    t['_seq'] = int(t['TouchSequence'])
    t['_zone_top'] = float(t['ZoneTop'])
    t['_zone_bot'] = float(t['ZoneBot'])
    t['_tf'] = t.get('SourceLabel', '').strip()
    t['_zone_key'] = (t['_zone_top'], t['_zone_bot'])
    return True

P1_QUAL = [t for t in P1_RAW if qualify_touch(t, N_P1)]
P1_QUAL.sort(key=lambda r: r['_rbi'])
P2_QUAL = [t for t in P2_RAW if qualify_touch(t, N_P2, score_fn=score_p2_touch)]
P2_QUAL.sort(key=lambda r: r['_rbi'])
print(f"  P1 qual: {len(P1_QUAL)}, P2 qual: {len(P2_QUAL)}", file=sys.stderr)

# =========================================================================
#  CT limit fill scanner
# =========================================================================

def scan_ct_limit_fill(bar_data, touch_bar, direction, zone_top, zone_bot, n_bars):
    if direction == 1:
        limit_px = zone_top - CT_LIMIT_TICKS * TICK_SIZE
    else:
        limit_px = zone_bot + CT_LIMIT_TICKS * TICK_SIZE
    for offset in range(1, CT_LIMIT_WINDOW + 1):
        idx = touch_bar + offset
        if idx >= n_bars: break
        o, h, l, c, dt = bar_data[idx]
        if direction == 1:
            if l <= limit_px: return (idx, min(o, limit_px), offset)
        else:
            if h >= limit_px: return (idx, max(o, limit_px), offset)
    return None

# =========================================================================
#  Generic 2-leg simulator (same as Part 1, with AE exit support)
# =========================================================================

def sim_2leg(bar_data, entry_bar, ep, direction, t1_ticks, t2_ticks, stop_ticks,
             tcap, n_bars, single_leg=False, be_trigger_ticks=None,
             t2_stop_after_t1=None, ae_threshold=None, ae_min_bars=None):
    """
    ae_threshold: adverse excursion in ticks at which to exit (if ae_min_bars also met)
    ae_min_bars: minimum bars before AE exit can trigger
    """
    if entry_bar >= n_bars: return None

    if direction == 1:
        stop_px = ep - stop_ticks * TICK_SIZE
        t1_px = ep + t1_ticks * TICK_SIZE
        t2_px = ep + t2_ticks * TICK_SIZE
    else:
        stop_px = ep + stop_ticks * TICK_SIZE
        t1_px = ep - t1_ticks * TICK_SIZE
        t2_px = ep - t2_ticks * TICK_SIZE

    leg1_open = True
    leg2_open = not single_leg
    leg1_pnl = leg2_pnl = 0.0
    leg1_exit = leg2_exit = 'NONE'
    leg1_exit_bar = leg2_exit_bar = entry_bar
    mfe = mae = 0.0
    be_triggered = False

    for i in range(entry_bar, min(entry_bar + tcap + 1, n_bars)):
        o, h, l, c, dt = bar_data[i]
        bh = i - entry_bar + 1

        if direction == 1:
            bmfe = (h - ep) / TICK_SIZE
            bmae = (ep - l) / TICK_SIZE
        else:
            bmfe = (ep - l) / TICK_SIZE
            bmae = (h - ep) / TICK_SIZE
        if bmfe > mfe: mfe = bmfe
        if bmae > mae: mae = bmae

        # BE step-up
        if be_trigger_ticks is not None and not be_triggered and mfe >= be_trigger_ticks:
            be_triggered = True
            if direction == 1:
                if ep > stop_px: stop_px = ep
            else:
                if ep < stop_px: stop_px = ep

        # Adverse excursion exit (real-time progressive check)
        if ae_threshold is not None and ae_min_bars is not None:
            if mae >= ae_threshold and bh >= ae_min_bars:
                pnl = (c - ep) / TICK_SIZE if direction == 1 else (ep - c) / TICK_SIZE
                if leg1_open:
                    leg1_pnl = pnl; leg1_exit = 'AE_EXIT'; leg1_exit_bar = i; leg1_open = False
                if leg2_open:
                    leg2_pnl = pnl; leg2_exit = 'AE_EXIT'; leg2_exit_bar = i; leg2_open = False
                break

        # Time cap
        if bh >= tcap:
            pnl = (c - ep) / TICK_SIZE if direction == 1 else (ep - c) / TICK_SIZE
            if leg1_open:
                leg1_pnl = pnl; leg1_exit = 'TIMECAP'; leg1_exit_bar = i; leg1_open = False
            if leg2_open:
                leg2_pnl = pnl; leg2_exit = 'TIMECAP'; leg2_exit_bar = i; leg2_open = False
            break

        # Stop
        stop_hit = (l <= stop_px) if direction == 1 else (h >= stop_px)
        if stop_hit:
            spnl = (stop_px - ep) / TICK_SIZE if direction == 1 else (ep - stop_px) / TICK_SIZE
            exit_type = 'BE' if be_triggered and abs(spnl) < 1.0 else 'STOP'
            if leg1_open:
                leg1_pnl = spnl; leg1_exit = exit_type; leg1_exit_bar = i; leg1_open = False
            if leg2_open:
                leg2_pnl = spnl; leg2_exit = exit_type; leg2_exit_bar = i; leg2_open = False
            break

        # T1
        if leg1_open:
            hit = (h >= t1_px) if direction == 1 else (l <= t1_px)
            if hit:
                leg1_pnl = float(t1_ticks); leg1_exit = 'TARGET_1'
                leg1_exit_bar = i; leg1_open = False
                if t2_stop_after_t1 is not None and leg2_open:
                    if direction == 1:
                        new_sp = ep + t2_stop_after_t1 * TICK_SIZE
                        if new_sp > stop_px: stop_px = new_sp
                    else:
                        new_sp = ep - t2_stop_after_t1 * TICK_SIZE
                        if new_sp < stop_px: stop_px = new_sp

        # T2
        if leg2_open:
            hit = (h >= t2_px) if direction == 1 else (l <= t2_px)
            if hit:
                leg2_pnl = float(t2_ticks); leg2_exit = 'TARGET_2'
                leg2_exit_bar = i; leg2_open = False

        if not leg1_open and not leg2_open:
            break

    if leg1_open or leg2_open:
        last_idx = min(entry_bar + tcap, n_bars - 1)
        last_c = bar_data[last_idx][3]
        pnl = (last_c - ep) / TICK_SIZE if direction == 1 else (ep - last_c) / TICK_SIZE
        if leg1_open: leg1_pnl = pnl; leg1_exit = 'END_DATA'; leg1_exit_bar = last_idx
        if leg2_open: leg2_pnl = pnl; leg2_exit = 'END_DATA'; leg2_exit_bar = last_idx

    exit_bar = max(leg1_exit_bar, leg2_exit_bar)
    bars_held = exit_bar - entry_bar + 1
    if single_leg:
        wpnl = leg1_pnl - COST_TICKS
    else:
        wpnl = LEG1_W * leg1_pnl + LEG2_W * leg2_pnl - COST_TICKS

    return dict(
        entry_price=ep, weighted_pnl=wpnl, bars_held=bars_held,
        leg1_exit=leg1_exit, leg1_pnl=leg1_pnl, leg1_exit_bar=leg1_exit_bar,
        leg2_exit=leg2_exit, leg2_pnl=leg2_pnl, leg2_exit_bar=leg2_exit_bar,
        entry_bar=entry_bar, exit_bar=exit_bar, mfe=mfe, mae=mae,
        t1_ticks=t1_ticks, t2_ticks=t2_ticks, stop_ticks=stop_ticks,
    )

# =========================================================================
#  Exit parameter functions
# =========================================================================

def get_exit_params_zr(touch, mode):
    zw = touch['_zw']
    return max(1, round(0.5 * zw)), max(1, round(1.0 * zw)), max(round(1.5 * zw), 120), 160

def get_exit_params_fixed(touch, mode):
    if mode == 'CT': return 40, 80, 190, 160
    else: return 60, 80, 240, 160

# =========================================================================
#  Full sequential sim with no-overlap + kill-switch
# =========================================================================

def run_full_sim(qualifying, bar_data, n_bars, exit_fn, single_leg=False,
                 ct_limit=True, be_trigger_mult=None, stop_override_fn=None,
                 t2_stop_after_t1_fn=None, ae_threshold_fn=None, ae_min_bars=None,
                 dynamic_t2_exit=False, hybrid_fn=None):
    """
    hybrid_fn: if set, fn(touch) -> 'single' or '2leg' to choose exit mode per trade.
    dynamic_t2_exit: if True, close T2 runner when a new qualifying different-zone
                     signal arrives (Section 10 mechanism).
    ae_threshold_fn: if set, fn(touch, mode) -> threshold in ticks for AE exit.
    """
    trades = []
    blocked = []
    in_trade_until = -1
    ct_limit_pending = False
    ct_limit_expires_at = -1

    ks_consec = 0
    ks_daily_pnl = 0.0
    ks_weekly_pnl = 0.0
    ks_halted = False
    ks_last_day = ''
    ks_last_week = ''
    ks_triggers = 0

    # For dynamic T2: track current trade state
    current_trade = None  # dict with leg1 filled status, zone_key, etc.
    dynamic_t2_closes = []  # records of T2 early closes

    # Build index: rbi -> qualifying touch (for dynamic T2 signal lookup)
    qual_by_rbi = {t['_rbi']: t for t in qualifying}

    for t in qualifying:
        rbi = t['_rbi']
        wt_entry_bar = rbi + 1
        if wt_entry_bar >= n_bars: continue

        direction = t['_direction']
        trend = t['_trend']

        if trend == 'CT':
            mode = 'CT'
        else:
            if t['_seq'] > WTNT_SEQ_MAX:
                blocked.append(dict(rbi=rbi, reason='SEQ_FILTER', touch=t))
                continue
            mode = 'WT'

        if ct_limit_pending and rbi >= ct_limit_expires_at:
            ct_limit_pending = False

        # Day/week reset
        dt_str = bar_data[wt_entry_bar][4]
        day_str = dt_str.split(' ')[0] if ' ' in dt_str else ''
        if day_str and day_str != ks_last_day:
            ks_daily_pnl = 0.0; ks_halted = False; ks_consec = 0; ks_last_day = day_str
        try:
            d = datetime.strptime(day_str, '%m/%d/%Y')
            wk = f"{d.year}-W{d.isocalendar()[1]}"
        except: wk = day_str
        if wk != ks_last_week:
            ks_weekly_pnl = 0.0; ks_last_week = wk

        # === Dynamic T2 exit check ===
        if dynamic_t2_exit and current_trade is not None:
            ct_info = current_trade
            # Is T1 filled and T2 still running?
            if ct_info['leg1_filled'] and wt_entry_bar <= ct_info['exit_bar']:
                # Is this a DIFFERENT zone?
                new_zone_key = t['_zone_key']
                if new_zone_key != ct_info['zone_key']:
                    # Close T2 runner at market (current bar's close before new entry)
                    close_bar = wt_entry_bar
                    if close_bar < n_bars:
                        close_px = bar_data[close_bar][0]  # Open of the new entry bar
                        if ct_info['direction'] == 1:
                            t2_close_pnl = (close_px - ct_info['entry_price']) / TICK_SIZE
                        else:
                            t2_close_pnl = (ct_info['entry_price'] - close_px) / TICK_SIZE

                        # Record the early close
                        # What was the original T2 leg PnL if we'd held?
                        orig_t2_pnl = ct_info['orig_leg2_pnl']

                        # Recompute the original trade's weighted PnL with early T2 close
                        new_wpnl = LEG1_W * ct_info['leg1_pnl'] + LEG2_W * t2_close_pnl - COST_TICKS
                        old_wpnl = ct_info['weighted_pnl']
                        pnl_delta = new_wpnl - old_wpnl

                        # Update the trade in the trades list
                        for tr in trades:
                            if tr['rbi'] == ct_info['rbi']:
                                tr['weighted_pnl'] = new_wpnl
                                tr['leg2_pnl'] = t2_close_pnl
                                tr['leg2_exit'] = 'DYNAMIC_T2'
                                tr['leg2_exit_bar'] = close_bar
                                tr['exit_bar'] = ct_info['leg1_exit_bar']
                                tr['bars_held'] = ct_info['leg1_exit_bar'] - tr['entry_bar'] + 1
                                break

                        # Update kill-switch for the PnL change
                        ks_daily_pnl += pnl_delta
                        ks_weekly_pnl += pnl_delta

                        dynamic_t2_closes.append(dict(
                            orig_rbi=ct_info['rbi'],
                            new_rbi=rbi,
                            t2_early_pnl=t2_close_pnl,
                            t2_orig_pnl=orig_t2_pnl,
                            pnl_given_up=orig_t2_pnl - t2_close_pnl,
                            new_zone_key=new_zone_key,
                            new_mode=mode,
                        ))

                        # Clear position — allow new signal to enter
                        in_trade_until = ct_info['leg1_exit_bar']
                        current_trade = None

        # Skip checks
        if wt_entry_bar <= in_trade_until:
            blocked.append(dict(rbi=rbi, reason='IN_POSITION', touch=t))
            continue
        if ct_limit_pending:
            blocked.append(dict(rbi=rbi, reason='LIMIT_PENDING', touch=t))
            continue
        if ks_halted:
            blocked.append(dict(rbi=rbi, reason='KILL_SWITCH', touch=t))
            continue

        # Entry
        if ct_limit and mode == 'CT':
            ct_limit_pending = True
            ct_limit_expires_at = rbi + CT_LIMIT_WINDOW
            fill = scan_ct_limit_fill(bar_data, rbi, direction,
                                       t['_zone_top'], t['_zone_bot'], n_bars)
            if fill is None:
                ct_limit_pending = True
                blocked.append(dict(rbi=rbi, reason='LIMIT_EXPIRED', touch=t))
                # For dynamic T2: if we closed T2 for this CT signal and it didn't fill...
                if dynamic_t2_exit and dynamic_t2_closes and dynamic_t2_closes[-1]['new_rbi'] == rbi:
                    dynamic_t2_closes[-1]['new_filled'] = False
                continue
            entry_bar, ep, _ = fill
            ct_limit_pending = False
        else:
            entry_bar = wt_entry_bar
            ep = bar_data[entry_bar][0]

        # Determine single vs 2-leg from hybrid_fn
        use_single = False
        if hybrid_fn:
            use_single = hybrid_fn(t) == 'single'
        elif single_leg:
            use_single = True

        # Compute exit params
        t1, t2, stop, tcap = exit_fn(t, mode)
        if stop_override_fn:
            stop = stop_override_fn(t, mode, stop)

        be_ticks = None
        if be_trigger_mult is not None:
            be_ticks = max(1, round(be_trigger_mult * t['_zw']))

        t2_stop_val = None
        if t2_stop_after_t1_fn is not None:
            t2_stop_val = t2_stop_after_t1_fn(t, mode)

        ae_thresh = None
        if ae_threshold_fn is not None:
            ae_thresh = ae_threshold_fn(t, mode)

        result = sim_2leg(bar_data, entry_bar, ep, direction,
                          t1, t2 if not use_single else t1, stop, tcap, n_bars,
                          single_leg=use_single, be_trigger_ticks=be_ticks,
                          t2_stop_after_t1=t2_stop_val,
                          ae_threshold=ae_thresh, ae_min_bars=ae_min_bars)

        if result is None: continue

        in_trade_until = result['exit_bar']

        # Kill-switch
        wpnl = result['weighted_pnl']
        ks_daily_pnl += wpnl
        ks_weekly_pnl += wpnl
        if wpnl < 0: ks_consec += 1
        else: ks_consec = 0
        if ks_consec >= KS_CONSEC: ks_halted = True; ks_triggers += 1
        if ks_daily_pnl <= KS_DAILY: ks_halted = True
        if ks_weekly_pnl <= KS_WEEKLY: ks_halted = True

        trade = dict(
            rbi=rbi, mode=mode, direction=direction,
            zone_width=t['_zw'], seq=t['_seq'], trend=t['_trend'],
            score=t['_score'], tf=t['_tf'],
            zone_top=t['_zone_top'], zone_bot=t['_zone_bot'],
            zone_key=t['_zone_key'],
            **result
        )
        trades.append(trade)

        # Track for dynamic T2
        if dynamic_t2_exit:
            current_trade = dict(
                rbi=rbi, entry_price=ep, direction=direction,
                zone_key=t['_zone_key'],
                leg1_filled=(result['leg1_exit'] == 'TARGET_1'),
                leg1_exit_bar=result['leg1_exit_bar'],
                leg1_pnl=result['leg1_pnl'],
                exit_bar=result['exit_bar'],
                weighted_pnl=result['weighted_pnl'],
                orig_leg2_pnl=result['leg2_pnl'],
            )
            if dynamic_t2_closes and dynamic_t2_closes[-1]['new_rbi'] == rbi:
                dynamic_t2_closes[-1]['new_filled'] = True
                dynamic_t2_closes[-1]['new_wpnl'] = wpnl

    return trades, blocked, ks_triggers, dynamic_t2_closes

# =========================================================================
#  Stats helpers
# =========================================================================

def calc_stats(trades):
    if not trades:
        return dict(n=0, wr=0, pf=0, ev=0, total_pnl=0, max_dd=0,
                    max_single_loss=0, mean_hold=0)
    pnls = [t['weighted_pnl'] for t in trades]
    wins = sum(1 for p in pnls if p > 0)
    gw = sum(p for p in pnls if p > 0)
    gl = sum(abs(p) for p in pnls if p < 0)
    pf = gw / gl if gl > 0 else float('inf')
    cum = peak = max_dd = 0
    for p in pnls:
        cum += p
        if cum > peak: peak = cum
        dd = peak - cum
        if dd > max_dd: max_dd = dd
    return dict(n=len(trades), wr=100*wins/len(trades), pf=pf,
                ev=sum(pnls)/len(pnls), total_pnl=sum(pnls), max_dd=max_dd,
                max_single_loss=max((abs(p) for p in pnls if p < 0), default=0),
                mean_hold=sum(t['bars_held'] for t in trades)/len(trades))

def fmt_pnl(v): return f"{v:.1f}"

# =========================================================================
#  Run baselines
# =========================================================================

print("Running baselines...", file=sys.stderr)
p1_zr, p1_zr_blk, p1_zr_ks, _ = run_full_sim(P1_QUAL, P1_BARS, N_P1, get_exit_params_zr, ct_limit=True)
p2_zr, p2_zr_blk, p2_zr_ks, _ = run_full_sim(P2_QUAL, P2_BARS, N_P2, get_exit_params_zr, ct_limit=True)
p1_zr_rbis = set(t['rbi'] for t in p1_zr)
p2_zr_rbis = set(t['rbi'] for t in p2_zr)

def freed_count(trades, base_rbis): return sum(1 for t in trades if t['rbi'] not in base_rbis)

out = []
def pr(s=''): out.append(s)

pr("# Throughput Optimization Analysis — Part 2 of 2")
pr()
pr(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
pr(f"P1 baseline: {len(p1_zr)} trades, {fmt_pnl(calc_stats(p1_zr)['total_pnl'])}t total PnL")
pr(f"P2 baseline: {len(p2_zr)} trades, {fmt_pnl(calc_stats(p2_zr)['total_pnl'])}t total PnL")
pr()

# =========================================================================
#  SECTION 8: WINNER VS LOSER RESOLUTION SPEED
# =========================================================================

print("Section 8: Winner vs loser...", file=sys.stderr)
pr("=" * 70)
pr("## SECTION 8: WINNER VS LOSER RESOLUTION SPEED")
pr("=" * 70)
pr()

winners = [t for t in p1_zr if t['weighted_pnl'] > 0]
losers = [t for t in p1_zr if t['weighted_pnl'] <= 0]

# Signals blocked per trade
ip_blocked = [b for b in p1_zr_blk if b['reason'] == 'IN_POSITION']

def signals_blocked_by_trade(trade, blocked_list):
    count = 0
    for b in blocked_list:
        entry = b['rbi'] + 1
        if trade['entry_bar'] <= entry <= trade['exit_bar']:
            count += 1
    return count

# Mean signal EV (from all P1 ZR trades)
mean_signal_ev = calc_stats(p1_zr)['ev']

pr("| Metric | Winners | Losers |")
pr("|--------|---------|--------|")
pr(f"| Count | {len(winners)} | {len(losers)} |")
w_hold = sum(t['bars_held'] for t in winners) / len(winners) if winners else 0
l_hold = sum(t['bars_held'] for t in losers) / len(losers) if losers else 0
pr(f"| Mean bars held | {w_hold:.1f} | {l_hold:.1f} |")
w_hold_s = sorted(t['bars_held'] for t in winners)
l_hold_s = sorted(t['bars_held'] for t in losers)
pr(f"| Median bars held | {w_hold_s[len(w_hold_s)//2] if w_hold_s else 0} | {l_hold_s[len(l_hold_s)//2] if l_hold_s else 0} |")

t1_bars_w = [t['leg1_exit_bar'] - t['entry_bar'] + 1 for t in winners if t['leg1_exit'] == 'TARGET_1']
pr(f"| Mean bars to T1 (winners) | {sum(t1_bars_w)/len(t1_bars_w):.1f} | -- |" if t1_bars_w else "| Mean bars to T1 | -- | -- |")
stop_bars_l = [t['bars_held'] for t in losers if t['leg1_exit'] == 'STOP']
pr(f"| Mean bars to stop (losers) | -- | {sum(stop_bars_l)/len(stop_bars_l):.1f} |" if stop_bars_l else "| Mean bars to stop | -- | -- |")

w_blocked = [signals_blocked_by_trade(t, ip_blocked) for t in winners]
l_blocked = [signals_blocked_by_trade(t, ip_blocked) for t in losers]
pr(f"| Signals blocked per trade | {sum(w_blocked)/len(w_blocked):.2f} | {sum(l_blocked)/len(l_blocked):.2f} |" if losers else "")
pr(f"| Blocking cost (blocked x {mean_signal_ev:.1f}t EV) | {sum(w_blocked)*mean_signal_ev:.1f} | {sum(l_blocked)*mean_signal_ev:.1f} |")
pr()

# Per-loser detail
pr("### Per-Loser Detail (all P1 ZR losers)")
pr()
if losers:
    pr("| # | bars_held | PnL | zone_width | mode | exit_type | signals_blocked |")
    pr("|---|----------|-----|-----------|------|-----------|----------------|")
    for i, t in enumerate(losers):
        sb = signals_blocked_by_trade(t, ip_blocked)
        pr(f"| {i+1} | {t['bars_held']} | {t['weighted_pnl']:.1f} | {t['zone_width']:.0f} | {t['mode']} | {t['leg1_exit']} | {sb} |")
else:
    pr("No losers in P1 ZR baseline.")
pr()

# Adverse excursion exit rules
pr("### Adverse Excursion Exit Rules")
pr()

ae_configs = [
    ("No rule (current)", None, None),
    ("AE > 0.75x zw + bar > 20", lambda t, m: max(1, round(0.75 * t['_zw'])), 20),
    ("AE > 1.0x zw + bar > 15", lambda t, m: max(1, round(1.0 * t['_zw'])), 15),
    ("AE > 0.5x zw + bar > 30", lambda t, m: max(1, round(0.5 * t['_zw'])), 30),
]

pr("| Rule | Losers caught (AE exit) | Winners killed | Freed (seq sim) | Net PnL | KS triggers |")
pr("|------|------------------------|---------------|----------------|---------|-------------|")

for label, ae_fn, ae_bars in ae_configs:
    if ae_fn is None:
        trades, blk, ks = p1_zr, p1_zr_blk, p1_zr_ks
    else:
        print(f"  AE: {label}...", file=sys.stderr)
        trades, blk, ks, _ = run_full_sim(P1_QUAL, P1_BARS, N_P1, get_exit_params_zr,
                                           ct_limit=True, ae_threshold_fn=ae_fn, ae_min_bars=ae_bars)
    s = calc_stats(trades)
    ae_exits = [t for t in trades if t.get('leg1_exit') == 'AE_EXIT']
    ae_losers = sum(1 for t in ae_exits if t['weighted_pnl'] <= 0)
    ae_winners_killed = sum(1 for t in ae_exits if t['weighted_pnl'] > 0)
    # Compare: trades that would have been winners under baseline but are now AE_EXIT losers
    freed = freed_count(trades, p1_zr_rbis)
    pr(f"| {label} | {ae_losers} | {ae_winners_killed} | {freed} | {fmt_pnl(s['total_pnl'])} | {ks} |")
pr()

# =========================================================================
#  SECTION 9: SIGNAL CLUSTERING AND THROUGHPUT WINDOWS
# =========================================================================

print("Section 9: Signal clustering...", file=sys.stderr)
pr("=" * 70)
pr("## SECTION 9: SIGNAL CLUSTERING AND THROUGHPUT WINDOWS")
pr("=" * 70)
pr()

# For each trade, compute "next qualifying signal arrives in N bars"
pr("### A) Next Signal Gap Analysis")
pr()

trade_next_gaps = []
for i, tr in enumerate(p1_zr):
    rbi = tr['rbi']
    next_gap = None
    for q in P1_QUAL:
        if q['_rbi'] > rbi:
            next_gap = q['_rbi'] - rbi
            break
    sb = signals_blocked_by_trade(tr, ip_blocked)
    trade_next_gaps.append((tr, next_gap, sb))

gap_bins = [(0, 15), (15, 30), (30, 60), (60, 99999)]
gap_labels = ['< 15 bars', '15-30 bars', '30-60 bars', '> 60 bars']

pr("| Next signal gap | Count | Mean bars_held | Mean signals blocked |")
pr("|----------------|-------|---------------|---------------------|")
for (lo, hi), lbl in zip(gap_bins, gap_labels):
    group = [(tr, ng, sb) for tr, ng, sb in trade_next_gaps if ng is not None and lo <= ng < hi]
    if group:
        mean_bh = sum(tr['bars_held'] for tr, _, _ in group) / len(group)
        mean_sb = sum(sb for _, _, sb in group) / len(group)
        pr(f"| {lbl} | {len(group)} | {mean_bh:.1f} | {mean_sb:.2f} |")
    else:
        pr(f"| {lbl} | 0 | -- | -- |")
no_next = sum(1 for _, ng, _ in trade_next_gaps if ng is None)
pr(f"| No next signal | {no_next} | -- | -- |")
pr()

# B) Cluster windows
pr("### B) Cluster Windows (3+ signals within 30 bars)")
pr()
cluster_windows = []
i = 0
while i < len(P1_QUAL):
    cluster = [P1_QUAL[i]]
    j = i + 1
    while j < len(P1_QUAL) and P1_QUAL[j]['_rbi'] - cluster[0]['_rbi'] <= 30:
        cluster.append(P1_QUAL[j])
        j += 1
    if len(cluster) >= 3:
        cluster_windows.append(cluster)
    i = j if len(cluster) > 1 else i + 1

pr(f"Cluster windows found: {len(cluster_windows)}")
for ci, cw in enumerate(cluster_windows):
    sigs = len(cw)
    span = cw[-1]['_rbi'] - cw[0]['_rbi']
    traded = sum(1 for s in cw if s['_rbi'] in p1_zr_rbis)
    pr(f"- Window {ci+1}: {sigs} signals in {span} bars, {traded} traded, {sigs-traded} blocked")
pr()
pr("> Cluster windows are rare on P1 (sparse signals). Exit tightening during clusters")
pr("> would affect very few trades. This is OBSERVATIONAL — no mechanism implemented.")
pr()

# =========================================================================
#  SECTION 10: DYNAMIC T2 EXIT ON NEW SIGNAL
# =========================================================================

print("Section 10: Dynamic T2 exit...", file=sys.stderr)
pr("=" * 70)
pr("## SECTION 10: DYNAMIC T2 EXIT ON NEW SIGNAL")
pr("=" * 70)
pr()

# Run P1 with dynamic T2 exit
p1_dyn, p1_dyn_blk, p1_dyn_ks, p1_dyn_closes = run_full_sim(
    P1_QUAL, P1_BARS, N_P1, get_exit_params_zr, ct_limit=True, dynamic_t2_exit=True)

s_base = calc_stats(p1_zr)
s_dyn = calc_stats(p1_dyn)

pr("| Metric | Current | Dynamic T2 exit |")
pr("|--------|---------|----------------|")
pr(f"| Total trades | {s_base['n']} | {s_dyn['n']} |")
pr(f"| T2 early closes triggered | -- | {len(p1_dyn_closes)} |")

if p1_dyn_closes:
    early_pnls = [c['t2_early_pnl'] for c in p1_dyn_closes]
    orig_pnls = [c['t2_orig_pnl'] for c in p1_dyn_closes]
    pr(f"| Mean T2 PnL on early close | -- | {sum(early_pnls)/len(early_pnls):.1f} |")
    pr(f"| Mean T2 PnL if held (given up) | -- | {sum(orig_pnls)/len(orig_pnls):.1f} |")
    new_filled = [c for c in p1_dyn_closes if c.get('new_filled', False)]
    new_expired = [c for c in p1_dyn_closes if not c.get('new_filled', True)]
    pr(f"| New signal trades taken | -- | {len(new_filled)} |")
    pr(f"| New signal CT limit EXPIRED | -- | {len(new_expired)} |")
    if new_expired:
        expired_cost = sum(LEG2_W * c['pnl_given_up'] for c in new_expired)
        pr(f"| Net cost of expired CT limits | -- | {expired_cost:.1f}t |")
    else:
        pr(f"| Net cost of expired CT limits | -- | 0.0t |")
    if new_filled:
        new_wpnls = [c.get('new_wpnl', 0) for c in new_filled]
        new_wins = sum(1 for p in new_wpnls if p > 0)
        pr(f"| New signal WR | -- | {100*new_wins/len(new_filled):.1f}% |")
        pr(f"| New signal total PnL | -- | {sum(new_wpnls):.1f} |")
else:
    pr(f"| Mean T2 PnL on early close | -- | -- |")
    pr(f"| New signal trades taken | -- | 0 |")

pr(f"| NET total PnL | {fmt_pnl(s_base['total_pnl'])} | {fmt_pnl(s_dyn['total_pnl'])} |")
pr(f"| Kill-switch triggers | {p1_zr_ks} | {p1_dyn_ks} |")
pr()

# Breakdown by T2 status at close
if p1_dyn_closes:
    pr("| T2 status at close | Count | Mean T2 early PnL | Mean new signal PnL |")
    pr("|-------------------|-------|-------------------|---------------------|")
    t2_prof = [c for c in p1_dyn_closes if c['t2_early_pnl'] > 0]
    t2_loss = [c for c in p1_dyn_closes if c['t2_early_pnl'] <= 0]
    for label, group in [("T2 was profitable", t2_prof), ("T2 was at loss", t2_loss)]:
        if group:
            mean_t2 = sum(c['t2_early_pnl'] for c in group) / len(group)
            filled_g = [c for c in group if c.get('new_filled')]
            mean_new = sum(c.get('new_wpnl', 0) for c in filled_g) / len(filled_g) if filled_g else 0
            pr(f"| {label} | {len(group)} | {mean_t2:.1f} | {mean_new:.1f} |")
        else:
            pr(f"| {label} | 0 | -- | -- |")
    pr()

# P2 cross-validation
print("  P2 dynamic T2...", file=sys.stderr)
p2_dyn, p2_dyn_blk, p2_dyn_ks, p2_dyn_closes = run_full_sim(
    P2_QUAL, P2_BARS, N_P2, get_exit_params_zr, ct_limit=True, dynamic_t2_exit=True)
s2_base = calc_stats(p2_zr)
s2_dyn = calc_stats(p2_dyn)

pr("### P2 Cross-Validation")
pr()
pr("| Period | Current Total PnL | Dynamic T2 Total PnL | Delta | KS triggers |")
pr("|--------|-------------------|---------------------|-------|-------------|")
pr(f"| P1 | {fmt_pnl(s_base['total_pnl'])} | {fmt_pnl(s_dyn['total_pnl'])} | {s_dyn['total_pnl']-s_base['total_pnl']:+.1f} | {p1_dyn_ks} |")
pr(f"| P2 | {fmt_pnl(s2_base['total_pnl'])} | {fmt_pnl(s2_dyn['total_pnl'])} | {s2_dyn['total_pnl']-s2_base['total_pnl']:+.1f} | {p2_dyn_ks} |")
pr()

# =========================================================================
#  SECTION 11: HYBRID EXIT STRATEGY
# =========================================================================

print("Section 11: Hybrid strategies...", file=sys.stderr)
pr("=" * 70)
pr("## SECTION 11: HYBRID EXIT STRATEGY")
pr("=" * 70)
pr()

# Hybrid A: zone-width-based single vs 2-leg
def hybrid_a(t):
    return 'single' if t['_zw'] < 150 else '2leg'

# Hybrid B: narrow=single, wide=dynamic T2
# (run separately since dynamic_t2 is a sim-level flag)

# Hybrid C: narrow=2leg with T2 stop at entry, wide=2leg current
# Implement via t2_stop_after_t1_fn that's conditional on zone width
def hybrid_c_t2_stop(t, m):
    if t['_zw'] < 150: return 0  # breakeven T2 for narrow
    return None  # None means no change for wide

# Hybrid D: wide=BE, narrow=current
# Part 1 showed BE NOT VIABLE across all bins. Skip.

hybrid_configs = []

# Current baseline
s = calc_stats(p1_zr)
hybrid_configs.append(("Current uniform ZR 2-leg", s, p1_zr_ks, p1_zr))

# Hybrid A
print("  Hybrid A...", file=sys.stderr)
ha_trades, ha_blk, ha_ks, _ = run_full_sim(P1_QUAL, P1_BARS, N_P1, get_exit_params_zr,
                                             ct_limit=True, hybrid_fn=hybrid_a)
s = calc_stats(ha_trades)
hybrid_configs.append(("Hybrid A: narrow=T1, wide=2leg", s, ha_ks, ha_trades))

# Hybrid B: narrow=single, wide=dynamic T2
print("  Hybrid B...", file=sys.stderr)
def hybrid_b_fn(t):
    return 'single' if t['_zw'] < 150 else '2leg'
hb_trades, hb_blk, hb_ks, hb_closes = run_full_sim(P1_QUAL, P1_BARS, N_P1, get_exit_params_zr,
                                                      ct_limit=True, hybrid_fn=hybrid_b_fn,
                                                      dynamic_t2_exit=True)
s = calc_stats(hb_trades)
hybrid_configs.append(("Hybrid B: narrow=T1, wide=dynamic T2", s, hb_ks, hb_trades))

# Hybrid C: narrow=BE T2, wide=current
print("  Hybrid C...", file=sys.stderr)
hc_trades, hc_blk, hc_ks, _ = run_full_sim(P1_QUAL, P1_BARS, N_P1, get_exit_params_zr,
                                              ct_limit=True, t2_stop_after_t1_fn=hybrid_c_t2_stop)
s = calc_stats(hc_trades)
hybrid_configs.append(("Hybrid C: narrow=BE T2, wide=current", s, hc_ks, hc_trades))

# Hybrid D: skipped per Part 1 S6C
pr("> **Hybrid D skipped**: Part 1 Section 6C found BE NOT VIABLE across all zone width bins")
pr("> (0.25x: -4010t, 0.33x: -2617t, 0.5x: -823t). No zone-width-conditional BE improvement exists.")
pr()

pr("| Config | Trades | Total PnL | Mean hold | Freed | Max DD | Max loss | KS |")
pr("|--------|--------|-----------|----------|-------|--------|---------|-----|")
for label, s, ks, trades in hybrid_configs:
    freed = freed_count(trades, p1_zr_rbis)
    pr(f"| {label} | {s['n']} | {fmt_pnl(s['total_pnl'])} | {s['mean_hold']:.1f} | {freed} | {s['max_dd']:.1f} | {s['max_single_loss']:.1f} | {ks} |")
pr()

# P2 cross-validation for best hybrid
best_hybrid = max(hybrid_configs[1:], key=lambda x: x[1]['total_pnl'])
best_label = best_hybrid[0]
pr(f"Best P1 hybrid: **{best_label}** ({fmt_pnl(best_hybrid[1]['total_pnl'])}t)")
pr()

# Run best hybrid on P2
print(f"  P2 cross-val: {best_label}...", file=sys.stderr)
if 'Hybrid A' in best_label:
    p2_hyb, _, p2_hyb_ks, _ = run_full_sim(P2_QUAL, P2_BARS, N_P2, get_exit_params_zr,
                                             ct_limit=True, hybrid_fn=hybrid_a)
elif 'Hybrid B' in best_label:
    p2_hyb, _, p2_hyb_ks, _ = run_full_sim(P2_QUAL, P2_BARS, N_P2, get_exit_params_zr,
                                             ct_limit=True, hybrid_fn=hybrid_b_fn, dynamic_t2_exit=True)
elif 'Hybrid C' in best_label:
    p2_hyb, _, p2_hyb_ks, _ = run_full_sim(P2_QUAL, P2_BARS, N_P2, get_exit_params_zr,
                                             ct_limit=True, t2_stop_after_t1_fn=hybrid_c_t2_stop)
else:
    p2_hyb, p2_hyb_ks = p2_zr, p2_zr_ks

s2_hyb = calc_stats(p2_hyb)

pr("| Period | Hybrid | Total PnL | vs current | Consistent? |")
pr("|--------|--------|-----------|------------|-------------|")
pr(f"| P1 | {best_label} | {fmt_pnl(best_hybrid[1]['total_pnl'])} | {best_hybrid[1]['total_pnl'] - calc_stats(p1_zr)['total_pnl']:+.1f} | baseline |")
consistent = "YES" if s2_hyb['total_pnl'] > s2_base['total_pnl'] else "NO"
pr(f"| P2 | same | {fmt_pnl(s2_hyb['total_pnl'])} | {s2_hyb['total_pnl'] - s2_base['total_pnl']:+.1f} | {consistent} |")
pr()

# =========================================================================
#  SECTION 12: COMBINED THROUGHPUT SUMMARY (Parts 1 + 2)
# =========================================================================

print("Section 12: Combined summary...", file=sys.stderr)
pr("=" * 70)
pr("## SECTION 12: COMBINED THROUGHPUT SUMMARY")
pr("=" * 70)
pr()

# Load Part 1 results from the answer keys
p1_fix, _, p1_fix_ks, _ = run_full_sim(P1_QUAL, P1_BARS, N_P1, get_exit_params_fixed, ct_limit=True)
p1_zr_t1, _, p1_zr_t1_ks, _ = run_full_sim(P1_QUAL, P1_BARS, N_P1, get_exit_params_zr,
                                              single_leg=True, ct_limit=True)
p1_fix_t1, _, p1_fix_t1_ks, _ = run_full_sim(P1_QUAL, P1_BARS, N_P1, get_exit_params_fixed,
                                               single_leg=True, ct_limit=True)
# Tighter stop (max 1.0x, 100)
p1_ts, _, p1_ts_ks, _ = run_full_sim(P1_QUAL, P1_BARS, N_P1, get_exit_params_zr, ct_limit=True,
                                      stop_override_fn=lambda t, m, s: max(round(1.0 * t['_zw']), 100))
# T2-only tighten (max 1.0x, 100 after T1)
p1_t2t, _, p1_t2t_ks, _ = run_full_sim(P1_QUAL, P1_BARS, N_P1, get_exit_params_zr, ct_limit=True,
                                         t2_stop_after_t1_fn=lambda t, m: -max(round(1.0 * t['_zw']), 100))
# BE step-up (best = 0.5x)
p1_be, _, p1_be_ks, _ = run_full_sim(P1_QUAL, P1_BARS, N_P1, get_exit_params_zr, ct_limit=True,
                                      be_trigger_mult=0.5)
# Best AE config
best_ae_label = None
best_ae_pnl = -99999
best_ae_trades = None
best_ae_ks = 0
for label, ae_fn, ae_bars in ae_configs[1:]:
    trades, _, ks, _ = run_full_sim(P1_QUAL, P1_BARS, N_P1, get_exit_params_zr,
                                     ct_limit=True, ae_threshold_fn=ae_fn, ae_min_bars=ae_bars)
    s = calc_stats(trades)
    if s['total_pnl'] > best_ae_pnl:
        best_ae_pnl = s['total_pnl']
        best_ae_label = label
        best_ae_trades = trades
        best_ae_ks = ks

all_results = [
    ("Current ZR 2-leg", calc_stats(p1_zr), p1_zr_ks, "baseline", "current"),
    ("Fixed exits (Part 1 S3)", calc_stats(p1_fix), p1_fix_ks, "fixed T/S", "low"),
    ("ZR single-leg T1 (Part 1 S4)", calc_stats(p1_zr_t1), p1_zr_t1_ks, "drop T2", "low"),
    ("Fixed single-leg T1 (Part 1 S4)", calc_stats(p1_fix_t1), p1_fix_t1_ks, "drop fixed T2", "low"),
    ("Full tighter stop (Part 1 S6A)", calc_stats(p1_ts), p1_ts_ks, "faster loss", "low"),
    ("T2-only tighter stop (Part 1 S6B)", calc_stats(p1_t2t), p1_t2t_ks, "faster T2", "low"),
    ("BE step-up 0.5x (Part 1 S6C)", calc_stats(p1_be), p1_be_ks, "BE exit", "low"),
    (f"Adverse excursion ({best_ae_label})" if best_ae_label else "AE exit", calc_stats(best_ae_trades) if best_ae_trades else calc_stats(p1_zr), best_ae_ks, "cond. early exit", "medium"),
    ("Dynamic T2 exit (S10)", s_dyn, p1_dyn_ks, "signal-triggered T2", "medium"),
    (f"Best hybrid (S11): {best_label}", best_hybrid[1], best_hybrid[2], "zone-width-based", "medium"),
]

pr("### All P1 Results")
pr()
pr("| Strategy | Mechanism | Trades | Total PnL | vs Current | Max DD | Max loss | KS | Complexity |")
pr("|----------|-----------|--------|-----------|------------|--------|---------|-----|------------|")

baseline_pnl = calc_stats(p1_zr)['total_pnl']
for label, s, ks, mech, cmplx in all_results:
    delta = s['total_pnl'] - baseline_pnl
    delta_str = "--" if label.startswith("Current") else f"{delta:+.1f}"
    high = " **HIGH**" if s['max_single_loss'] > 300 else ""
    pr(f"| {label} | {mech} | {s['n']} | {fmt_pnl(s['total_pnl'])} | {delta_str} | {s['max_dd']:.1f} | {s['max_single_loss']:.1f}{high} | {ks} | {cmplx} |")
pr()

# P2 cross-validation for all key configs
pr("### P2 Cross-Validation Summary")
pr()

p2_fix, _, p2_fix_ks, _ = run_full_sim(P2_QUAL, P2_BARS, N_P2, get_exit_params_fixed, ct_limit=True)
p2_zr_t1, _, p2_zr_t1_ks, _ = run_full_sim(P2_QUAL, P2_BARS, N_P2, get_exit_params_zr,
                                              single_leg=True, ct_limit=True)
p2_t2t, _, p2_t2t_ks, _ = run_full_sim(P2_QUAL, P2_BARS, N_P2, get_exit_params_zr, ct_limit=True,
                                         t2_stop_after_t1_fn=lambda t, m: -max(round(1.0 * t['_zw']), 100))
p2_be, _, p2_be_ks, _ = run_full_sim(P2_QUAL, P2_BARS, N_P2, get_exit_params_zr, ct_limit=True,
                                      be_trigger_mult=0.5)

p2_base_pnl = calc_stats(p2_zr)['total_pnl']

p2_results = [
    ("Current ZR 2-leg", calc_stats(p2_zr), p2_zr_ks),
    ("Fixed exits", calc_stats(p2_fix), p2_fix_ks),
    ("ZR single-leg T1", calc_stats(p2_zr_t1), p2_zr_t1_ks),
    ("T2-only tighter stop", calc_stats(p2_t2t), p2_t2t_ks),
    ("BE step-up 0.5x", calc_stats(p2_be), p2_be_ks),
    ("Dynamic T2 exit", s2_dyn, p2_dyn_ks),
    (f"Best hybrid ({best_label})", s2_hyb, p2_hyb_ks),
]

pr("| Config | P1 Total PnL | P2 Total PnL | P1 KS | P2 KS | Classification |")
pr("|--------|-------------|-------------|-------|-------|---------------|")

p1_lookup = {label: (s, ks) for label, s, ks, _, _ in all_results}

for p2_label, p2_s, p2_ks in p2_results:
    # Find matching P1 result
    p1_match = None
    for p1_label, p1_s, p1_ks_val, _, _ in all_results:
        if p2_label in p1_label or p1_label.startswith(p2_label[:20]):
            p1_match = (p1_s, p1_ks_val)
            break
    if p1_match is None:
        p1_match = (calc_stats(p1_zr), p1_zr_ks)

    p1_s, p1_ks_val = p1_match
    p1_pnl = p1_s['total_pnl']
    p2_pnl = p2_s['total_pnl']

    beats_p1 = p1_pnl > baseline_pnl
    beats_p2 = p2_pnl > p2_base_pnl
    ks_increase = (p1_ks_val > 0 and p1_zr_ks == 0) or (p2_ks > 0 and p2_zr_ks == 0)
    high_exp = p1_s['max_single_loss'] > 300

    # Asymmetric bias: marginal on P1 but strong on P2 for zone-width-dependent mechanisms
    p2_improvement_pct = (p2_pnl - p2_base_pnl) / p2_base_pnl * 100 if p2_base_pnl > 0 else 0
    p1_improvement_pct = (p1_pnl - baseline_pnl) / baseline_pnl * 100 if baseline_pnl > 0 else 0
    zone_dependent = any(k in p2_label for k in ['hybrid', 'Hybrid', 'Dynamic', 'T2', 'single'])
    asymmetric_promising = zone_dependent and p2_improvement_pct > 15 and abs(p1_improvement_pct) < 5

    if p2_label == "Current ZR 2-leg":
        classification = "baseline"
    elif high_exp:
        classification = "HIGH EXPOSURE"
    elif beats_p1 and beats_p2 and not ks_increase:
        classification = "ACTIONABLE"
    elif beats_p1 and beats_p2:
        classification = "HIGH VARIANCE" if ks_increase else "ACTIONABLE"
    elif asymmetric_promising:
        classification = "PROMISING (P2 strong)"
    elif beats_p1 or beats_p2:
        classification = "PROMISING"
    else:
        classification = "NOT VIABLE"

    pr(f"| {p2_label} | {fmt_pnl(p1_pnl)} | {fmt_pnl(p2_pnl)} | {p1_ks_val} | {p2_ks} | {classification} |")

pr()

# =========================================================================
#  FINAL RECOMMENDATION
# =========================================================================

pr("## FINAL RECOMMENDATION")
pr()

# Find best config that beats baseline on both P1 and P2 with max_single_loss <= 300
risk_adj_candidates = []
for p2_label, p2_s, p2_ks in p2_results:
    for p1_label, p1_s, p1_ks_val, _, _ in all_results:
        if p2_label in p1_label or p1_label.startswith(p2_label[:20]):
            if (p1_s['total_pnl'] > baseline_pnl or p2_s['total_pnl'] > p2_base_pnl):
                risk_adj_candidates.append((p2_label, p1_s, p2_s, p1_ks_val, p2_ks))
            break

# Check if anything beats current on both
actionable = [c for c in risk_adj_candidates
              if c[1]['total_pnl'] > baseline_pnl and c[2]['total_pnl'] > p2_base_pnl
              and c[1]['max_single_loss'] <= 300]

if actionable:
    best = max(actionable, key=lambda c: c[1]['total_pnl'] + c[2]['total_pnl'])
    pr(f"**Recommended config: {best[0]}**")
    pr()
    pr(f"- P1 Total PnL: {fmt_pnl(best[1]['total_pnl'])} ({best[1]['total_pnl']-baseline_pnl:+.1f} vs current)")
    pr(f"- P2 Total PnL: {fmt_pnl(best[2]['total_pnl'])} ({best[2]['total_pnl']-p2_base_pnl:+.1f} vs current)")
    pr(f"- Max single loss: {best[1]['max_single_loss']:.1f}t (within 300t budget)")
    pr(f"- KS triggers: P1={best[3]}, P2={best[4]}")
else:
    pr("**Recommended config: Current ZR 2-leg (no change)**")
    pr()
    pr("No config beats the current ZR 2-leg exit framework on BOTH P1 and P2")
    pr("with acceptable risk (max single loss <= 300t) and stable kill-switch triggers.")
    pr()
    pr("The throughput analysis across 20+ configurations confirms the existing")
    pr("zone-relative 2-leg exit is already optimal:")
    pr()
    pr("**EXACT PARAMETERS (unchanged):**")
    pr("- T1 = 0.5 x zone_width_ticks (67% of position)")
    pr("- T2 = 1.0 x zone_width_ticks (33% of position)")
    pr("- Stop = max(1.5 x zone_width_ticks, 120t)")
    pr("- Time cap = 160 bars")
    pr("- CT entry: 5t limit (20-bar fill window)")
    pr("- WT entry: market at next bar open")
    pr("- No zone-width-based routing")
    pr("- No dynamic T2 exit")
    pr("- No BE step-up")
    pr()

    # Check if any config is PROMISING for paper trade monitoring
    promising = [c for c in risk_adj_candidates
                 if c[2]['total_pnl'] > p2_base_pnl and c[1]['max_single_loss'] <= 300]
    if promising:
        best_p = max(promising, key=lambda c: c[2]['total_pnl'])
        pr(f"> **MONITOR during paper trading:** {best_p[0]} showed P2 improvement")
        pr(f"> ({fmt_pnl(best_p[2]['total_pnl'])} vs {fmt_pnl(p2_base_pnl)} baseline).")
        pr(f"> If paper trading zone width distribution resembles P2 (88% over 100t),")
        pr(f"> this mechanism may become ACTIONABLE.")

pr()
pr("---")
pr("*Sequential freed signal simulation used throughout. P1 primary, P2 cross-validation.")
pr("Kill-switch triggers counted for all configs.*")

# =========================================================================
#  Write output
# =========================================================================

outdir = f'{BASE}/04-backtest/zone_touch/output'
outpath = f'{outdir}/throughput_analysis_part2.md'
with open(outpath, 'w', encoding='utf-8') as f:
    f.write('\n'.join(out))

print(f"\nResults saved to {outpath}", file=sys.stderr)
print("Done.", file=sys.stderr)
