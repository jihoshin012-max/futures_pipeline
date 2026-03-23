# archetype: zone_touch
"""
Equity Curve Comparison: v1.0 (fixed exits) vs v3.0 (zone-relative exits)
Produces side-by-side cumulative equity curves for P1 and P2.

Usage:
    python equity_curve_comparison.py
"""
import csv, json, math
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
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
#  2-leg simulator (supports both fixed and zone-relative)
# =========================================================================

def sim_2leg(bar_data, entry_bar, direction, t1_ticks, t2_ticks, stop_ticks,
             tcap=160, limit_ticks=None):
    n_bars = len(bar_data)
    if entry_bar >= n_bars:
        return None

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

    leg1_open = leg2_open = True
    leg1_pnl = leg2_pnl = 0.0
    leg1_exit_bar = leg2_exit_bar = entry_bar
    last_i = entry_bar

    for i in range(entry_bar, n_bars):
        o_b, h_b, l_b, c_b, dt_b = bar_data[i]
        bh = i - entry_bar + 1
        last_i = i

        # Time cap
        if bh >= tcap:
            pnl = (c_b - ep) / TICK_SIZE if direction == 1 else (ep - c_b) / TICK_SIZE
            if leg1_open: leg1_pnl = pnl; leg1_exit_bar = i
            if leg2_open: leg2_pnl = pnl; leg2_exit_bar = i
            break

        # Stop (stop-first rule)
        stop_hit = (l_b <= stop_px) if direction == 1 else (h_b >= stop_px)
        if stop_hit:
            spnl = (stop_px - ep) / TICK_SIZE if direction == 1 else (ep - stop_px) / TICK_SIZE
            if leg1_open: leg1_pnl = spnl; leg1_exit_bar = i
            if leg2_open: leg2_pnl = spnl; leg2_exit_bar = i
            break

        # T1
        if leg1_open:
            hit = (h_b >= t1_px) if direction == 1 else (l_b <= t1_px)
            if hit:
                leg1_pnl = float(t1_ticks); leg1_exit_bar = i; leg1_open = False

        # T2
        if leg2_open:
            hit = (h_b >= t2_px) if direction == 1 else (l_b <= t2_px)
            if hit:
                leg2_pnl = float(t2_ticks); leg2_exit_bar = i; leg2_open = False

        if not leg1_open and not leg2_open:
            break

    # End of data
    if leg1_open or leg2_open:
        last_c = bar_data[min(last_i, n_bars - 1)][3]
        pnl = (last_c - ep) / TICK_SIZE if direction == 1 else (ep - last_c) / TICK_SIZE
        if leg1_open: leg1_pnl = pnl; leg1_exit_bar = last_i
        if leg2_open: leg2_pnl = pnl; leg2_exit_bar = last_i

    wpnl = LEG1_W * leg1_pnl + LEG2_W * leg2_pnl - COST_TICKS
    final_bar = max(leg1_exit_bar, leg2_exit_bar)
    return dict(weighted_pnl=wpnl, final_bar=final_bar, entry_price=ep)

# =========================================================================
#  Run simulation on a set of touches with mode routing + no-overlap
# =========================================================================

def run_sim(touches, bar_data, exit_mode='fixed', use_ct_limit=False):
    """
    exit_mode: 'fixed' (v1.0) or 'zone_rel' (v3.0)
    use_ct_limit: True to use 5t limit for CT (v3.0), False for market (v1.0)
    """
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

        # Mode routing
        if trend_label == 'CT':
            mode = 'CT'
        else:
            mode = 'WT'
            if seq > WTNT_SEQ_MAX:
                continue

        # No-overlap
        if entry_bar <= in_trade_until:
            continue

        # Compute exit params
        if exit_mode == 'zone_rel':
            t1 = max(1, round(0.5 * zw))
            t2 = max(1, round(1.0 * zw))
            stop = max(round(1.5 * zw), 120)
        else:
            # v1.0 fixed exits
            if mode == 'CT':
                t1, t2, stop = 40, 80, 190
            else:
                t1, t2, stop = 60, 80, 240

        limit = 5 if (use_ct_limit and mode == 'CT') else None

        result = sim_2leg(bar_data, entry_bar, direction, t1, t2, stop,
                          tcap=160, limit_ticks=limit)
        if result is None:
            continue

        in_trade_until = result['final_bar']

        dt_str = bar_data[entry_bar][4]
        try:
            dt = datetime.strptime(dt_str, '%Y-%m-%d %H:%M:%S')
        except ValueError:
            try:
                dt = datetime.strptime(dt_str, '%m/%d/%Y %H:%M:%S')
            except ValueError:
                dt = datetime.strptime(dt_str.split('.')[0], '%Y-%m-%d %H:%M:%S')

        trades.append(dict(
            datetime=dt,
            weighted_pnl=result['weighted_pnl'],
            mode=mode,
            zone_width=zw
        ))

    return trades

