# archetype: zone_touch
"""
P1 Validation — Zone-Relative Exit Framework (GATE decision).

Reads p1_scored_touches_acal.csv (pre-scored) + NQ_bardata_P1.csv.
Runs 5 validations comparing zone-relative exits against P2 benchmarks.

Usage:
    python p1_zone_relative_gate.py
"""
import csv, sys, math
from collections import Counter, defaultdict

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

# =========================================================================
#  Trend classification (non-direction-aware, from feature_config.json)
# =========================================================================

import json
with open(f'{BASE}/04-backtest/zone_touch/output/feature_config.json') as f:
    FCFG = json.load(f)
TREND_P33 = FCFG['trend_slope_p33']
TREND_P67 = FCFG['trend_slope_p67']

def classify_trend(slope):
    if slope <= TREND_P33: return 'CT'
    if slope >= TREND_P67: return 'WT'
    return 'NT'

# =========================================================================
#  2-leg simulator (zone-relative version)
# =========================================================================

def sim_2leg_zr(bar_data, entry_bar, direction, zone_width_ticks,
                t1_mult=0.5, t2_mult=1.0, stop_mult=1.5, tcap=160,
                stop_floor=None, limit_ticks=None):
    """
    Zone-relative 2-leg exit simulator.

    limit_ticks: if set, entry is limit order at touch_price ± limit_ticks.
                 Returns None if not filled within 1 bar.
    stop_floor:  if set, stop = max(stop_mult * zw, stop_floor)
    """
    n_bars = len(bar_data)
    if entry_bar >= n_bars:
        return None

    # Zone-relative targets in ticks
    t1_ticks = max(1, round(t1_mult * zone_width_ticks))
    t2_ticks = max(1, round(t2_mult * zone_width_ticks))
    stop_ticks = max(1, round(stop_mult * zone_width_ticks))
    if stop_floor is not None:
        stop_ticks = max(stop_ticks, stop_floor)

    # Entry
    if limit_ticks is not None:
        # Limit entry: check if bar fills within limit_ticks of open
        o, h, l, c, dt = bar_data[entry_bar]
        # For limit entry on demand (long): limit = open - limit_ticks * TICK
        # Actually: limit order at 5t better than market open
        # The "5t limit" means we place a limit order 5 ticks better than
        # the touch bar close (which ~ next bar open). Practically:
        # entry at open - 5t for longs, open + 5t for shorts.
        # Fill if price reaches our limit during the bar.
        if direction == 1:
            limit_px = o - limit_ticks * TICK_SIZE
            if l <= limit_px:
                ep = limit_px
            else:
                return None  # not filled
        else:
            limit_px = o + limit_ticks * TICK_SIZE
            if h >= limit_px:
                ep = limit_px
            else:
                return None  # not filled
    else:
        ep = bar_data[entry_bar][0]  # Open (market entry)

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
            if leg1_open:
                leg1_pnl = pnl; leg1_exit = 'TIMECAP'; leg1_exit_bar = i
            if leg2_open:
                leg2_pnl = pnl; leg2_exit = 'TIMECAP'; leg2_exit_bar = i
            break

        # Stop
        stop_hit = (l_b <= stop_px) if direction == 1 else (h_b >= stop_px)
        if stop_hit:
            spnl = (stop_px - ep) / TICK_SIZE if direction == 1 else (ep - stop_px) / TICK_SIZE
            if leg1_open:
                leg1_pnl = spnl; leg1_exit = 'STOP'; leg1_exit_bar = i
            if leg2_open:
                leg2_pnl = spnl; leg2_exit = 'STOP'; leg2_exit_bar = i
            break

        # Target 1
        if leg1_open:
            hit = (h_b >= t1_px) if direction == 1 else (l_b <= t1_px)
            if hit:
                leg1_pnl = float(t1_ticks); leg1_exit = 'TARGET_1'
                leg1_exit_bar = i; leg1_open = False

        # Target 2
        if leg2_open:
            hit = (h_b >= t2_px) if direction == 1 else (l_b <= t2_px)
            if hit:
                leg2_pnl = float(t2_ticks); leg2_exit = 'TARGET_2'
                leg2_exit_bar = i; leg2_open = False

        if not leg1_open and not leg2_open:
            break

    # End of data
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
        leg1_exit_bar=leg1_exit_bar, leg2_exit_bar=leg2_exit_bar
    )

# =========================================================================
#  Load bar data
# =========================================================================

print("Loading P1 bar data...")
bar_data = []  # (Open, High, Low, Last, datetime_str)
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

# =========================================================================
#  Load scored touches
# =========================================================================

