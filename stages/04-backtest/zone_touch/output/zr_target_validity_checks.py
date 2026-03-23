# archetype: zone_touch
"""
Zone-Relative Target Validity Checks
CHECK 1: T2 fill rate by zone width bin
CHECK 2: BE step-up analysis by zone width bin

Uses P1+P2 bar data + scored touches. Simulates zone-relative 2-leg exits
with per-leg exit type tracking.
"""
import csv, json, math, os, sys
from collections import defaultdict

# =========================================================================
#  Constants
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

# =========================================================================
#  2-leg simulator with full per-leg tracking
# =========================================================================

def sim_2leg_detailed(bar_data, entry_bar, direction, zone_width_ticks,
                      t1_mult=0.5, t2_mult=1.0, stop_mult=1.5,
                      tcap=160, stop_floor=120, limit_ticks=None,
                      be_after_t1=False, be_level_mult=None):
    """
    be_after_t1: if True, move leg2 stop to entry (or be_level_mult * zw above entry)
                 after T1 fills
    be_level_mult: if set, move leg2 stop to entry + be_level_mult * zw * direction
                   (0 = entry, 0.25 = 0.25x zw profit locked)
    """
    n_bars = len(bar_data)
    if entry_bar >= n_bars:
        return None

    t1_ticks = max(1, round(t1_mult * zone_width_ticks))
    t2_ticks = max(1, round(t2_mult * zone_width_ticks))
    stop_ticks = max(round(stop_mult * zone_width_ticks), stop_floor)

    # Entry
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

    leg1_open = True
    leg2_open = True
    leg1_pnl = leg2_pnl = 0.0
    leg1_exit = leg2_exit = 'END_OF_DATA'
    leg1_exit_bar = leg2_exit_bar = entry_bar
    mfe = mae = 0.0
    t1_filled = False
    leg2_stop_px = stop_px  # may change after T1 fill if BE enabled

    for i in range(entry_bar, n_bars):
        o_b, h_b, l_b, c_b, dt_b = bar_data[i]
        bh = i - entry_bar + 1

        # MFE/MAE
        if direction == 1:
            bmfe = (h_b - ep) / TICK_SIZE
            bmae = (ep - l_b) / TICK_SIZE
        else:
            bmfe = (ep - l_b) / TICK_SIZE
            bmae = (h_b - ep) / TICK_SIZE
        if bmfe > mfe: mfe = bmfe
        if bmae > mae: mae = bmae

        # Time cap
        if bh >= tcap:
            pnl = (c_b - ep) / TICK_SIZE if direction == 1 else (ep - c_b) / TICK_SIZE
            if leg1_open: leg1_pnl = pnl; leg1_exit = 'TIMECAP'; leg1_exit_bar = i
            if leg2_open: leg2_pnl = pnl; leg2_exit = 'TIMECAP'; leg2_exit_bar = i
            break

        # Stop (stop-first rule) — leg1 uses original stop, leg2 uses possibly-adjusted stop
        if leg1_open:
            stop_hit = (l_b <= stop_px) if direction == 1 else (h_b >= stop_px)
            if stop_hit:
                spnl = (stop_px - ep) / TICK_SIZE if direction == 1 else (ep - stop_px) / TICK_SIZE
                leg1_pnl = spnl; leg1_exit = 'STOP'; leg1_exit_bar = i
                leg1_open = False

        if leg2_open:
            stop_hit2 = (l_b <= leg2_stop_px) if direction == 1 else (h_b >= leg2_stop_px)
            if stop_hit2:
                spnl2 = (leg2_stop_px - ep) / TICK_SIZE if direction == 1 else (ep - leg2_stop_px) / TICK_SIZE
                leg2_pnl = spnl2; leg2_exit = 'STOP_BE' if t1_filled and be_after_t1 else 'STOP'
                leg2_exit_bar = i; leg2_open = False

        if not leg1_open and not leg2_open:
            break

        # T1
        if leg1_open:
            hit = (h_b >= t1_px) if direction == 1 else (l_b <= t1_px)
            if hit:
                leg1_pnl = float(t1_ticks); leg1_exit = 'TARGET_1'
                leg1_exit_bar = i; leg1_open = False
                t1_filled = True

                # BE step-up for leg 2
                if be_after_t1 and leg2_open:
                    if be_level_mult is not None and be_level_mult > 0:
                        be_offset = round(be_level_mult * zone_width_ticks) * TICK_SIZE
                        if direction == 1:
                            leg2_stop_px = ep + be_offset
                        else:
                            leg2_stop_px = ep - be_offset
                    else:
                        leg2_stop_px = ep  # move to breakeven

        # T2
        if leg2_open:
            hit = (h_b >= t2_px) if direction == 1 else (l_b <= t2_px)
            if hit:
                leg2_pnl = float(t2_ticks); leg2_exit = 'TARGET_2'
                leg2_exit_bar = i; leg2_open = False

        if not leg1_open and not leg2_open:
            break

    # End of data
    if leg1_open or leg2_open:
        last_c = bar_data[min(i, n_bars - 1)][3]
        pnl = (last_c - ep) / TICK_SIZE if direction == 1 else (ep - last_c) / TICK_SIZE
        if leg1_open: leg1_pnl = pnl; leg1_exit = 'END_OF_DATA'; leg1_exit_bar = i
        if leg2_open: leg2_pnl = pnl; leg2_exit = 'END_OF_DATA'; leg2_exit_bar = i

    wpnl = LEG1_W * leg1_pnl + LEG2_W * leg2_pnl - COST_TICKS
    final_bar = max(leg1_exit_bar, leg2_exit_bar)

    return dict(
        entry_price=ep, weighted_pnl=wpnl,
        leg1_exit=leg1_exit, leg1_pnl=leg1_pnl,
        leg2_exit=leg2_exit, leg2_pnl=leg2_pnl,
        t1_ticks=t1_ticks, t2_ticks=t2_ticks, stop_ticks=stop_ticks,
        mfe=mfe, mae=mae, final_bar=final_bar,
        zone_width=zone_width_ticks, t1_filled=t1_filled
    )