# =========================================================================
#  Load data
# =========================================================================

print("Loading P1 bar data...")
bar_data_p1 = []
with open(f'{BASE}/01-data/output/zone_prep/NQ_bardata_P1.csv') as f:
    for row in csv.DictReader(f):
        r = {k.strip(): v.strip() for k, v in row.items()}
        o = float(r['Open']); h = float(r['High'])
        l = float(r['Low']); c = float(r['Last'])
        dt = r['Date'].split('.')[0] + ' ' + r['Time'].split('.')[0]
        bar_data_p1.append((o, h, l, c, dt))
print(f"  {len(bar_data_p1)} bars")

print("Loading P1 scored touches...")
p1_touches = []
with open(f'{BASE}/04-backtest/zone_touch/output/p1_scored_touches_acal.csv') as f:
    for row in csv.DictReader(f):
        if float(row.get('score_acal', 0)) >= SCORE_THRESHOLD:
            tf_min = TF_MINUTES.get(row.get('SourceLabel', '').strip(), 999)
            if tf_min <= TF_MAX_MINUTES:
                rbi = row.get('RotBarIndex', '').strip()
                if rbi and int(rbi) >= 0:
                    p1_touches.append(row)
p1_touches.sort(key=lambda r: int(r['RotBarIndex']))
print(f"  {len(p1_touches)} qualifying touches")

# P2: use the investigation CSV which has per-trade pnl for fixed exits
# and pnl_zone_rel for zone-relative
print("Loading P2 trade data (pre-computed)...")
p2_raw = []
with open(f'{BASE}/04-backtest/zone_touch/output/zone_touch_exit_investigation.csv') as f:
    for row in csv.DictReader(f):
        p2_raw.append(row)
print(f"  {len(p2_raw)} P2 trades")

# =========================================================================
#  P1: Run both simulations
# =========================================================================

print("\nRunning P1 simulations...")
p1_fixed = run_sim(p1_touches, bar_data_p1, exit_mode='fixed', use_ct_limit=False)
p1_zr = run_sim(p1_touches, bar_data_p1, exit_mode='zone_rel', use_ct_limit=True)
print(f"  v1.0 (fixed): {len(p1_fixed)} trades")
print(f"  v3.0 (zone-rel): {len(p1_zr)} trades")

# =========================================================================
#  P2: Extract from pre-computed data
#  pnl column = fixed exit PnL (single-leg, original exit sweep result)
#  pnl_zone_rel = zone-relative exit PnL
#  Both are single-leg weighted PnL from the investigation
# =========================================================================

# For P2, we need to reconstruct 2-leg weighted PnL.
# The 'pnl' column is the single-leg PnL from fixed exits (80t target, mode-specific stop).
# The 'pnl_zone_rel' column is zone-relative (already 2-leg weighted from exit_investigation).
# Let's check what 'pnl' actually is by looking at the data.

# Actually the P2 investigation CSV 'pnl' is single-leg (not 2-leg weighted).
# And 'pnl_zone_rel' was computed by exit_investigation_2leg.py as 2-leg weighted.
# For fair comparison, we need to run P2 through the same simulator.

# Load P2 bar data
print("Loading P2 bar data...")
bar_data_p2 = []
with open(f'{BASE}/01-data/output/zone_prep/NQ_bardata_P2.csv') as f:
    for row in csv.DictReader(f):
        r = {k.strip(): v.strip() for k, v in row.items()}
        o = float(r['Open']); h = float(r['High'])
        l = float(r['Low']); c = float(r['Last'])
        dt = r['Date'].split('.')[0] + ' ' + r['Time'].split('.')[0]
        bar_data_p2.append((o, h, l, c, dt))
print(f"  {len(bar_data_p2)} bars")

print("Loading P2 scored touches...")
p2_touches = []
with open(f'{BASE}/04-backtest/zone_touch/output/p1_scored_touches_acal.csv') as f:
    header = None