print("Loading P1 scored touches (A-Cal)...")
raw_touches = []
with open(f'{BASE}/04-backtest/zone_touch/output/p1_scored_touches_acal.csv') as f:
    for row in csv.DictReader(f):
        raw_touches.append(row)
print(f"  {len(raw_touches)} total touches")

# =========================================================================
#  Filter qualifying touches
# =========================================================================

def get_qualifying_touches(touches):
    """Filter: score >= 16.66, TF <= 120m, valid RotBarIndex."""
    out = []
    for t in touches:
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
        out.append(t)
    # Sort by RotBarIndex (chronological)
    out.sort(key=lambda r: int(r['RotBarIndex']))
    return out

qualifying = get_qualifying_touches(raw_touches)
print(f"  {len(qualifying)} qualifying (score >= {SCORE_THRESHOLD}, TF <= {TF_MAX_MINUTES}m)")

# =========================================================================
#  Simulation runner with mode routing + no-overlap
# =========================================================================

def run_simulation(touches, limit_ticks_ct=None, limit_ticks_wt=None,
                   stop_floor=None, label=""):
    """
    Run zone-relative 2-leg simulation with mode routing and no-overlap.

    Returns list of trade dicts.
    """
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

        # Trend from CSV (non-direction-aware)
        ts_str = t.get('TrendSlope', '').strip()
        # TrendSlope may be empty for some rows; also check the second TrendSlope column
        if not ts_str:
            # Fall back to TrendLabel from CSV
            trend_label = t.get('TrendLabel', 'NT').strip()
            if not trend_label:
                trend_label = 'NT'
        else:
            trend_slope = float(ts_str)
            trend_label = classify_trend(trend_slope)

        # Mode routing
        if trend_label == 'CT':
            mode = 'CT'
            # CT: no seq gate
            limit = limit_ticks_ct
        else:
            mode = 'WT'
            # WT/NT: seq <= 5
            if seq > WTNT_SEQ_MAX:
                continue
            limit = limit_ticks_wt

        # No-overlap
        if entry_bar <= in_trade_until:
            continue

        # Simulate
        result = sim_2leg_zr(bar_data, entry_bar, direction, zw,
                             t1_mult=0.5, t2_mult=1.0, stop_mult=1.5,
                             tcap=160, stop_floor=stop_floor,
                             limit_ticks=limit)
        if result is None:
            continue

        # Update in_trade_until
        final_exit_bar = max(result['leg1_exit_bar'], result['leg2_exit_bar'])
        in_trade_until = final_exit_bar

        trade = dict(
            mode=mode,
            trend_label=trend_label,
            direction=direction,
            zone_width=zw,
            seq=seq,
            **result
        )
        trades.append(trade)

    return trades

# =========================================================================
#  Stats helpers
# =========================================================================

def calc_stats(trades):
    if not trades:
        return dict(n=0, wr=0, pf=0, ev=0, max_dd=0, stop_rate=0, tc_rate=0,
                    gross_win=0, gross_loss=0)
    pnls = [t['weighted_pnl'] for t in trades]
    wins = sum(1 for p in pnls if p > 0)
    gw = sum(p for p in pnls if p > 0)
    gl = sum(abs(p) for p in pnls if p < 0)
    pf = gw / gl if gl > 0 else float('inf')
    ev = sum(pnls) / len(pnls)
    max_dd = max((abs(p) for p in pnls if p < 0), default=0)
    stops = sum(1 for t in trades if t['leg1_exit'] == 'STOP')
    tcs = sum(1 for t in trades if t['leg1_exit'] == 'TIMECAP')
    n = len(trades)
    return dict(n=n, wr=100*wins/n, pf=pf, ev=ev, max_dd=max_dd,
                stop_rate=100*stops/n, tc_rate=100*tcs/n,
                gross_win=gw, gross_loss=gl)

def fmt_pf(pf):
    return f"{pf:.2f}" if pf < 9999 else "inf"

# =========================================================================
#  VALIDATION 1: Zone-relative baseline on P1
# =========================================================================

print("\n" + "=" * 70)
print("VALIDATION 1: Zone-Relative 2-Leg Baseline on P1")
print("=" * 70)
print("  Entry: market at next bar open")
print("  T1=0.5x ZW (67%), T2=1.0x ZW (33%), Stop=1.5x ZW, TC=160 bars")
print("  Cost=3t per trade\n")

v1_trades = run_simulation(qualifying)
v1_all = calc_stats(v1_trades)
v1_ct = calc_stats([t for t in v1_trades if t['mode'] == 'CT'])
v1_wt = calc_stats([t for t in v1_trades if t['mode'] == 'WT'])

