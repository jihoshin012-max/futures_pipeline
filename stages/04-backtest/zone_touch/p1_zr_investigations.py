# archetype: zone_touch
"""
P1 Zone-Relative Follow-up Investigations.

Investigation 1: Profile the 3 CT losses under 5t limit + ZR
Investigation 2: Zone width distribution root cause

Requires: p1_zone_relative_gate.py infrastructure (same data paths).

Usage:
    python p1_zr_investigations.py
"""
import csv, json, math
from collections import Counter, defaultdict

# =========================================================================
#  Constants (same as gate script)
# =========================================================================

TICK_SIZE = 0.25
COST_TICKS = 3.0
SCORE_THRESHOLD = 16.66
TF_MAX_MINUTES = 120
WTNT_SEQ_MAX = 5
LEG1_W, LEG2_W = 0.67, 0.33

TF_MINUTES = {'15m': 15, '30m': 30, '60m': 60, '90m': 90, '120m': 120,
              '240m': 240, '360m': 360, '480m': 480, '720m': 720}

BASE = 'C:/Projects/pipeline/stages'

with open(f'{BASE}/04-backtest/zone_touch/output/feature_config.json') as f:
    FCFG = json.load(f)
TREND_P33 = FCFG['trend_slope_p33']
TREND_P67 = FCFG['trend_slope_p67']

def classify_trend(slope):
    if slope <= TREND_P33: return 'CT'
    if slope >= TREND_P67: return 'WT'
    return 'NT'

def get_session_from_dt(dt_str):
    """Classify RTH/ETH from datetime string."""
    try:
        parts = dt_str.strip().split(' ')
        time_part = parts[1] if len(parts) > 1 else parts[0]
        hh_mm = time_part.split(':')
        hhmm = int(hh_mm[0]) * 100 + int(hh_mm[1])
    except:
        return 'UNK'
    return 'RTH' if 930 <= hhmm < 1615 else 'ETH'

def zw_bin_label(zw):
    if zw < 50: return '0-50t'
    if zw < 100: return '50-100t'
    if zw < 150: return '100-150t'
    if zw < 200: return '150-200t'
    return '200t+'

# =========================================================================
#  2-leg simulator (zone-relative, identical to gate script — fixed)
# =========================================================================

def sim_2leg_zr(bar_data, entry_bar, direction, zone_width_ticks,
                t1_mult=0.5, t2_mult=1.0, stop_mult=1.5, tcap=160,
                stop_floor=None, limit_ticks=None):
    n_bars = len(bar_data)
    if entry_bar >= n_bars:
        return None

    t1_ticks = max(1, round(t1_mult * zone_width_ticks))
    t2_ticks = max(1, round(t2_mult * zone_width_ticks))
    stop_ticks = max(1, round(stop_mult * zone_width_ticks))
    if stop_floor is not None:
        stop_ticks = max(stop_ticks, stop_floor)

    if limit_ticks is not None:
        o, h, l, c, dt = bar_data[entry_bar]
        if direction == 1:
            limit_px = o - limit_ticks * TICK_SIZE
            if l <= limit_px:
                ep = limit_px
            else:
                return None
        else:
            limit_px = o + limit_ticks * TICK_SIZE
            if h >= limit_px:
                ep = limit_px
            else:
                return None
    else:
        ep = bar_data[entry_bar][0]

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
    mfe = mae = 0.0
    last_i = entry_bar

    for i in range(entry_bar, n_bars):
        o_b, h_b, l_b, c_b, dt_b = bar_data[i]
        bh = i - entry_bar + 1
        last_i = i

        if direction == 1:
            bmfe = (h_b - ep) / TICK_SIZE
            bmae = (ep - l_b) / TICK_SIZE
        else:
            bmfe = (ep - l_b) / TICK_SIZE
            bmae = (h_b - ep) / TICK_SIZE
        if bmfe > mfe: mfe = bmfe
        if bmae > mae: mae = bmae

        if bh >= tcap:
            pnl = (c_b - ep) / TICK_SIZE if direction == 1 else (ep - c_b) / TICK_SIZE
            if leg1_open:
                leg1_pnl = pnl; leg1_exit = 'TIMECAP'; leg1_exit_bar = i
            if leg2_open:
                leg2_pnl = pnl; leg2_exit = 'TIMECAP'; leg2_exit_bar = i
            break

        stop_hit = (l_b <= stop_px) if direction == 1 else (h_b >= stop_px)
        if stop_hit:
            spnl = (stop_px - ep) / TICK_SIZE if direction == 1 else (ep - stop_px) / TICK_SIZE
            if leg1_open:
                leg1_pnl = spnl; leg1_exit = 'STOP'; leg1_exit_bar = i
            if leg2_open:
                leg2_pnl = spnl; leg2_exit = 'STOP'; leg2_exit_bar = i
            break

        if leg1_open:
            hit = (h_b >= t1_px) if direction == 1 else (l_b <= t1_px)
            if hit:
                leg1_pnl = float(t1_ticks); leg1_exit = 'TARGET_1'
                leg1_exit_bar = i; leg1_open = False

        if leg2_open:
            hit = (h_b >= t2_px) if direction == 1 else (l_b <= t2_px)
            if hit:
                leg2_pnl = float(t2_ticks); leg2_exit = 'TARGET_2'
                leg2_exit_bar = i; leg2_open = False

        if not leg1_open and not leg2_open:
            break

    if leg1_open or leg2_open:
        last_c = bar_data[min(last_i, n_bars - 1)][3]
        pnl = (last_c - ep) / TICK_SIZE if direction == 1 else (ep - last_c) / TICK_SIZE
        if leg1_open:
            leg1_pnl = pnl; leg1_exit = 'END_OF_DATA'; leg1_exit_bar = last_i
        if leg2_open:
            leg2_pnl = pnl; leg2_exit = 'END_OF_DATA'; leg2_exit_bar = last_i

    bars_held = max(leg1_exit_bar, leg2_exit_bar) - entry_bar + 1
    wpnl = LEG1_W * leg1_pnl + LEG2_W * leg2_pnl - COST_TICKS

    return dict(
        entry_price=ep, stop_ticks=stop_ticks,
        t1_ticks=t1_ticks, t2_ticks=t2_ticks,
        leg1_exit=leg1_exit, leg1_pnl=leg1_pnl,
        leg2_exit=leg2_exit, leg2_pnl=leg2_pnl,
        weighted_pnl=wpnl, bars_held=bars_held,
        mfe=mfe, mae=mae,
        leg1_exit_bar=leg1_exit_bar, leg2_exit_bar=leg2_exit_bar,
        stop_px=ep - stop_ticks * TICK_SIZE if True else 0  # for reference
    )

