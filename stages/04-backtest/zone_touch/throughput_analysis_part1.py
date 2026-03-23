# archetype: zone_touch
"""
Throughput Optimization Analysis — Part 1 of 2.

Compares ZR vs fixed exits, early exits, single-leg T1, stop tightening,
and BE step-up for throughput improvement. All configs use sequential
freed signal simulation with kill-switch inside the cascade.

P1 is primary. P2 is cross-validation only.

Usage:
    python throughput_analysis_part1.py > output/throughput_analysis_part1.md
"""
import csv, json, sys, math, os
from collections import Counter, defaultdict
from datetime import datetime

# =========================================================================
#  Constants
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

# Load scoring config
with open(f'{BASE}/04-backtest/zone_touch/output/feature_config.json') as f:
    FCFG = json.load(f)
TREND_P33 = FCFG['trend_slope_p33']
TREND_P67 = FCFG['trend_slope_p67']

# =========================================================================
#  Data loading
# =========================================================================

def load_bar_data(path):
    """Load bar data as list of (Open, High, Low, Last, datetime_str)."""
    bars = []
    with open(path) as f:
        for row in csv.DictReader(f):
            r = {k.strip(): v.strip() for k, v in row.items()}
            o = float(r['Open'])
            h = float(r['High'])
            l = float(r['Low'])
            c = float(r['Last'])
            dt = r['Date'].split('.')[0] + ' ' + r['Time'].split('.')[0]
            bars.append((o, h, l, c, dt))
    return bars

def load_p1_touches():
    """Load P1 scored touches from p1_scored_touches_acal.csv."""
    touches = []
    with open(f'{BASE}/04-backtest/zone_touch/output/p1_scored_touches_acal.csv') as f:
        reader = csv.DictReader(f)
        for row in reader:
            touches.append(row)
    return touches

def load_p2_touches():
    """Load P2 raw touches from merged CSVs."""
    touches = []
    for fname in ['NQ_merged_P2a.csv', 'NQ_merged_P2b.csv']:
        with open(f'{BASE}/01-data/output/zone_prep/{fname}') as f:
            for row in csv.DictReader(f):
                rbi = int(row['RotBarIndex'])
                if rbi >= 0:
                    touches.append(row)
    touches.sort(key=lambda r: int(r['RotBarIndex']))
    return touches

print("Loading P1 bar data...", file=sys.stderr)
P1_BARS = load_bar_data(f'{BASE}/01-data/output/zone_prep/NQ_bardata_P1.csv')
N_P1 = len(P1_BARS)
print(f"  {N_P1} bars", file=sys.stderr)

print("Loading P2 bar data...", file=sys.stderr)
P2_BARS = load_bar_data(f'{BASE}/01-data/output/zone_prep/NQ_bardata_P2.csv')
N_P2 = len(P2_BARS)
print(f"  {N_P2} bars", file=sys.stderr)

print("Loading P1 touches...", file=sys.stderr)
P1_RAW = load_p1_touches()
print(f"  {len(P1_RAW)} total P1 touches", file=sys.stderr)

print("Loading P2 touches...", file=sys.stderr)
P2_RAW = load_p2_touches()
print(f"  {len(P2_RAW)} total P2 touches", file=sys.stderr)

# =========================================================================
#  Trend classification
# =========================================================================

def classify_trend(slope):
    if slope <= TREND_P33: return 'CT'
    if slope >= TREND_P67: return 'WT'
    return 'NT'

# =========================================================================
#  P2 scoring (needed for P2 cross-validation)
# =========================================================================

with open(f'{BASE}/04-backtest/zone_touch/output/scoring_model_acal.json') as f:
    MODEL = json.load(f)
WEIGHTS = MODEL['weights']
BIN_EDGES = MODEL['bin_edges']

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

# Build zone history for P2 F10
p2_zone_history = {}
for t in P2_RAW:
    key = (t['ZoneTop'], t['ZoneBot'], t.get('SourceLabel', ''))
    if key not in p2_zone_history:
        p2_zone_history[key] = []
    p2_zone_history[key].append(t)

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
                      WEIGHTS['F10_PriorPenetration'],
                      prior_pen is None)
    f04 = score_f04(touch.get('CascadeState', '').strip(),
                    WEIGHTS['F04_CascadeState'])
    f01 = score_f01(touch.get('SourceLabel', '').strip(),
                    WEIGHTS['F01_Timeframe'])
    f21_str = touch.get('ZoneAgeBars', '').strip()
    f21_raw = float(f21_str) if f21_str else 0.0
    f21 = bin_numeric(f21_raw, BIN_EDGES['F21_ZoneAge'][0],
                      BIN_EDGES['F21_ZoneAge'][1], WEIGHTS['F21_ZoneAge'])
    return f10 + f04 + f01 + f21

# =========================================================================
#  Qualify touches
# =========================================================================

def get_qualifying_p1(touches, n_bars):
    """Filter P1 touches: score >= 16.66, TF <= 120m, valid RotBarIndex."""
    out = []
    for t in touches:
        score = float(t['score_acal'])
        if score < SCORE_THRESHOLD: continue
        tf = TF_MINUTES.get(t.get('SourceLabel', '').strip(), 999)
        if tf > TF_MAX_MINUTES: continue
        rbi_str = t.get('RotBarIndex', '').strip()
        if not rbi_str: continue
        rbi = int(rbi_str)
        if rbi < 0 or rbi + 1 >= n_bars: continue
        # Attach parsed fields
        t['_rbi'] = rbi
        t['_score'] = score
        ts_str = t.get('TrendSlope', '').strip()
        # Handle duplicate TrendSlope columns: use the last one if present
        # The CSV has TrendSlope at col 13 (may be empty) and col 67
        # We need the numeric one
        if not ts_str:
            # Try TrendLabel directly
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
        out.append(t)
    out.sort(key=lambda r: r['_rbi'])
    return out

def get_qualifying_p2(touches, n_bars):
    """Filter P2 touches: score >= 16.66, TF <= 120m."""
    out = []
    for t in touches:
        tf = TF_MINUTES.get(t.get('SourceLabel', '').strip(), 999)
        if tf > TF_MAX_MINUTES: continue
        rbi_str = t.get('RotBarIndex', '').strip()
        if not rbi_str: continue
        rbi = int(rbi_str)
        if rbi < 0 or rbi + 1 >= n_bars: continue
        score = score_p2_touch(t)
        if score < SCORE_THRESHOLD: continue
        t['_rbi'] = rbi
        t['_score'] = score
        ts_str = t.get('TrendSlope', '').strip()
        t['_trend_slope'] = float(ts_str) if ts_str else 0.0
        t['_trend'] = classify_trend(t['_trend_slope'])
        t['_direction'] = 1 if t['TouchType'].strip() == 'DEMAND_EDGE' else -1
        zw_str = t.get('ZoneWidthTicks', '').strip()
        t['_zw'] = float(zw_str) if zw_str else (float(t['ZoneTop']) - float(t['ZoneBot'])) / TICK_SIZE
        t['_seq'] = int(t['TouchSequence'])
        t['_zone_top'] = float(t['ZoneTop'])
        t['_zone_bot'] = float(t['ZoneBot'])
        t['_tf'] = t.get('SourceLabel', '').strip()
        out.append(t)
    out.sort(key=lambda r: r['_rbi'])
    return out

P1_QUAL = get_qualifying_p1(P1_RAW, N_P1)
P2_QUAL = get_qualifying_p2(P2_RAW, N_P2)
print(f"  P1 qualifying: {len(P1_QUAL)}", file=sys.stderr)
print(f"  P2 qualifying: {len(P2_QUAL)}", file=sys.stderr)

# =========================================================================
#  CT limit fill scanner (20-bar window, matches replication harness)
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
            if l <= limit_px:
                return (idx, min(o, limit_px), offset)
        else:
            if h >= limit_px:
                return (idx, max(o, limit_px), offset)
    return None

# =========================================================================
#  Generic 2-leg simulator
# =========================================================================

def sim_2leg(bar_data, entry_bar, ep, direction, t1_ticks, t2_ticks, stop_ticks,
             tcap, n_bars, single_leg=False, be_trigger_ticks=None,
             t2_stop_after_t1=None):
    """
    Generic 2-leg (or single-leg) simulator.

    be_trigger_ticks: if set, move stop to entry after MFE exceeds this value.
                      Applies to full position (both legs).
    t2_stop_after_t1: if set, after T1 fills move stop to this many ticks from
                      entry (0=breakeven, positive=above entry for long).
                      Only affects remaining open legs after T1.

    Returns dict with keys: weighted_pnl, bars_held, leg1_exit, leg2_exit,
           leg1_pnl, leg2_pnl, entry_bar, exit_bar, mfe, mae,
           leg1_exit_bar, leg2_exit_bar, t1_ticks, t2_ticks, stop_ticks
    Or None if entry_bar >= n_bars.
    """
    if entry_bar >= n_bars:
        return None

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

        # MFE/MAE
        if direction == 1:
            bmfe = (h - ep) / TICK_SIZE
            bmae = (ep - l) / TICK_SIZE
        else:
            bmfe = (ep - l) / TICK_SIZE
            bmae = (h - ep) / TICK_SIZE
        if bmfe > mfe: mfe = bmfe
        if bmae > mae: mae = bmae

        # BE step-up check
        if be_trigger_ticks is not None and not be_triggered and mfe >= be_trigger_ticks:
            be_triggered = True
            if direction == 1:
                if ep > stop_px:
                    stop_px = ep
            else:
                if ep < stop_px:
                    stop_px = ep

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
                # T2-only stop tightening after T1 fills
                if t2_stop_after_t1 is not None and leg2_open:
                    if direction == 1:
                        new_sp = ep + t2_stop_after_t1 * TICK_SIZE
                        if new_sp > stop_px:
                            stop_px = new_sp
                    else:
                        new_sp = ep - t2_stop_after_t1 * TICK_SIZE
                        if new_sp < stop_px:
                            stop_px = new_sp

        # T2 (skip if single leg)
        if leg2_open:
            hit = (h >= t2_px) if direction == 1 else (l <= t2_px)
            if hit:
                leg2_pnl = float(t2_ticks); leg2_exit = 'TARGET_2'
                leg2_exit_bar = i; leg2_open = False

        if not leg1_open and not leg2_open:
            break

    # End of data
    if leg1_open or leg2_open:
        last_idx = min(entry_bar + tcap, n_bars - 1)
        last_c = bar_data[last_idx][3]
        pnl = (last_c - ep) / TICK_SIZE if direction == 1 else (ep - last_c) / TICK_SIZE
        if leg1_open:
            leg1_pnl = pnl; leg1_exit = 'END_DATA'; leg1_exit_bar = last_idx
        if leg2_open:
            leg2_pnl = pnl; leg2_exit = 'END_DATA'; leg2_exit_bar = last_idx

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