# =========================================================================
#  Run simulation with mode routing + no-overlap
# =========================================================================

def run_sim(touches, bar_data, be_after_t1=False, be_level_mult=None):
    trades = []
    in_trade_until = -1
    n_bars = len(bar_data)

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
            trend_label = t.get('TrendLabel', 'NT').strip() or 'NT'
        else:
            trend_label = classify_trend(float(ts_str))

        if trend_label == 'CT':
            mode = 'CT'
            limit = 5
        else:
            mode = 'WT'
            if seq > WTNT_SEQ_MAX:
                continue
            limit = None

        if entry_bar <= in_trade_until:
            continue

        result = sim_2leg_detailed(bar_data, entry_bar, direction, zw,
                                    be_after_t1=be_after_t1,
                                    be_level_mult=be_level_mult,
                                    limit_ticks=limit)
        if result is None:
            continue

        in_trade_until = result['final_bar']
        result['mode'] = mode
        result['direction'] = direction
        trades.append(result)

    return trades

# =========================================================================
#  Zone width bin helpers
# =========================================================================

BINS = [(50, 100), (100, 150), (150, 200), (200, 300), (300, 9999)]
BIN_LABELS = ['50-100t', '100-150t', '150-200t', '200-300t', '300t+']

def bin_label(zw):
    for (lo, hi), lbl in zip(BINS, BIN_LABELS):
        if lo <= zw < hi:
            return lbl
    if zw < 50:
        return '<50t'
    return '300t+'

def bin_trades(trades):
    binned = defaultdict(list)
    for t in trades:
        binned[bin_label(t['zone_width'])].append(t)
    return binned

# =========================================================================
#  Load data
# =========================================================================

print("Loading bar data...")
bar_data = {}
for period, fname in [('P1', 'NQ_bardata_P1.csv'), ('P2', 'NQ_bardata_P2.csv')]:
    bars = []
    with open(f'{BASE}/01-data/output/zone_prep/{fname}') as f:
        for row in csv.DictReader(f):
            r = {k.strip(): v.strip() for k, v in row.items()}
            o = float(r['Open']); h = float(r['High'])
            l = float(r['Low']); c = float(r['Last'])
            dt = r['Date'].split('.')[0] + ' ' + r['Time'].split('.')[0]
            bars.append((o, h, l, c, dt))
    bar_data[period] = bars
    print(f"  {period}: {len(bars)} bars")

