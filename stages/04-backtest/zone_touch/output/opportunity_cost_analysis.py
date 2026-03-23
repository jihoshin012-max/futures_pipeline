# archetype: zone_touch
"""
Opportunity Cost Analysis — blocked signals from IN_POSITION and LIMIT_PENDING.

Profiles blocked vs traded signals, simulates blocked signals independently,
analyzes overlap status, tests priority override and 2-position variants.

Usage:
    python stages/04-backtest/zone_touch/output/opportunity_cost_analysis.py
"""
import csv, json, sys
from collections import Counter, defaultdict

TICK_SIZE = 0.25
COST_TICKS = 3.0
SCORE_THRESHOLD = 16.66
LEG1_W, LEG2_W = 0.67, 0.33
T1_MULT, T2_MULT, STOP_MULT = 0.5, 1.0, 1.5
STOP_FLOOR = 120
TCAP = 160
CT_LIMIT_TICKS = 5
CT_LIMIT_WINDOW = 20
TF_MAX = 120
WTNT_SEQ_MAX = 5

BASE = 'C:/Projects/pipeline/stages'

with open(f'{BASE}/04-backtest/zone_touch/output/feature_config.json') as f:
    FCFG = json.load(f)
with open(f'{BASE}/04-backtest/zone_touch/output/scoring_model_acal.json') as f:
    MODEL = json.load(f)

TREND_P33 = FCFG['trend_slope_p33']
TREND_P67 = FCFG['trend_slope_p67']
WEIGHTS = MODEL['weights']
BIN_EDGES = MODEL['bin_edges']

TF_MINUTES = {'15m':15,'30m':30,'60m':60,'90m':90,'120m':120,
              '240m':240,'360m':360,'480m':480,'720m':720}

# ── Load bar data ──
print("Loading bar data...")
bar_data = []
with open(f'{BASE}/01-data/output/zone_prep/NQ_bardata_P2.csv') as f:
    for row in csv.DictReader(f):
        r = {k.strip(): v.strip() for k, v in row.items()}
        bar_data.append((float(r['Open']), float(r['High']),
                         float(r['Low']), float(r['Last'])))
n_bars = len(bar_data)
print(f"  {n_bars} bars")

# ── Load touches ──
print("Loading touches...")
touches = []
for fname in ['NQ_merged_P2a.csv', 'NQ_merged_P2b.csv']:
    with open(f'{BASE}/01-data/output/zone_prep/{fname}') as f:
        for row in csv.DictReader(f):
            if int(row['RotBarIndex']) >= 0:
                touches.append(row)
touches.sort(key=lambda r: int(r['RotBarIndex']))
print(f"  {len(touches)} touches")

# ── Zone history for F10 ──
zone_history = {}
for t in touches:
    key = (t['ZoneTop'], t['ZoneBot'], t.get('SourceLabel', ''))
    zone_history.setdefault(key, []).append(t)

def get_prior_pen(touch):
    seq = int(touch['TouchSequence'])
    if seq <= 1: return None
    key = (touch['ZoneTop'], touch['ZoneBot'], touch.get('SourceLabel', ''))
    rbi = int(touch['RotBarIndex'])
    for prev in reversed(zone_history.get(key, [])):
        if int(prev['RotBarIndex']) >= rbi: continue
        if int(prev['TouchSequence']) == seq - 1:
            pen = prev.get('Penetration', '').strip()
            return float(pen) if pen else None
    return None

# ── Scoring ──
def bin_numeric(val, p33, p67, w, nan=False):
    if nan: return 0.0
    if val <= p33: return w
    if val >= p67: return 0.0
    return w / 2.0