print(f"{'Metric':<22} {'P1 Zone-Rel':>12} {'P2 Zone-Rel':>12} {'Consistent?':>12}")
print("-" * 60)
print(f"{'Trades':<22} {v1_all['n']:>12} {'312':>12} {'—':>12}")
print(f"{'WR':<22} {v1_all['wr']:>11.1f}% {'92.0%':>12} {'YES' if v1_all['wr'] > 80 else 'NO':>12}")
print(f"{'PF':<22} {fmt_pf(v1_all['pf']):>12} {'28.69':>12} {'YES' if v1_all['pf'] > 3 else 'NO':>12}")
print(f"{'EV/trade':<22} {v1_all['ev']:>11.1f}t {'107.4':>12} {'—':>12}")
print(f"{'Max DD (single)':<22} {v1_all['max_dd']:>11.1f}t {'154t':>12} {'—':>12}")
print(f"{'Stop rate':<22} {v1_all['stop_rate']:>11.1f}% {'—':>12} {'—':>12}")
print(f"{'Timecap rate':<22} {v1_all['tc_rate']:>11.1f}% {'—':>12} {'—':>12}")

print(f"\n  CT split:  {v1_ct['n']} trades, WR={v1_ct['wr']:.1f}%, PF={fmt_pf(v1_ct['pf'])}, EV={v1_ct['ev']:.1f}t")
print(f"  WT split:  {v1_wt['n']} trades, WR={v1_wt['wr']:.1f}%, PF={fmt_pf(v1_wt['pf'])}, EV={v1_wt['ev']:.1f}t")

# =========================================================================
#  VALIDATION 2: CT 5t limit + zone-relative on P1
# =========================================================================

print("\n" + "=" * 70)
print("VALIDATION 2: CT 5t Limit + Zone-Relative on P1")
print("=" * 70)
print("  CT: 5t limit entry, WT: market entry\n")

v2_trades = run_simulation(qualifying, limit_ticks_ct=5, limit_ticks_wt=None)
v2_ct = calc_stats([t for t in v2_trades if t['mode'] == 'CT'])
v2_wt = calc_stats([t for t in v2_trades if t['mode'] == 'WT'])
v2_all = calc_stats(v2_trades)

# CT fill rate
ct_total = sum(1 for t in qualifying
               if classify_trend(float(t['TrendSlope']) if t.get('TrendSlope', '').strip() else 0.0) == 'CT')
ct_fills = v2_ct['n']

print(f"{'Metric':<22} {'P1 5t+ZR':>12} {'Notes':>20}")
print("-" * 56)
print(f"{'CT trades (filled)':<22} {v2_ct['n']:>12} {'of ~' + str(ct_total) + ' signals':>20}")
print(f"{'CT WR':<22} {v2_ct['wr']:>11.1f}% {'':>20}")
print(f"{'CT PF':<22} {fmt_pf(v2_ct['pf']):>12} {'':>20}")
print(f"{'CT EV/trade':<22} {v2_ct['ev']:>11.1f}t {'':>20}")
ct_losses = sum(1 for t in v2_trades if t['mode'] == 'CT' and t['weighted_pnl'] < 0)
print(f"{'CT losses':<22} {ct_losses:>12} {'target: 0':>20}")
print(f"{'WT trades':<22} {v2_wt['n']:>12} {'market entry':>20}")
print(f"{'WT WR':<22} {v2_wt['wr']:>11.1f}% {'':>20}")
print(f"{'WT PF':<22} {fmt_pf(v2_wt['pf']):>12} {'':>20}")
print(f"{'WT EV/trade':<22} {v2_wt['ev']:>11.1f}t {'':>20}")

# =========================================================================
#  VALIDATION 3: Stop floor test on P1
# =========================================================================

print("\n" + "=" * 70)
print("VALIDATION 3: Stop Floor Test on P1")
print("=" * 70)
print("  Comparing: stop=1.5x ZW  vs  stop=max(1.5x ZW, 120t)\n")

v3_pure = run_simulation(qualifying, stop_floor=None)
v3_floor = run_simulation(qualifying, stop_floor=120)

v3_pure_s = calc_stats(v3_pure)
v3_floor_s = calc_stats(v3_floor)

# Count trades affected by floor
affected = 0
for t in v3_floor:
    zw = t['zone_width']
    pure_stop = max(1, round(1.5 * zw))
    if pure_stop < 120:
        affected += 1

# Narrow zone subset (50-100t)
narrow_pure = [t for t in v3_pure if 50 <= t['zone_width'] <= 100]
narrow_floor = [t for t in v3_floor if 50 <= t['zone_width'] <= 100]
np_s = calc_stats(narrow_pure)
nf_s = calc_stats(narrow_floor)