print("Loading scored touches...")
touches = {}
for period, fname in [('P1', 'p1_scored_touches_acal.csv')]:
    raw = []
    with open(f'{BASE}/04-backtest/zone_touch/output/{fname}') as f:
        for row in csv.DictReader(f):
            if float(row.get('score_acal', 0)) >= SCORE_THRESHOLD:
                tf_min = TF_MINUTES.get(row.get('SourceLabel', '').strip(), 999)
                if tf_min <= TF_MAX_MINUTES:
                    rbi = row.get('RotBarIndex', '').strip()
                    if rbi and int(rbi) >= 0:
                        raw.append(row)
    raw.sort(key=lambda r: int(r['RotBarIndex']))
    touches[period] = raw
    print(f"  {period}: {len(raw)} qualifying touches")

# Check for P2 scored touches
p2_scored = f'{BASE}/04-backtest/zone_touch/output/p2_scored_touches_acal.csv'
if os.path.exists(p2_scored):
    raw = []
    with open(p2_scored) as f:
        for row in csv.DictReader(f):
            if float(row.get('score_acal', 0)) >= SCORE_THRESHOLD:
                tf_min = TF_MINUTES.get(row.get('SourceLabel', '').strip(), 999)
                if tf_min <= TF_MAX_MINUTES:
                    rbi = row.get('RotBarIndex', '').strip()
                    if rbi and int(rbi) >= 0:
                        raw.append(row)
    raw.sort(key=lambda r: int(r['RotBarIndex']))
    touches['P2'] = raw
    print(f"  P2: {len(raw)} qualifying touches")
    has_p2_touches = True
else:
    print("  P2 scored touches not found — using investigation CSV for P2")
    has_p2_touches = False

# =========================================================================
#  CHECK 1: T2 fill rate by zone width bin
# =========================================================================

print("\n" + "=" * 80)
print("CHECK 1: T2 Fill Rate by Zone Width Bin (Zone-Relative Exits)")
print("  T1=0.5x zw, T2=1.0x zw, Stop=max(1.5x zw, 120t), TC=160")
print("  CT: 5t limit entry, WT/NT: market entry")
print("=" * 80)

all_trades = []
for period in ['P1']:
    trades = run_sim(touches[period], bar_data[period])
    for t in trades:
        t['period'] = period
    all_trades.extend(trades)
    print(f"\n  {period}: {len(trades)} trades simulated")

if has_p2_touches:
    p2_trades = run_sim(touches['P2'], bar_data['P2'])
    for t in p2_trades:
        t['period'] = 'P2'
    all_trades.extend(p2_trades)
    print(f"  P2: {len(p2_trades)} trades simulated")
