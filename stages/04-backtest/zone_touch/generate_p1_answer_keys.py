# archetype: zone_touch
"""
Generate P1 answer keys for C++ replication gate testing.

Runs the replication harness scoring + entry + exit logic on P1 data
with both ZONEREL and FIXED exit configs. Output format matches the
C++ comparison parser (rbi, mode, direction, ..., score, trend, tf).

Usage:
    python generate_p1_answer_keys.py

Outputs:
    output/p1_replication_answer_key_zr.csv
    output/p1_replication_answer_key_fixed.csv
    output/p1_replication_skipped_zr.csv
    output/p1_replication_skipped_fixed.csv

Scoring logic is identical to replication_harness.py v3.0.
"""
import csv, json, math, sys
from datetime import datetime
from collections import defaultdict

# =========================================================================
#  Config — frozen from replication_harness.py v3.0
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
TREND_P33 = FCFG['trend_slope_p33']
TREND_P67 = FCFG['trend_slope_p67']
TREND_LOOKBACK = 50

# Zone-relative exit config
ZR_T1_MULT = 0.5
ZR_T2_MULT = 1.0
ZR_STOP_MULT = 1.5
ZR_STOP_FLOOR = 120
ZR_TCAP = 160

# Fixed exit config (CT / WT)
FIXED_CT_T1 = 40;   FIXED_CT_T2 = 80;   FIXED_CT_STOP = 190;  FIXED_CT_TCAP = 160
FIXED_WT_T1 = 60;   FIXED_WT_T2 = 80;   FIXED_WT_STOP = 240;  FIXED_WT_TCAP = 160

LEG1_W, LEG2_W = 0.67, 0.33

# CT limit entry
CT_LIMIT_TICKS = 5
CT_LIMIT_WINDOW = 20

TF_MAX_MINUTES = 120
WTNT_SEQ_MAX = 5

# Kill-switch
KS_CONSEC = 3
KS_DAILY = -400.0
KS_WEEKLY = -800.0

TF_MINUTES = {'15m':15, '30m':30, '60m':60, '90m':90, '120m':120,
              '240m':240, '360m':360, '480m':480, '720m':720}

# =========================================================================
#  Scoring functions — identical to replication_harness.py
# =========================================================================

def bin_numeric(val, p33, p67, weight, is_nan=False):
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

def classify_trend(slope, touch_type):
    if slope <= TREND_P33: return 'CT'
    if slope >= TREND_P67: return 'WT'
    return 'NT'

def get_prior_penetration(touch, zone_history):
    seq = int(touch['TouchSequence'])
    if seq <= 1:
        return None
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

def score_touch(touch, zone_history):
    prior_pen = get_prior_penetration(touch, zone_history)
    f10_nan = (prior_pen is None)
    f10_raw = 0.0 if f10_nan else prior_pen
    f10_pts, _ = bin_numeric(
        f10_raw, BIN_EDGES['F10_PriorPenetration'][0],
        BIN_EDGES['F10_PriorPenetration'][1],
        WEIGHTS['F10_PriorPenetration'], f10_nan)

    f04_raw = touch.get('CascadeState', '').strip()
    f04_pts, _ = score_f04(f04_raw, WEIGHTS['F04_CascadeState'])

    f01_raw = touch.get('SourceLabel', '').strip()
    f01_pts, _ = score_f01(f01_raw, WEIGHTS['F01_Timeframe'])

    f21_raw_str = touch.get('ZoneAgeBars', '').strip()
    f21_raw = float(f21_raw_str) if f21_raw_str else 0.0
    f21_pts, _ = bin_numeric(
        f21_raw, BIN_EDGES['F21_ZoneAge'][0],
        BIN_EDGES['F21_ZoneAge'][1],
        WEIGHTS['F21_ZoneAge'])

    return f10_pts + f04_pts + f01_pts + f21_pts

# =========================================================================
#  CT limit fill scanner — identical to replication_harness.py
# =========================================================================

def scan_ct_limit_fill(bar_data, touch_bar, direction, zone_top, zone_bot):
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
    return None