def sim_forced_exit(bar_data, entry_bar, ep, direction, exit_bars, n_bars):
    """Exit at market after exactly exit_bars bars from entry."""
    if entry_bar >= n_bars: return None
    exit_idx = min(entry_bar + exit_bars - 1, n_bars - 1)
    mfe = mae = 0.0
    for i in range(entry_bar, exit_idx + 1):
        o, h, l, c, dt = bar_data[i]
        if direction == 1:
            bmfe = (h - ep) / TICK_SIZE
            bmae = (ep - l) / TICK_SIZE
        else:
            bmfe = (ep - l) / TICK_SIZE
            bmae = (h - ep) / TICK_SIZE
        if bmfe > mfe: mfe = bmfe
        if bmae > mae: mae = bmae
    last_c = bar_data[exit_idx][3]
    pnl = (last_c - ep) / TICK_SIZE if direction == 1 else (ep - last_c) / TICK_SIZE
    wpnl = pnl - COST_TICKS
    return dict(
        entry_price=ep, weighted_pnl=wpnl, bars_held=exit_bars,
        leg1_exit='FORCED', leg1_pnl=pnl, leg1_exit_bar=exit_idx,
        leg2_exit='NONE', leg2_pnl=0.0, leg2_exit_bar=exit_idx,
        entry_bar=entry_bar, exit_bar=exit_idx, mfe=mfe, mae=mae,
        t1_ticks=0, t2_ticks=0, stop_ticks=0,
    )

# =========================================================================
#  Full sequential simulation with no-overlap + kill-switch
# =========================================================================

def get_exit_params_zr(touch, mode):
    """Zone-relative exit parameters."""
    zw = touch['_zw']
    t1 = max(1, round(0.5 * zw))
    t2 = max(1, round(1.0 * zw))
    stop = max(round(1.5 * zw), 120)
    return t1, t2, stop, 160

def get_exit_params_fixed(touch, mode):
    """Fixed exit parameters (prior config)."""
    if mode == 'CT':
        return 40, 80, 190, 160
    else:
        return 60, 80, 240, 160