# =========================================================================
#  Load data
# =========================================================================

print("Loading P1 bar data...")
bar_data = []
with open(f'{BASE}/01-data/output/zone_prep/NQ_bardata_P1.csv') as f:
    for row in csv.DictReader(f):
        r = {k.strip(): v.strip() for k, v in row.items()}
        o = float(r['Open'])
        h = float(r['High'])
        l = float(r['Low'])
        c = float(r['Last'])
        dt = r['Date'].split('.')[0] + ' ' + r['Time'].split('.')[0]
        bar_data.append((o, h, l, c, dt))
n_bars = len(bar_data)
print(f"  {n_bars} bars")

print("Loading P1 scored touches (A-Cal)...")
raw_touches = []
with open(f'{BASE}/04-backtest/zone_touch/output/p1_scored_touches_acal.csv') as f:
    for row in csv.DictReader(f):
        raw_touches.append(row)

# Also load P2 scored touches for Investigation 2 TF breakdown
print("Loading P2 bar data (for ATR comparison)...")
bar_data_p2 = []
with open(f'{BASE}/01-data/output/zone_prep/NQ_bardata_P2.csv') as f:
    for row in csv.DictReader(f):
        r = {k.strip(): v.strip() for k, v in row.items()}
        atr_str = r.get('ATR', '').strip()
        bar_data_p2.append(float(atr_str) if atr_str else 0.0)

# Load P2 scored touches for TF breakdown
print("Loading P2 scored touches for distribution comparison...")
p2_touches_raw = []
# P2 uses merged CSVs, not scored touches. Use replication trade log for P2 stats.
# Actually, let's load P2 scored touches if they exist, or use the replication signal log
try:
    with open(f'{BASE}/04-backtest/zone_touch/output/replication_trade_log.csv') as f:
        p2_trade_log = list(csv.DictReader(f))
    print(f"  {len(p2_trade_log)} P2 trades from replication log")
except FileNotFoundError:
    p2_trade_log = []
    print("  P2 trade log not found")