# =========================================================================
#  2-leg exit simulator — parameterized for both ZONEREL and FIXED
# =========================================================================

def sim_2leg(bar_data, entry_bar, entry_price, direction,
             t1_ticks, t2_ticks, stop_ticks, time_cap):
    n_bars = len(bar_data)
    if entry_bar >= n_bars:
        return None

    ep = entry_price
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
    leg1_exit_bar = leg2_exit_bar = entry_bar
    mfe = mae = 0.0
    last_i = entry_bar

    for i in range(entry_bar, n_bars):
        bh = i - entry_bar + 1
        o, h, l, c, dt = bar_data[i]

        # MFE/MAE
        if direction == 1:
            excursion_fav = (h - ep) / TICK_SIZE
            excursion_adv = (ep - l) / TICK_SIZE
        else:
            excursion_fav = (ep - l) / TICK_SIZE
            excursion_adv = (h - ep) / TICK_SIZE
        mfe = max(mfe, excursion_fav)
        mae = max(mae, excursion_adv)

        last_i = i

        # Time cap (>= matches C++ barsHeld >= timeCap)
        if bh >= time_cap:
            pnl = (c - ep) / TICK_SIZE if direction == 1 else (ep - c) / TICK_SIZE
            if leg1_open:
                leg1_pnl = pnl; leg1_exit = 'TIMECAP'
                leg1_exit_bar = i; leg1_open = False
            if leg2_open:
                leg2_pnl = pnl; leg2_exit = 'TIMECAP'
                leg2_exit_bar = i; leg2_open = False
            break

        # Stop-first
        stop_hit = (l <= stop_px) if direction == 1 else (h >= stop_px)
        if stop_hit:
            spnl = (stop_px - ep) / TICK_SIZE if direction == 1 else (ep - stop_px) / TICK_SIZE
            if leg1_open:
                leg1_pnl = spnl; leg1_exit = 'STOP'
                leg1_exit_bar = i; leg1_open = False
            if leg2_open:
                leg2_pnl = spnl; leg2_exit = 'STOP'
                leg2_exit_bar = i; leg2_open = False
            break

        # Targets
        if leg1_open:
            hit = (h >= t1_px) if direction == 1 else (l <= t1_px)
            if hit:
                leg1_pnl = float(t1_ticks)
                leg1_exit = 'TARGET_1'
                leg1_exit_bar = i; leg1_open = False

        if leg2_open:
            hit = (h >= t2_px) if direction == 1 else (l <= t2_px)
            if hit:
                leg2_pnl = float(t2_ticks)
                leg2_exit = 'TARGET_2'
                leg2_exit_bar = i; leg2_open = False

        if not leg1_open and not leg2_open:
            break

    # Ran out of bars
    if leg1_open or leg2_open:
        last_c = bar_data[min(last_i, n_bars - 1)][3]
        pnl = (last_c - ep) / TICK_SIZE if direction == 1 else (ep - last_c) / TICK_SIZE
        if leg1_open:
            leg1_pnl = pnl; leg1_exit = 'END_OF_DATA'
            leg1_exit_bar = last_i
        if leg2_open:
            leg2_pnl = pnl; leg2_exit = 'END_OF_DATA'
            leg2_exit_bar = last_i

    bars_held = max(leg1_exit_bar, leg2_exit_bar) - entry_bar + 1
    wpnl = LEG1_W * leg1_pnl + LEG2_W * leg2_pnl - COST_TICKS

    return dict(
        entry_price=ep, stop_price=stop_px,
        t1_target=t1_px, t2_target=t2_px,
        stop_ticks=stop_ticks, t1_ticks=t1_ticks, t2_ticks=t2_ticks,
        leg1_exit=leg1_exit, leg1_pnl=leg1_pnl, leg1_exit_bar=leg1_exit_bar,
        leg2_exit=leg2_exit, leg2_pnl=leg2_pnl, leg2_exit_bar=leg2_exit_bar,
        weighted_pnl=wpnl, bars_held=bars_held, mfe=mfe, mae=mae
    )