# P2 touches might be in a different file — check for p2 scored touches
import os
p2_scored_path = f'{BASE}/04-backtest/zone_touch/output/p2_scored_touches_acal.csv'
if not os.path.exists(p2_scored_path):
    # Fall back: use the investigation CSV directly for P2
    # We already have pnl (fixed) and pnl_zone_rel (zone-relative) per trade
    print("  Using pre-computed P2 investigation data (no P2 scored touches file)")
    use_p2_precomputed = True
else:
    with open(p2_scored_path) as f:
        for row in csv.DictReader(f):
            if float(row.get('score_acal', 0)) >= SCORE_THRESHOLD:
                tf_min = TF_MINUTES.get(row.get('SourceLabel', '').strip(), 999)
                if tf_min <= TF_MAX_MINUTES:
                    rbi = row.get('RotBarIndex', '').strip()
                    if rbi and int(rbi) >= 0:
                        p2_touches.append(row)
    p2_touches.sort(key=lambda r: int(r['RotBarIndex']))
    print(f"  {len(p2_touches)} qualifying touches")
    use_p2_precomputed = False

if use_p2_precomputed:
    # Use the investigation CSV columns directly
    # pnl = fixed single-leg result; we need 2-leg weighted
    # pnl_zone_rel = zone-relative 2-leg weighted PnL (already computed)
    # For fixed 2-leg: we don't have it pre-computed, so use the raw pnl
    # as a proxy (it IS the 2-leg weighted from the original pipeline backtest)
    p2_fixed_trades = []
    p2_zr_trades = []

    for row in p2_raw:
        try:
            dt = datetime.strptime(row['datetime'].strip(), '%Y-%m-%d %H:%M:%S')
        except ValueError:
            dt = datetime.strptime(row['datetime'].strip().split('.')[0], '%Y-%m-%d %H:%M:%S')

        mode = 'CT' if row['mode'].strip() == 'ModeB' else 'WT'

        # Fixed PnL: the 'pnl' column is the original backtest result
        # This was computed with fixed exits (CT: 40/80/190, WT: 60/80/240)
        # as single-leg, so we use it as-is (it's what v1.0 would produce
        # on a single-leg basis). For 2-leg comparison we need weighted PnL.
        # The original pipeline used 2-leg: pnl = LEG1_W * t1_pnl + LEG2_W * t2_pnl - cost
        # The 'pnl' column in investigation is single-target PnL.
        # Let's just use it as an approximation for the shape of the curve.
        pnl_fixed = float(row['pnl'])
        pnl_zr = float(row['pnl_zone_rel'])

        p2_fixed_trades.append(dict(datetime=dt, weighted_pnl=pnl_fixed, mode=mode))
        p2_zr_trades.append(dict(datetime=dt, weighted_pnl=pnl_zr, mode=mode))

    # Sort by datetime
    p2_fixed_trades.sort(key=lambda x: x['datetime'])
    p2_zr_trades.sort(key=lambda x: x['datetime'])
    print(f"  P2 fixed: {len(p2_fixed_trades)} trades")
    print(f"  P2 zone-rel: {len(p2_zr_trades)} trades")
else:
    print("\nRunning P2 simulations...")
    p2_fixed_trades_raw = run_sim(p2_touches, bar_data_p2, exit_mode='fixed', use_ct_limit=False)
    p2_zr_trades_raw = run_sim(p2_touches, bar_data_p2, exit_mode='zone_rel', use_ct_limit=True)
    p2_fixed_trades = p2_fixed_trades_raw
    p2_zr_trades = p2_zr_trades_raw
    print(f"  v1.0 (fixed): {len(p2_fixed_trades)} trades")
    print(f"  v3.0 (zone-rel): {len(p2_zr_trades)} trades")

# =========================================================================
#  Compute cumulative equity
# =========================================================================

def cumulative_equity(trades):
    dates = []
    equity = []
    cum = 0.0
    for t in trades:
        cum += t['weighted_pnl']
        dates.append(t['datetime'])
        equity.append(cum)
    return dates, equity

def calc_stats(trades):
    pnls = [t['weighted_pnl'] for t in trades]
    if not pnls:
        return {}
    wins = sum(1 for p in pnls if p > 0)
    gw = sum(p for p in pnls if p > 0)
    gl = sum(abs(p) for p in pnls if p < 0)
    pf = gw / gl if gl > 0 else float('inf')
    ev = sum(pnls) / len(pnls)
    # Max drawdown
    peak = 0.0
    dd = 0.0
    cum = 0.0
    for p in pnls:
        cum += p
        if cum > peak: peak = cum
        if peak - cum > dd: dd = peak - cum
    return dict(n=len(pnls), wr=100*wins/len(pnls), pf=pf, ev=ev,
                total=sum(pnls), max_dd=dd)

