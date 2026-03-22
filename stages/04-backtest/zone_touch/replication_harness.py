"""
Replication Harness — ATEAM_ZONE_BOUNCE_V1 standalone CSV test.

Reads P2 bar data + merged zone touches, runs identical scoring + 2-leg exit
logic as the C++ autotrader, outputs trade_log.csv with ALL Part A columns.

Usage:
    python replication_harness.py

Outputs:
    output/replication_trade_log.csv   — full Part A trade log
    output/replication_signal_log.csv  — all signals (traded + skipped)
    stdout                             — aggregate stats + answer key comparison
"""
import csv, json, sys, math
from datetime import datetime
from collections import Counter

# =========================================================================
#  P1-Frozen Config (must match zone_bounce_config.h exactly)
# =========================================================================

TICK_SIZE = 0.25
COST_TICKS = 3.0
SCORE_THRESHOLD = 16.66

BASE = 'C:/Projects/pipeline/stages'

with open(f'{BASE}/04-backtest/zone_touch/output/scoring_model_acal.json') as f:
    MODEL = json.load(f)
with open(f'{BASE}/04-backtest/zone_touch/output/feature_config.json') as f:
    FCFG = json.load(f)

WEIGHTS = MODEL['weights']
BIN_EDGES = MODEL['bin_edges']
TREND_P33 = FCFG['trend_slope_p33']   # -0.30755...
TREND_P67 = FCFG['trend_slope_p67']   #  0.34030...
TREND_LOOKBACK = 50

# Exit params
EXIT = {
    'CT':   {'t1': 40, 't2': 80, 'stop': 190, 'tcap': 160},
    'WTNT': {'t1': 60, 't2': 80, 'stop': 240, 'tcap': 160},
}
LEG1_W, LEG2_W = 0.67, 0.33
TF_MAX_MINUTES = 120
WTNT_SEQ_MAX = 5

# Kill-switch
KS_CONSEC = 3
KS_DAILY = -400.0
KS_WEEKLY = -800.0

# EOD flatten
FLATTEN_HHMM = 1655

# =========================================================================
#  Scoring functions (match Python prompt3 + C++ config.h)
# =========================================================================

def bin_numeric(val, p33, p67, weight, is_nan=False):
    """Low <= p33 = best (full weight), Mid = half, High >= p67 = 0."""
    if is_nan:
        return 0.0, -1
    if val <= p33:
        return weight, 0
    if val >= p67:
        return 0.0, 2
    return weight / 2.0, 1

def score_f04(cascade, weight):
    if cascade == 'NO_PRIOR':    return weight, 2
    if cascade == 'PRIOR_HELD':  return weight / 2.0, 1
    if cascade == 'PRIOR_BROKE': return 0.0, 0
    return 0.0, -1

def score_f01(tf_str, weight):
    if tf_str == '30m':  return weight, 2
    if tf_str == '480m': return 0.0, 0
    if tf_str:           return weight / 2.0, 1
    return 0.0, -1

TF_MINUTES = {'15m':15, '30m':30, '60m':60, '90m':90, '120m':120,
              '240m':240, '360m':360, '480m':480, '720m':720}

# =========================================================================
#  Trend computation
# =========================================================================

def compute_trend_slope(bar_data, bar_idx, lookback=TREND_LOOKBACK):
    """Simple linear regression slope of Last over trailing `lookback` bars."""
    if bar_idx < lookback:
        return 0.0
    n = lookback
    sum_x = sum_y = sum_xy = sum_x2 = 0.0
    for i in range(n):
        x = float(i)
        y = bar_data[bar_idx - n + 1 + i][3]  # Last
        sum_x += x
        sum_y += y
        sum_xy += x * y
        sum_x2 += x * x
    denom = n * sum_x2 - sum_x * sum_x
    if abs(denom) < 1e-12:
        return 0.0
    return (n * sum_xy - sum_x * sum_y) / denom

def classify_trend(slope, touch_type):
    """Trend label — matches pipeline prompt3 (non-direction-aware).
    NOTE: Build spec says direction-aware, but pipeline uses simple slope
    cutoffs without considering touch direction. The C++ autotrader must
    match the pipeline for replication. See prompt3_holdout.py lines 208-216.
    """
    if slope <= TREND_P33: return 'CT'
    if slope >= TREND_P67: return 'WT'
    return 'NT'