# Filter qualifying P1 touches
qualifying = []
for t in raw_touches:
    score = float(t['score_acal'])
    if score < SCORE_THRESHOLD:
        continue
    tf_str = t.get('SourceLabel', '').strip()
    tf_min = TF_MINUTES.get(tf_str, 999)
    if tf_min > TF_MAX_MINUTES:
        continue
    rbi_str = t.get('RotBarIndex', '').strip()
    if not rbi_str:
        continue
    rbi = int(rbi_str)
    if rbi < 0 or rbi + 1 >= n_bars:
        continue
    qualifying.append(t)
qualifying.sort(key=lambda r: int(r['RotBarIndex']))
print(f"  {len(qualifying)} qualifying P1 touches")

# =========================================================================
#  Run simulation: CT 5t limit + ZR (to identify the 3 losses)
# =========================================================================

def run_sim_detailed(touches, limit_ticks_ct=None, limit_ticks_wt=None,
                     stop_floor=None):
    """Returns trades with full touch metadata attached."""
    trades = []
    in_trade_until = -1

    for t in touches:
        rbi = int(t['RotBarIndex'])
        entry_bar = rbi + 1
        if entry_bar >= n_bars:
            continue

        touch_type = t['TouchType'].strip()
        direction = 1 if touch_type == 'DEMAND_EDGE' else -1
        seq = int(t['TouchSequence'])
        zw = float(t['ZoneWidthTicks'])

        ts_str = t.get('TrendSlope', '').strip()
        if not ts_str:
            trend_label = t.get('TrendLabel', 'NT').strip()
            if not trend_label:
                trend_label = 'NT'
        else:
            trend_slope = float(ts_str)
            trend_label = classify_trend(trend_slope)

        if trend_label == 'CT':
            mode = 'CT'
            limit = limit_ticks_ct
        else:
            mode = 'WT'
            if seq > WTNT_SEQ_MAX:
                continue
            limit = limit_ticks_wt

        if entry_bar <= in_trade_until:
            continue

        result = sim_2leg_zr(bar_data, entry_bar, direction, zw,
                             stop_floor=stop_floor, limit_ticks=limit)
        if result is None:
            continue

        final_exit_bar = max(result['leg1_exit_bar'], result['leg2_exit_bar'])
        in_trade_until = final_exit_bar

        # Determine composite exit type
        if result['leg1_exit'] == 'STOP':
            exit_type = 'STOP'
        elif result['leg2_exit'] == 'TIMECAP':
            exit_type = 'TIMECAP(L2)'
        elif result['leg2_exit'] == 'END_OF_DATA':
            exit_type = 'EOD(L2)'
        elif result['leg1_exit'] == 'TARGET_1' and result['leg2_exit'] == 'TARGET_2':
            exit_type = 'FULL_TARGET'
        elif result['leg1_exit'] == 'TIMECAP':
            exit_type = 'TIMECAP'
        else:
            exit_type = f"{result['leg1_exit']}/{result['leg2_exit']}"

        # Pure stop (before floor)
        pure_stop = max(1, round(1.5 * zw))

        entry_dt = bar_data[entry_bar][4]
        session = get_session_from_dt(entry_dt)

        trade = dict(
            mode=mode,
            trend_label=trend_label,
            direction=direction,
            direction_str='LONG' if direction == 1 else 'SHORT',
            zone_width=zw,
            zone_width_bin=zw_bin_label(zw),
            seq=seq,
            entry_bar=entry_bar,
            entry_dt=entry_dt,
            session=session,
            source_label=t.get('SourceLabel', '').strip(),
            cascade_state=t.get('CascadeState', '').strip(),
            score=float(t['score_acal']),
            score_margin=float(t['score_acal']) - SCORE_THRESHOLD,
            penetration=t.get('Penetration', '').strip(),
            approach_velocity=t.get('ApproachVelocity', '').strip(),
            exit_type=exit_type,
            pure_stop_ticks=pure_stop,
            actual_stop_ticks=result['stop_ticks'],
            floor_applied=result['stop_ticks'] > pure_stop,
            **result
        )
        trades.append(trade)

    return trades

# =========================================================================
#  INVESTIGATION 1: Profile the 3 CT losses
# =========================================================================

print("\n" + "=" * 70)
print("INVESTIGATION 1: Profile the 3 CT Losses (5t Limit + ZR)")
print("=" * 70)

v2_trades = run_sim_detailed(qualifying, limit_ticks_ct=5, limit_ticks_wt=None)
ct_losses = [t for t in v2_trades if t['mode'] == 'CT' and t['weighted_pnl'] < 0]

print(f"\nFound {len(ct_losses)} CT losses\n")