print(f"{'Metric':<28} {'1.5x pure':>12} {'max(1.5x,120t)':>15}")
print("-" * 57)
print(f"{'Trades affected by floor':<28} {'—':>12} {affected:>15}")
print(f"{'WR':<28} {v3_pure_s['wr']:>11.1f}% {v3_floor_s['wr']:>14.1f}%")
print(f"{'PF':<28} {fmt_pf(v3_pure_s['pf']):>12} {fmt_pf(v3_floor_s['pf']):>15}")
print(f"{'Narrow zone (50-100t) WR':<28} {np_s['wr']:>11.1f}% {nf_s['wr']:>14.1f}%")
print(f"{'Narrow zone (50-100t) PF':<28} {fmt_pf(np_s['pf']):>12} {fmt_pf(nf_s['pf']):>15}")
print(f"{'Narrow zone count':<28} {len(narrow_pure):>12} {len(narrow_floor):>15}")

# =========================================================================
#  VALIDATION 4: Zone width distribution comparison
# =========================================================================

print("\n" + "=" * 70)
print("VALIDATION 4: Zone Width Distribution Comparison")
print("=" * 70)

bins_def = [(0, 50), (50, 100), (100, 150), (150, 200), (200, 99999)]
bin_labels = ['0-50t', '50-100t', '100-150t', '150-200t', '200t+']
p2_counts = [4, 33, 74, 62, 139]
p2_total = sum(p2_counts)

# Use v1_trades (market entry, same population)
p1_bins = [0] * 5
for t in v1_trades:
    zw = t['zone_width']
    for i, (lo, hi) in enumerate(bins_def):
        if lo <= zw < hi:
            p1_bins[i] += 1
            break

p1_total = sum(p1_bins)

print(f"\n{'Zone width bin':<16} {'P1 count':>10} {'P1 %':>8} {'P2 count':>10} {'P2 %':>8}")
print("-" * 54)
for i, lbl in enumerate(bin_labels):
    p1_pct = 100 * p1_bins[i] / p1_total if p1_total else 0
    p2_pct = 100 * p2_counts[i] / p2_total
    print(f"{lbl:<16} {p1_bins[i]:>10} {p1_pct:>7.1f}% {p2_counts[i]:>10} {p2_pct:>7.1f}%")

# Chi-square-ish similarity check
max_diff = max(abs(100*p1_bins[i]/p1_total - 100*p2_counts[i]/p2_total)
               for i in range(5)) if p1_total else 999
dist_similar = max_diff < 15  # within 15pp per bin
print(f"\nMax bin difference: {max_diff:.1f}pp — {'SIMILAR' if dist_similar else 'DIFFERENT'}")

# =========================================================================
#  VALIDATION 5: Per zone-width-bin performance on P1
# =========================================================================

print("\n" + "=" * 70)
print("VALIDATION 5: Per Zone-Width-Bin Performance on P1")
print("=" * 70)

p2_wr = [100.0, 75.8, 90.5, 95.2, 95.0]
p2_pf = [float('inf'), 4.77, 8.79, 294.8, 54.22]

print(f"\n{'Zone width':<12} {'P1 WR':>8} {'P1 PF':>8} {'P2 WR':>8} {'P2 PF':>8} {'Consistent?':>12}")
print("-" * 58)

for i, lbl in enumerate(bin_labels):
    lo, hi = bins_def[i]
    bin_trades = [t for t in v1_trades if lo <= t['zone_width'] < hi]
    bs = calc_stats(bin_trades)
    if bs['n'] > 0:
        # Consistent if both WR direction and PF direction roughly match
        wr_ok = (bs['wr'] > 70 and p2_wr[i] > 70) or abs(bs['wr'] - p2_wr[i]) < 15
        pf_ok = (bs['pf'] > 2 and p2_pf[i] > 2)
        consistent = 'YES' if (wr_ok and pf_ok) else 'WEAK' if wr_ok else 'NO'
        print(f"{lbl:<12} {bs['wr']:>7.1f}% {fmt_pf(bs['pf']):>8} {p2_wr[i]:>7.1f}% {fmt_pf(p2_pf[i]):>8} {consistent:>12}  (n={bs['n']})")
    else:
        print(f"{lbl:<12} {'—':>8} {'—':>8} {p2_wr[i]:>7.1f}% {fmt_pf(p2_pf[i]):>8} {'N/A':>12}  (n=0)")

# =========================================================================
#  SUMMARY TABLE + VERDICT
# =========================================================================