# =========================================================================
#  2-leg simulator (matches exit_sweep_phase1.py exactly)
# =========================================================================

def sim_2leg(bar_data, entry_bar, direction, params):
    n_bars = len(bar_data)
    if entry_bar >= n_bars:
        return None

    ep = bar_data[entry_bar][0]  # Open
    t1_ticks = params['t1']
    t2_ticks = params['t2']
    stop_ticks = params['stop']
    tcap = params['tcap']

    if direction == 1:
        stop_px = ep - stop_ticks * TICK_SIZE
        t1_px = ep + t1_ticks * TICK_SIZE
        t2_px = ep + t2_ticks * TICK_SIZE
    else:
        stop_px = ep + stop_ticks * TICK_SIZE
        t1_px = ep - t1_ticks * TICK_SIZE
        t2_px = ep - t2_ticks * TICK_SIZE

    leg1_open = leg2_open = True
    leg1_pnl = leg2_pnl = 0.0
    leg1_exit = leg2_exit = 'NONE'
    leg1_exit_bar = leg2_exit_bar = -1
    leg1_exit_px = leg2_exit_px = 0.0
    mfe = mae = 0.0
    last_i = entry_bar

    for i in range(entry_bar, n_bars):
        o, h, l, c, dt = bar_data[i]
        bh = i - entry_bar + 1
        last_i = i

        # MFE/MAE
        if direction == 1:
            bmfe = (h - ep) / TICK_SIZE
            bmae = (ep - l) / TICK_SIZE
        else:
            bmfe = (ep - l) / TICK_SIZE
            bmae = (h - ep) / TICK_SIZE
        if bmfe > mfe: mfe = bmfe
        if bmae > mae: mae = bmae

        # NOTE: EOD flatten (16:55 ET) is a live-trading safety feature in the
        # C++ autotrader. The pipeline backtests do NOT use it. Disabled here
        # for replication fidelity. The C++ autotrader will implement it for
        # live paper trading, tested separately via SC replay.

        # Time cap
        if bh >= tcap:
            pnl = (c - ep) / TICK_SIZE if direction == 1 else (ep - c) / TICK_SIZE
            if leg1_open:
                leg1_pnl = pnl; leg1_exit = 'TIMECAP'
                leg1_exit_bar = i; leg1_exit_px = c; leg1_open = False
            if leg2_open:
                leg2_pnl = pnl; leg2_exit = 'TIMECAP'
                leg2_exit_bar = i; leg2_exit_px = c; leg2_open = False
            break

        # Stop-first
        stop_hit = (l <= stop_px) if direction == 1 else (h >= stop_px)
        if stop_hit:
            spnl = (stop_px - ep) / TICK_SIZE if direction == 1 else (ep - stop_px) / TICK_SIZE
            if leg1_open:
                leg1_pnl = spnl; leg1_exit = 'STOP'
                leg1_exit_bar = i; leg1_exit_px = stop_px; leg1_open = False
            if leg2_open:
                leg2_pnl = spnl; leg2_exit = 'STOP'
                leg2_exit_bar = i; leg2_exit_px = stop_px; leg2_open = False
            break

        # Targets
        if leg1_open:
            hit = (h >= t1_px) if direction == 1 else (l <= t1_px)
            if hit:
                leg1_pnl = float(t1_ticks)
                leg1_exit = 'TARGET_1'
                leg1_exit_bar = i; leg1_exit_px = t1_px; leg1_open = False

        if leg2_open:
            hit = (h >= t2_px) if direction == 1 else (l <= t2_px)
            if hit:
                leg2_pnl = float(t2_ticks)
                leg2_exit = 'TARGET_2'
                leg2_exit_bar = i; leg2_exit_px = t2_px; leg2_open = False

        if not leg1_open and not leg2_open:
            break

    # Ran out of bars
    if leg1_open or leg2_open:
        last_c = bar_data[min(last_i, n_bars - 1)][3]
        pnl = (last_c - ep) / TICK_SIZE if direction == 1 else (ep - last_c) / TICK_SIZE
        if leg1_open:
            leg1_pnl = pnl; leg1_exit = 'END_OF_DATA'
            leg1_exit_bar = last_i; leg1_exit_px = last_c
        if leg2_open:
            leg2_pnl = pnl; leg2_exit = 'END_OF_DATA'
            leg2_exit_bar = last_i; leg2_exit_px = last_c

    bars_held = max(leg1_exit_bar, leg2_exit_bar) - entry_bar + 1
    wpnl = LEG1_W * leg1_pnl + LEG2_W * leg2_pnl - COST_TICKS

    return dict(
        entry_price=ep, stop_price=stop_px,
        t1_target=t1_px, t2_target=t2_px,
        leg1_exit=leg1_exit, leg1_pnl=leg1_pnl,
        leg1_exit_bar=leg1_exit_bar, leg1_exit_px=leg1_exit_px,
        leg2_exit=leg2_exit, leg2_pnl=leg2_pnl,
        leg2_exit_bar=leg2_exit_bar, leg2_exit_px=leg2_exit_px,
        weighted_pnl=wpnl, bars_held=bars_held, mfe=mfe, mae=mae
    )