else:
    # Use investigation CSV for P2 — extract zone-relative results
    p2_inv = []
    with open(f'{BASE}/04-backtest/zone_touch/output/zone_touch_exit_investigation.csv') as f:
        for row in csv.DictReader(f):
            zw = float(row['zone_width'])
            pnl_zr = float(row['pnl_zone_rel'])
            mfe_val = float(row['mfe'])
            mae_val = float(row['mae'])
            # We need per-leg exit types for T2 analysis.
            # The investigation CSV doesn't have per-leg zone-relative exits.
            # We need to simulate from bar data.
            p2_inv.append(row)

    # We need P2 touches with RotBarIndex to simulate. Check investigation CSV.
    # Unfortunately investigation CSV doesn't have RotBarIndex.
    # We'll run P2 from P1 scored touches mapped... no, P2 has different data.
    # Let's use the existing investigation CSV 'pnl_zone_rel' column
    # and approximate T2 outcomes from MFE data.
    print("  P2: using investigation CSV (per-leg detail approximate)")

    # For P2, estimate T2 fill from MFE: if mfe >= t2_ticks, T2 likely fills
    for row in p2_inv:
        zw = float(row['zone_width'])
        t2_ticks = max(1, round(1.0 * zw))
        mfe_val = float(row['mfe'])
        pnl_zr = float(row['pnl_zone_rel'])

        t2_filled = mfe_val >= t2_ticks
        t1_ticks = max(1, round(0.5 * zw))
        t1_filled = mfe_val >= t1_ticks
        stop_ticks = max(round(1.5 * zw), 120)

        # Determine approximate leg2 exit type
        if t2_filled:
            leg2_exit = 'TARGET_2'
            leg2_pnl = float(t2_ticks)
        elif mfe_val < stop_ticks * 0.1:  # very low MFE → likely stop
            leg2_exit = 'STOP'
            leg2_pnl = -float(stop_ticks)
        else:
            # Could be timecap or stop
            # If pnl_zone_rel is positive and t1 filled, leg2 likely timecap
            if t1_filled and pnl_zr > 0:
                leg2_exit = 'TIMECAP'
                leg2_pnl = pnl_zr  # approximate
            else:
                leg2_exit = 'STOP'
                leg2_pnl = -float(stop_ticks)

        all_trades.append(dict(
            zone_width=zw, t1_ticks=t1_ticks, t2_ticks=t2_ticks,
            stop_ticks=stop_ticks, mfe=mfe_val, mae=float(row['mae']),
            leg1_exit='TARGET_1' if t1_filled else 'STOP',
            leg2_exit=leg2_exit, leg2_pnl=leg2_pnl,
            weighted_pnl=pnl_zr, t1_filled=t1_filled,
            period='P2', mode='CT' if row['mode'].strip() == 'ModeB' else 'WT'
        ))

# Now analyze by bin
binned = defaultdict(list)
for t in all_trades:
    binned[bin_label(t['zone_width'])].append(t)

print(f"\n{'Zone Width':<12} {'N':>4} {'T2 Target':>10} {'T2 Fill%':>9} {'T2 TC%':>7} {'T2 Stop%':>9} {'Mean T2 PnL':>12} {'Mean MFE':>9}")
print("-" * 78)

for lbl in BIN_LABELS:
    trades = binned.get(lbl, [])
    if not trades:
        print(f"{lbl:<12} {'—':>4}")
        continue

    n = len(trades)
    t2_fills = sum(1 for t in trades if t['leg2_exit'] == 'TARGET_2')
    t2_stops = sum(1 for t in trades if 'STOP' in t['leg2_exit'])
    t2_tc = sum(1 for t in trades if t['leg2_exit'] == 'TIMECAP')
    mean_t2_pnl = sum(t['leg2_pnl'] for t in trades) / n
    mean_mfe = sum(t['mfe'] for t in trades) / n

    # Representative T2 target
    t2_targets = [t['t2_ticks'] for t in trades]
    mean_t2_target = sum(t2_targets) / len(t2_targets)

    print(f"{lbl:<12} {n:>4} {mean_t2_target:>9.0f}t {100*t2_fills/n:>8.1f}% {100*t2_tc/n:>6.1f}% {100*t2_stops/n:>8.1f}% {mean_t2_pnl:>11.1f}t {mean_mfe:>8.1f}t")

# Also show <50t if any
if '<50t' in binned:
    trades = binned['<50t']
    n = len(trades)
    t2_fills = sum(1 for t in trades if t['leg2_exit'] == 'TARGET_2')
    t2_stops = sum(1 for t in trades if 'STOP' in t['leg2_exit'])
    t2_tc = sum(1 for t in trades if t['leg2_exit'] == 'TIMECAP')
    mean_t2_pnl = sum(t['leg2_pnl'] for t in trades) / n
    mean_mfe = sum(t['mfe'] for t in trades) / n
    t2_targets = [t['t2_ticks'] for t in trades]
    mean_t2_target = sum(t2_targets) / len(t2_targets)
    print(f"{'<50t':<12} {n:>4} {mean_t2_target:>9.0f}t {100*t2_fills/n:>8.1f}% {100*t2_tc/n:>6.1f}% {100*t2_stops/n:>8.1f}% {mean_t2_pnl:>11.1f}t {mean_mfe:>8.1f}t")