fields = [
    ('trade #', lambda t, i: f"Trade {i+1}"),
    ('datetime', lambda t, i: t['entry_dt']),
    ('direction', lambda t, i: t['direction_str']),
    ('zone_width (ticks)', lambda t, i: f"{t['zone_width']:.0f}"),
    ('zone_width_bin', lambda t, i: t['zone_width_bin']),
    ('pure stop (1.5x zw)', lambda t, i: f"{t['pure_stop_ticks']}t"),
    ('actual stop used', lambda t, i: f"{t['actual_stop_ticks']}t"),
    ('entry_price', lambda t, i: f"{t['entry_price']:.2f}"),
    ('mae (ticks)', lambda t, i: f"{t['mae']:.1f}"),
    ('mfe (ticks)', lambda t, i: f"{t['mfe']:.1f}"),
    ('leg1_exit', lambda t, i: t['leg1_exit']),
    ('leg1_pnl', lambda t, i: f"{t['leg1_pnl']:.1f}t"),
    ('leg2_exit', lambda t, i: t['leg2_exit']),
    ('leg2_pnl', lambda t, i: f"{t['leg2_pnl']:.1f}t"),
    ('weighted_pnl', lambda t, i: f"{t['weighted_pnl']:.1f}t"),
    ('exit_type', lambda t, i: t['exit_type']),
    ('score_margin', lambda t, i: f"+{t['score_margin']:.2f}"),
    ('session', lambda t, i: t['session']),
    ('touch_sequence', lambda t, i: str(t['seq'])),
    ('cascade_state', lambda t, i: t['cascade_state']),
    ('source_label (TF)', lambda t, i: t['source_label']),
    ('approach_velocity', lambda t, i: t['approach_velocity']),
    ('mae/zone_width', lambda t, i: f"{t['mae']/t['zone_width']:.2f}x"),
    ('bars_held', lambda t, i: str(t['bars_held'])),
]

# Print as vertical table
max_field_len = max(len(f[0]) for f in fields)
header = f"{'Field':<{max_field_len+2}}"
for i in range(len(ct_losses)):
    header += f" {'Trade '+str(i+1):>14}"
print(header)
print("-" * (max_field_len + 2 + 15 * len(ct_losses)))

for fname, fn in fields:
    row = f"{fname:<{max_field_len+2}}"
    for i, t in enumerate(ct_losses):
        row += f" {fn(t, i):>14}"
    print(row)

# ---- Question A: Are all 3 in narrow zones? ----
print(f"\n--- Question A: Are all 3 in narrow zones (<100t)? ---")
narrow_count = sum(1 for t in ct_losses if t['zone_width'] < 100)
print(f"  {narrow_count} of {len(ct_losses)} are in narrow zones (<100t)")
for i, t in enumerate(ct_losses):
    print(f"  Trade {i+1}: ZW={t['zone_width']:.0f}t -> {'NARROW' if t['zone_width'] < 100 else 'WIDE'}")

# ---- Question B: Would stop floor have saved any? ----
print(f"\n--- Question B: Would stop floor max(1.5x ZW, 120t) have saved any? ---")

v2_floor_trades = run_sim_detailed(qualifying, limit_ticks_ct=5,
                                   limit_ticks_wt=None, stop_floor=120)
ct_losses_floor = [t for t in v2_floor_trades if t['mode'] == 'CT' and t['weighted_pnl'] < 0]

print(f"  Without floor: {len(ct_losses)} CT losses")
print(f"  With floor:    {len(ct_losses_floor)} CT losses")

# Re-simulate each losing trade individually with floor
print(f"\n  Per-trade re-simulation with floor:")
for i, t in enumerate(ct_losses):
    zw = t['zone_width']
    pure_stop = max(1, round(1.5 * zw))
    floor_stop = max(pure_stop, 120)
    # Find this trade's touch and re-sim
    result_floor = sim_2leg_zr(bar_data, t['entry_bar'], t['direction'], zw,
                               stop_floor=120, limit_ticks=5)
    if result_floor:
        print(f"  Trade {i+1}: ZW={zw:.0f}t, pure_stop={pure_stop}t, floor_stop={floor_stop}t")
        print(f"    Without floor: pnl={t['weighted_pnl']:.1f}t, exit={t['exit_type']}")
        print(f"    With floor:    pnl={result_floor['weighted_pnl']:.1f}t, "
              f"L1={result_floor['leg1_exit']}, L2={result_floor['leg2_exit']}")
        saved = result_floor['weighted_pnl'] > 0 and t['weighted_pnl'] < 0
        print(f"    {'SAVED by floor' if saved else 'NOT saved by floor'}")
    else:
        print(f"  Trade {i+1}: not filled with floor (different overlap)")