# =========================================================================
#  Load P1 data
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
        base_dt = r['Date'].split('.')[0] + ' ' + r['Time'].split('.')[0]
        bar_data.append((o, h, l, c, base_dt))
n_bars = len(bar_data)
print(f"  {n_bars} bars")

print("Loading P1 zone touches...")
touches = []
for fname in ['NQ_merged_P1a.csv', 'NQ_merged_P1b.csv']:
    with open(f'{BASE}/01-data/output/zone_prep/{fname}') as f:
        for row in csv.DictReader(f):
            rbi = int(row['RotBarIndex'])
            if rbi < 0:
                continue
            touches.append(row)

touches.sort(key=lambda r: int(r['RotBarIndex']))
print(f"  {len(touches)} touches (RotBarIndex >= 0)")

# Build zone history for F10
zone_history = {}
for t in touches:
    key = (t['ZoneTop'], t['ZoneBot'], t.get('SourceLabel', ''))
    if key not in zone_history:
        zone_history[key] = []
    zone_history[key].append(t)

# =========================================================================
#  Run simulation for a given exit mode
# =========================================================================

def run_simulation(exit_mode):
    """Run full simulation. exit_mode = 'zonerel' or 'fixed'."""
    trade_log = []
    skipped_log = []

    in_trade_until = -1
    ct_limit_pending = False
    ct_limit_expires_at = -1

    ks_consec = 0
    ks_daily_pnl = 0.0
    ks_weekly_pnl = 0.0
    ks_session_halted = False
    ks_daily_halted = False
    ks_weekly_halted = False
    ks_last_day = ''
    ks_last_week = ''

    trade_counter = 0
    ct_limit_expired = 0

    for touch in touches:
        rbi = int(touch['RotBarIndex'])
        touch_bar = rbi
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
        zone_top = float(touch['ZoneTop'])
        zone_bot = float(touch['ZoneBot'])
        zw_str = touch.get('ZoneWidthTicks', '').strip()
        zone_width_ticks = float(zw_str) if zw_str else (zone_top - zone_bot) / TICK_SIZE

        acal_score = score_touch(touch, zone_history)

        ts_str = touch.get('TrendSlope', '').strip()
        trend_slope = float(ts_str) if ts_str else 0.0
        trend_label = classify_trend(trend_slope, touch_type)

        # Entry bar datetime
        entry_dt = bar_data[wt_entry_bar][4]

        # CT limit expiry check
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
        elif tf_min > TF_MAX_MINUTES or tf_min == 999:
            skip_reason = 'TF_FILTER'
        else:
            if trend_label == 'CT':
                mode = 'CT'
            else:
                if seq > WTNT_SEQ_MAX:
                    skip_reason = 'SEQ_FILTER'
                else:
                    mode = 'WTNT'

        # No-overlap
        if skip_reason is None and wt_entry_bar <= in_trade_until:
            skip_reason = 'IN_POSITION'

        # LIMIT_PENDING
        if skip_reason is None and ct_limit_pending:
            skip_reason = 'LIMIT_PENDING'

        # Kill-switch
        if skip_reason is None:
            if ks_session_halted or ks_daily_halted or ks_weekly_halted:
                skip_reason = 'KILL_SWITCH'

        if skip_reason:
            skipped_log.append(dict(
                datetime=entry_dt, touch_type=touch_type,
                source_label=tf_str, acal_score=f"{acal_score:.4f}",
                trend_label=trend_label, skip_reason=skip_reason
            ))
            continue

        # ---- Execute trade ----
        if mode == 'CT':
            ct_limit_pending = True
            ct_limit_expires_at = touch_bar + CT_LIMIT_WINDOW

            fill_result = scan_ct_limit_fill(
                bar_data, touch_bar, direction, zone_top, zone_bot)

            if fill_result is None:
                ct_limit_expired += 1
                skipped_log.append(dict(
                    datetime=entry_dt, touch_type=touch_type,
                    source_label=tf_str, acal_score=f"{acal_score:.4f}",
                    trend_label=trend_label, skip_reason='LIMIT_EXPIRED'
                ))
                continue

            fill_bar, fill_price, _ = fill_result
            ct_limit_pending = False
            entry_bar = fill_bar
            entry_price = fill_price
            entry_dt = bar_data[entry_bar][4]
        else:
            entry_bar = wt_entry_bar
            entry_price = bar_data[entry_bar][0]
            entry_dt = bar_data[entry_bar][4]

        # Compute exit ticks
        if exit_mode == 'zonerel':
            t1 = max(1, int(ZR_T1_MULT * zone_width_ticks + 0.5))
            t2 = max(1, int(ZR_T2_MULT * zone_width_ticks + 0.5))
            st = max(int(ZR_STOP_MULT * zone_width_ticks + 0.5), ZR_STOP_FLOOR)
            tc = ZR_TCAP
        else:  # fixed
            if mode == 'CT':
                t1, t2, st, tc = FIXED_CT_T1, FIXED_CT_T2, FIXED_CT_STOP, FIXED_CT_TCAP
            else:
                t1, t2, st, tc = FIXED_WT_T1, FIXED_WT_T2, FIXED_WT_STOP, FIXED_WT_TCAP

        result = sim_2leg(bar_data, entry_bar, entry_price, direction,
                          t1, t2, st, tc)
        if result is None:
            continue

        trade_counter += 1

        final_exit_bar = max(result['leg1_exit_bar'], result['leg2_exit_bar'])
        in_trade_until = final_exit_bar

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

        trade_log.append(dict(
            rbi=rbi,
            mode=mode if mode == 'CT' else 'WTNT',
            direction=direction,
            zone_width=f"{zone_width_ticks:.1f}",
            entry_price=f"{entry_price:.2f}" if isinstance(entry_price, float) else entry_price,
            weighted_pnl=result['weighted_pnl'],
            bars_held=result['bars_held'],
            leg1_exit=result['leg1_exit'],
            leg1_pnl=result['leg1_pnl'],
            leg2_exit=result['leg2_exit'],
            leg2_pnl=result['leg2_pnl'],
            mfe=result['mfe'],
            mae=result['mae'],
            t1_ticks=result['t1_ticks'],
            t2_ticks=result['t2_ticks'],
            stop_ticks=result['stop_ticks'],
            entry_bar=entry_bar,
            exit_bar=final_exit_bar,
            score=acal_score,
            trend=trend_label,
            tf=tf_str,
        ))

    print(f"  [{exit_mode.upper()}] {len(trade_log)} trades, "
          f"{len(skipped_log)} skipped, {ct_limit_expired} CT expired")
    return trade_log, skipped_log