# =========================================================================
#  Load data
# =========================================================================

print("Loading bar data...")
bar_data = []  # list of (Open, High, Low, Last, datetime_str)
with open(f'{BASE}/01-data/output/zone_prep/NQ_bardata_P2.csv') as f:
    for row in csv.DictReader(f):
        r = {k.strip(): v.strip() for k, v in row.items()}
        o = float(r['Open'])
        h = float(r['High'])
        l = float(r['Low'])
        c = float(r['Last'])
        base_dt = r['Date'].split('.')[0] + ' ' + r['Time'].split('.')[0]
        bar_data.append((o, h, l, c, base_dt))
n_bars = len(bar_data)
print(f"  {n_bars} bars")

# Parse bar datetimes for index lookup
def parse_bar_dt(dt_str):
    base = dt_str.split('.')[0]
    parts = base.split(' ')
    if '/' in parts[0]:
        d = datetime.strptime(base, '%m/%d/%Y %H:%M:%S')
    else:
        d = datetime.strptime(base, '%Y-%m-%d %H:%M:%S')
    return d.strftime('%Y-%m-%d %H:%M:%S')

bar_dt_norm = {}
for i, (o, h, l, c, dt) in enumerate(bar_data):
    try:
        bar_dt_norm[parse_bar_dt(dt)] = i
    except:
        pass

print("Loading zone touches...")
touches = []  # list of dicts, sorted by RotBarIndex
for fname in ['NQ_merged_P2a.csv', 'NQ_merged_P2b.csv']:
    with open(f'{BASE}/01-data/output/zone_prep/{fname}') as f:
        for row in csv.DictReader(f):
            rbi = int(row['RotBarIndex'])
            if rbi < 0:
                continue
            touches.append(row)

# Sort by RotBarIndex (chronological)
touches.sort(key=lambda r: int(r['RotBarIndex']))
print(f"  {len(touches)} touches (RotBarIndex >= 0)")

# Build zone history for F10 (prior penetration lookup)
# Key = (ZoneTop, ZoneBot, SourceLabel) -> list of touches in order
print("Building zone history for F10...")
zone_history = {}
for t in touches:
    key = (t['ZoneTop'], t['ZoneBot'], t.get('SourceLabel', ''))
    if key not in zone_history:
        zone_history[key] = []
    zone_history[key].append(t)

def get_prior_penetration(touch):
    """Get F10: PenetrationTicks from the prior touch on the same zone."""
    seq = int(touch['TouchSequence'])
    if seq <= 1:
        return None  # no prior touch

    key = (touch['ZoneTop'], touch['ZoneBot'], touch.get('SourceLabel', ''))
    history = zone_history.get(key, [])

    rbi = int(touch['RotBarIndex'])
    for prev in reversed(history):
        prev_rbi = int(prev['RotBarIndex'])
        if prev_rbi >= rbi:
            continue
        prev_seq = int(prev['TouchSequence'])
        if prev_seq == seq - 1:
            pen = prev.get('Penetration', '').strip()
            return float(pen) if pen else None
    return None

# =========================================================================
#  Score a touch
# =========================================================================