def score_touch(t):
    pp = get_prior_pen(t)
    f10_nan = pp is None
    f10 = bin_numeric(0 if f10_nan else pp,
        BIN_EDGES['F10_PriorPenetration'][0],
        BIN_EDGES['F10_PriorPenetration'][1],
        WEIGHTS['F10_PriorPenetration'], f10_nan)
    cs = t.get('CascadeState','').strip()
    if cs == 'UNKNOWN': cs = 'NO_PRIOR'
    f04 = WEIGHTS['F04_CascadeState'] if cs == 'NO_PRIOR' else \
          WEIGHTS['F04_CascadeState']/2 if cs == 'PRIOR_HELD' else 0.0
    tf = t.get('SourceLabel','').strip()
    f01 = WEIGHTS['F01_Timeframe'] if tf == '30m' else \
          0.0 if tf == '480m' else \
          WEIGHTS['F01_Timeframe']/2 if tf else 0.0
    age = float(t.get('ZoneAgeBars','0').strip() or '0')
    f21 = bin_numeric(age, BIN_EDGES['F21_ZoneAge'][0],
        BIN_EDGES['F21_ZoneAge'][1], WEIGHTS['F21_ZoneAge'])
    return f10 + f04 + f01 + f21

def classify_trend(slope):
    if slope <= TREND_P33: return 'CT'
    if slope >= TREND_P67: return 'WT'
    return 'NT'

# ── 2-leg simulator ──
def sim_2leg(entry_bar, entry_price, direction, zone_width_ticks):
    if entry_bar >= n_bars: return None
    t1t = max(1, round(T1_MULT * zone_width_ticks))
    t2t = max(1, round(T2_MULT * zone_width_ticks))
    st = max(round(STOP_MULT * zone_width_ticks), STOP_FLOOR)
    ep = entry_price
    if direction == 1:
        sp = ep - st*TICK_SIZE; t1p = ep + t1t*TICK_SIZE; t2p = ep + t2t*TICK_SIZE
    else:
        sp = ep + st*TICK_SIZE; t1p = ep - t1t*TICK_SIZE; t2p = ep - t2t*TICK_SIZE

    l1_open = l2_open = True
    l1_pnl = l2_pnl = 0.0
    l1_exit = l2_exit = 'NONE'
    l1_bar = l2_bar = -1
    mfe = mae = 0.0
    last_i = entry_bar

    for i in range(entry_bar, n_bars):
        o, h, l, c = bar_data[i]
        bh = i - entry_bar + 1
        last_i = i
        bmfe = (h-ep)/TICK_SIZE if direction==1 else (ep-l)/TICK_SIZE
        bmae = (ep-l)/TICK_SIZE if direction==1 else (h-ep)/TICK_SIZE
        if bmfe > mfe: mfe = bmfe
        if bmae > mae: mae = bmae

        if bh >= TCAP:
            pnl = (c-ep)/TICK_SIZE if direction==1 else (ep-c)/TICK_SIZE
            if l1_open: l1_pnl=pnl; l1_exit='TIMECAP'; l1_bar=i; l1_open=False
            if l2_open: l2_pnl=pnl; l2_exit='TIMECAP'; l2_bar=i; l2_open=False
            break
        stop_hit = (l <= sp) if direction==1 else (h >= sp)
        if stop_hit:
            pnl = (sp-ep)/TICK_SIZE if direction==1 else (ep-sp)/TICK_SIZE
            if l1_open: l1_pnl=pnl; l1_exit='STOP'; l1_bar=i; l1_open=False
            if l2_open: l2_pnl=pnl; l2_exit='STOP'; l2_bar=i; l2_open=False
            break
        if l1_open:
            hit = (h >= t1p) if direction==1 else (l <= t1p)
            if hit: l1_pnl=float(t1t); l1_exit='TARGET_1'; l1_bar=i; l1_open=False
        if l2_open:
            hit = (h >= t2p) if direction==1 else (l <= t2p)
            if hit: l2_pnl=float(t2t); l2_exit='TARGET_2'; l2_bar=i; l2_open=False
        if not l1_open and not l2_open: break

    if l1_open or l2_open:
        lc = bar_data[min(last_i, n_bars-1)][3]
        pnl = (lc-ep)/TICK_SIZE if direction==1 else (ep-lc)/TICK_SIZE
        if l1_open: l1_pnl=pnl; l1_exit='TIMECAP'; l1_bar=last_i
        if l2_open: l2_pnl=pnl; l2_exit='TIMECAP'; l2_bar=last_i

    final_bar = max(l1_bar, l2_bar)
    bars_held = final_bar - entry_bar + 1
    wpnl = LEG1_W*l1_pnl + LEG2_W*l2_pnl - COST_TICKS
    return dict(entry_price=ep, stop_ticks=st, t1_ticks=t1t, t2_ticks=t2t,
                l1_exit=l1_exit, l1_pnl=l1_pnl, l2_exit=l2_exit, l2_pnl=l2_pnl,
                wpnl=wpnl, bars_held=bars_held, mfe=mfe, mae=mae,
                final_bar=final_bar, entry_bar=entry_bar)

