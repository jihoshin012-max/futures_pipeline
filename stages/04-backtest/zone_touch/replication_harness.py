# archetype: zone_touch
"""
Replication Harness v3.0 — ATEAM_ZONE_BOUNCE_V1 (zone-relative exits).

Zone-relative exit framework:
  T1 = 0.5 × zone_width_ticks from entry
  T2 = 1.0 × zone_width_ticks from entry
  Stop = max(1.5 × zone_width_ticks, 120) from entry
  Time cap = 160 bars
  2-leg: 67/33 split, cost 3t per trade

CT entry: 5t limit inside zone edge (20-bar fill window)
WT entry: market at next bar open

Reads P2 bar data + merged zone touches, runs identical scoring + 2-leg exit
logic as the C++ autotrader, outputs trade_log and skipped_signals CSVs.

Usage:
    python replication_harness.py

Outputs:
    output/p2_twoleg_answer_key_zr.csv   — full Part A trade log (zone-relative)
    output/p2_skipped_signals_zr.csv     — all skipped signals with reasons
    stdout                               — aggregate stats + verification
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

# Zone-relative exit multipliers (Part A v3.0)
T1_MULT = 0.5
T2_MULT = 1.0
STOP_MULT = 1.5
STOP_FLOOR = 120      # ticks — protects narrow zones
TCAP = 160             # bars
LEG1_W, LEG2_W = 0.67, 0.33

# CT limit entry
CT_LIMIT_TICKS = 5     # 5t inside zone edge
CT_LIMIT_WINDOW = 20   # bars to scan for fill

TF_MAX_MINUTES = 120
WTNT_SEQ_MAX = 5

# Kill-switch
KS_CONSEC = 3
KS_DAILY = -400.0
KS_WEEKLY = -800.0

# EOD flatten (live only — disabled for backtest replication fidelity)
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
#  CT limit fill scanner (20-bar window)
# =========================================================================

def scan_ct_limit_fill(bar_data, touch_bar, direction, zone_top, zone_bot):
    """
    CT 5t limit entry: place limit order 5 ticks inside zone edge.
      DEMAND (LONG):  limit = ZoneTop - 5 × tick_size
      SUPPLY (SHORT): limit = ZoneBot + 5 × tick_size

    Scan bars 1..20 after touch bar for fill.
      LONG fill:  first bar where Low <= limit_price
      SHORT fill: first bar where High >= limit_price
      Fill price: min(Open, limit) for LONG, max(Open, limit) for SHORT

    Returns: (fill_bar, fill_price, bars_to_fill) or None if expired.
    """
    n_bars = len(bar_data)

    if direction == 1:
        limit_price = zone_top - CT_LIMIT_TICKS * TICK_SIZE
    else:
        limit_price = zone_bot + CT_LIMIT_TICKS * TICK_SIZE

    for offset in range(1, CT_LIMIT_WINDOW + 1):
        bar_idx = touch_bar + offset
        if bar_idx >= n_bars:
            break
        o, h, l, c, dt = bar_data[bar_idx]

        if direction == 1:
            if l <= limit_price:
                fill_price = min(o, limit_price)
                return (bar_idx, fill_price, offset)
        else:
            if h >= limit_price:
                fill_price = max(o, limit_price)
                return (bar_idx, fill_price, offset)

    return None  # LIMIT_EXPIRED

# =========================================================================
#  2-leg simulator (zone-relative version)
# =========================================================================

def sim_2leg_zr(bar_data, entry_bar, entry_price, direction,
                zone_width_ticks):
    """
    Zone-relative 2-leg exit simulator.

    Exit levels computed from entry_price (not zone edge):
      T1 = 0.5 × zone_width_ticks
      T2 = 1.0 × zone_width_ticks
      Stop = max(1.5 × zone_width_ticks, 120)
      Time cap = 160 bars
    """
    n_bars = len(bar_data)
    if entry_bar >= n_bars:
        return None

    ep = entry_price
    t1_ticks = max(1, round(T1_MULT * zone_width_ticks))
    t2_ticks = max(1, round(T2_MULT * zone_width_ticks))
    stop_ticks = max(round(STOP_MULT * zone_width_ticks), STOP_FLOOR)

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

        # Time cap
        if bh >= TCAP:
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
        stop_ticks=stop_ticks, t1_ticks=t1_ticks, t2_ticks=t2_ticks,
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

# ---- Population assertion: detect multi-group duplicates ----
seen_keys = {}
n_dupes = 0
for t in touches:
    key = (t['DateTime'], t['TouchType'], t['ZoneTop'], t['ZoneBot'])
    if key in seen_keys:
        n_dupes += 1
    else:
        seen_keys[key] = True
if n_dupes > 0:
    print(f"  WARNING: {n_dupes} duplicate trade keys (DateTime+TouchType+Zone).")
    print("  This file may contain multi-group rows, not unique trades.")
    print("  Deduplicate before using as a trade population.")
else:
    print(f"  Population check: {len(touches)} unique trade keys (OK)")

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
#  Main simulation loop
#  - Zone-relative exits (0.5x/1.0x/1.5x zone_width, stop floor 120t)
#  - CT: 5t limit entry with 20-bar fill window
#  - WT: market at next bar open
#  - LIMIT_PENDING: while CT limit is active, ALL new signals are blocked
#  - No-overlap: if in position, skip new signals
#  - Kill-switch: consecutive loss / daily / weekly limits
# =========================================================================

print("\nRunning replication simulation (zone-relative v3.0)...")

trade_log = []
signal_log = []    # ALL signals (traded + skipped) — for comprehensive log
skipped_log = []   # Skipped signals only — separate output file

# Position state
in_trade_until = -1       # bar index when current trade fully exits

# CT limit pending state
ct_limit_pending = False
ct_limit_expires_at = -1  # bar index when limit expires (touch_bar + 20)

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

# CT limit fill tracking
ct_limit_signals = 0
ct_limit_fills = 0
ct_limit_expired = 0
ct_fill_bars = []        # bars to fill for filled orders
ct_price_improvements = 0  # fills better than limit price

for touch in touches:
    rbi = int(touch['RotBarIndex'])
    touch_bar = rbi
    # For WT: entry at next bar open (rbi + 1)
    # For CT: entry determined by limit fill scan
    wt_entry_bar = rbi + 1
    if wt_entry_bar >= n_bars:
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

    # Zone data
    zone_top = float(touch['ZoneTop'])
    zone_bot = float(touch['ZoneBot'])
    zw_str = touch.get('ZoneWidthTicks', '').strip()
    if zw_str:
        zone_width_ticks = float(zw_str)
    else:
        zone_width_ticks = (zone_top - zone_bot) / TICK_SIZE

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

    # Entry bar datetime for logging (use touch bar + 1 as reference)
    entry_dt = bar_data[wt_entry_bar][4]

    # ---- Check if CT limit has expired ----
    if ct_limit_pending and rbi >= ct_limit_expires_at:
        ct_limit_pending = False

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

    # No-overlap: in active position
    if skip_reason is None and wt_entry_bar <= in_trade_until:
        skip_reason = 'IN_POSITION'

    # LIMIT_PENDING: CT limit order is active (placed but not filled/expired)
    if skip_reason is None and ct_limit_pending:
        skip_reason = 'LIMIT_PENDING'

    # Kill-switch
    if skip_reason is None:
        if ks_session_halted or ks_daily_halted or ks_weekly_halted:
            skip_reason = 'KILL_SWITCH'

    # ---- Log signal (comprehensive) ----
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
        # Log to skipped signals output
        skipped_log.append(dict(
            datetime=entry_dt,
            touch_type=touch_type,
            source_label=tf_str,
            acal_score=f"{acal_score:.4f}",
            trend_label=trend_label,
            skip_reason=skip_reason
        ))
        continue

    # ---- Execute trade (mode-dependent entry) ----

    if mode == 'CT':
        # CT: 5t limit entry with 20-bar fill window
        ct_limit_signals += 1

        # Mark limit as pending BEFORE scanning for fill.
        # Subsequent touches with rbi < expires_at will see LIMIT_PENDING.
        ct_limit_pending = True
        ct_limit_expires_at = touch_bar + CT_LIMIT_WINDOW

        fill_result = scan_ct_limit_fill(
            bar_data, touch_bar, direction, zone_top, zone_bot)

        if fill_result is None:
            # LIMIT_EXPIRED — no fill within 20 bars.
            # Leave ct_limit_pending = True so signals with rbi in
            # [touch_bar+1, touch_bar+19] see LIMIT_PENDING.
            # The expiry check at loop top clears it when rbi >= expires_at.
            ct_limit_expired += 1
            skipped_log.append(dict(
                datetime=entry_dt,
                touch_type=touch_type,
                source_label=tf_str,
                acal_score=f"{acal_score:.4f}",
                trend_label=trend_label,
                skip_reason='LIMIT_EXPIRED'
            ))
            continue

        fill_bar, fill_price, bars_to_fill = fill_result
        ct_limit_fills += 1
        ct_fill_bars.append(bars_to_fill)

        # Check price improvement
        if direction == 1:
            limit_px = zone_top - CT_LIMIT_TICKS * TICK_SIZE
            if fill_price < limit_px:
                ct_price_improvements += 1
        else:
            limit_px = zone_bot + CT_LIMIT_TICKS * TICK_SIZE
            if fill_price > limit_px:
                ct_price_improvements += 1

        # Filled — clear pending. in_trade_until covers blocking from
        # fill_bar onward (IN_POSITION). Signals between touch_bar+1 and
        # fill_bar-1 are covered by in_trade_until too since
        # final_exit_bar >= fill_bar and wt_entry_bar = rbi+1 <= final_exit_bar.
        ct_limit_pending = False

        entry_bar = fill_bar
        entry_price = fill_price
        entry_type = 'LIMIT_5T'
        entry_dt = bar_data[entry_bar][4]

    else:
        # WT/NT: market at next bar open
        entry_bar = wt_entry_bar
        entry_price = bar_data[entry_bar][0]  # Open
        entry_type = 'MARKET'
        entry_dt = bar_data[entry_bar][4]

    # Simulate 2-leg exit
    result = sim_2leg_zr(bar_data, entry_bar, entry_price, direction,
                         zone_width_ticks)
    if result is None:
        continue

    trade_counter += 1
    trade_id = f"ZB_{trade_counter:04d}"

    # Update position state
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
    row = dict(
        trade_id=trade_id,
        mode=mode,
        datetime=entry_dt,
        direction='LONG' if direction == 1 else 'SHORT',
        touch_type=touch_type,
        source_label=tf_str,
        zone_top=f"{zone_top:.2f}",
        zone_bot=f"{zone_bot:.2f}",
        zone_width_ticks=f"{zone_width_ticks:.1f}",
        entry_type=entry_type,
        entry_price=f"{result['entry_price']:.2f}",
        stop_ticks=result['stop_ticks'],
        t1_ticks=result['t1_ticks'],
        t2_ticks=result['t2_ticks'],
        stop_price=f"{result['stop_price']:.2f}",
        t1_target_price=f"{result['t1_target']:.2f}",
        t2_target_price=f"{result['t2_target']:.2f}",
        leg1_exit_type=result['leg1_exit'],
        leg1_pnl_ticks=f"{result['leg1_pnl']:.2f}",
        leg2_exit_type=result['leg2_exit'],
        leg2_pnl_ticks=f"{result['leg2_pnl']:.2f}",
        weighted_pnl=f"{wpnl:.4f}",
        bars_held=result['bars_held'],
        mfe_ticks=f"{result['mfe']:.2f}",
        mae_ticks=f"{result['mae']:.2f}",
    )
    trade_log.append(row)

# =========================================================================
#  Write output CSVs
# =========================================================================

TRADE_COLS = [
    'trade_id', 'mode', 'datetime', 'direction', 'touch_type', 'source_label',
    'zone_top', 'zone_bot', 'zone_width_ticks',
    'entry_type', 'entry_price',
    'stop_ticks', 't1_ticks', 't2_ticks',
    'stop_price', 't1_target_price', 't2_target_price',
    'leg1_exit_type', 'leg1_pnl_ticks',
    'leg2_exit_type', 'leg2_pnl_ticks',
    'weighted_pnl', 'bars_held', 'mfe_ticks', 'mae_ticks',
]

SKIPPED_COLS = [
    'datetime', 'touch_type', 'source_label', 'acal_score', 'trend_label',
    'skip_reason'
]

SIGNAL_COLS = [
    'datetime', 'touch_type', 'source_label', 'acal_score', 'score_margin',
    'trend_label', 'sbb_label', 'action', 'skip_reason', 'current_position_pnl'
]

outdir = f'{BASE}/04-backtest/zone_touch/output'

with open(f'{outdir}/p2_twoleg_answer_key_zr.csv', 'w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=TRADE_COLS)
    writer.writeheader()
    writer.writerows(trade_log)

with open(f'{outdir}/p2_skipped_signals_zr.csv', 'w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=SKIPPED_COLS)
    writer.writeheader()
    writer.writerows(skipped_log)

with open(f'{outdir}/replication_signal_log.csv', 'w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=SIGNAL_COLS)
    writer.writeheader()
    writer.writerows(signal_log)

print(f"\nWrote {len(trade_log)} trades to p2_twoleg_answer_key_zr.csv")
print(f"Wrote {len(skipped_log)} skipped signals to p2_skipped_signals_zr.csv")
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
    print(f"  Leg1 rates: T1={100*l1_target/n:.1f}% Stop={100*l1_stop/n:.1f}% "
          f"TC={100*l1_tc/n:.1f}%")

print("\n" + "=" * 60)
print("REPLICATION HARNESS v3.0 — AGGREGATE RESULTS")
print("  Zone-relative: T1=0.5x, T2=1.0x, Stop=max(1.5x, 120t)")
print("  CT: 5t limit (20-bar window), WT: market")
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
#  CT 5t Limit Fill Verification
# =========================================================================

print("\n" + "=" * 60)
print("CT 5T LIMIT FILL VERIFICATION")
print("=" * 60)
print(f"  CT signals (qualified):  {ct_limit_signals}")
print(f"  CT fills (within 20b):   {ct_limit_fills}")
print(f"  CT expired (no fill):    {ct_limit_expired}")
if ct_limit_signals > 0:
    fill_rate = 100 * ct_limit_fills / ct_limit_signals
    print(f"  Fill rate:               {fill_rate:.1f}%  (target ~95%)")
if ct_fill_bars:
    mean_bars = sum(ct_fill_bars) / len(ct_fill_bars)
    print(f"  Mean bars to fill:       {mean_bars:.1f}")
    print(f"  Median bars to fill:     {sorted(ct_fill_bars)[len(ct_fill_bars)//2]}")
    print(f"  Max bars to fill:        {max(ct_fill_bars)}")
print(f"  Price improvement fills: {ct_price_improvements}")

# =========================================================================
#  Verification vs Exit Investigation Benchmarks
# =========================================================================

print("\n" + "=" * 60)
print("VERIFICATION vs EXIT INVESTIGATION (P2)")
print("=" * 60)
print("  NOTE: Exit investigation ran CT/WT independently (no LIMIT_PENDING).")
print("  Small WT count differences expected.\n")

all_pnls = [float(r['weighted_pnl']) for r in trade_log]
all_wins = sum(1 for p in all_pnls if p > 0)
all_gw = sum(p for p in all_pnls if p > 0)
all_gl = sum(abs(p) for p in all_pnls if p < 0)
all_pf = all_gw / all_gl if all_gl > 0 else float('inf')
all_wr = 100 * all_wins / len(all_pnls) if all_pnls else 0

n_ct = len(ct)
n_wt = len(wt)
lp_skips = sum(1 for s in skipped_log if s['skip_reason'] == 'LIMIT_PENDING')
le_skips = sum(1 for s in skipped_log if s['skip_reason'] == 'LIMIT_EXPIRED')

print(f"{'Metric':<24} {'Harness':>10} {'Exit Inv':>10} {'Match?':>8}")
print("-" * 54)
print(f"{'Total trades':<24} {len(trade_log):>10} {'~302':>10} {'':>8}")
print(f"{'CT trades (filled)':<24} {n_ct:>10} {'~177':>10} {'':>8}")
print(f"{'CT LIMIT_EXPIRED':<24} {ct_limit_expired:>10} {'~10':>10} {'':>8}")
print(f"{'WT trades':<24} {n_wt:>10} {'<=125':>10} {'':>8}")
print(f"{'LIMIT_PENDING skips':<24} {lp_skips:>10} {'small':>10} {'':>8}")
print(f"{'WR':<24} {all_wr:>9.1f}% {'~92.0%':>10} {'':>8}")
pf_str = f"{all_pf:.2f}" if all_pf < 9999 else "inf"
print(f"{'PF':<24} {pf_str:>10} {'~28.69':>10} {'':>8}")

# =========================================================================
#  Rename old answer key for reference
# =========================================================================

import os, shutil
old_ak = f'{outdir}/p2_twoleg_answer_key.csv'
renamed_ak = f'{outdir}/p2_twoleg_answer_key_fixed.csv'
if os.path.exists(old_ak) and not os.path.exists(renamed_ak):
    shutil.copy2(old_ak, renamed_ak)
    print(f"\nCopied old answer key to p2_twoleg_answer_key_fixed.csv")

print("\nReplication harness v3.0 complete.")