def score_touch(touch):
    """Full A-Cal scoring with per-feature breakdown."""
    # F10
    prior_pen = get_prior_penetration(touch)
    f10_nan = (prior_pen is None)
    f10_raw = 0.0 if f10_nan else prior_pen
    f10_pts, f10_bin = bin_numeric(
        f10_raw, BIN_EDGES['F10_PriorPenetration'][0],
        BIN_EDGES['F10_PriorPenetration'][1],
        WEIGHTS['F10_PriorPenetration'], f10_nan)

    # F04
    f04_raw = touch.get('CascadeState', '').strip()
    f04_pts, f04_bin = score_f04(f04_raw, WEIGHTS['F04_CascadeState'])

    # F01
    f01_raw = touch.get('SourceLabel', '').strip()
    f01_pts, f01_bin = score_f01(f01_raw, WEIGHTS['F01_Timeframe'])

    # F21
    f21_raw_str = touch.get('ZoneAgeBars', '').strip()
    f21_raw = float(f21_raw_str) if f21_raw_str else 0.0
    f21_pts, f21_bin = bin_numeric(
        f21_raw, BIN_EDGES['F21_ZoneAge'][0],
        BIN_EDGES['F21_ZoneAge'][1],
        WEIGHTS['F21_ZoneAge'])

    total = f10_pts + f04_pts + f01_pts + f21_pts
    return dict(
        f10_raw=f10_raw, f10_nan=f10_nan, f10_bin=f10_bin, f10_pts=f10_pts,
        f04_raw=f04_raw, f04_bin=f04_bin, f04_pts=f04_pts,
        f01_raw=f01_raw, f01_bin=f01_bin, f01_pts=f01_pts,
        f21_raw=f21_raw, f21_bin=f21_bin, f21_pts=f21_pts,
        total=total
    )

# =========================================================================
#  Session classification
# =========================================================================

def get_session(bar_idx):
    dt = bar_data[bar_idx][4]
    try:
        t = dt.split(' ')[1] if ' ' in dt else ''
        hh_mm = t.split(':')
        hhmm = int(hh_mm[0]) * 100 + int(hh_mm[1]) if len(hh_mm) >= 2 else 0
    except:
        hhmm = 0
    return 'RTH' if 930 <= hhmm < 1615 else 'ETH'

# =========================================================================
#  Main simulation loop (with no-overlap + kill-switch)
# =========================================================================

print("\nRunning replication simulation...")

trade_log = []
signal_log = []

# Position state
in_trade = False
in_trade_until = -1  # bar index when current trade exits
current_mode = None

# Kill-switch state
ks_consec = 0
ks_daily_pnl = 0.0
ks_weekly_pnl = 0.0
ks_session_halted = False
ks_daily_halted = False
ks_weekly_halted = False
ks_last_day = ''
ks_last_week = ''

trade_counter = 0