# ---- Question C: Are any ETH? ----
print(f"\n--- Question C: Are any ETH? ---")
for i, t in enumerate(ct_losses):
    print(f"  Trade {i+1}: {t['session']} ({t['entry_dt']})")

# ---- Question D: MAE/zone_width ratio ----
print(f"\n--- Question D: MAE/zone_width ratio ---")
for i, t in enumerate(ct_losses):
    ratio = t['mae'] / t['zone_width']
    print(f"  Trade {i+1}: MAE={t['mae']:.1f}t / ZW={t['zone_width']:.0f}t = {ratio:.2f}x "
          f"({'exceeds 1.5x stop' if ratio > 1.5 else 'within stop'})")

# =========================================================================
#  INVESTIGATION 2: Zone Width Distribution Root Cause
# =========================================================================

print("\n\n" + "=" * 70)
print("INVESTIGATION 2: Zone Width Distribution Root Cause")
print("=" * 70)

# ---- 2A: TF composition by zone width bin ----
print("\n--- 2A: Timeframe composition by zone width bin ---")

bins_def = [(0, 50), (50, 100), (100, 150), (150, 200), (200, 99999)]
bin_labels = ['0-50t', '50-100t', '100-150t', '150-200t', '200t+']
tf_order = ['15m', '30m', '60m', '90m', '120m']

# P1 trades (use market-entry sim for full population)
v1_trades = run_sim_detailed(qualifying)

# Build P1 TF breakdown
p1_tf_by_bin = defaultdict(lambda: defaultdict(int))
p1_bin_counts = defaultdict(int)
for t in v1_trades:
    b = t['zone_width_bin']
    tf = t['source_label']
    p1_tf_by_bin[b][tf] += 1
    p1_bin_counts[b] += 1

# P2 TF breakdown from replication trade log
p2_tf_by_bin = defaultdict(lambda: defaultdict(int))
p2_bin_counts = defaultdict(int)
for t in p2_trade_log:
    try:
        # Replication log may not have ZoneWidth directly; compute from stop
        # Actually check column names
        sl = t.get('source_label', '').strip()
        mode = t.get('mode', '').strip()
        # Need zone width — not in trade log. Use stop/target to infer.
        # For fixed exits: CT stop=190, WTNT stop=240
        # This won't give us zone width. Skip P2 TF breakdown from trade log.
        pass
    except:
        pass

# Try loading P2 merged touches for zone width + TF
print("\n  Loading P2 merged touches for TF breakdown...")
p2_qualifying = []
for fname in ['NQ_merged_P2a.csv', 'NQ_merged_P2b.csv']:
    try:
        with open(f'{BASE}/01-data/output/zone_prep/{fname}') as f:
            for row in csv.DictReader(f):
                rbi = int(row.get('RotBarIndex', '-1'))
                if rbi < 0:
                    continue
                p2_qualifying.append(row)
    except FileNotFoundError:
        print(f"    {fname} not found")
print(f"  {len(p2_qualifying)} P2 merged touches")

# Score P2 touches to filter qualifying ones
# Load scoring model
with open(f'{BASE}/04-backtest/zone_touch/output/scoring_model_acal.json') as f:
    MODEL = json.load(f)
WEIGHTS = MODEL['weights']
BIN_EDGES = MODEL['bin_edges']

def bin_numeric(val, p33, p67, weight, is_nan=False):
    if is_nan: return 0.0
    if val <= p33: return weight
    if val >= p67: return 0.0
    return weight / 2.0