# ── CT limit fill scanner ──
def scan_ct_fill(touch_bar, direction, zone_top, zone_bot):
    if direction == 1:
        lim = zone_top - CT_LIMIT_TICKS * TICK_SIZE
    else:
        lim = zone_bot + CT_LIMIT_TICKS * TICK_SIZE
    for off in range(1, CT_LIMIT_WINDOW + 1):
        bi = touch_bar + off
        if bi >= n_bars: break
        o, h, l, c = bar_data[bi]
        if direction == 1 and l <= lim:
            return (bi, min(o, lim))
        if direction == -1 and h >= lim:
            return (bi, max(o, lim))
    return None

# ═════════════════════════════════════════════════════════════════
#  Full simulation with configurable position limit
# ═════════════════════════════════════════════════════════════════
def run_simulation(max_positions=1, override_rule=False):
    """
    Run the full harness with configurable max simultaneous positions.
    Returns (trades, skipped, stats_dict).
    """
    trade_log = []
    skip_log = []

    # Track active positions (list of dicts with entry_bar, final_bar, mode, etc.)
    active_positions = []

    # CT limit state
    ct_limit_pending = False
    ct_limit_expires_at = -1

    # Kill-switch
    ks_consec = 0; ks_daily = 0.0; ks_weekly = 0.0
    ks_sess_halt = ks_day_halt = ks_week_halt = False
    ks_last_day = ''

    trade_counter = 0
    ct_signals = 0; ct_fills = 0; ct_expired = 0
    override_count = 0
    override_old_pnls = []

    for ti, touch in enumerate(touches):
        rbi = int(touch['RotBarIndex'])
        touch_bar = rbi
        wt_entry_bar = rbi + 1
        if wt_entry_bar >= n_bars: continue

        tt = touch['TouchType'].strip()
        if tt not in ('DEMAND_EDGE', 'SUPPLY_EDGE'): continue
        direction = 1 if tt == 'DEMAND_EDGE' else -1
        tf_str = touch.get('SourceLabel','').strip()
        tf_min = TF_MINUTES.get(tf_str, 999)
        seq = int(touch['TouchSequence'])
        zw_str = touch.get('ZoneWidthTicks','').strip()
        zw = float(zw_str) if zw_str else (float(touch['ZoneTop'])-float(touch['ZoneBot']))/TICK_SIZE
        zone_top = float(touch['ZoneTop'])
        zone_bot = float(touch['ZoneBot'])

        score = score_touch(touch)
        ts_str = touch.get('TrendSlope','').strip()
        trend_slope = float(ts_str) if ts_str else 0.0
        trend = classify_trend(trend_slope)

        # Remove expired positions
        active_positions = [p for p in active_positions if p['final_bar'] >= wt_entry_bar]

        # Check limit expiry
        if ct_limit_pending and rbi >= ct_limit_expires_at:
            ct_limit_pending = False

        # Day reset
        entry_dt = bar_data[wt_entry_bar][3]  # not datetime, just for day tracking
        day_str = touch.get('DateTime','').split(' ')[0] if touch.get('DateTime') else ''
        if day_str and day_str != ks_last_day:
            ks_daily = 0.0; ks_sess_halt = ks_day_halt = False; ks_consec = 0
            ks_last_day = day_str

        # Gate checks
        skip_reason = None
        mode = None

        if score < SCORE_THRESHOLD:
            skip_reason = 'BELOW_THRESHOLD'
        elif tf_min > TF_MAX or tf_min == 999:
            skip_reason = 'TF_FILTER'
        else:
            if trend == 'CT': mode = 'CT'
            else:
                if seq > WTNT_SEQ_MAX: skip_reason = 'SEQ_FILTER'
                else: mode = 'WTNT'

        # Position check
        if not skip_reason:
            in_pos = len(active_positions) >= max_positions

            # Override check for max_positions=1
            if in_pos and override_rule and max_positions == 1 and len(active_positions) == 1:
                cur = active_positions[0]
                bars_in = wt_entry_bar - cur['entry_bar']
                # Compute unrealized PnL
                if wt_entry_bar < n_bars:
                    cur_price = bar_data[wt_entry_bar][3]  # Last
                    unreal = (cur_price - cur['entry_price'])/TICK_SIZE if cur['direction']==1 \
                             else (cur['entry_price'] - cur_price)/TICK_SIZE
                else:
                    unreal = 0

                score_margin = score - SCORE_THRESHOLD
                cur_margin = cur.get('score_margin', 0)

                if score_margin > cur_margin and unreal < 0 and bars_in < 20:
                    # Override: close current at market, take new
                    # Compute the old trade's actual PnL at close
                    close_price = bar_data[wt_entry_bar][0] if wt_entry_bar < n_bars else cur['entry_price']
                    old_pnl_raw = (close_price - cur['entry_price'])/TICK_SIZE if cur['direction']==1 \
                                  else (cur['entry_price'] - close_price)/TICK_SIZE
                    old_wpnl = old_pnl_raw - COST_TICKS  # simplified: full position PnL

                    override_count += 1
                    override_old_pnls.append(old_wpnl)

                    # Update kill-switch with old trade's loss
                    ks_daily += old_wpnl
                    ks_weekly += old_wpnl
                    if old_wpnl < 0: ks_consec += 1
                    else: ks_consec = 0

                    # Remove the old position
                    active_positions = []
                    in_pos = False

            if in_pos:
                skip_reason = 'IN_POSITION'

        if not skip_reason and ct_limit_pending:
            skip_reason = 'LIMIT_PENDING'

        if not skip_reason and (ks_sess_halt or ks_day_halt or ks_week_halt):
            skip_reason = 'KILL_SWITCH'

        if skip_reason:
            # Record blocked signal info for analysis
            unrealized = 0.0
            cur_trade_info = None
            if active_positions and skip_reason in ('IN_POSITION', 'LIMIT_PENDING'):
                cur = active_positions[0]
                if wt_entry_bar < n_bars:
                    cur_price = bar_data[wt_entry_bar][3]
                    unrealized = (cur_price - cur['entry_price'])/TICK_SIZE if cur['direction']==1 \
                                 else (cur['entry_price'] - cur_price)/TICK_SIZE
                cur_trade_info = {
                    'bars_in': wt_entry_bar - cur['entry_bar'],
                    'unrealized': unrealized,
                    'cur_wpnl': cur.get('wpnl', 0),
                    'cur_score': cur.get('score', 0),
                }

            skip_log.append(dict(
                datetime=touch.get('DateTime',''),
                touch_type=tt, source_label=tf_str,
                score=score, trend=trend, skip_reason=skip_reason,
                zone_width=zw, zone_top=zone_top, zone_bot=zone_bot,
                direction=direction, touch_idx=ti,
                cur_trade_info=cur_trade_info,
            ))
            continue

        # Execute trade
        entry_bar = -1; entry_price = 0.0; entry_type = 'MARKET'

        if mode == 'CT':
            ct_signals += 1
            ct_limit_pending = True
            ct_limit_expires_at = touch_bar + CT_LIMIT_WINDOW
            fill = scan_ct_fill(touch_bar, direction, zone_top, zone_bot)
            if fill is None:
                ct_expired += 1
                skip_log.append(dict(
                    datetime=touch.get('DateTime',''),
                    touch_type=tt, source_label=tf_str,
                    score=score, trend=trend, skip_reason='LIMIT_EXPIRED',
                    zone_width=zw, zone_top=zone_top, zone_bot=zone_bot,
                    direction=direction, touch_idx=ti, cur_trade_info=None,
                ))
                continue
            ct_fills += 1
            ct_limit_pending = False
            entry_bar, entry_price = fill
            entry_type = 'LIMIT_5T'
        else:
            entry_bar = wt_entry_bar
            entry_price = bar_data[entry_bar][0]
            entry_type = 'MARKET'

        result = sim_2leg(entry_bar, entry_price, direction, zw)
        if result is None: continue

        trade_counter += 1
        result['trade_id'] = f"ZB_{trade_counter:04d}"
        result['mode'] = mode
        result['entry_type'] = entry_type
        result['direction'] = direction
        result['score'] = score
        result['score_margin'] = score - SCORE_THRESHOLD
        result['zone_width'] = zw
        result['zone_top'] = zone_top
        result['zone_bot'] = zone_bot
        result['source_label'] = tf_str
        result['touch_type'] = tt
        result['datetime'] = touch.get('DateTime','')
        result['trend'] = trend
        result['touch_idx'] = ti
        trade_log.append(result)

        active_positions.append(result)

        # Kill-switch
        wpnl = result['wpnl']
        ks_daily += wpnl; ks_weekly += wpnl
        if wpnl < 0: ks_consec += 1
        else: ks_consec = 0
        if ks_consec >= 3: ks_sess_halt = True
        if ks_daily <= -600: ks_day_halt = True
        if ks_weekly <= -1200: ks_week_halt = True

    return trade_log, skip_log, dict(
        ct_signals=ct_signals, ct_fills=ct_fills, ct_expired=ct_expired,
        override_count=override_count, override_old_pnls=override_old_pnls,
    )