for touch in touches:
    rbi = int(touch['RotBarIndex'])
    entry_bar = rbi + 1
    if entry_bar >= n_bars:
        continue

    touch_type = touch['TouchType'].strip()
    if touch_type not in ('DEMAND_EDGE', 'SUPPLY_EDGE'):
        continue

    direction = 1 if touch_type == 'DEMAND_EDGE' else -1
    tf_str = touch.get('SourceLabel', '').strip()
    tf_min = TF_MINUTES.get(tf_str, 999)
    seq = int(touch['TouchSequence'])
    sbb = touch.get('SBB_Label', '').strip()
    if not sbb:
        sbb = 'NORMAL'

    # Score
    sc = score_touch(touch)
    acal_score = sc['total']
    score_margin = acal_score - SCORE_THRESHOLD

    # Trend — use merged CSV's TrendSlope (matches pipeline + ZBV4 computation)
    ts_str = touch.get('TrendSlope', '').strip()
    trend_slope = float(ts_str) if ts_str else 0.0
    trend_label = classify_trend(trend_slope, touch_type)

    # Session
    session = get_session(rbi)

    # Entry bar datetime for logging
    entry_dt = bar_data[entry_bar][4]

    # ---- Determine action ----
    skip_reason = None
    mode = None

    # Kill-switch day/week reset
    try:
        day_str = entry_dt.split(' ')[0]
    except:
        day_str = ''
    if day_str and day_str != ks_last_day:
        ks_daily_pnl = 0.0
        ks_session_halted = False
        ks_daily_halted = False
        ks_consec = 0
        ks_last_day = day_str

    # Approximate week boundary (reset on Monday-ish)
    try:
        d = datetime.strptime(day_str, '%m/%d/%Y')
        week_key = f"{d.year}-W{d.isocalendar()[1]}"
    except:
        week_key = day_str
    if week_key != ks_last_week:
        ks_weekly_pnl = 0.0
        ks_weekly_halted = False
        ks_last_week = week_key

    # Score gate
    if acal_score < SCORE_THRESHOLD:
        skip_reason = 'BELOW_THRESHOLD'
    # TF filter
    elif tf_min > TF_MAX_MINUTES or tf_min == 999:
        skip_reason = 'TF_FILTER'
    else:
        # Mode routing
        if trend_label == 'CT':
            mode = 'CT'
        else:
            if seq > WTNT_SEQ_MAX:
                skip_reason = 'SEQ_FILTER'
            else:
                mode = 'WTNT'

    # No-overlap
    if skip_reason is None and entry_bar <= in_trade_until:
        skip_reason = 'IN_POSITION'

    # Kill-switch
    if skip_reason is None:
        if ks_session_halted or ks_daily_halted or ks_weekly_halted:
            skip_reason = 'KILL_SWITCH'

    # ---- Log signal ----
    sig_entry = dict(
        datetime=entry_dt,
        touch_type=touch_type,
        source_label=tf_str,
        acal_score=f"{acal_score:.4f}",
        score_margin=f"{score_margin:.4f}",
        trend_label=trend_label,
        sbb_label=sbb,
        action='SKIP' if skip_reason else 'TRADE',
        skip_reason=skip_reason or '',
        current_position_pnl='0.00'
    )
    signal_log.append(sig_entry)

    if skip_reason:
        continue

    # ---- Execute trade ----
    params = EXIT[mode]
    result = sim_2leg(bar_data, entry_bar, direction, params)
    if result is None:
        continue

    trade_counter += 1
    trade_id = f"ZB_{trade_counter:04d}"

    # Update in_trade_until
    final_exit_bar = max(result['leg1_exit_bar'], result['leg2_exit_bar'])
    in_trade_until = final_exit_bar

    # Kill-switch update
    wpnl = result['weighted_pnl']
    ks_daily_pnl += wpnl
    ks_weekly_pnl += wpnl
    if wpnl < 0:
        ks_consec += 1
    else:
        ks_consec = 0
    if ks_consec >= KS_CONSEC:
        ks_session_halted = True
    if ks_daily_pnl <= KS_DAILY:
        ks_daily_halted = True
    if ks_weekly_pnl <= KS_WEEKLY:
        ks_weekly_halted = True

    # Build full trade_log row
    BIN_LABELS = {-1: 'NULL', 0: 'Low', 1: 'Mid', 2: 'High'}
    row = dict(
        trade_id=trade_id,
        mode=mode,
        datetime=entry_dt,
        direction='LONG' if direction == 1 else 'SHORT',
        touch_type=touch_type,
        source_label=tf_str,
        touch_sequence=seq,
        F10_raw=f"{sc['f10_raw']:.4f}" if not sc['f10_nan'] else '',
        F04_raw=sc['f04_raw'],
        F01_raw=sc['f01_raw'],
        F21_raw=f"{sc['f21_raw']:.4f}",
        F10_bin=sc['f10_bin'],
        F04_bin=sc['f04_bin'],
        F01_bin=sc['f01_bin'],
        F21_bin=sc['f21_bin'],
        F10_points=f"{sc['f10_pts']:.4f}",
        F04_points=f"{sc['f04_pts']:.4f}",
        F01_points=f"{sc['f01_pts']:.4f}",
        F21_points=f"{sc['f21_pts']:.4f}",
        acal_score=f"{acal_score:.4f}",
        score_margin=f"{score_margin:.4f}",
        trend_slope=f"{trend_slope:.6f}",
        trend_label=trend_label,
        sbb_label=sbb,
        session=session,
        entry_bar_index=entry_bar,
        entry_price=f"{result['entry_price']:.2f}",
        stop_price=f"{result['stop_price']:.2f}",
        t1_target_price=f"{result['t1_target']:.2f}",
        t2_target_price=f"{result['t2_target']:.2f}",
        leg1_exit_type=result['leg1_exit'],
        leg1_exit_price=f"{result['leg1_exit_px']:.2f}",
        leg1_exit_bar=result['leg1_exit_bar'],
        leg1_pnl_ticks=f"{result['leg1_pnl']:.2f}",
        leg2_exit_type=result['leg2_exit'],
        leg2_exit_price=f"{result['leg2_exit_px']:.2f}",
        leg2_exit_bar=result['leg2_exit_bar'],
        leg2_pnl_ticks=f"{result['leg2_pnl']:.2f}",
        weighted_pnl=f"{wpnl:.4f}",
        bars_held=result['bars_held'],
        mfe_ticks=f"{result['mfe']:.2f}",
        mae_ticks=f"{result['mae']:.2f}",
        slippage_ticks='0.0',
        latency_ms='0'
    )
    trade_log.append(row)