# Period breakdown
for period in ['P1', 'P2']:
    ptrades = [t for t in all_trades if t['period'] == period]
    if not ptrades:
        continue
    print(f"\n  --- {period} breakdown ---")
    pbinned = defaultdict(list)
    for t in ptrades:
        pbinned[bin_label(t['zone_width'])].append(t)

    print(f"  {'Zone Width':<12} {'N':>4} {'T2 Fill%':>9} {'T2 Stop%':>9} {'Mean MFE':>9} {'MFE/ZW':>7}")
    print(f"  " + "-" * 54)
    for lbl in BIN_LABELS:
        trades = pbinned.get(lbl, [])
        if not trades:
            continue
        n = len(trades)
        t2_fills = sum(1 for t in trades if t['leg2_exit'] == 'TARGET_2')
        t2_stops = sum(1 for t in trades if 'STOP' in t['leg2_exit'])
        mean_mfe = sum(t['mfe'] for t in trades) / n
        mean_zw = sum(t['zone_width'] for t in trades) / n
        mfe_ratio = mean_mfe / mean_zw if mean_zw > 0 else 0
        print(f"  {lbl:<12} {n:>4} {100*t2_fills/n:>8.1f}% {100*t2_stops/n:>8.1f}% {mean_mfe:>8.1f}t {mfe_ratio:>6.2f}x")

# =========================================================================
#  CHECK 1b: MFE analysis for trades where T2 did NOT fill
# =========================================================================

print("\n" + "=" * 80)
print("CHECK 1b: MFE Analysis for T2-Miss Trades (T1 filled but T2 did not)")
print("=" * 80)