def calc_stats(trades):
    if not trades: return dict(n=0, wr=0, pf=0, ev=0, total=0)
    pnls = [t['wpnl'] for t in trades]
    wins = sum(1 for p in pnls if p > 0)
    gw = sum(p for p in pnls if p > 0)
    gl = sum(abs(p) for p in pnls if p < 0)
    pf = gw/gl if gl > 0 else float('inf')
    return dict(n=len(trades), wr=100*wins/len(trades), pf=pf,
                ev=sum(pnls)/len(trades), total=sum(pnls), wins=wins)

# ═════════════════════════════════════════════════════════════════
#  1. BASELINE RUN (max_positions=1, no override)
# ═════════════════════════════════════════════════════════════════
print("\n" + "="*65)
print("RUNNING BASELINE (1 position, no override)...")
print("="*65)
trades_1, skips_1, meta_1 = run_simulation(max_positions=1)
s1 = calc_stats(trades_1)
print(f"  Trades: {s1['n']}, WR: {s1['wr']:.1f}%, PF: {s1['pf']:.2f}, Total: {s1['total']:.1f}t")

# ═════════════════════════════════════════════════════════════════
#  ANALYSIS 1: Profile blocked vs traded signals
# ═════════════════════════════════════════════════════════════════
print("\n" + "="*65)
print("1. PROFILE: Blocked vs Traded Signals")
print("="*65)