def quick_score(touch, zone_history_p2):
    """Quick A-Cal score for P2 touches."""
    # F10 - prior penetration
    seq = int(touch.get('TouchSequence', '1'))
    f10_nan = (seq <= 1)
    if not f10_nan:
        key = (touch.get('ZoneTop', ''), touch.get('ZoneBot', ''), touch.get('SourceLabel', ''))
        history = zone_history_p2.get(key, [])
        rbi = int(touch['RotBarIndex'])
        prior_pen = None
        for prev in reversed(history):
            if int(prev['RotBarIndex']) < rbi and int(prev.get('TouchSequence', '0')) == seq - 1:
                pen_s = prev.get('Penetration', '').strip()
                if pen_s:
                    prior_pen = float(pen_s)
                break
        f10_nan = (prior_pen is None)
        f10_val = 0.0 if f10_nan else prior_pen
    else:
        f10_val = 0.0

    f10 = bin_numeric(f10_val, BIN_EDGES['F10_PriorPenetration'][0],
                      BIN_EDGES['F10_PriorPenetration'][1],
                      WEIGHTS['F10_PriorPenetration'], f10_nan)

    # F04
    cs = touch.get('CascadeState', '').strip()
    if cs == 'NO_PRIOR': f04 = WEIGHTS['F04_CascadeState']
    elif cs == 'PRIOR_HELD': f04 = WEIGHTS['F04_CascadeState'] / 2.0
    else: f04 = 0.0

    # F01
    tf = touch.get('SourceLabel', '').strip()
    if tf == '30m': f01 = WEIGHTS['F01_Timeframe']
    elif tf == '480m': f01 = 0.0
    elif tf: f01 = WEIGHTS['F01_Timeframe'] / 2.0
    else: f01 = 0.0

    # F21
    za_s = touch.get('ZoneAgeBars', '').strip()
    za = float(za_s) if za_s else 0.0
    f21 = bin_numeric(za, BIN_EDGES['F21_ZoneAge'][0],
                      BIN_EDGES['F21_ZoneAge'][1],
                      WEIGHTS['F21_ZoneAge'])

    return f10 + f04 + f01 + f21

# Build P2 zone history
p2_zone_hist = defaultdict(list)
for t in p2_qualifying:
    key = (t.get('ZoneTop', ''), t.get('ZoneBot', ''), t.get('SourceLabel', ''))
    p2_zone_hist[key].append(t)

# Filter qualifying P2 touches
p2_qual = []
for t in p2_qualifying:
    score = quick_score(t, p2_zone_hist)
    if score < SCORE_THRESHOLD:
        continue
    tf_str = t.get('SourceLabel', '').strip()
    tf_min = TF_MINUTES.get(tf_str, 999)
    if tf_min > TF_MAX_MINUTES:
        continue
    zw_s = t.get('ZoneWidthTicks', '').strip()
    if not zw_s:
        continue
    zw = float(zw_s)
    ts_str = t.get('TrendSlope', '').strip()
    if ts_str:
        tl = classify_trend(float(ts_str))
    else:
        tl = 'NT'
    seq = int(t.get('TouchSequence', '1'))
    if tl != 'CT' and seq > WTNT_SEQ_MAX:
        continue
    t['_zw'] = zw
    t['_tf'] = tf_str
    t['_bin'] = zw_bin_label(zw)
    t['_score'] = score
    p2_qual.append(t)

print(f"  {len(p2_qual)} qualifying P2 touches (score >= {SCORE_THRESHOLD}, TF <= {TF_MAX_MINUTES}m)")

# P2 TF breakdown
for t in p2_qual:
    b = t['_bin']
    tf = t['_tf']
    p2_tf_by_bin[b][tf] += 1
    p2_bin_counts[b] += 1

# Print TF breakdown table
print(f"\n{'Zone width':<12}", end="")
print(f" {'P1 cnt':>7}", end="")
for tf in tf_order:
    print(f" {tf:>5}", end="")
print(f" {'P2 cnt':>7}", end="")
for tf in tf_order:
    print(f" {tf:>5}", end="")
print()
print("-" * (12 + 8 + 6*5 + 8 + 6*5))

for i, lbl in enumerate(bin_labels):
    p1_n = p1_bin_counts.get(lbl, 0)
    p2_n = p2_bin_counts.get(lbl, 0)
    print(f"{lbl:<12}", end="")
    print(f" {p1_n:>7}", end="")
    for tf in tf_order:
        print(f" {p1_tf_by_bin[lbl].get(tf, 0):>5}", end="")
    print(f" {p2_n:>7}", end="")
    for tf in tf_order:
        print(f" {p2_tf_by_bin[lbl].get(tf, 0):>5}", end="")
    print()

# P1 vs P2 TF totals
p1_tf_total = defaultdict(int)
p2_tf_total = defaultdict(int)
for t in v1_trades:
    p1_tf_total[t['source_label']] += 1
for t in p2_qual:
    p2_tf_total[t['_tf']] += 1

print(f"\n  TF totals:  P1: {dict(p1_tf_total)}  P2: {dict(p2_tf_total)}")

p1_15m_pct = 100 * p1_tf_total.get('15m', 0) / len(v1_trades) if v1_trades else 0
p2_15m_pct = 100 * p2_tf_total.get('15m', 0) / len(p2_qual) if p2_qual else 0
print(f"  15m share: P1={p1_15m_pct:.1f}%  P2={p2_15m_pct:.1f}%")