# =========================================================================
#  Run both configs
# =========================================================================

print("\nRunning ZONEREL simulation...")
zr_trades, zr_skipped = run_simulation('zonerel')

print("Running FIXED simulation...")
fixed_trades, fixed_skipped = run_simulation('fixed')

# =========================================================================
#  Write answer keys (C++ comparison format)
# =========================================================================

AK_COLS = ['rbi', 'mode', 'direction', 'zone_width', 'entry_price',
           'weighted_pnl', 'bars_held', 'leg1_exit', 'leg1_pnl',
           'leg2_exit', 'leg2_pnl', 'mfe', 'mae', 't1_ticks', 't2_ticks',
           'stop_ticks', 'entry_bar', 'exit_bar', 'score', 'trend', 'tf']

SKIP_COLS = ['datetime', 'touch_type', 'source_label', 'acal_score',
             'trend_label', 'skip_reason']

outdir = f'{BASE}/04-backtest/zone_touch/output'

for label, trades, skipped in [
    ('zr', zr_trades, zr_skipped),
    ('fixed', fixed_trades, fixed_skipped),
]:
    ak_path = f'{outdir}/p1_replication_answer_key_{label}.csv'
    with open(ak_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=AK_COLS)
        writer.writeheader()
        writer.writerows(trades)
    print(f"Wrote {len(trades)} trades to p1_replication_answer_key_{label}.csv")

    sk_path = f'{outdir}/p1_replication_skipped_{label}.csv'
    with open(sk_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=SKIP_COLS)
        writer.writeheader()
        writer.writerows(skipped)