blocked = [s for s in skips_1 if s['skip_reason'] in ('IN_POSITION', 'LIMIT_PENDING')]
traded = trades_1

print(f"\n{'Metric':<25} {'Blocked':>10} {'Traded':>10}")
print("-"*47)
print(f"{'Count':<25} {len(blocked):>10} {len(traded):>10}")
b_scores = [s['score'] for s in blocked]
t_scores = [t['score'] for t in traded]
print(f"{'Mean acal_score':<25} {sum(b_scores)/len(b_scores):>10.2f} {sum(t_scores)/len(t_scores):>10.2f}")
b_margins = [s['score'] - SCORE_THRESHOLD for s in blocked]
t_margins = [t['score_margin'] for t in traded]
print(f"{'Mean score_margin':<25} {sum(b_margins)/len(b_margins):>10.2f} {sum(t_margins)/len(t_margins):>10.2f}")
b_ct = sum(1 for s in blocked if s['trend'] == 'CT')
t_ct = sum(1 for t in traded if t['trend'] == 'CT')
print(f"{'% CT':<25} {100*b_ct/len(blocked):>9.1f}% {100*t_ct/len(traded):>9.1f}%")
print(f"{'% WT/NT':<25} {100*(len(blocked)-b_ct)/len(blocked):>9.1f}% {100*(len(traded)-t_ct)/len(traded):>9.1f}%")
b_zw = [s['zone_width'] for s in blocked]
t_zw = [t['zone_width'] for t in traded]
print(f"{'Mean zone_width':<25} {sum(b_zw)/len(b_zw):>10.1f} {sum(t_zw)/len(t_zw):>10.1f}")