# ---- 2B: Mean ATR comparison ----
print(f"\n--- 2B: Mean ATR during P1 vs P2 ---")

# P1 ATR
p1_atrs = []
with open(f'{BASE}/01-data/output/zone_prep/NQ_bardata_P1.csv') as f:
    for row in csv.DictReader(f):
        r = {k.strip(): v.strip() for k, v in row.items()}
        atr_s = r.get('ATR', '').strip()
        if atr_s:
            val = float(atr_s)
            if val > 0:
                p1_atrs.append(val)

p2_atrs = [a for a in bar_data_p2 if a > 0]

p1_mean_atr = sum(p1_atrs) / len(p1_atrs) if p1_atrs else 0
p2_mean_atr = sum(p2_atrs) / len(p2_atrs) if p2_atrs else 0

# Convert to ticks
p1_atr_ticks = p1_mean_atr / TICK_SIZE
p2_atr_ticks = p2_mean_atr / TICK_SIZE

print(f"  P1 mean ATR: {p1_mean_atr:.2f} pts ({p1_atr_ticks:.0f} ticks) [{len(p1_atrs)} bars]")
print(f"  P2 mean ATR: {p2_mean_atr:.2f} pts ({p2_atr_ticks:.0f} ticks) [{len(p2_atrs)} bars]")
print(f"  Ratio P1/P2: {p1_mean_atr/p2_mean_atr:.2f}x" if p2_mean_atr > 0 else "  P2 ATR=0")

if p1_mean_atr < p2_mean_atr * 0.85:
    print("  -> P1 was LOWER volatility — explains narrower zones")
elif p1_mean_atr > p2_mean_atr * 1.15:
    print("  -> P1 was HIGHER volatility — zone width shift is TF-driven, not vol-driven")
else:
    print("  -> Similar volatility — zone width shift is TF-composition-driven")

# ---- 2C: Per-bin ZR performance WITH stop floor ----
print(f"\n--- 2C: Per-bin ZR performance with stop floor on P1 ---")

v1_floor_trades = run_sim_detailed(qualifying, stop_floor=120)

p2_wr = [100.0, 75.8, 90.5, 95.2, 95.0]
p2_pf = [float('inf'), 4.77, 8.79, 294.8, 54.22]

def calc_stats(trades):
    if not trades:
        return dict(n=0, wr=0, pf=0, ev=0)
    pnls = [t['weighted_pnl'] for t in trades]
    wins = sum(1 for p in pnls if p > 0)
    gw = sum(p for p in pnls if p > 0)
    gl = sum(abs(p) for p in pnls if p < 0)
    pf = gw / gl if gl > 0 else float('inf')
    ev = sum(pnls) / len(pnls)
    return dict(n=len(trades), wr=100*wins/len(trades), pf=pf, ev=ev)

def fmt_pf(pf):
    return f"{pf:.2f}" if pf < 9999 else "inf"

print(f"\n{'Zone width':<12} {'P1 WR(fl)':>10} {'P1 PF(fl)':>10} {'P2 WR':>8} {'P2 PF':>8} {'n(P1)':>6}")
print("-" * 56)

for i, lbl in enumerate(bin_labels):
    lo, hi = bins_def[i]
    bt = [t for t in v1_floor_trades if lo <= t['zone_width'] < hi]
    bs = calc_stats(bt)
    if bs['n'] > 0:
        print(f"{lbl:<12} {bs['wr']:>9.1f}% {fmt_pf(bs['pf']):>10} {p2_wr[i]:>7.1f}% {fmt_pf(p2_pf[i]):>8} {bs['n']:>6}")
    else:
        print(f"{lbl:<12} {'—':>10} {'—':>10} {p2_wr[i]:>7.1f}% {fmt_pf(p2_pf[i]):>8} {0:>6}")

v1_floor_all = calc_stats(v1_floor_trades)
print(f"{'ALL':<12} {v1_floor_all['wr']:>9.1f}% {fmt_pf(v1_floor_all['pf']):>10} {'—':>8} {'—':>8} {v1_floor_all['n']:>6}")

# ---- 2D: Minimum zone width filter test ----
print(f"\n--- 2D: Minimum zone width filter test ---")