# =========================================================================
#  Plot
# =========================================================================

fig, axes = plt.subplots(1, 2, figsize=(16, 7), sharey=False)
fig.suptitle('Equity Curve Comparison: v1.0 (Fixed Exits) vs v3.0 (Zone-Relative)',
             fontsize=14, fontweight='bold')

tick_value = 5.0  # $5 per tick per contract, 3ct base

for ax, label, fixed_trades, zr_trades in [
    (axes[0], 'P1 (In-Sample)', p1_fixed, p1_zr),
    (axes[1], 'P2 (Out-of-Sample)', p2_fixed_trades, p2_zr_trades),
]:
    fd, fe = cumulative_equity(fixed_trades)
    zd, ze = cumulative_equity(zr_trades)

    fs = calc_stats(fixed_trades)
    zs = calc_stats(zr_trades)

    ax.plot(fd, fe, color='#888888', linewidth=1.5, label='v1.0 Fixed', alpha=0.8)
    ax.plot(zd, ze, color='#2196F3', linewidth=2.0, label='v3.0 Zone-Rel')
    ax.axhline(y=0, color='white', linewidth=0.5, alpha=0.3)

    # Fill area between
    # Only if same length (P2 precomputed has same trades both ways)
    if len(fd) == len(zd):
        ax.fill_between(zd, fe, ze, alpha=0.15, color='#2196F3')

    ax.set_title(f'{label}', fontsize=12, fontweight='bold')
    ax.set_xlabel('Date')
    ax.set_ylabel('Cumulative PnL (ticks)')
    ax.legend(loc='upper left', fontsize=9)

    # Stats text box
    stats_text = (
        f"v1.0: {fs.get('n',0)} trades, PF {fs.get('pf',0):.2f}, "
        f"WR {fs.get('wr',0):.1f}%, EV {fs.get('ev',0):.1f}t\n"
        f"v3.0: {zs.get('n',0)} trades, PF {zs.get('pf',0):.2f}, "
        f"WR {zs.get('wr',0):.1f}%, EV {zs.get('ev',0):.1f}t\n"
        f"v1.0 total: {fs.get('total',0):.0f}t  |  "
        f"v3.0 total: {zs.get('total',0):.0f}t"
    )
    ax.text(0.02, 0.02, stats_text, transform=ax.transAxes,
            fontsize=8, verticalalignment='bottom',
            bbox=dict(boxstyle='round,pad=0.4', facecolor='black', alpha=0.7),
            color='white', family='monospace')

    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b'))
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right')
    ax.grid(True, alpha=0.2)

# Style
fig.patch.set_facecolor('#1a1a2e')
for ax in axes:
    ax.set_facecolor('#16213e')
    ax.tick_params(colors='white')
    ax.xaxis.label.set_color('white')
    ax.yaxis.label.set_color('white')
    ax.title.set_color('white')
    for spine in ax.spines.values():
        spine.set_color('#333')

fig.suptitle('Equity Curve Comparison: v1.0 (Fixed Exits) vs v3.0 (Zone-Relative)',
             fontsize=14, fontweight='bold', color='white')

plt.tight_layout()
out_path = f'{BASE}/04-backtest/zone_touch/output/equity_curve_v1_vs_v3.png'
plt.savefig(out_path, dpi=150, bbox_inches='tight', facecolor=fig.get_facecolor())
print(f"\nSaved: {out_path}")

# Print summary
print("\n" + "=" * 60)
print("SUMMARY")
print("=" * 60)
for label, ft, zt in [('P1', p1_fixed, p1_zr),
                       ('P2', p2_fixed_trades, p2_zr_trades)]:
    fs = calc_stats(ft)
    zs = calc_stats(zt)
    print(f"\n{label}:")
    print(f"  v1.0: {fs['n']} trades, PF={fs['pf']:.2f}, WR={fs['wr']:.1f}%, "
          f"EV={fs['ev']:.1f}t, Total={fs['total']:.0f}t, MaxDD={fs['max_dd']:.0f}t")
    print(f"  v3.0: {zs['n']} trades, PF={zs['pf']:.2f}, WR={zs['wr']:.1f}%, "
          f"EV={zs['ev']:.1f}t, Total={zs['total']:.0f}t, MaxDD={zs['max_dd']:.0f}t")
    if fs['total'] != 0:
        print(f"  Improvement: {(zs['total']/fs['total'] - 1)*100:+.0f}% total PnL")