# =========================================================================
#  Compare against old throughput answer keys
# =========================================================================

def compare_answer_keys(new_path, old_path, label):
    """Compare new replication keys vs old throughput keys."""
    try:
        with open(old_path) as f:
            old_rows = list(csv.DictReader(f))
    except FileNotFoundError:
        print(f"  [{label}] Old answer key not found: {old_path}")
        return

    with open(new_path) as f:
        new_rows = list(csv.DictReader(f))

    print(f"\n{'='*60}")
    print(f"  COMPARISON: {label}")
    print(f"{'='*60}")
    print(f"  Old (throughput): {len(old_rows)} trades")
    print(f"  New (replication): {len(new_rows)} trades")

    # Build rbi -> row maps
    old_by_rbi = {}
    for r in old_rows:
        old_by_rbi.setdefault(int(r['rbi']), []).append(r)
    new_by_rbi = {}
    for r in new_rows:
        new_by_rbi.setdefault(int(r['rbi']), []).append(r)

    old_rbis = set(old_by_rbi.keys())
    new_rbis = set(new_by_rbi.keys())

    only_old = sorted(old_rbis - new_rbis)
    only_new = sorted(new_rbis - old_rbis)
    common = sorted(old_rbis & new_rbis)

    print(f"  Common RBIs: {len(common)}")
    print(f"  Only in old: {len(only_old)}")
    print(f"  Only in new: {len(only_new)}")

    if only_old:
        print(f"  Old-only RBIs (first 10): {only_old[:10]}")
    if only_new:
        print(f"  New-only RBIs (first 10): {only_new[:10]}")

    # Compare common trades
    mismatched = 0
    for rbi in common:
        o = old_by_rbi[rbi][0]
        n = new_by_rbi[rbi][0]
        ep_ok = abs(float(n['entry_price']) - float(o['entry_price'])) < 0.02
        l1_ok = n['leg1_exit'] == o['leg1_exit']
        l2_ok = n['leg2_exit'] == o['leg2_exit']
        pnl_ok = abs(float(n['weighted_pnl']) - float(o['weighted_pnl'])) < 1.0
        if not (ep_ok and l1_ok and l2_ok and pnl_ok):
            mismatched += 1
    print(f"  Common matched: {len(common) - mismatched}/{len(common)}")
    print(f"  Common mismatched: {mismatched}/{len(common)}")

    # Score analysis for divergent touches
    if only_old:
        print(f"\n  Touches in old but not new (score < threshold in replication):")
        for rbi in only_old[:5]:
            r = old_by_rbi[rbi][0]
            print(f"    rbi={rbi} mode={r['mode']} old_score={r.get('score','?')}")

print("\n\nComparing against throughput answer keys...")
compare_answer_keys(
    f'{outdir}/p1_replication_answer_key_zr.csv',
    f'{outdir}/p1_twoleg_answer_key_zr.csv',
    'ZONEREL')
compare_answer_keys(
    f'{outdir}/p1_replication_answer_key_fixed.csv',
    f'{outdir}/p1_twoleg_answer_key_fixed.csv',
    'FIXED')

# Aggregate stats for new keys
for label, trades in [('ZONEREL', zr_trades), ('FIXED', fixed_trades)]:
    if not trades:
        continue
    pnls = [float(t['weighted_pnl']) for t in trades]
    wins = sum(1 for p in pnls if p > 0)
    gw = sum(p for p in pnls if p > 0)
    gl = sum(abs(p) for p in pnls if p < 0)
    pf = gw / gl if gl > 0 else float('inf')
    ct = sum(1 for t in trades if t['mode'] == 'CT')
    wt = sum(1 for t in trades if t['mode'] == 'WTNT')
    print(f"\n  [{label}] {len(trades)} trades (CT={ct}, WT={wt}), "
          f"WR={100*wins/len(trades):.1f}%, PF={pf:.2f}, "
          f"Total PnL={sum(pnls):.1f}t")

print("\nDone.")