def run_full_sim(qualifying, bar_data, n_bars, exit_fn, single_leg=False,
                 ct_limit=True, forced_exit_bars=None, be_trigger_mult=None,
                 stop_override_fn=None, t2_stop_after_t1_fn=None):
    """
    Run full sequential simulation with no-overlap + kill-switch.

    exit_fn(touch, mode) -> (t1_ticks, t2_ticks, stop_ticks, tcap)
    forced_exit_bars: if set, ignore exit_fn and force exit at this bar count
    be_trigger_mult: if set, BE step-up triggers at this fraction of zone width
    t2_stop_after_t1_fn: if set, fn(touch, mode) -> ticks from entry for T2 stop after T1 fills
    stop_override_fn: if set, overrides stop from exit_fn: fn(touch, mode, orig_stop) -> new_stop

    Returns (trades, blocked_qualifying, ks_triggers)
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

    for t in qualifying:
        rbi = t['_rbi']
        wt_entry_bar = rbi + 1
        if wt_entry_bar >= n_bars:
            continue

        direction = t['_direction']
        trend = t['_trend']

        # Mode routing
        if trend == 'CT':
            mode = 'CT'
        else:
            if t['_seq'] > WTNT_SEQ_MAX:
                blocked.append(dict(rbi=rbi, reason='SEQ_FILTER', touch=t))
                continue
            mode = 'WT'

        # CT limit expiry check
        if ct_limit_pending and rbi >= ct_limit_expires_at:
            ct_limit_pending = False

        # Day/week reset for kill-switch
        dt_str = bar_data[wt_entry_bar][4]
        day_str = dt_str.split(' ')[0] if ' ' in dt_str else ''
        if day_str and day_str != ks_last_day:
            ks_daily_pnl = 0.0
            ks_halted = False
            ks_consec = 0
            ks_last_day = day_str
        try:
            d = datetime.strptime(day_str, '%m/%d/%Y')
            wk = f"{d.year}-W{d.isocalendar()[1]}"
        except:
            wk = day_str
        if wk != ks_last_week:
            ks_weekly_pnl = 0.0
            ks_last_week = wk

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
                ct_limit_pending = True  # stays pending until expiry
                blocked.append(dict(rbi=rbi, reason='LIMIT_EXPIRED', touch=t))
                continue
            entry_bar, ep, _ = fill
            ct_limit_pending = False
        else:
            entry_bar = wt_entry_bar
            ep = bar_data[entry_bar][0]  # Open

        # Compute exit params
        if forced_exit_bars is not None:
            result = sim_forced_exit(bar_data, entry_bar, ep, direction,
                                     forced_exit_bars, n_bars)
        else:
            t1, t2, stop, tcap = exit_fn(t, mode)
            if stop_override_fn:
                stop = stop_override_fn(t, mode, stop)
            be_ticks = None
            if be_trigger_mult is not None:
                be_ticks = max(1, round(be_trigger_mult * t['_zw']))
            t2_stop_val = None
            if t2_stop_after_t1_fn is not None:
                t2_stop_val = t2_stop_after_t1_fn(t, mode)
            result = sim_2leg(bar_data, entry_bar, ep, direction,
                              t1, t2 if not single_leg else t1, stop, tcap, n_bars,
                              single_leg=single_leg, be_trigger_ticks=be_ticks,
                              t2_stop_after_t1=t2_stop_val)

        if result is None:
            continue

        in_trade_until = result['exit_bar']

        # Kill-switch update
        wpnl = result['weighted_pnl']
        ks_daily_pnl += wpnl
        ks_weekly_pnl += wpnl
        if wpnl < 0:
            ks_consec += 1
        else:
            ks_consec = 0
        if ks_consec >= KS_CONSEC:
            ks_halted = True
            ks_triggers += 1
        if ks_daily_pnl <= KS_DAILY:
            ks_halted = True
        if ks_weekly_pnl <= KS_WEEKLY:
            ks_halted = True

        trade = dict(
            rbi=rbi, mode=mode, direction=direction,
            zone_width=t['_zw'], seq=t['_seq'], trend=t['_trend'],
            score=t['_score'], tf=t['_tf'],
            zone_top=t['_zone_top'], zone_bot=t['_zone_bot'],
            **result
        )
        trades.append(trade)

    return trades, blocked, ks_triggers

# =========================================================================
#  Stats helpers
# =========================================================================

def calc_stats(trades):
    if not trades:
        return dict(n=0, wr=0, pf=0, ev=0, total_pnl=0, max_dd=0,
                    max_single_loss=0, mean_hold=0, ks_triggers=0)
    pnls = [t['weighted_pnl'] for t in trades]
    wins = sum(1 for p in pnls if p > 0)
    gw = sum(p for p in pnls if p > 0)
    gl = sum(abs(p) for p in pnls if p < 0)
    pf = gw / gl if gl > 0 else float('inf')
    ev = sum(pnls) / len(pnls)
    total = sum(pnls)
    # Max drawdown (peak-to-trough of cumulative PnL)
    cum = 0
    peak = 0
    max_dd = 0
    for p in pnls:
        cum += p
        if cum > peak:
            peak = cum
        dd = peak - cum
        if dd > max_dd:
            max_dd = dd
    max_loss = max((abs(p) for p in pnls if p < 0), default=0)
    mean_hold = sum(t['bars_held'] for t in trades) / len(trades)
    return dict(n=len(trades), wr=100*wins/len(trades), pf=pf, ev=ev,
                total_pnl=total, max_dd=max_dd, max_single_loss=max_loss,
                mean_hold=mean_hold)

def fmt_pf(pf):
    return f"{pf:.2f}" if pf < 9999 else "inf"

def fmt_pnl(v):
    return f"{v:.1f}"

# =========================================================================
#  MFE computation at specific bars
# =========================================================================

def compute_mfe_profile(bar_data, entry_bar, ep, direction, n_bars, max_bar=160):
    """Compute MFE at each bar from entry. Returns list of (bar_offset, mfe_ticks)."""
    mfe = 0.0
    profile = []
    for i in range(entry_bar, min(entry_bar + max_bar + 1, n_bars)):
        o, h, l, c, dt = bar_data[i]
        if direction == 1:
            bmfe = (h - ep) / TICK_SIZE
        else:
            bmfe = (ep - l) / TICK_SIZE
        if bmfe > mfe:
            mfe = bmfe
        profile.append((i - entry_bar + 1, mfe))
    return profile

# =========================================================================
#  Get session hour from bar datetime
# =========================================================================

def get_hour_et(dt_str):
    """Extract hour (ET) from datetime string."""
    try:
        parts = dt_str.split(' ')
        time_parts = parts[1].split(':') if len(parts) > 1 else ['0']
        return int(time_parts[0])
    except:
        return 0

# =========================================================================
#  MAIN ANALYSIS
# =========================================================================

out = []  # markdown output lines

def pr(s=''):
    out.append(s)

pr("# Throughput Optimization Analysis — Part 1 of 2")
pr()
pr(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
pr(f"P1 bars: {N_P1:,} | P1 qualifying signals: {len(P1_QUAL)}")
pr(f"P2 bars: {N_P2:,} | P2 qualifying signals: {len(P2_QUAL)}")
pr()

# =========================================================================
#  Run baseline simulations (needed throughout)
# =========================================================================

print("Running P1 ZR baseline...", file=sys.stderr)
p1_zr_trades, p1_zr_blocked, p1_zr_ks = run_full_sim(
    P1_QUAL, P1_BARS, N_P1, get_exit_params_zr, ct_limit=True)

print("Running P1 Fixed baseline...", file=sys.stderr)
p1_fix_trades, p1_fix_blocked, p1_fix_ks = run_full_sim(
    P1_QUAL, P1_BARS, N_P1, get_exit_params_fixed, ct_limit=True)

print("Running P2 ZR baseline...", file=sys.stderr)
p2_zr_trades, p2_zr_blocked, p2_zr_ks = run_full_sim(
    P2_QUAL, P2_BARS, N_P2, get_exit_params_zr, ct_limit=True)

print("Running P2 Fixed baseline...", file=sys.stderr)
p2_fix_trades, p2_fix_blocked, p2_fix_ks = run_full_sim(
    P2_QUAL, P2_BARS, N_P2, get_exit_params_fixed, ct_limit=True)

# Track traded RBI sets for freed signal counting
p1_zr_rbis = set(t['rbi'] for t in p1_zr_trades)

def freed_count(trades, baseline_rbis):
    """Count trades not in baseline (freed signals)."""
    return sum(1 for t in trades if t['rbi'] not in baseline_rbis)

def freed_pnl(trades, baseline_rbis):
    """Sum PnL of trades not in baseline."""
    return sum(t['weighted_pnl'] for t in trades if t['rbi'] not in baseline_rbis)

def original_pnl(trades, baseline_rbis):
    """Sum PnL of trades that ARE in baseline."""
    return sum(t['weighted_pnl'] for t in trades if t['rbi'] in baseline_rbis)

# =========================================================================
#  Write P1 answer keys
# =========================================================================

def write_answer_key(trades, blocked, filename, label):
    """Write answer key CSV."""
    outdir = f'{BASE}/04-backtest/zone_touch/output'
    cols = ['rbi', 'mode', 'direction', 'zone_width', 'entry_price',
            'weighted_pnl', 'bars_held', 'leg1_exit', 'leg1_pnl',
            'leg2_exit', 'leg2_pnl', 'mfe', 'mae', 't1_ticks', 't2_ticks',
            'stop_ticks', 'entry_bar', 'exit_bar', 'score', 'trend', 'tf']
    with open(f'{outdir}/{filename}', 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=cols, extrasaction='ignore')
        writer.writeheader()
        for t in trades:
            writer.writerow(t)

    # Write blocked signals
    skip_cols = ['rbi', 'reason']
    skip_file = filename.replace('answer_key', 'skipped_signals')
    with open(f'{outdir}/{skip_file}', 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=skip_cols, extrasaction='ignore')
        writer.writeheader()
        for b in blocked:
            writer.writerow(b)

    print(f"  Wrote {len(trades)} trades to {filename}, {len(blocked)} blocked to {skip_file}", file=sys.stderr)

print("Writing P1 answer keys...", file=sys.stderr)
write_answer_key(p1_zr_trades, p1_zr_blocked,
                 'p1_twoleg_answer_key_zr.csv', 'P1 ZR')
write_answer_key(p1_fix_trades, p1_fix_blocked,
                 'p1_twoleg_answer_key_fixed.csv', 'P1 Fixed')

# Also generate P2 fixed answer key if needed
write_answer_key(p2_fix_trades, p2_fix_blocked,
                 'p2_twoleg_answer_key_fixed_v2.csv', 'P2 Fixed')

# =========================================================================
#  SECTION 1: Signal Arrival Patterns
# =========================================================================

print("Section 1: Signal arrival patterns...", file=sys.stderr)
pr("=" * 70)
pr("## SECTION 1: SIGNAL ARRIVAL PATTERNS")
pr("=" * 70)
pr()

# A) Signal arrival rate
gaps = []
for i in range(1, len(P1_QUAL)):
    gap = P1_QUAL[i]['_rbi'] - P1_QUAL[i-1]['_rbi']
    gaps.append(gap)

if gaps:
    gaps_s = sorted(gaps)
    mean_gap = sum(gaps) / len(gaps)
    median_gap = gaps_s[len(gaps_s)//2]
    p10 = gaps_s[int(0.1 * len(gaps_s))]
    p90 = gaps_s[int(0.9 * len(gaps_s))]
    pr("### A) Signal Arrival Rate (P1)")
    pr()
    pr(f"- Mean bars between signals: **{mean_gap:.1f}**")
    pr(f"- Median bars between signals: **{median_gap}**")
    pr(f"- P10: **{p10}** bars | P90: **{p90}** bars")
    pr()

# Hourly table
hour_bins = [(6,8), (8,10), (10,12), (12,14), (14,16), (16,18)]
traded_rbis = set(t['rbi'] for t in p1_zr_trades)
blocked_in_pos = set(b['rbi'] for b in p1_zr_blocked if b['reason'] == 'IN_POSITION')

pr("| Hour (ET) | Qualifying signals | Trades (ZR) | Blocked (IN_POSITION) |")
pr("|-----------|-------------------|-------------|----------------------|")
for lo, hi in hour_bins:
    sig_count = 0
    trade_count = 0
    block_count = 0
    for t in P1_QUAL:
        hr = get_hour_et(P1_BARS[min(t['_rbi'] + 1, N_P1 - 1)][4])
        if lo <= hr < hi:
            sig_count += 1
            if t['_rbi'] in traded_rbis:
                trade_count += 1
            elif t['_rbi'] in blocked_in_pos:
                block_count += 1
    pr(f"| {lo:02d}-{hi:02d} | {sig_count} | {trade_count} | {block_count} |")
pr()

# B) Cluster detection
pr("### B) Cluster Detection (P1)")
pr()
# Find clusters: signals within 20 bars of each other
clusters_2 = 0
clusters_3plus = 0
signals_in_2 = 0
signals_in_3plus = 0
i = 0
while i < len(P1_QUAL):
    cluster = [P1_QUAL[i]]
    j = i + 1
    while j < len(P1_QUAL) and P1_QUAL[j]['_rbi'] - cluster[-1]['_rbi'] <= 20:
        cluster.append(P1_QUAL[j])
        j += 1
    if len(cluster) == 2:
        clusters_2 += 1
        signals_in_2 += 2
    elif len(cluster) >= 3:
        clusters_3plus += 1
        signals_in_3plus += len(cluster)
    i = j if len(cluster) > 1 else i + 1

total_sigs = len(P1_QUAL)
pr("| Cluster size | Occurrences | Signals in clusters | % of all signals |")
pr("|-------------|-------------|--------------------|-----------------| ")
pr(f"| 2 signals within 20 bars | {clusters_2} | {signals_in_2} | {100*signals_in_2/total_sigs:.1f}% |")
pr(f"| 3+ signals within 20 bars | {clusters_3plus} | {signals_in_3plus} | {100*signals_in_3plus/total_sigs:.1f}% |")
pr()

# C) Blocked signal hour concentration
pr("### C) Blocked Signal Hour Concentration")
pr()
pr("| Hour (ET) | Blocked (IN_POSITION) | % of all blocked |")
pr("|-----------|----------------------|-----------------|")
total_blocked_ip = len(blocked_in_pos)
for lo, hi in hour_bins:
    count = 0
    for b in p1_zr_blocked:
        if b['reason'] != 'IN_POSITION': continue
        hr = get_hour_et(P1_BARS[min(b['rbi'] + 1, N_P1 - 1)][4])
        if lo <= hr < hi:
            count += 1
    pct = 100*count/total_blocked_ip if total_blocked_ip > 0 else 0
    pr(f"| {lo:02d}-{hi:02d} | {count} | {pct:.1f}% |")
pr()

# D) Blocking by zone type
pr("### D) Blocking by Zone Type")
pr()
# For each blocked IN_POSITION signal, check if it's same zone as current trade
# We need to match blocked signal to the trade blocking it
same_zone_blocks = []
diff_zone_same_tf_blocks = []
diff_zone_diff_tf_blocks = []

for b in p1_zr_blocked:
    if b['reason'] != 'IN_POSITION': continue
    bt = b['touch']
    b_zone = (bt['_zone_top'], bt['_zone_bot'])
    b_tf = bt['_tf']
    # Find blocking trade
    blocking_trade = None
    for tr in p1_zr_trades:
        if tr['entry_bar'] <= bt['_rbi'] + 1 <= tr['exit_bar']:
            blocking_trade = tr
            break
    if blocking_trade is None: continue
    tr_zone = (blocking_trade['zone_top'], blocking_trade['zone_bot'])
    tr_tf = blocking_trade['tf']
    if b_zone == tr_zone:
        same_zone_blocks.append(b)
    elif b_tf == tr_tf:
        diff_zone_same_tf_blocks.append(b)
    else:
        diff_zone_diff_tf_blocks.append(b)

def hyp_pnl_blocked(blocks):
    """Hypothetical score mean for blocked signals."""
    if not blocks: return 0, 0
    scores = [b['touch']['_score'] for b in blocks]
    return sum(scores)/len(scores), len(blocks)

pr("| Block type | Count | Mean score | Addressable? |")
pr("|-----------|-------|-----------|-------------|")
s_sc, s_n = hyp_pnl_blocked(same_zone_blocks)
d1_sc, d1_n = hyp_pnl_blocked(diff_zone_same_tf_blocks)
d2_sc, d2_n = hyp_pnl_blocked(diff_zone_diff_tf_blocks)
pr(f"| Same zone as current trade | {s_n} | {s_sc:.2f} | NO |")
pr(f"| Different zone, same TF | {d1_n} | {d1_sc:.2f} | YES |")
pr(f"| Different zone, different TF | {d2_n} | {d2_sc:.2f} | YES |")
addressable = d1_n + d2_n
total_ip = s_n + d1_n + d2_n
pr(f"\n**Addressable fraction: {addressable}/{total_ip} = {100*addressable/total_ip:.1f}%**" if total_ip > 0 else "")
pr()

# P2 cross-validation: arrival patterns
pr("### P2 Cross-Validation: Signal Arrival")
pr()
p2_gaps = []
for i in range(1, len(P2_QUAL)):
    p2_gaps.append(P2_QUAL[i]['_rbi'] - P2_QUAL[i-1]['_rbi'])
if p2_gaps:
    p2_mean_gap = sum(p2_gaps) / len(p2_gaps)
    p2_median_gap = sorted(p2_gaps)[len(p2_gaps)//2]
    pr(f"- P2 mean gap: {p2_mean_gap:.1f} bars | P2 median gap: {p2_median_gap}")
    pr(f"- P1 mean gap: {mean_gap:.1f} bars | P1 median gap: {median_gap}")
    pr(f"- Density similar: {'YES' if abs(p2_mean_gap - mean_gap) / mean_gap < 0.3 else 'NO'}")
pr()

# P2 clusters
i = 0
p2_c2 = p2_c3 = p2_s2 = p2_s3 = 0
while i < len(P2_QUAL):
    cluster = [P2_QUAL[i]]
    j = i + 1
    while j < len(P2_QUAL) and P2_QUAL[j]['_rbi'] - cluster[-1]['_rbi'] <= 20:
        cluster.append(P2_QUAL[j])
        j += 1
    if len(cluster) == 2: p2_c2 += 1; p2_s2 += 2
    elif len(cluster) >= 3: p2_c3 += 1; p2_s3 += len(cluster)
    i = j if len(cluster) > 1 else i + 1
p2_total = len(P2_QUAL)
pr(f"P2 clusters: 2-signal={p2_c2} ({100*p2_s2/p2_total:.1f}%), 3+={p2_c3} ({100*p2_s3/p2_total:.1f}%)")
pr()

# =========================================================================
#  SECTION 2: Time-to-Profit Curves
# =========================================================================

print("Section 2: MFE curves...", file=sys.stderr)
pr("=" * 70)
pr("## SECTION 2: TIME-TO-PROFIT CURVES (MFE)")
pr("=" * 70)
pr()

# Compute MFE profiles for all P1 ZR trades
bar_checkpoints = [5, 10, 15, 20, 30, 40, 50, 75, 100, 120, 160]
zw_bins = [(50, 100), (100, 150), (150, 200), (200, 300), (300, 9999)]
zw_labels = ['50-100t', '100-150t', '150-200t', '200-300t', '300t+']

# Collect MFE profiles per trade
trade_profiles = []
for tr in p1_zr_trades:
    prof = compute_mfe_profile(P1_BARS, tr['entry_bar'], tr['entry_price'],
                                tr['direction'], N_P1, 160)
    # Convert to dict: bar_offset -> mfe
    prof_dict = {bh: mfe for bh, mfe in prof}
    trade_profiles.append((tr, prof_dict))

pr("### MFE by Zone Width (absolute ticks)")
pr()
header = "| Zone width | N |"
for b in [10, 20, 30, 50, 100]:
    header += f" MFE@{b} |"
header += " Final MFE |"
pr(header)
pr("|" + "---|" * (len([10,20,30,50,100]) + 3))

for bi, (lo, hi) in enumerate(zw_bins):
    bin_trades = [(tr, prof) for tr, prof in trade_profiles
                  if lo <= tr['zone_width'] < hi]
    n = len(bin_trades)
    flag = " LOW SAMPLE" if n < 8 else ""
    row = f"| {zw_labels[bi]} | {n}{flag} |"
    for b in [10, 20, 30, 50, 100]:
        if n > 0:
            vals = [prof.get(b, 0) for _, prof in bin_trades]
            row += f" {sum(vals)/len(vals):.1f} |"
        else:
            row += " — |"
    if n > 0:
        finals = [tr['mfe'] for tr, _ in bin_trades]
        row += f" {sum(finals)/len(finals):.1f} |"
    else:
        row += " — |"
    pr(row)
pr()

pr("### MFE as Fraction of Zone Width")
pr()
header2 = "| Zone width | N |"
for b in [10, 20, 30, 50]:
    header2 += f" MFE/ZW @{b} |"
pr(header2)
pr("|" + "---|" * (len([10,20,30,50]) + 2))

for bi, (lo, hi) in enumerate(zw_bins):
    bin_trades = [(tr, prof) for tr, prof in trade_profiles
                  if lo <= tr['zone_width'] < hi]
    n = len(bin_trades)
    flag = " LOW SAMPLE" if n < 8 else ""
    row = f"| {zw_labels[bi]} | {n}{flag} |"
    for b in [10, 20, 30, 50]:
        if n > 0:
            vals = [prof.get(b, 0) / tr['zone_width'] for tr, prof in bin_trades if tr['zone_width'] > 0]
            row += f" {sum(vals)/len(vals):.3f} |" if vals else " — |"
        else:
            row += " — |"
    pr(row)
pr()

# Bar where MFE/ZW reaches 80%
pr("### MFE/ZW Plateau Analysis")
pr()
for period_label, trades_profiles in [("P1", trade_profiles)]:
    all_frac_by_bar = defaultdict(list)
    for tr, prof in trades_profiles:
        zw = tr['zone_width']
        if zw <= 0: continue
        for bh in range(1, 161):
            mfe_val = prof.get(bh, 0)
            all_frac_by_bar[bh].append(mfe_val / zw)
    # Find bar where mean MFE/ZW >= 0.8
    bar_80 = None
    for bh in range(1, 161):
        if bh in all_frac_by_bar:
            mean_frac = sum(all_frac_by_bar[bh]) / len(all_frac_by_bar[bh])
            if mean_frac >= 0.8:
                bar_80 = bh
                break
    pr(f"- {period_label}: MFE/ZW reaches 80% at bar **{bar_80}**" if bar_80 else f"- {period_label}: MFE/ZW never reaches 80% within 160 bars")

# Same for P2
p2_profiles = []
for tr in p2_zr_trades:
    prof = compute_mfe_profile(P2_BARS, tr['entry_bar'], tr['entry_price'],
                                tr['direction'], N_P2, 160)
    prof_dict = {bh: mfe for bh, mfe in prof}
    p2_profiles.append((tr, prof_dict))

p2_frac_by_bar = defaultdict(list)
for tr, prof in p2_profiles:
    zw = tr['zone_width']
    if zw <= 0: continue
    for bh in range(1, 161):
        p2_frac_by_bar[bh].append(prof.get(bh, 0) / zw)

p2_bar_80 = None
for bh in range(1, 161):
    if bh in p2_frac_by_bar:
        if sum(p2_frac_by_bar[bh]) / len(p2_frac_by_bar[bh]) >= 0.8:
            p2_bar_80 = bh
            break
pr(f"- P2: MFE/ZW reaches 80% at bar **{p2_bar_80}**" if p2_bar_80 else "- P2: MFE/ZW never reaches 80%")
pr()

# MFE/ZW by CT vs WT
pr("### MFE/ZW by Mode (CT vs WT)")
pr()
pr("| Mode | N | MFE/ZW @10 | MFE/ZW @20 | MFE/ZW @30 | MFE/ZW @50 |")
pr("|------|---|-----------|-----------|-----------|-----------|")
for mode_label in ['CT', 'WT']:
    mode_trades = [(tr, prof) for tr, prof in trade_profiles
                   if tr['mode'] == mode_label]
    n = len(mode_trades)
    row = f"| {mode_label} | {n} |"
    for b in [10, 20, 30, 50]:
        if n > 0:
            vals = [prof.get(b, 0) / tr['zone_width'] for tr, prof in mode_trades if tr['zone_width'] > 0]
            row += f" {sum(vals)/len(vals):.3f} |" if vals else " — |"
        else:
            row += " — |"
    pr(row)
pr()

# =========================================================================
#  SECTION 3: Early Exit Simulations
# =========================================================================

print("Section 3: Early exit simulations...", file=sys.stderr)
pr("=" * 70)
pr("## SECTION 3: EARLY EXIT SIMULATIONS")
pr("=" * 70)
pr()

forced_bars = [10, 15, 20, 30, 50, 75]
forced_results = {}

for fb in forced_bars:
    print(f"  Forced exit at bar {fb}...", file=sys.stderr)
    trades, blocked, ks = run_full_sim(
        P1_QUAL, P1_BARS, N_P1, get_exit_params_zr,
        ct_limit=True, forced_exit_bars=fb)
    forced_results[fb] = (trades, blocked, ks)

# Also run fixed exits with freed signals
pr("### Early Exit — Original Trades")
pr()
pr("| Exit config | Trades | Mean PnL | Total PnL | WR | Freed signals | KS triggers |")
pr("|------------|--------|---------|-----------|-----|--------------|-------------|")

for fb in forced_bars:
    trades, blocked, ks = forced_results[fb]
    s = calc_stats(trades)
    freed = freed_count(trades, p1_zr_rbis)
    pr(f"| {fb} bars | {s['n']} | {s['ev']:.1f} | {fmt_pnl(s['total_pnl'])} | {s['wr']:.1f}% | {freed} | {ks} |")

# Current ZR baseline
zr_s = calc_stats(p1_zr_trades)
pr(f"| Current ZR | {zr_s['n']} | {zr_s['ev']:.1f} | {fmt_pnl(zr_s['total_pnl'])} | {zr_s['wr']:.1f}% | 0 | {p1_zr_ks} |")

# Fixed exits
fix_s = calc_stats(p1_fix_trades)
fix_freed = freed_count(p1_fix_trades, p1_zr_rbis)
pr(f"| Fixed exits | {fix_s['n']} | {fix_s['ev']:.1f} | {fmt_pnl(fix_s['total_pnl'])} | {fix_s['wr']:.1f}% | {fix_freed} | {p1_fix_ks} |")
pr()

# Combined table (original + unblocked breakdown)
pr("### Combined Result (Original + Freed PnL)")
pr()
pr("| Exit config | Original PnL | Freed PnL | TOTAL PnL | vs current | KS triggers |")
pr("|------------|-------------|-----------|-----------|------------|-------------|")

zr_total = zr_s['total_pnl']
for fb in forced_bars:
    trades, blocked, ks = forced_results[fb]
    s = calc_stats(trades)
    orig = original_pnl(trades, p1_zr_rbis)
    freed_p = freed_pnl(trades, p1_zr_rbis)
    delta = s['total_pnl'] - zr_total
    pr(f"| {fb} bars | {fmt_pnl(orig)} | {fmt_pnl(freed_p)} | {fmt_pnl(s['total_pnl'])} | {delta:+.1f} | {ks} |")

pr(f"| Current ZR | {fmt_pnl(zr_total)} | 0 | {fmt_pnl(zr_total)} | baseline | {p1_zr_ks} |")
fix_orig = original_pnl(p1_fix_trades, p1_zr_rbis)
fix_freed_p = freed_pnl(p1_fix_trades, p1_zr_rbis)
fix_delta = fix_s['total_pnl'] - zr_total
pr(f"| Fixed exits + freed | {fmt_pnl(fix_orig)} | {fmt_pnl(fix_freed_p)} | {fmt_pnl(fix_s['total_pnl'])} | {fix_delta:+.1f} | {p1_fix_ks} |")
pr()

# P2 cross-validation of best forced exit bar
best_fb = max(forced_bars, key=lambda fb: calc_stats(forced_results[fb][0])['total_pnl'])
print(f"  P2 cross-val: forced exit at bar {best_fb}...", file=sys.stderr)
p2_forced_trades, _, p2_forced_ks = run_full_sim(
    P2_QUAL, P2_BARS, N_P2, get_exit_params_zr, ct_limit=True, forced_exit_bars=best_fb)
p2_forced_s = calc_stats(p2_forced_trades)
p2_zr_s = calc_stats(p2_zr_trades)

pr("### P2 Cross-Validation (Best P1 Forced Exit)")
pr()
pr(f"| Period | Best exit bar | Total PnL | vs current | Consistent? |")
pr(f"|--------|-------------|-----------|------------|-------------|")
pr(f"| P1 | {best_fb} | {fmt_pnl(calc_stats(forced_results[best_fb][0])['total_pnl'])} | baseline | — |")
p2_delta = p2_forced_s['total_pnl'] - p2_zr_s['total_pnl']
consistent = "YES" if p2_delta > 0 else "NO"
pr(f"| P2 | {best_fb} | {fmt_pnl(p2_forced_s['total_pnl'])} | {p2_delta:+.1f} | {consistent} |")
pr()

# =========================================================================
#  SECTION 4: Single-Leg T1 Throughput
# =========================================================================

print("Section 4: Single-leg T1...", file=sys.stderr)
pr("=" * 70)
pr("## SECTION 4: SINGLE-LEG T1 THROUGHPUT")
pr("=" * 70)
pr()

# ZR single-leg T1
print("  ZR single-leg...", file=sys.stderr)
p1_zr_t1_trades, p1_zr_t1_blocked, p1_zr_t1_ks = run_full_sim(
    P1_QUAL, P1_BARS, N_P1, get_exit_params_zr, single_leg=True, ct_limit=True)

# Fixed single-leg T1
def get_exit_params_fixed_t1(touch, mode):
    if mode == 'CT': return 40, 40, 190, 160
    else: return 60, 60, 240, 160

print("  Fixed single-leg...", file=sys.stderr)
p1_fix_t1_trades, p1_fix_t1_blocked, p1_fix_t1_ks = run_full_sim(
    P1_QUAL, P1_BARS, N_P1, get_exit_params_fixed_t1, single_leg=True, ct_limit=True)

pr("### A) Single-Leg Baseline")
pr()
pr("| Strategy | Trades | Mean hold | Mean PnL | Total PnL | Blocked | KS triggers |")
pr("|----------|--------|----------|---------|-----------|---------|-------------|")

zr_s = calc_stats(p1_zr_trades)
fix_s = calc_stats(p1_fix_trades)
zr_t1_s = calc_stats(p1_zr_t1_trades)
fix_t1_s = calc_stats(p1_fix_t1_trades)

blocked_ip_zr = sum(1 for b in p1_zr_blocked if b['reason'] == 'IN_POSITION')
blocked_ip_fix = sum(1 for b in p1_fix_blocked if b['reason'] == 'IN_POSITION')
blocked_ip_zr_t1 = sum(1 for b in p1_zr_t1_blocked if b['reason'] == 'IN_POSITION')
blocked_ip_fix_t1 = sum(1 for b in p1_fix_t1_blocked if b['reason'] == 'IN_POSITION')

pr(f"| 2-leg ZR (current) | {zr_s['n']} | {zr_s['mean_hold']:.1f} | {zr_s['ev']:.1f} | {fmt_pnl(zr_s['total_pnl'])} | {blocked_ip_zr} | {p1_zr_ks} |")
pr(f"| 2-leg Fixed | {fix_s['n']} | {fix_s['mean_hold']:.1f} | {fix_s['ev']:.1f} | {fmt_pnl(fix_s['total_pnl'])} | {blocked_ip_fix} | {p1_fix_ks} |")
pr(f"| ZR single-leg T1 | {zr_t1_s['n']} | {zr_t1_s['mean_hold']:.1f} | {zr_t1_s['ev']:.1f} | {fmt_pnl(zr_t1_s['total_pnl'])} | {blocked_ip_zr_t1} | {p1_zr_t1_ks} |")
pr(f"| Fixed single-leg T1 | {fix_t1_s['n']} | {fix_t1_s['mean_hold']:.1f} | {fix_t1_s['ev']:.1f} | {fmt_pnl(fix_t1_s['total_pnl'])} | {blocked_ip_fix_t1} | {p1_fix_t1_ks} |")
pr()

# B) T2 runner marginal value
pr("### B) T2 Runner Marginal Value (ZR exits)")
pr()

zw_bins_t2 = [(0, 150), (150, 250), (250, 9999)]
zw_labels_t2 = ['ZW < 150t', '150-250t', '250t+']

# For ZR trades where T1 filled (removed stale header — actual tables printed below)

# Collect T2 marginal data from ZR 2-leg trades
t1_filled_zr = [t for t in p1_zr_trades if t['leg1_exit'] == 'TARGET_1']

def t2_marginal_table(trades, blocked_list, qualifying, bar_data, n_bars,
                      exit_fn, zw_bins, zw_labels):
    """Compute T2 marginal value table with blocked-after-T1 analysis."""
    lines = []

    t1_filled = [t for t in trades if t['leg1_exit'] == 'TARGET_1']

    def bin_trades(tlist, lo, hi):
        return [t for t in tlist if lo <= t['zone_width'] < hi]

    all_bins = [(0, 99999)] + list(zip([b[0] for b in zw_bins], [b[1] for b in zw_bins]))

    # T1 filled count
    row = "| Trades where T1 filled |"
    for lo, hi in all_bins:
        row += f" {len(bin_trades(t1_filled, lo, hi))} |"
    lines.append(row)

    # Mean bars T1 fill -> final exit
    row = "| Mean bars T1->T2 exit |"
    for lo, hi in all_bins:
        bt = bin_trades(t1_filled, lo, hi)
        if bt:
            vals = [t['exit_bar'] - t['leg1_exit_bar'] for t in bt]
            row += f" {sum(vals)/len(vals):.1f} |"
        else:
            row += " --- |"
    lines.append(row)

    # Mean T2 marginal PnL
    row = "| Mean T2 marginal PnL |"
    for lo, hi in all_bins:
        bt = bin_trades(t1_filled, lo, hi)
        if bt:
            vals = [LEG2_W * t['leg2_pnl'] for t in bt]
            row += f" {sum(vals)/len(vals):.1f} |"
        else:
            row += " --- |"
    lines.append(row)

    # Signals blocked after T1 fill (during T2 hold window)
    # For each T1-filled trade, find qualifying signals with rbi+1 in [leg1_exit_bar+1, exit_bar]
    # that are blocked IN_POSITION
    blocked_after_t1_by_bin = {(lo, hi): [] for lo, hi in all_bins}
    ip_blocked_rbis = set(b['rbi'] for b in blocked_list if b['reason'] == 'IN_POSITION')

    for tr in t1_filled:
        t1_bar = tr['leg1_exit_bar']
        final_bar = tr['exit_bar']
        tr_zw = tr['zone_width']
        # Find blocked signals in T2 window
        for q in qualifying:
            q_entry = q['_rbi'] + 1
            if q_entry <= t1_bar or q_entry > final_bar:
                continue
            if q['_rbi'] not in ip_blocked_rbis:
                continue
            for (lo, hi) in all_bins:
                if lo <= tr_zw < hi:
                    blocked_after_t1_by_bin[(lo, hi)].append(q)

    row = "| Signals blocked after T1 |"
    for lo, hi in all_bins:
        row += f" {len(blocked_after_t1_by_bin[(lo, hi)])} |"
    lines.append(row)

    # Hypothetical value of blocked signals (simulate them with same exit framework)
    row = "| Blocked signal hyp value |"
    for lo, hi in all_bins:
        bsigs = blocked_after_t1_by_bin[(lo, hi)]
        if not bsigs:
            row += " 0.0 |"
            continue
        hyp_pnl = 0.0
        for q in bsigs:
            direction = q['_direction']
            trend = q['_trend']
            mode = 'CT' if trend == 'CT' else 'WT'
            entry_bar_q = q['_rbi'] + 1
            if entry_bar_q >= n_bars:
                continue
            ep_q = bar_data[entry_bar_q][0]
            t1_q, t2_q, stop_q, tcap_q = exit_fn(q, mode)
            r = sim_2leg(bar_data, entry_bar_q, ep_q, direction,
                         t1_q, t2_q, stop_q, tcap_q, n_bars)
            if r:
                hyp_pnl += r['weighted_pnl']
        row += f" {hyp_pnl:.1f} |"
    lines.append(row)

    return lines

pr("**ZR exits (T2 = 1.0x zone_width):**")
pr()
header = "| Metric | All |"
for lbl in zw_labels_t2:
    header += f" {lbl} |"
pr(header)
pr("|" + "---|" * (len(zw_labels_t2) + 2))
for line in t2_marginal_table(p1_zr_trades, p1_zr_blocked, P1_QUAL, P1_BARS, N_P1,
                              get_exit_params_zr, zw_bins_t2, zw_labels_t2):
    pr(line)
pr()

pr("**Fixed exits (T2 = 80t):**")
pr()
header = "| Metric | All |"
for lbl in zw_labels_t2:
    header += f" {lbl} |"
pr(header)
pr("|" + "---|" * (len(zw_labels_t2) + 2))
for line in t2_marginal_table(p1_fix_trades, p1_fix_blocked, P1_QUAL, P1_BARS, N_P1,
                              get_exit_params_fixed, zw_bins_t2, zw_labels_t2):
    pr(line)
pr()

# P2 cross-validation
pr("### P2 Cross-Validation (Single-Leg T1)")
pr()
p2_zr_t1_trades, _, p2_zr_t1_ks = run_full_sim(
    P2_QUAL, P2_BARS, N_P2, get_exit_params_zr, single_leg=True, ct_limit=True)
p2_fix_t1_trades, _, p2_fix_t1_ks = run_full_sim(
    P2_QUAL, P2_BARS, N_P2, get_exit_params_fixed_t1, single_leg=True, ct_limit=True)

p2_zr_s = calc_stats(p2_zr_trades)
p2_fix_s = calc_stats(p2_fix_trades)
p2_zr_t1_s = calc_stats(p2_zr_t1_trades)
p2_fix_t1_s = calc_stats(p2_fix_t1_trades)

pr("| Period | Config | 2-leg Total PnL | T1-only Total PnL | Winner |")
pr("|--------|--------|----------------|-------------------|--------|")
zr_w = "2-leg" if p2_zr_s['total_pnl'] >= p2_zr_t1_s['total_pnl'] else "T1-only"
fix_w = "2-leg" if p2_fix_s['total_pnl'] >= p2_fix_t1_s['total_pnl'] else "T1-only"
pr(f"| P1 | ZR | {fmt_pnl(zr_s['total_pnl'])} | {fmt_pnl(zr_t1_s['total_pnl'])} | {'2-leg' if zr_s['total_pnl'] >= zr_t1_s['total_pnl'] else 'T1-only'} |")
pr(f"| P1 | Fixed | {fmt_pnl(fix_s['total_pnl'])} | {fmt_pnl(fix_t1_s['total_pnl'])} | {'2-leg' if fix_s['total_pnl'] >= fix_t1_s['total_pnl'] else 'T1-only'} |")
pr(f"| P2 | ZR | {fmt_pnl(p2_zr_s['total_pnl'])} | {fmt_pnl(p2_zr_t1_s['total_pnl'])} | {zr_w} |")
pr(f"| P2 | Fixed | {fmt_pnl(p2_fix_s['total_pnl'])} | {fmt_pnl(p2_fix_t1_s['total_pnl'])} | {fix_w} |")
pr()

# =========================================================================
#  SECTION 5: Speed-at-Entry as Predictor
# =========================================================================

print("Section 5: Speed-at-entry...", file=sys.stderr)
pr("=" * 70)
pr("## SECTION 5: SPEED-AT-ENTRY AS PREDICTOR")
pr("=" * 70)
pr()

# For each trade, determine if T1 was fast (<15 bars) or slow (>30 bars)
fast_trades = [t for t in p1_zr_trades if t['leg1_exit'] == 'TARGET_1' and (t['leg1_exit_bar'] - t['entry_bar'] + 1) < 15]
slow_trades = [t for t in p1_zr_trades if t['leg1_exit'] == 'TARGET_1' and (t['leg1_exit_bar'] - t['entry_bar'] + 1) > 30]

pr("### A) Features Correlated with Speed")
pr()
pr("| Feature | Fast MFE (T1 in <15 bars) | Slow MFE (T1 in >30 bars) |")
pr("|---------|--------------------------|--------------------------|")

def mean_or_dash(trades, key):
    vals = [t.get(key, 0) for t in trades]
    return f"{sum(vals)/len(vals):.1f}" if vals else "—"

def pct_mode(trades, mode_val):
    if not trades: return "—"
    return f"{100*sum(1 for t in trades if t['mode'] == mode_val)/len(trades):.1f}%"

def pct_rth(trades, bar_data, n_bars):
    if not trades: return "—"
    rth = sum(1 for t in trades if 930 <= _hhmm(bar_data[min(t['entry_bar'], n_bars-1)][4]) < 1615)
    return f"{100*rth/len(trades):.1f}%"

def _hhmm(dt_str):
    try:
        parts = dt_str.split(' ')
        tp = parts[1].split(':') if len(parts) > 1 else ['0','0']
        return int(tp[0]) * 100 + int(tp[1])
    except:
        return 0

pr(f"| Mean zone width | {mean_or_dash(fast_trades, 'zone_width')} | {mean_or_dash(slow_trades, 'zone_width')} |")

fast_margins = [t['score'] - SCORE_THRESHOLD for t in fast_trades]
slow_margins = [t['score'] - SCORE_THRESHOLD for t in slow_trades]
fm_str = f"{sum(fast_margins)/len(fast_margins):.2f}" if fast_margins else "—"
sm_str = f"{sum(slow_margins)/len(slow_margins):.2f}" if slow_margins else "—"
pr(f"| Mean score margin | {fm_str} | {sm_str} |")
pr(f"| % CT | {pct_mode(fast_trades, 'CT')} | {pct_mode(slow_trades, 'CT')} |")
pr(f"| % RTH | {pct_rth(fast_trades, P1_BARS, N_P1)} | {pct_rth(slow_trades, P1_BARS, N_P1)} |")
pr()

# B) Zone-width-controlled (150-250t only)
pr("### B) Zone-Width-Controlled Speed Check (150-250t only)")
pr()
fast_ctrl = [t for t in fast_trades if 150 <= t['zone_width'] < 250]
slow_ctrl = [t for t in slow_trades if 150 <= t['zone_width'] < 250]

pr(f"Fast trades (150-250t): {len(fast_ctrl)} | Slow trades (150-250t): {len(slow_ctrl)}")
pr()
pr("| Feature (150-250t only) | Fast T1 (<15 bars) | Slow T1 (>30 bars) |")
pr("|------------------------|-------------------|-------------------|")
fast_m = [t['score'] - SCORE_THRESHOLD for t in fast_ctrl]
slow_m = [t['score'] - SCORE_THRESHOLD for t in slow_ctrl]
fm_ctrl = f"{sum(fast_m)/len(fast_m):.2f}" if fast_m else "—"
sm_ctrl = f"{sum(slow_m)/len(slow_m):.2f}" if slow_m else "—"
pr(f"| Mean score margin | {fm_ctrl} | {sm_ctrl} |")
pr(f"| % CT | {pct_mode(fast_ctrl, 'CT')} | {pct_mode(slow_ctrl, 'CT')} |")
pr(f"| % RTH | {pct_rth(fast_ctrl, P1_BARS, N_P1)} | {pct_rth(slow_ctrl, P1_BARS, N_P1)} |")
pr()

dominant_predictor = "zone width" if len(fast_ctrl) < 3 or len(slow_ctrl) < 3 else "mixed"
if len(fast_ctrl) < 3 or len(slow_ctrl) < 3:
    pr(f"> **LOW SAMPLE within 150-250t bin** — cannot reliably assess whether features predict speed beyond zone width.")
    pr(f"> [SUGGESTION] Use zone-width-based exit selection (Section 4B) rather than adaptive logic.")
pr()

# =========================================================================
#  SECTION 6: Stop Tightening for Throughput
# =========================================================================

print("Section 6: Stop tightening...", file=sys.stderr)
pr("=" * 70)
pr("## SECTION 6: STOP TIGHTENING FOR THROUGHPUT")
pr("=" * 70)
pr()

# A) Full-position stop tightening
pr("### A) Full-Position Stop Tightening")
pr()

stop_configs = [
    ("max(1.5x, 120) ZR current", None),
    ("max(1.0x, 100)", lambda t, m, s: max(round(1.0 * t['_zw']), 100)),
    ("max(0.75x, 80)", lambda t, m, s: max(round(0.75 * t['_zw']), 80)),
    ("Fixed 120t for all", lambda t, m, s: 120),
    ("Fixed 80t for all", lambda t, m, s: 80),
    ("Fixed exits (CT 190t, WT 240t)", None),  # special: use fixed exit fn
]

stop_results = {}

for label, stop_fn in stop_configs:
    if label == "max(1.5x, 120) ZR current":
        # Already computed
        stop_results[label] = (p1_zr_trades, p1_zr_blocked, p1_zr_ks)
    elif label == "Fixed exits (CT 190t, WT 240t)":
        stop_results[label] = (p1_fix_trades, p1_fix_blocked, p1_fix_ks)
    else:
        print(f"  Stop config: {label}...", file=sys.stderr)
        trades, blocked, ks = run_full_sim(
            P1_QUAL, P1_BARS, N_P1, get_exit_params_zr,
            ct_limit=True, stop_override_fn=stop_fn)
        stop_results[label] = (trades, blocked, ks)

pr("| Stop | Trades stopped | Trades | Freed (seq sim) | Net PnL | KS triggers |")
pr("|------|---------------|--------|----------------|---------|-------------|")

for label, _ in stop_configs:
    trades, blocked, ks = stop_results[label]
    s = calc_stats(trades)
    freed = freed_count(trades, p1_zr_rbis)
    stopped = sum(1 for t in trades if t['leg1_exit'] == 'STOP')
    pr(f"| {label} | {stopped} | {s['n']} | {freed} | {fmt_pnl(s['total_pnl'])} | {ks} |")
pr()

# B) T2-leg-only stop tightening (after T1 fills)
pr("### B) T2-Leg Stop Tightening (after T1 fills)")
pr()

# Now we have t2_stop_after_t1 support in the sim
t2_stop_cfgs = [
    ("Original stop (current)", None),
    ("max(1.0x, 100) after T1", lambda t, m: -max(round(1.0 * t['_zw']), 100)),  # tighter loss stop
    ("Entry (breakeven T2)", lambda t, m: 0),  # stop at entry
    ("T1 price (lock profit)", lambda t, m: max(1, round(0.5 * t['_zw']))),  # lock T1 profit
]

t2_stop_results = {}
for label, fn in t2_stop_cfgs:
    if fn is None:
        t2_stop_results[label] = (p1_zr_trades, p1_zr_blocked, p1_zr_ks)
    else:
        print(f"  T2-only stop: {label}...", file=sys.stderr)
        trades, blocked, ks = run_full_sim(
            P1_QUAL, P1_BARS, N_P1, get_exit_params_zr,
            ct_limit=True, t2_stop_after_t1_fn=fn)
        t2_stop_results[label] = (trades, blocked, ks)

pr("| T2 stop (after T1 fills) | Trades | Freed (seq sim) | Net PnL | KS triggers |")
pr("|-------------------------|--------|----------------|---------|-------------|")
for label, _ in t2_stop_cfgs:
    trades, blocked, ks = t2_stop_results[label]
    s = calc_stats(trades)
    freed = freed_count(trades, p1_zr_rbis)
    pr(f"| {label} | {s['n']} | {freed} | {fmt_pnl(s['total_pnl'])} | {ks} |")
pr()

# T2 marginal value context
t1_filled = [t for t in p1_zr_trades if t['leg1_exit'] == 'TARGET_1']
pr(f"Context: {len(t1_filled)} of {len(p1_zr_trades)} ZR trades had T1 fill.")
if t1_filled:
    t2_hold = [t['exit_bar'] - t['leg1_exit_bar'] for t in t1_filled]
    t2_marg = [LEG2_W * t['leg2_pnl'] for t in t1_filled]
    pr(f"- Mean bars T1->T2 exit: {sum(t2_hold)/len(t2_hold):.1f}")
    pr(f"- Total T2 marginal PnL: {sum(t2_marg):.1f}t")
    t2_stopped = [t for t in t1_filled if t['leg2_exit'] == 'STOP']
    pr(f"- T2 stopped after T1: {len(t2_stopped)} (loss: {sum(LEG2_W*t['leg2_pnl'] for t in t2_stopped):.1f}t)")
pr()

# C) BE step-up
pr("### C) Full-Position BE Step-Up (Zone-Relative)")
pr()

be_configs = [
    ("No BE (current)", None),
    ("MFE > 0.25x zw", 0.25),
    ("MFE > 0.33x zw", 0.33),
    ("MFE > 0.5x zw (=T1)", 0.5),
]

be_results = {}

for label, be_mult in be_configs:
    if be_mult is None:
        be_results[label] = (p1_zr_trades, p1_zr_blocked, p1_zr_ks)
    else:
        print(f"  BE config: {label}...", file=sys.stderr)
        trades, blocked, ks = run_full_sim(
            P1_QUAL, P1_BARS, N_P1, get_exit_params_zr,
            ct_limit=True, be_trigger_mult=be_mult)
        be_results[label] = (trades, blocked, ks)

pr("| BE trigger | Trades | Stopped at BE | Net PnL | Freed signals | KS triggers |")
pr("|-----------|--------|--------------|---------|--------------|-------------|")

for label, _ in be_configs:
    trades, blocked, ks = be_results[label]
    s = calc_stats(trades)
    be_exits = sum(1 for t in trades if t.get('leg1_exit') == 'BE')
    freed = freed_count(trades, p1_zr_rbis)
    pr(f"| {label} | {s['n']} | {be_exits} | {fmt_pnl(s['total_pnl'])} | {freed} | {ks} |")
pr()

# BE by zone width bin
pr("### BE Split by Zone Width (trigger = 0.25x zw)")
pr()
if 'MFE > 0.25x zw' in be_results:
    be_trades = be_results['MFE > 0.25x zw'][0]
    pr("| Zone width | Trades | BE stops | Net PnL change vs no-BE | Freed |")
    pr("|-----------|--------|---------|------------------------|-------|")
    for (lo, hi), lbl in zip([(0,150), (150,250), (250,9999)], ['ZW < 150t', '150-250t', '250t+']):
        be_bin = [t for t in be_trades if lo <= t['zone_width'] < hi]
        baseline_bin = [t for t in p1_zr_trades if lo <= t['zone_width'] < hi]
        be_pnl = sum(t['weighted_pnl'] for t in be_bin)
        base_pnl = sum(t['weighted_pnl'] for t in baseline_bin)
        delta = be_pnl - base_pnl
        be_stops = sum(1 for t in be_bin if t.get('leg1_exit') == 'BE')
        freed = sum(1 for t in be_bin if t['rbi'] not in p1_zr_rbis)
        pr(f"| {lbl} | {len(be_bin)} | {be_stops} | {delta:+.1f} | {freed} |")
    pr()

# D) Risk Profile
pr("### D) Risk Profile by Stop Level")
pr()

pr("| Stop config | Max single loss | Worst 2-trade daily | % daily budget (-600t) | Max DD | P95 MAE | HIGH EXPOSURE? |")
pr("|------------|----------------|--------------------|-----------------------|--------|---------|---------------|")

for label, _ in stop_configs:
    trades, blocked, ks = stop_results[label]
    s = calc_stats(trades)
    max_loss = s['max_single_loss']
    worst_2 = 0
    pnls = [t['weighted_pnl'] for t in trades]
    for i in range(len(pnls) - 1):
        if pnls[i] < 0 and pnls[i+1] < 0:
            combo = abs(pnls[i]) + abs(pnls[i+1])
            if combo > worst_2:
                worst_2 = combo
    pct_budget = 100 * max_loss / 600
    high_exp = "YES" if max_loss > 300 else "NO"
    # P95 adverse excursion
    maes = sorted([t['mae'] for t in trades])
    p95_mae = maes[int(0.95 * len(maes))] if maes else 0
    pr(f"| {label} | {max_loss:.1f}t | {worst_2:.1f}t | {pct_budget:.1f}% | {s['max_dd']:.1f}t | {p95_mae:.1f}t | {high_exp} |")
pr()

# P2 cross-validation of best tighter stop
best_stop_label = None
best_stop_pnl = -99999
for label, _ in stop_configs:
    if label == "max(1.5x, 120) ZR current": continue
    if label == "Fixed exits (CT 190t, WT 240t)": continue
    trades, _, _ = stop_results[label]
    s = calc_stats(trades)
    if s['total_pnl'] > best_stop_pnl:
        best_stop_pnl = s['total_pnl']
        best_stop_label = label

if best_stop_label:
    # Find the stop_fn for this config
    stop_fn_map = {
        "max(1.0x, 100)": lambda t, m, s: max(round(1.0 * t['_zw']), 100),
        "max(0.75x, 80)": lambda t, m, s: max(round(0.75 * t['_zw']), 80),
        "Fixed 120t for all": lambda t, m, s: 120,
        "Fixed 80t for all": lambda t, m, s: 80,
    }
    if best_stop_label in stop_fn_map:
        print(f"  P2 cross-val: best stop ({best_stop_label})...", file=sys.stderr)
        p2_stop_trades, _, p2_stop_ks = run_full_sim(
            P2_QUAL, P2_BARS, N_P2, get_exit_params_zr,
            ct_limit=True, stop_override_fn=stop_fn_map[best_stop_label])
        p2_stop_s = calc_stats(p2_stop_trades)

        pr("### P2 Cross-Validation (Tighter Stop)")
        pr()
        pr(f"| Period | Current stop PnL | Tighter stop ({best_stop_label}) PnL | Winner |")
        pr(f"|--------|-----------------|--------------------------------------|--------|")
        p2_baseline = calc_stats(p2_zr_trades)['total_pnl']
        winner = "tighter" if p2_stop_s['total_pnl'] > p2_baseline else "current"
        pr(f"| P1 | {fmt_pnl(zr_s['total_pnl'])} | {fmt_pnl(best_stop_pnl)} | {'tighter' if best_stop_pnl > zr_s['total_pnl'] else 'current'} |")
        pr(f"| P2 | {fmt_pnl(p2_baseline)} | {fmt_pnl(p2_stop_s['total_pnl'])} | {winner} |")
        pr()

# =========================================================================
#  SECTION 7: Optimal Throughput Configuration
# =========================================================================

print("Section 7: Summary...", file=sys.stderr)
pr("=" * 70)
pr("## SECTION 7: OPTIMAL THROUGHPUT CONFIGURATION")
pr("=" * 70)
pr()

# Collect all P1 results
all_configs = []

# Current ZR 2-leg
s = calc_stats(p1_zr_trades)
all_configs.append(("Current ZR 2-leg", s, p1_zr_ks))

# Fixed exits
s = calc_stats(p1_fix_trades)
all_configs.append(("Fixed exits (CT 40/80/190, WT 60/80/240)", s, p1_fix_ks))

# Best forced bar exit
best_fb_s = calc_stats(forced_results[best_fb][0])
all_configs.append((f"Best fixed bar exit ({best_fb}b)", best_fb_s, forced_results[best_fb][2]))

# ZR single-leg T1
s = calc_stats(p1_zr_t1_trades)
all_configs.append(("ZR single-leg T1", s, p1_zr_t1_ks))

# Fixed single-leg T1
s = calc_stats(p1_fix_t1_trades)
all_configs.append(("Fixed single-leg T1", s, p1_fix_t1_ks))

# Best tighter stop
if best_stop_label:
    s = calc_stats(stop_results[best_stop_label][0])
    all_configs.append((f"Best tighter stop ({best_stop_label})", s, stop_results[best_stop_label][2]))

# Best BE
best_be_label = None
best_be_pnl = -99999
for label, _ in be_configs:
    if label == "No BE (current)": continue
    trades, _, _ = be_results[label]
    s = calc_stats(trades)
    if s['total_pnl'] > best_be_pnl:
        best_be_pnl = s['total_pnl']
        best_be_label = label
if best_be_label:
    s = calc_stats(be_results[best_be_label][0])
    all_configs.append((f"Best BE ({best_be_label})", s, be_results[best_be_label][2]))

# Best T2-only stop tighten
best_t2_label = None
best_t2_pnl = -99999
for label, _ in t2_stop_cfgs:
    if label == "Original stop (current)": continue
    trades, _, _ = t2_stop_results[label]
    s = calc_stats(trades)
    if s['total_pnl'] > best_t2_pnl:
        best_t2_pnl = s['total_pnl']
        best_t2_label = label
if best_t2_label:
    s = calc_stats(t2_stop_results[best_t2_label][0])
    all_configs.append((f"Best T2-only tighten ({best_t2_label})", s, t2_stop_results[best_t2_label][2]))

pr("| Config | Trades | Mean PnL | Total PnL | Mean hold | Max DD | Max loss | KS |")
pr("|--------|--------|---------|-----------|----------|--------|---------|-----|")
for label, s, ks in all_configs:
    pr(f"| {label} | {s['n']} | {s['ev']:.1f} | {fmt_pnl(s['total_pnl'])} | {s['mean_hold']:.1f} | {s['max_dd']:.1f} | {s['max_single_loss']:.1f} | {ks} |")
pr()

# P2 cross-validation summary
pr("### P2 Cross-Validation Summary")
pr()

# Run P2 for each config
p2_configs = []

# Current ZR
s = calc_stats(p2_zr_trades)
p2_configs.append(("Current ZR 2-leg", s, p2_zr_ks))

# Fixed exits
s = calc_stats(p2_fix_trades)
p2_configs.append(("Fixed exits", s, p2_fix_ks))

# Best forced bar
s = calc_stats(p2_forced_trades)
p2_configs.append((f"Best P1 exit ({best_fb}b)", s, p2_forced_ks))

# ZR single-leg T1
s = calc_stats(p2_zr_t1_trades)
p2_configs.append(("ZR single-leg T1", s, p2_zr_t1_ks))

# Fixed single-leg T1
s = calc_stats(p2_fix_t1_trades)
p2_configs.append(("Fixed single-leg T1", s, p2_fix_t1_ks))

# Best tighter stop (if P2 was run)
if best_stop_label and best_stop_label in stop_fn_map:
    s = calc_stats(p2_stop_trades)
    p2_configs.append((f"Best tighter stop", s, p2_stop_ks))

# Best BE on P2
if best_be_label:
    be_mult = dict(be_configs).get(best_be_label)
    if be_mult is not None:
        print(f"  P2 cross-val: BE ({best_be_label})...", file=sys.stderr)
        p2_be_trades, _, p2_be_ks = run_full_sim(
            P2_QUAL, P2_BARS, N_P2, get_exit_params_zr,
            ct_limit=True, be_trigger_mult=be_mult)
        s = calc_stats(p2_be_trades)
        p2_configs.append((f"Best BE ({best_be_label})", s, p2_be_ks))

# Best T2-only tighten on P2
if best_t2_label:
    t2_fn = dict(t2_stop_cfgs).get(best_t2_label)
    if t2_fn is not None:
        print(f"  P2 cross-val: T2-only ({best_t2_label})...", file=sys.stderr)
        p2_t2_trades, _, p2_t2_ks = run_full_sim(
            P2_QUAL, P2_BARS, N_P2, get_exit_params_zr,
            ct_limit=True, t2_stop_after_t1_fn=t2_fn)
        s = calc_stats(p2_t2_trades)
        p2_configs.append((f"Best T2-only tighten ({best_t2_label})", s, p2_t2_ks))

# Find P1 baseline PnL
p1_baseline_pnl = calc_stats(p1_zr_trades)['total_pnl']
p2_baseline_pnl = calc_stats(p2_zr_trades)['total_pnl']
p1_baseline_ks = p1_zr_ks
p2_baseline_ks = p2_zr_ks

pr("| Config | P1 Total PnL | P2 Total PnL | P1 KS | P2 KS | Classification |")
pr("|--------|-------------|-------------|-------|-------|---------------|")

# Match P1 → P2 configs via explicit mapping
p2_lookup = {}
for p2_label, p2_s, p2_ks in p2_configs:
    p2_lookup[p2_label] = (p2_s, p2_ks)

p1_to_p2_map = {
    "Current ZR 2-leg": "Current ZR 2-leg",
    "Fixed exits (CT 40/80/190, WT 60/80/240)": "Fixed exits",
    f"Best fixed bar exit ({best_fb}b)": f"Best P1 exit ({best_fb}b)",
    "ZR single-leg T1": "ZR single-leg T1",
    "Fixed single-leg T1": "Fixed single-leg T1",
}
if best_stop_label:
    p1_to_p2_map[f"Best tighter stop ({best_stop_label})"] = "Best tighter stop"
if best_be_label:
    p1_to_p2_map[f"Best BE ({best_be_label})"] = f"Best BE ({best_be_label})"
if best_t2_label:
    p1_to_p2_map[f"Best T2-only tighten ({best_t2_label})"] = f"Best T2-only tighten ({best_t2_label})"

for label, s, ks in all_configs:
    p1_pnl = s['total_pnl']
    p1_ks_val = ks

    # Find matching P2 config
    p2_key = p1_to_p2_map.get(label)
    p2_match = p2_lookup.get(p2_key) if p2_key else None

    if p2_match:
        p2_s, p2_ks = p2_match
        p2_pnl = p2_s['total_pnl']

        beats_p1 = p1_pnl > p1_baseline_pnl
        beats_p2 = p2_pnl > p2_baseline_pnl
        ks_increase = (p1_ks_val > 0 and p1_baseline_ks == 0) or (p2_ks > 0 and p2_baseline_ks == 0)
        ks_high = ks_increase or (p1_baseline_ks > 0 and p1_ks_val > p1_baseline_ks * 1.5)
        # HIGH EXPOSURE: max single loss > 50% of -600t daily budget
        high_exposure = s['max_single_loss'] > 300

        if label == "Current ZR 2-leg":
            classification = "baseline"
        elif high_exposure:
            classification = "HIGH EXPOSURE" + (" (beats both)" if beats_p1 and beats_p2 else "")
        elif beats_p1 and beats_p2 and not ks_high:
            classification = "ACTIONABLE"
        elif beats_p1 and beats_p2 and ks_high:
            classification = "HIGH VARIANCE"
        elif beats_p1:
            classification = "PROMISING"
        else:
            classification = "NOT VIABLE"

        pr(f"| {label} | {fmt_pnl(p1_pnl)} | {fmt_pnl(p2_pnl)} | {p1_ks_val} | {p2_ks} | {classification} |")
    else:
        classification = "NO P2 DATA"
        pr(f"| {label} | {fmt_pnl(p1_pnl)} | — | {p1_ks_val} | — | {classification} |")

pr()

# Best combined (cherry-picked, flagged as overfitted ceiling)
pr("> **OVERFITTED CEILING**: The best combined config cherry-picks from each section on P1.")
pr("> This is the upper bound, not a deployable config.")
pr()
pr("> **REMINDER**: Do NOT freeze any new exit config from this prompt.")
pr("> Throughput Part 2 (dynamic T2 exit) may alter the optimal config.")
pr("> Section 7 identifies candidates only.")

# =========================================================================
#  Write output
# =========================================================================

outdir = f'{BASE}/04-backtest/zone_touch/output'
outpath = f'{outdir}/throughput_analysis_part1.md'
with open(outpath, 'w', encoding='utf-8') as f:
    f.write('\n'.join(out))

print(f"\nResults saved to {outpath}", file=sys.stderr)
print("Done.", file=sys.stderr)