# =========================================================================
#  Write output CSVs
# =========================================================================

TRADE_COLS = [
    'trade_id', 'mode', 'datetime', 'direction', 'touch_type', 'source_label',
    'touch_sequence', 'F10_raw', 'F04_raw', 'F01_raw', 'F21_raw',
    'F10_bin', 'F04_bin', 'F01_bin', 'F21_bin',
    'F10_points', 'F04_points', 'F01_points', 'F21_points',
    'acal_score', 'score_margin', 'trend_slope', 'trend_label',
    'sbb_label', 'session',
    'entry_bar_index', 'entry_price', 'stop_price',
    't1_target_price', 't2_target_price',
    'leg1_exit_type', 'leg1_exit_price', 'leg1_exit_bar', 'leg1_pnl_ticks',
    'leg2_exit_type', 'leg2_exit_price', 'leg2_exit_bar', 'leg2_pnl_ticks',
    'weighted_pnl', 'bars_held', 'mfe_ticks', 'mae_ticks',
    'slippage_ticks', 'latency_ms'
]

SIGNAL_COLS = [
    'datetime', 'touch_type', 'source_label', 'acal_score', 'score_margin',
    'trend_label', 'sbb_label', 'action', 'skip_reason', 'current_position_pnl'
]

outdir = f'{BASE}/04-backtest/zone_touch/output'