# ═════════════════════════════════════════════════════════════════
#  ANALYSIS 2: Simulate blocked signals independently
# ═════════════════════════════════════════════════════════════════
print("\n" + "="*65)
print("2. HYPOTHETICAL: Blocked signals simulated independently")
print("="*65)

hypo_results = []
for s in blocked:
    ti = s['touch_idx']
    t = touches[ti]
    rbi = int(t['RotBarIndex'])
    direction = s['direction']
    zw = s['zone_width']
    zone_top = s['zone_top']
    zone_bot = s['zone_bot']
    trend = s['trend']

    if trend == 'CT':
        fill = scan_ct_fill(rbi, direction, zone_top, zone_bot)
        if fill is None:
            continue
        entry_bar, entry_price = fill
    else:
        entry_bar = rbi + 1
        if entry_bar >= n_bars: continue
        entry_price = bar_data[entry_bar][0]

    result = sim_2leg(entry_bar, entry_price, direction, zw)
    if result: hypo_results.append(result)

hs = calc_stats(hypo_results)
print(f"\n  Simulated: {len(hypo_results)} blocked signals (of {len(blocked)})")
print(f"  Hypothetical WR:         {hs['wr']:.1f}%")
print(f"  Hypothetical PF:         {hs['pf']:.2f}")
print(f"  Hypothetical mean wPnL:  {hs['ev']:.1f}t")
print(f"  Would-be winners:        {hs['wins']}/{hs['n']}")
print(f"  Would-be total PnL:      {hs['total']:.1f}t")

# ═════════════════════════════════════════════════════════════════
#  ANALYSIS 3: Overlap analysis — current trade status when blocked
# ═════════════════════════════════════════════════════════════════
print("\n" + "="*65)
print("3. OVERLAP: Current trade status when signal was blocked")
print("="*65)

in_profit = in_loss = within_10 = past_50 = cur_won = cur_lost = 0
for s in blocked:
    info = s.get('cur_trade_info')
    if not info: continue
    if info['unrealized'] > 0: in_profit += 1
    else: in_loss += 1
    if info['bars_in'] <= 10: within_10 += 1
    if info['bars_in'] > 50: past_50 += 1
    if info['cur_wpnl'] > 0: cur_won += 1
    else: cur_lost += 1

print(f"\n  {'Current trade status':<35} {'Count':>6}")
print(f"  {'-'*43}")
print(f"  {'Unrealized > 0 (in profit)':<35} {in_profit:>6}")
print(f"  {'Unrealized < 0 (at loss)':<35} {in_loss:>6}")
print(f"  {'Within first 10 bars of entry':<35} {within_10:>6}")
print(f"  {'Past bar 50 of entry':<35} {past_50:>6}")
print(f"  {'Current trade eventually WON':<35} {cur_won:>6}")
print(f"  {'Current trade eventually LOST':<35} {cur_lost:>6}")

# ═════════════════════════════════════════════════════════════════
#  ANALYSIS 4: Priority override simulation
# ═════════════════════════════════════════════════════════════════
print("\n" + "="*65)
print("4. PRIORITY OVERRIDE: Close losing trade for higher-score signal")
print("="*65)

trades_ov, skips_ov, meta_ov = run_simulation(max_positions=1, override_rule=True)
s_ov = calc_stats(trades_ov)

print(f"\n  {'Metric':<30} {'No override':>12} {'With override':>14}")
print(f"  {'-'*58}")
print(f"  {'Total trades':<30} {s1['n']:>12} {s_ov['n']:>14}")
print(f"  {'Overrides triggered':<30} {'--':>12} {meta_ov['override_count']:>14}")
if meta_ov['override_old_pnls']:
    mean_old = sum(meta_ov['override_old_pnls'])/len(meta_ov['override_old_pnls'])
    print(f"  {'Old trade PnL at close (mean)':<30} {'--':>12} {mean_old:>13.1f}t")