for lbl in BIN_LABELS:
    trades = binned.get(lbl, [])
    t2_misses = [t for t in trades if t['t1_filled'] and t['leg2_exit'] != 'TARGET_2']
    if not t2_misses:
        continue

    mfes = [t['mfe'] for t in t2_misses]
    zws = [t['zone_width'] for t in t2_misses]
    mfe_ratios = [t['mfe'] / t['zone_width'] for t in t2_misses if t['zone_width'] > 0]

    print(f"\n  {lbl}: {len(t2_misses)} T2 misses (T1 filled)")
    print(f"    MFE: min={min(mfes):.0f}t, mean={sum(mfes)/len(mfes):.0f}t, "
          f"median={sorted(mfes)[len(mfes)//2]:.0f}t, max={max(mfes):.0f}t")
    print(f"    MFE/ZW: min={min(mfe_ratios):.2f}x, mean={sum(mfe_ratios)/len(mfe_ratios):.2f}x, "
          f"median={sorted(mfe_ratios)[len(mfe_ratios)//2]:.2f}x, max={max(mfe_ratios):.2f}x")

    # Histogram of MFE/ZW
    buckets = [0.25, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
    for b in buckets:
        count = sum(1 for r in mfe_ratios if r >= b)
        print(f"    MFE >= {b:.2f}x zw: {count}/{len(mfe_ratios)} ({100*count/len(mfe_ratios):.0f}%)")

# =========================================================================
#  CHECK 2: BE step-up analysis by zone width bin (P1 only — simulation)
# =========================================================================

print("\n" + "=" * 80)
print("CHECK 2: BE Step-Up Analysis by Zone Width Bin")
print("  After T1 fills, move leg2 stop to entry (BE) or to 0.25x/0.5x zw profit")
print("  P1 data only (requires bar-level simulation)")
print("=" * 80)

# Run 4 variants on P1
variants = [
    ('No BE', False, None),
    ('BE at entry', True, 0.0),
    ('BE at 0.25x zw', True, 0.25),
    ('BE at 0.5x zw', True, 0.5),
]

p1_results = {}
for name, be_flag, be_mult in variants:
    trades = run_sim(touches['P1'], bar_data['P1'],
                     be_after_t1=be_flag, be_level_mult=be_mult)
    for t in trades:
        t['period'] = 'P1'
    p1_results[name] = trades

# Wide zones (>= 200t)
print(f"\n{'':30} {'No BE':>10} {'BE@entry':>10} {'BE@0.25x':>10} {'BE@0.5x':>10}")
print("-" * 72)

for width_range, width_label in [
    ((200, 300), '200-300t'),
    ((300, 9999), '300t+'),
    ((0, 150), '<150t (narrow)'),
    ((0, 9999), 'ALL'),
]:
    lo, hi = width_range

    # Leg2 stats for each variant
    row_pnl = f"  {width_label + ': Leg2 PnL':<28}"
    row_fill = f"  {width_label + ': T2 fill%':<28}"
    row_wpnl = f"  {width_label + ': wPnL/trade':<28}"
    row_n = f"  {width_label + ': N':<28}"

    for name, _, _ in variants:
        trades = [t for t in p1_results[name] if lo <= t['zone_width'] < hi]
        if not trades:
            row_pnl += f"{'—':>10}"
            row_fill += f"{'—':>10}"
            row_wpnl += f"{'—':>10}"
            row_n += f"{'—':>10}"
            continue

        n = len(trades)
        t2_fills = sum(1 for t in trades if t['leg2_exit'] == 'TARGET_2')
        mean_leg2 = sum(t['leg2_pnl'] for t in trades) / n
        mean_wpnl = sum(t['weighted_pnl'] for t in trades) / n

        row_n += f"{n:>10}"
        row_pnl += f"{mean_leg2:>9.1f}t"
        row_fill += f"{100*t2_fills/n:>9.1f}%"
        row_wpnl += f"{mean_wpnl:>9.1f}t"

    print(row_n)
    print(row_fill)
    print(row_pnl)
    print(row_wpnl)
    print()

# Detailed breakdown: what happens to trades after BE triggers
print("\n--- BE Impact Detail (P1, zones >= 200t) ---")
no_be_wide = [t for t in p1_results['No BE'] if t['zone_width'] >= 200]
be_entry_wide = [t for t in p1_results['BE at entry'] if t['zone_width'] >= 200]

if no_be_wide and be_entry_wide:
    print(f"\n  No BE:    {len(no_be_wide)} trades, "
          f"total wPnL = {sum(t['weighted_pnl'] for t in no_be_wide):.0f}t")
    print(f"  BE@entry: {len(be_entry_wide)} trades, "
          f"total wPnL = {sum(t['weighted_pnl'] for t in be_entry_wide):.0f}t")

    # Count BE-specific outcomes
    be_stops = sum(1 for t in be_entry_wide if t['leg2_exit'] == 'STOP_BE')
    print(f"  Leg2 stopped by BE rule: {be_stops}/{len(be_entry_wide)}")

    # For trades where BE stops leg2, what was the leg2 PnL vs no-BE?
    # Match by trade index
    if len(no_be_wide) == len(be_entry_wide):
        be_helped = 0
        be_hurt = 0
        for nb, be in zip(no_be_wide, be_entry_wide):
            if be['leg2_exit'] == 'STOP_BE':
                # BE stopped this trade — compare leg2 pnl
                if be['leg2_pnl'] > nb['leg2_pnl']:
                    be_helped += 1
                elif be['leg2_pnl'] < nb['leg2_pnl']:
                    be_hurt += 1
        print(f"  Of BE-stopped trades: BE helped {be_helped}, BE hurt {be_hurt}")

print("\n--- BE Impact Detail (P1, zones < 150t) ---")
no_be_narrow = [t for t in p1_results['No BE'] if t['zone_width'] < 150]
be_entry_narrow = [t for t in p1_results['BE at entry'] if t['zone_width'] < 150]

if no_be_narrow and be_entry_narrow:
    print(f"\n  No BE:    {len(no_be_narrow)} trades, "
          f"total wPnL = {sum(t['weighted_pnl'] for t in no_be_narrow):.0f}t")
    print(f"  BE@entry: {len(be_entry_narrow)} trades, "
          f"total wPnL = {sum(t['weighted_pnl'] for t in be_entry_narrow):.0f}t")

    be_stops = sum(1 for t in be_entry_narrow if t['leg2_exit'] == 'STOP_BE')
    print(f"  Leg2 stopped by BE rule: {be_stops}/{len(be_entry_narrow)}")

print("\nDone.")