print("\n" + "=" * 70)
print("SUMMARY TABLE")
print("=" * 70)

# Evaluate pass/fail
zr_pf_pass = v1_all['pf'] > 3.0
zr_wr_pass = v1_all['wr'] > 80.0
ct_zero_loss = ct_losses == 0
floor_helps = (nf_s['pf'] > np_s['pf']) if (np_s['n'] > 0 and nf_s['n'] > 0) else False

# Per-bin consistency: check weakest bins
bin_consistent = True
for i, lbl in enumerate(bin_labels):
    lo, hi = bins_def[i]
    bt = [t for t in v1_trades if lo <= t['zone_width'] < hi]
    bs = calc_stats(bt)
    if bs['n'] >= 5 and (bs['wr'] < 60 or (bs['pf'] < 1.5 and p2_pf[i] > 3)):
        bin_consistent = False

results = [
    ("ZR baseline PF > 3.0", f"PF={fmt_pf(v1_all['pf'])}", "28.69", "PASS" if zr_pf_pass else "FAIL"),
    ("ZR baseline WR > 80%", f"WR={v1_all['wr']:.1f}%", "92.0%", "PASS" if zr_wr_pass else "FAIL"),
    ("CT 5t + ZR zero losses", f"{ct_losses} losses", "~0 losses", "PASS" if ct_zero_loss else "FAIL"),
    ("Stop floor helps narrow", "YES" if floor_helps else "NO", "—",
     "PASS" if floor_helps or np_s['pf'] > 3 else "ADVISORY"),
    ("Zone width dist similar", f"max {max_diff:.0f}pp", "—", "PASS" if dist_similar else "WARN"),
    ("Per-bin perf consistent", "YES" if bin_consistent else "NO", "—",
     "PASS" if bin_consistent else "FAIL"),
]

print(f"\n{'Test':<30} {'P1 Result':>14} {'P2 Result':>12} {'PASS/FAIL':>10}")
print("-" * 68)
for test, p1r, p2r, verdict in results:
    print(f"{test:<30} {p1r:>14} {p2r:>12} {verdict:>10}")

# =========================================================================
#  VERDICT
# =========================================================================

print("\n" + "=" * 70)
print("VERDICT")
print("=" * 70)

all_pass = all(v == 'PASS' for _, _, _, v in results)
zr_passes = zr_pf_pass and zr_wr_pass
strong = v1_all['pf'] > 5.0 and v1_all['wr'] > 85.0
narrow_fail = not floor_helps and np_s['n'] > 0 and np_s['pf'] < 2.0
zr_fail = not zr_pf_pass or not zr_wr_pass

if zr_fail:
    print("\n  RESULT: ZR FAILS — deploy fixed exits with 5t CT limit only")
    print(f"  P1 PF={fmt_pf(v1_all['pf'])}, WR={v1_all['wr']:.1f}% — below thresholds")
elif all_pass and strong:
    print("\n  RESULT: STRONG PASS — adopt zone-relative framework + 5t CT entry")
    print(f"  P1 PF={fmt_pf(v1_all['pf'])} (>5.0), WR={v1_all['wr']:.1f}% (>85%)")
    print("  All validations passed. Zone-relative replaces fixed exits.")
elif all_pass:
    print("\n  RESULT: PASS — adopt zone-relative framework + 5t CT entry")
    print(f"  P1 PF={fmt_pf(v1_all['pf'])} (>3.0), WR={v1_all['wr']:.1f}% (>80%)")
    print("  All validations passed.")
elif zr_passes and narrow_fail:
    print("\n  RESULT: CONDITIONAL PASS — adopt ZR with stop floor")
    print(f"  P1 PF={fmt_pf(v1_all['pf'])}, WR={v1_all['wr']:.1f}% — ZR baseline passes")
    print(f"  Narrow zone weakness detected — applying max(1.5x ZW, 120t) stop floor")
else:
    print("\n  RESULT: MIXED — manual decision required")
    print(f"  P1 PF={fmt_pf(v1_all['pf'])}, WR={v1_all['wr']:.1f}%")
    failing = [test for test, _, _, v in results if v not in ('PASS', 'ADVISORY')]
    if failing:
        print(f"  Issues: {', '.join(failing)}")

# Per-mode summary
print(f"\n  Mode breakdown:")
print(f"    CT: {v1_ct['n']} trades, WR={v1_ct['wr']:.1f}%, PF={fmt_pf(v1_ct['pf'])}")
print(f"    WT: {v1_wt['n']} trades, WR={v1_wt['wr']:.1f}%, PF={fmt_pf(v1_wt['pf'])}")
print(f"    CT 5t-limit losses: {ct_losses}")