print(f"  {'WR':<30} {s1['wr']:>11.1f}% {s_ov['wr']:>13.1f}%")
print(f"  {'PF':<30} {s1['pf']:>12.2f} {s_ov['pf']:>14.2f}")
print(f"  {'Net total PnL':<30} {s1['total']:>11.1f}t {s_ov['total']:>13.1f}t")

# ═════════════════════════════════════════════════════════════════
#  ANALYSIS 5: Allow 2 simultaneous positions
# ═════════════════════════════════════════════════════════════════
print("\n" + "="*65)
print("5. TWO POSITIONS: Up to 2 simultaneous trades")
print("="*65)

trades_2, skips_2, meta_2 = run_simulation(max_positions=2)
s2 = calc_stats(trades_2)
additional = s2['n'] - s1['n']

# Analyze concurrent pairs
concurrent_pairs = []
for i, t1 in enumerate(trades_2):
    for t2 in trades_2[i+1:]:
        # Check if they overlap in time
        if t2['entry_bar'] <= t1['final_bar'] and t1['entry_bar'] <= t2['final_bar']:
            same_tf = t1['source_label'] == t2['source_label']
            same_dir = t1['direction'] == t2['direction']
            concurrent_pairs.append(dict(
                same_tf=same_tf, same_dir=same_dir,
                t1_mode=t1['mode'], t2_mode=t2['mode'],
                t1_src=t1['source_label'], t2_src=t2['source_label'],
            ))

same_tf_pairs = sum(1 for p in concurrent_pairs if p['same_tf'])
cross_tf_pairs = len(concurrent_pairs) - same_tf_pairs
same_dir_pairs = sum(1 for p in concurrent_pairs if p['same_dir'])

# Max concurrent exposure
max_exposure = 0
for t in trades_2:
    concurrent_at_entry = sum(1 for t2 in trades_2
        if t2['entry_bar'] <= t['entry_bar'] <= t2['final_bar'])
    if concurrent_at_entry > max_exposure:
        max_exposure = concurrent_at_entry

print(f"\n  {'Metric':<35} {'1 position':>12} {'2 positions':>12}")
print(f"  {'-'*61}")
print(f"  {'Total trades':<35} {s1['n']:>12} {s2['n']:>12}")
print(f"  {'Additional trades':<35} {'--':>12} {additional:>12}")
print(f"  {'WR':<35} {s1['wr']:>11.1f}% {s2['wr']:>11.1f}%")
print(f"  {'PF':<35} {s1['pf']:>12.2f} {s2['pf']:>12.2f}")
print(f"  {'Net total PnL':<35} {s1['total']:>11.1f}t {s2['total']:>11.1f}t")
print(f"  {'Max concurrent positions':<35} {'1':>12} {max_exposure:>12}")
print(f"  {'Concurrent pairs (overlapping)':<35} {'--':>12} {len(concurrent_pairs):>12}")
print(f"  {'  Same TF (correlated)':<35} {'--':>12} {same_tf_pairs:>12}")
print(f"  {'  Cross TF':<35} {'--':>12} {cross_tf_pairs:>12}")
print(f"  {'  Same direction':<35} {'--':>12} {same_dir_pairs:>12}")

# ═════════════════════════════════════════════════════════════════
#  SUMMARY
# ═════════════════════════════════════════════════════════════════
print("\n" + "="*65)
print("SUMMARY")
print("="*65)

print(f"\n  {'Variant':<30} {'Trades':>7} {'WR':>7} {'PF':>8} {'Total PnL':>11}")
print(f"  {'-'*65}")
print(f"  {'Baseline (1 pos)':<30} {s1['n']:>7} {s1['wr']:>6.1f}% {s1['pf']:>8.2f} {s1['total']:>10.1f}t")
print(f"  {'Priority override':<30} {s_ov['n']:>7} {s_ov['wr']:>6.1f}% {s_ov['pf']:>8.2f} {s_ov['total']:>10.1f}t")
print(f"  {'2 positions':<30} {s2['n']:>7} {s2['wr']:>6.1f}% {s2['pf']:>8.2f} {s2['total']:>10.1f}t")
print(f"  {'Blocked (hypothetical)':<30} {hs['n']:>7} {hs['wr']:>6.1f}% {hs['pf']:>8.2f} {hs['total']:>10.1f}t")