with open(f'{outdir}/replication_trade_log.csv', 'w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=TRADE_COLS)
    writer.writeheader()
    writer.writerows(trade_log)

with open(f'{outdir}/replication_signal_log.csv', 'w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=SIGNAL_COLS)
    writer.writeheader()
    writer.writerows(signal_log)

print(f"\nWrote {len(trade_log)} trades to replication_trade_log.csv")
print(f"Wrote {len(signal_log)} signals to replication_signal_log.csv")

# =========================================================================
#  Aggregate stats
# =========================================================================

ct = [r for r in trade_log if r['mode'] == 'CT']
wt = [r for r in trade_log if r['mode'] == 'WTNT']

def calc_stats(group, label):
    if not group:
        print(f"\n{label}: 0 trades")
        return
    pnls = [float(r['weighted_pnl']) for r in group]
    wins = sum(1 for p in pnls if p > 0)
    gw = sum(p for p in pnls if p > 0)
    gl = sum(abs(p) for p in pnls if p < 0)
    pf = gw / gl if gl > 0 else float('inf')
    total = sum(pnls)
    l1 = Counter(r['leg1_exit_type'] for r in group)
    l2 = Counter(r['leg2_exit_type'] for r in group)
    print(f"\n{label}: {len(group)} trades")
    print(f"  Win rate: {wins}/{len(group)} = {100*wins/len(group):.1f}%")
    print(f"  PF @3t: {pf:.2f}")
    print(f"  Total PnL: {total:.1f}t")
    print(f"  Leg1 exits: {dict(l1)}")
    print(f"  Leg2 exits: {dict(l2)}")

    # Stop/target/timecap rates
    n = len(group)
    l1_target = sum(1 for r in group if r['leg1_exit_type'] == 'TARGET_1')
    l1_stop = sum(1 for r in group if r['leg1_exit_type'] == 'STOP')
    l1_tc = sum(1 for r in group if r['leg1_exit_type'] == 'TIMECAP')
    l1_flat = sum(1 for r in group if r['leg1_exit_type'] == 'FLATTEN_EOD')
    print(f"  Leg1 rates: T1={100*l1_target/n:.1f}% Stop={100*l1_stop/n:.1f}% "
          f"TC={100*l1_tc/n:.1f}% Flat={100*l1_flat/n:.1f}%")

print("\n" + "=" * 60)
print("REPLICATION HARNESS — AGGREGATE RESULTS")
print("=" * 60)
calc_stats(ct, "CT Mode")
calc_stats(wt, "WT/NT Mode")
calc_stats(trade_log, "All-Mode Combined")

# Signal breakdown
print(f"\nSignal breakdown:")
actions = Counter(s['action'] for s in signal_log)
skips = Counter(s['skip_reason'] for s in signal_log if s['skip_reason'])
print(f"  Total signals: {len(signal_log)}")
print(f"  Traded: {actions.get('TRADE', 0)}")
print(f"  Skipped: {actions.get('SKIP', 0)}")
print(f"  Skip reasons: {dict(skips)}")

# =========================================================================
#  Compare against p2_twoleg_answer_key.csv
# =========================================================================

print("\n" + "=" * 60)
print("COMPARISON vs p2_twoleg_answer_key.csv")
print("=" * 60)

try:
    with open(f'{outdir}/p2_twoleg_answer_key.csv') as f:
        ak = list(csv.DictReader(f))

    # Answer key has no overlap filtering — it simulates all 91 trades independently.
    # Harness has overlap filtering — some trades are skipped.
    # Compare: trades that appear in BOTH (matched by entry_price + direction).
    ak_by_ep = {}
    for r in ak:
        key = (r['entry_price'], r['direction'])
        ak_by_ep[key] = r

    matched = 0
    entry_match = 0
    l1_exit_match = 0
    l2_exit_match = 0
    pnl_match = 0
    mismatches = []

    for r in trade_log:
        key = (r['entry_price'], r['direction'])
        if key not in ak_by_ep:
            continue
        a = ak_by_ep[key]
        matched += 1

        if abs(float(r['entry_price']) - float(a['entry_price'])) < 0.01:
            entry_match += 1
        if r['leg1_exit_type'] == a['leg1_exit']:
            l1_exit_match += 1
        else:
            mismatches.append(('leg1_exit', r['trade_id'], r['leg1_exit_type'], a['leg1_exit']))
        if r['leg2_exit_type'] == a['leg2_exit']:
            l2_exit_match += 1
        else:
            mismatches.append(('leg2_exit', r['trade_id'], r['leg2_exit_type'], a['leg2_exit']))
        if abs(float(r['weighted_pnl']) - float(a['weighted_pnl'])) < 1.0:
            pnl_match += 1
        else:
            mismatches.append(('wpnl', r['trade_id'],
                             r['weighted_pnl'], a['weighted_pnl']))

    print(f"Answer key trades: {len(ak)}")
    print(f"Harness trades: {len(trade_log)}")
    print(f"Matched (by entry_price+direction): {matched}")
    print(f"  Entry price match: {entry_match}/{matched}")
    print(f"  Leg1 exit match:   {l1_exit_match}/{matched}")
    print(f"  Leg2 exit match:   {l2_exit_match}/{matched}")
    print(f"  Weighted PnL (±1t): {pnl_match}/{matched}")

    if mismatches:
        print(f"\nMismatches ({len(mismatches)}):")
        for m in mismatches[:10]:
            print(f"  {m}")

    # Trades in answer key but NOT in harness (skipped by overlap/kill-switch)
    harness_keys = set((r['entry_price'], r['direction']) for r in trade_log)
    ak_only = [r for r in ak if (r['entry_price'], r['direction']) not in harness_keys]
    if ak_only:
        print(f"\nAnswer key trades not in harness ({len(ak_only)}) — skipped by overlap/kill-switch:")
        for r in ak_only[:5]:
            print(f"  {r['trade_id']} {r['datetime']} {r['direction']} {r['mode']} ep={r['entry_price']}")

except FileNotFoundError:
    print("  p2_twoleg_answer_key.csv not found — skipping comparison")