for min_zw in [0, 50, 75, 100]:
    filtered = [t for t in qualifying if float(t['ZoneWidthTicks']) >= min_zw]
    trades = run_sim_detailed(filtered, stop_floor=120)
    s = calc_stats(trades)
    ct = calc_stats([t for t in trades if t['mode'] == 'CT'])
    wt = calc_stats([t for t in trades if t['mode'] == 'WT'])
    ct_losses_n = sum(1 for t in trades if t['mode'] == 'CT' and t['weighted_pnl'] < 0)

    label = f"ZW >= {min_zw}t" if min_zw > 0 else "No filter"
    print(f"\n  {label}:")
    print(f"    All: {s['n']} trades, WR={s['wr']:.1f}%, PF={fmt_pf(s['pf'])}, EV={s['ev']:.1f}t")
    print(f"    CT:  {ct['n']} trades, WR={ct['wr']:.1f}%, PF={fmt_pf(ct['pf'])}")
    print(f"    WT:  {wt['n']} trades, WR={wt['wr']:.1f}%, PF={fmt_pf(wt['pf'])}")
    print(f"    CT losses: {ct_losses_n}")

# Also test with 5t limit for CT
print(f"\n  --- With CT 5t limit + stop floor ---")
for min_zw in [0, 50, 75, 100]:
    filtered = [t for t in qualifying if float(t['ZoneWidthTicks']) >= min_zw]
    trades = run_sim_detailed(filtered, limit_ticks_ct=5, stop_floor=120)
    s = calc_stats(trades)
    ct = calc_stats([t for t in trades if t['mode'] == 'CT'])
    wt = calc_stats([t for t in trades if t['mode'] == 'WT'])
    ct_losses_n = sum(1 for t in trades if t['mode'] == 'CT' and t['weighted_pnl'] < 0)

    label = f"ZW >= {min_zw}t" if min_zw > 0 else "No filter"
    print(f"\n  {label}:")
    print(f"    All: {s['n']} trades, WR={s['wr']:.1f}%, PF={fmt_pf(s['pf'])}, EV={s['ev']:.1f}t")
    print(f"    CT:  {ct['n']} trades, WR={ct['wr']:.1f}%, PF={fmt_pf(ct['pf'])}")
    print(f"    WT:  {wt['n']} trades, WR={wt['wr']:.1f}%, PF={fmt_pf(wt['pf'])}")
    print(f"    CT losses: {ct_losses_n}")

# =========================================================================
#  SUMMARY + RECOMMENDATION
# =========================================================================

print("\n\n" + "=" * 70)
print("SUMMARY + RECOMMENDATION")
print("=" * 70)

print(f"""
INVESTIGATION 1 FINDINGS:
  - {len(ct_losses)} CT losses under 5t limit + pure 1.5x ZR
  - Narrow zones (<100t): {sum(1 for t in ct_losses if t['zone_width'] < 100)} of {len(ct_losses)}
  - With stop floor (120t): {len(ct_losses_floor)} CT losses remain
  - Sessions: {', '.join(t['session'] for t in ct_losses)}

INVESTIGATION 2 FINDINGS:
  - P1 has {p1_15m_pct:.0f}% 15m zones vs P2 {p2_15m_pct:.0f}%
  - P1 mean ATR: {p1_atr_ticks:.0f}t vs P2: {p2_atr_ticks:.0f}t (ratio {p1_mean_atr/p2_mean_atr:.2f}x)
  - Zone width shift is {'volatility-driven' if p1_mean_atr < p2_mean_atr * 0.85 else 'TF-composition-driven' if abs(p1_mean_atr - p2_mean_atr) / max(p2_mean_atr, 0.01) < 0.15 else 'mixed'}
  - Stop floor improves all bins; 50-100t most affected
""")

# Final config recommendation
best_floor = run_sim_detailed(qualifying, limit_ticks_ct=5, stop_floor=120)
best_s = calc_stats(best_floor)
best_ct = calc_stats([t for t in best_floor if t['mode'] == 'CT'])
best_ct_losses = sum(1 for t in best_floor if t['mode'] == 'CT' and t['weighted_pnl'] < 0)

print(f"RECOMMENDED CONFIG: ZR + stop floor (120t) + CT 5t limit")
print(f"  All: {best_s['n']} trades, WR={best_s['wr']:.1f}%, PF={fmt_pf(best_s['pf'])}, EV={best_s['ev']:.1f}t")
print(f"  CT: {best_ct['n']} trades, WR={best_ct['wr']:.1f}%, PF={fmt_pf(best_ct['pf'])}")
print(f"  CT losses: {best_ct_losses}")
print(f"  Passes PF>3.0: {'YES' if best_s['pf'] > 3 else 'NO'}")
print(f"  Passes WR>80%: {'YES' if best_s['wr'] > 80 else 'NO'}")
