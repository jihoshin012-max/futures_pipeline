# archetype: zone_touch
"""
Zone-relative 2-leg exit simulation.
Compare zone-relative 2-leg vs deployed 2-leg baseline.

Deployed baseline (from user spec):
  CT: T1=40t(67%), T2=80t(33%), Stop=190t, TC=160
  WT: T1=60t(67%), T2=80t(33%), Stop=240t, TC=160

Zone-relative 2-leg:
  Leg 1 (67%): target = 0.5x zone_width, stop = 1.5x zone_width
  Leg 2 (33%): target = 1.0x zone_width, stop = 1.5x zone_width
"""
import pandas as pd
import numpy as np
import warnings
warnings.filterwarnings('ignore')

# ── Paths ──────────────────────────────────────────────────────────────
BASE = "c:/Projects/pipeline"
TRADE_PATH = f"{BASE}/stages/04-backtest/zone_touch/output/p2_trade_details.csv"
MERGED_P2A = f"{BASE}/stages/01-data/output/zone_prep/NQ_merged_P2a.csv"
MERGED_P2B = f"{BASE}/stages/01-data/output/zone_prep/NQ_merged_P2b.csv"
BARDATA_PATH = f"{BASE}/stages/01-data/output/zone_prep/NQ_bardata_P2.csv"
INVEST_CSV = f"{BASE}/stages/04-backtest/zone_touch/output/zone_touch_exit_investigation.csv"

TICK_SIZE = 0.25
COST_TICKS = 3

# ── Load data ──────────────────────────────────────────────────────────
print("Loading data...")
trades = pd.read_csv(TRADE_PATH)
invest = pd.read_csv(INVEST_CSV)
touches_a = pd.read_csv(MERGED_P2A)
touches_b = pd.read_csv(MERGED_P2B)
touches = pd.concat([touches_a, touches_b], ignore_index=True)

bardata = pd.read_csv(BARDATA_PATH, low_memory=False)
bardata.columns = [c.strip() for c in bardata.columns]
print(f"  Trades: {len(trades)}, Bars: {len(bardata)}")

# Parse datetimes
trades['dt'] = pd.to_datetime(trades['datetime'])
touches['dt'] = pd.to_datetime(touches['DateTime'])

# ── Join trades to touches (same logic as Part 1) ─────────────────────
trades['expected_appdir'] = np.where(trades['direction'] == 'LONG', -1, 1)
touch_cols_keep = ['ZoneWidthTicks', 'TouchSequence', 'SourceLabel',
                   'ZoneTop', 'ZoneBot', 'TouchType', 'RotBarIndex', 'CascadeState',
                   'Penetration', 'BarIndex', 'ApproachDir']

merged_parts = []
for period in ['P2a', 'P2b']:
    t_sub = trades[trades['period'] == period].copy().sort_values('dt').reset_index(drop=True)
    tc_sub = touches[(touches['Period'] == period) & (touches['RotBarIndex'] >= 0)].copy()
    tc_sub = tc_sub.sort_values('dt').reset_index(drop=True)
    if len(t_sub) == 0 or len(tc_sub) == 0:
        merged_parts.append(t_sub)
        continue
    merge_cols = list(dict.fromkeys(['dt'] + touch_cols_keep))
    result = pd.merge_asof(
        t_sub, tc_sub[merge_cols],
        on='dt', tolerance=pd.Timedelta('5min'), direction='nearest',
        suffixes=('', '_touch')
    )
    dir_mismatch = result['ApproachDir'].astype(float) != result['expected_appdir'].astype(float)
    if dir_mismatch.sum() > 0:
        for idx in result[dir_mismatch].index:
            trade_dt = result.loc[idx, 'dt']
            exp_dir = result.loc[idx, 'expected_appdir']
            candidates = tc_sub[
                (tc_sub['ApproachDir'] == exp_dir) &
                ((tc_sub['dt'] - trade_dt).abs() < pd.Timedelta('5min'))
            ]
            if len(candidates) > 0:
                best = candidates.loc[(candidates['dt'] - trade_dt).abs().idxmin()]
                for col in touch_cols_keep:
                    result.loc[idx, col] = best[col]
            else:
                for col in touch_cols_keep:
                    result.loc[idx, col] = np.nan
    merged_parts.append(result)

df = pd.concat(merged_parts, ignore_index=True).sort_values('trade_id').reset_index(drop=True)
print(f"  Matched RotBarIndex: {df['RotBarIndex'].notna().sum()}/{len(df)}")

# ── Bar data arrays for fast access ────────────────────────────────────
bar_open = bardata['Open'].values.astype(float)
bar_high = bardata['High'].values.astype(float)
bar_low = bardata['Low'].values.astype(float)
bar_close = bardata['Last'].values.astype(float)
n_bars = len(bardata)

# ── 2-leg simulation engine ───────────────────────────────────────────
def simulate_2leg(entry_bar_idx, entry_price, direction,
                  t1_ticks, t2_ticks, stop_ticks, timecap,
                  leg1_pct=0.67, leg2_pct=0.33):
    """
    Simulate 2-leg exit. Returns dict with:
      exit_type, raw_pnl_ticks, bars_held, t1_filled, t2_filled
    """
    t1_pts = t1_ticks * TICK_SIZE
    t2_pts = t2_ticks * TICK_SIZE
    stop_pts = stop_ticks * TICK_SIZE

    t1_filled = False
    end_bar = min(entry_bar_idx + timecap, n_bars)

    for b in range(entry_bar_idx, end_bar):
        bh = b - entry_bar_idx + 1

        if direction == 'LONG':
            adverse = entry_price - bar_low[b]
            favorable = bar_high[b] - entry_price
        else:
            adverse = bar_high[b] - entry_price
            favorable = bar_low[b] - entry_price
            favorable = entry_price - bar_low[b]  # favorable for SHORT = price drops

        # Check stop first (applies to full remaining position)
        if direction == 'LONG':
            if bar_low[b] <= entry_price - stop_pts:
                if t1_filled:
                    # Leg 1 already banked, leg 2 stopped
                    raw_pnl = leg1_pct * t1_ticks + leg2_pct * (-stop_ticks)
                    return {'exit_type': 'T1+STOP', 'raw_pnl': raw_pnl, 'bars_held': bh,
                            't1_filled': True, 't2_filled': False}
                else:
                    raw_pnl = -stop_ticks
                    return {'exit_type': 'STOP', 'raw_pnl': raw_pnl, 'bars_held': bh,
                            't1_filled': False, 't2_filled': False}
        else:  # SHORT
            if bar_high[b] >= entry_price + stop_pts:
                if t1_filled:
                    raw_pnl = leg1_pct * t1_ticks + leg2_pct * (-stop_ticks)
                    return {'exit_type': 'T1+STOP', 'raw_pnl': raw_pnl, 'bars_held': bh,
                            't1_filled': True, 't2_filled': False}
                else:
                    raw_pnl = -stop_ticks
                    return {'exit_type': 'STOP', 'raw_pnl': raw_pnl, 'bars_held': bh,
                            't1_filled': False, 't2_filled': False}

        # Check targets
        if direction == 'LONG':
            fav = bar_high[b] - entry_price
        else:
            fav = entry_price - bar_low[b]

        if not t1_filled and fav >= t1_pts:
            t1_filled = True
            # Check if T2 also hit on same bar
            if fav >= t2_pts:
                raw_pnl = leg1_pct * t1_ticks + leg2_pct * t2_ticks
                return {'exit_type': 'TARGET', 'raw_pnl': raw_pnl, 'bars_held': bh,
                        't1_filled': True, 't2_filled': True}

        if t1_filled and fav >= t2_pts:
            raw_pnl = leg1_pct * t1_ticks + leg2_pct * t2_ticks
            return {'exit_type': 'TARGET', 'raw_pnl': raw_pnl, 'bars_held': bh,
                    't1_filled': True, 't2_filled': True}

    # Timecap
    if end_bar > entry_bar_idx:
        if direction == 'LONG':
            close_pnl = (bar_close[end_bar - 1] - entry_price) / TICK_SIZE
        else:
            close_pnl = (entry_price - bar_close[end_bar - 1]) / TICK_SIZE

        if t1_filled:
            raw_pnl = leg1_pct * t1_ticks + leg2_pct * close_pnl
        else:
            raw_pnl = close_pnl
        return {'exit_type': 'TIMECAP', 'raw_pnl': raw_pnl, 'bars_held': timecap,
                't1_filled': t1_filled, 't2_filled': False}

    return {'exit_type': 'TIMECAP', 'raw_pnl': 0, 'bars_held': 0,
            't1_filled': False, 't2_filled': False}


# ── Single-leg simulation (for reference) ─────────────────────────────
def simulate_1leg(entry_bar_idx, entry_price, direction,
                  target_ticks, stop_ticks, timecap):
    """Single-leg exit simulation."""
    target_pts = target_ticks * TICK_SIZE
    stop_pts = stop_ticks * TICK_SIZE
    end_bar = min(entry_bar_idx + timecap, n_bars)

    for b in range(entry_bar_idx, end_bar):
        bh = b - entry_bar_idx + 1
        if direction == 'LONG':
            if bar_low[b] <= entry_price - stop_pts:
                return {'exit_type': 'STOP', 'raw_pnl': -stop_ticks, 'bars_held': bh}
            if bar_high[b] >= entry_price + target_pts:
                return {'exit_type': 'TARGET', 'raw_pnl': target_ticks, 'bars_held': bh}
        else:
            if bar_high[b] >= entry_price + stop_pts:
                return {'exit_type': 'STOP', 'raw_pnl': -stop_ticks, 'bars_held': bh}
            if bar_low[b] <= entry_price - target_pts:
                return {'exit_type': 'TARGET', 'raw_pnl': target_ticks, 'bars_held': bh}

    if end_bar > entry_bar_idx:
        if direction == 'LONG':
            close_pnl = (bar_close[end_bar - 1] - entry_price) / TICK_SIZE
        else:
            close_pnl = (entry_price - bar_close[end_bar - 1]) / TICK_SIZE
        return {'exit_type': 'TIMECAP', 'raw_pnl': close_pnl, 'bars_held': timecap}

    return {'exit_type': 'TIMECAP', 'raw_pnl': 0, 'bars_held': 0}


# ══════════════════════════════════════════════════════════════════════
# Run simulations
# ══════════════════════════════════════════════════════════════════════

# Prepare entry bar indices
df['entry_bar_idx'] = df['RotBarIndex'].apply(lambda x: int(x) + 1 if pd.notna(x) and x >= 0 else -1)
valid = df[df['entry_bar_idx'] >= 0].copy()

print(f"\nValid trades for simulation: {len(valid)}/{len(df)}")

# ── A) Deployed 2-leg baseline ────────────────────────────────────────
print("\n" + "="*70)
print("DEPLOYED 2-LEG BASELINE")
print("  CT: T1=40t(67%), T2=80t(33%), Stop=190t, TC=160")
print("  WT: T1=60t(67%), T2=80t(33%), Stop=240t, TC=160")
print("="*70)

baseline_results = []
for idx in valid.index:
    entry_bar = valid.loc[idx, 'entry_bar_idx']
    entry_price = valid.loc[idx, 'entry_price']
    direction = valid.loc[idx, 'direction']
    trend = valid.loc[idx, 'trend_label']

    if trend == 'CT':
        res = simulate_2leg(entry_bar, entry_price, direction,
                           t1_ticks=40, t2_ticks=80, stop_ticks=190, timecap=160)
    else:  # WT
        res = simulate_2leg(entry_bar, entry_price, direction,
                           t1_ticks=60, t2_ticks=80, stop_ticks=240, timecap=160)

    res['trade_id'] = valid.loc[idx, 'trade_id']
    res['trend_label'] = trend
    res['net_pnl'] = res['raw_pnl'] - COST_TICKS
    baseline_results.append(res)

bl = pd.DataFrame(baseline_results)

def report_stats(results_df, label):
    wins = results_df[results_df['net_pnl'] > 0]
    losses = results_df[results_df['net_pnl'] <= 0]
    gross_win = wins['net_pnl'].sum()
    gross_loss = losses['net_pnl'].abs().sum()
    pf = gross_win / gross_loss if gross_loss > 0 else float('inf')
    wr = len(wins) / len(results_df) * 100 if len(results_df) > 0 else 0
    ev = results_df['net_pnl'].mean()
    total = results_df['net_pnl'].sum()
    t1_rate = results_df['t1_filled'].mean() * 100 if 't1_filled' in results_df else 0
    print(f"  {label:35s} | n={len(results_df):4d} | WR={wr:5.1f}% | PF={pf:7.2f} | EV={ev:7.1f} | Total={total:9.1f} | T1%={t1_rate:5.1f}%")

print("\nDeployed 2-leg baseline:")
report_stats(bl, "ALL")
report_stats(bl[bl['trend_label']=='CT'], "CT")
report_stats(bl[bl['trend_label']=='WT'], "WT")

# Exit type breakdown
print("\n  Exit type breakdown:")
for et in bl['exit_type'].unique():
    sub = bl[bl['exit_type']==et]
    print(f"    {et:15s}: {len(sub):4d} trades, mean net PnL = {sub['net_pnl'].mean():7.1f}")

# ── B) Part 1 single-leg baseline (for comparison) ────────────────────
print("\n" + "="*70)
print("PART 1 SINGLE-LEG BASELINE (Stop=190, Target=80, TC=120)")
print("="*70)

sl_results = []
for idx in valid.index:
    entry_bar = valid.loc[idx, 'entry_bar_idx']
    entry_price = valid.loc[idx, 'entry_price']
    direction = valid.loc[idx, 'direction']
    trend = valid.loc[idx, 'trend_label']

    res = simulate_1leg(entry_bar, entry_price, direction,
                       target_ticks=80, stop_ticks=190, timecap=120)
    res['trade_id'] = valid.loc[idx, 'trade_id']
    res['trend_label'] = trend
    res['net_pnl'] = res['raw_pnl'] - COST_TICKS
    sl_results.append(res)

sl = pd.DataFrame(sl_results)
report_stats(sl, "ALL (single-leg 190/80 TC=120)")
report_stats(sl[sl['trend_label']=='CT'], "CT")
report_stats(sl[sl['trend_label']=='WT'], "WT")

# ── C) Zone-relative 2-leg ────────────────────────────────────────────
print("\n" + "="*70)
print("ZONE-RELATIVE 2-LEG")
print("  Leg 1 (67%): target = 0.5x zone_width, stop = 1.5x zone_width")
print("  Leg 2 (33%): target = 1.0x zone_width, stop = 1.5x zone_width")
print("  TC = 160 (matching deployed)")
print("="*70)

zr_results = []
for idx in valid.index:
    entry_bar = valid.loc[idx, 'entry_bar_idx']
    entry_price = valid.loc[idx, 'entry_price']
    direction = valid.loc[idx, 'direction']
    trend = valid.loc[idx, 'trend_label']
    zone_w = valid.loc[idx, 'ZoneWidthTicks']

    if pd.isna(zone_w) or zone_w <= 0:
        continue

    t1 = zone_w * 0.5
    t2 = zone_w * 1.0
    stop = zone_w * 1.5

    res = simulate_2leg(entry_bar, entry_price, direction,
                       t1_ticks=t1, t2_ticks=t2, stop_ticks=stop, timecap=160)
    res['trade_id'] = valid.loc[idx, 'trade_id']
    res['trend_label'] = trend
    res['zone_width'] = zone_w
    res['net_pnl'] = res['raw_pnl'] - COST_TICKS
    res['t1_ticks'] = t1
    res['t2_ticks'] = t2
    res['stop_ticks'] = stop
    zr_results.append(res)

zr = pd.DataFrame(zr_results)
print("\nZone-relative 2-leg (0.5x/1.0x targets, 1.5x stop):")
report_stats(zr, "ALL")
report_stats(zr[zr['trend_label']=='CT'], "CT")
report_stats(zr[zr['trend_label']=='WT'], "WT")

# Exit type breakdown
print("\n  Exit type breakdown:")
for et in zr['exit_type'].unique():
    sub = zr[zr['exit_type']==et]
    print(f"    {et:15s}: {len(sub):4d} trades, mean net PnL = {sub['net_pnl'].mean():7.1f}")

# Average stop/target in ticks
print(f"\n  Average T1: {zr['t1_ticks'].mean():.0f}t, T2: {zr['t2_ticks'].mean():.0f}t, Stop: {zr['stop_ticks'].mean():.0f}t")

# ── D) Zone-relative 2-leg by zone width bin ──────────────────────────
print("\n  By zone width bin:")
zr['zone_width_bin'] = pd.cut(zr['zone_width'], bins=[0,50,100,150,200,float('inf')],
                               labels=['0-50t','50-100t','100-150t','150-200t','200t+'], right=False)
for zw_bin in ['0-50t','50-100t','100-150t','150-200t','200t+']:
    sub = zr[zr['zone_width_bin']==zw_bin]
    if len(sub) > 0:
        report_stats(sub, f"  {zw_bin}")

# ── E) Sweep of zone-relative multipliers (2-leg) ─────────────────────
print("\n" + "="*70)
print("ZONE-RELATIVE 2-LEG SWEEP")
print("  Format: T1=Ax, T2=Bx, Stop=Cx (all × zone_width)")
print("="*70)

combos = [
    # (t1_mult, t2_mult, stop_mult, label)
    (0.25, 0.5,  1.0,  "0.25x/0.50x/1.0x"),
    (0.25, 0.5,  1.5,  "0.25x/0.50x/1.5x"),
    (0.25, 0.75, 1.5,  "0.25x/0.75x/1.5x"),
    (0.25, 1.0,  1.5,  "0.25x/1.00x/1.5x"),
    (0.50, 0.75, 1.5,  "0.50x/0.75x/1.5x"),
    (0.50, 1.0,  1.5,  "0.50x/1.00x/1.5x"),
    (0.50, 1.0,  2.0,  "0.50x/1.00x/2.0x"),
    (0.50, 1.5,  1.5,  "0.50x/1.50x/1.5x"),
    (0.50, 1.5,  2.0,  "0.50x/1.50x/2.0x"),
    (0.75, 1.0,  1.5,  "0.75x/1.00x/1.5x"),
    (0.75, 1.5,  2.0,  "0.75x/1.50x/2.0x"),
    (1.0,  1.5,  2.0,  "1.00x/1.50x/2.0x"),
    (1.0,  2.0,  2.5,  "1.00x/2.00x/2.5x"),
]

print(f"\n  {'T1/T2/Stop':22s} | {'n':5s} | {'WR':6s} | {'PF':8s} | {'EV':8s} | {'Total':10s} | {'T1%':6s} | {'AvgT1':6s} | {'AvgT2':6s} | {'AvgStp':7s}")
print("  " + "-"*110)

for t1m, t2m, sm, label in combos:
    total_win = 0
    total_loss = 0
    wins = 0
    n = 0
    t1_fills = 0
    t1_sum = 0
    t2_sum = 0
    s_sum = 0

    for idx in valid.index:
        entry_bar = valid.loc[idx, 'entry_bar_idx']
        entry_price = valid.loc[idx, 'entry_price']
        direction = valid.loc[idx, 'direction']
        zone_w = valid.loc[idx, 'ZoneWidthTicks']
        if pd.isna(zone_w) or zone_w <= 0:
            continue

        t1 = zone_w * t1m
        t2 = zone_w * t2m
        stop = zone_w * sm
        t1_sum += t1
        t2_sum += t2
        s_sum += stop

        res = simulate_2leg(entry_bar, entry_price, direction,
                           t1_ticks=t1, t2_ticks=t2, stop_ticks=stop, timecap=160)
        net = res['raw_pnl'] - COST_TICKS
        n += 1
        if res['t1_filled']:
            t1_fills += 1
        if net > 0:
            total_win += net
            wins += 1
        else:
            total_loss += abs(net)

    pf = total_win / total_loss if total_loss > 0 else float('inf')
    wr = wins / n * 100 if n > 0 else 0
    ev = (total_win - total_loss) / n if n > 0 else 0
    total = total_win - total_loss
    t1r = t1_fills / n * 100 if n > 0 else 0

    print(f"  {label:22s} | {n:5d} | {wr:5.1f}% | {pf:8.2f} | {ev:8.1f} | {total:10.1f} | {t1r:5.1f}% | {t1_sum/n:5.0f}t | {t2_sum/n:5.0f}t | {s_sum/n:6.0f}t")

# ── F) Zone-relative 2-leg sweep split by CT/WT ──────────────────────
for trend in ['CT', 'WT']:
    print(f"\n  {trend} only:")
    trend_valid = valid[valid['trend_label'] == trend]
    print(f"  {'T1/T2/Stop':22s} | {'n':5s} | {'WR':6s} | {'PF':8s} | {'EV':8s} | {'Total':10s}")
    print("  " + "-"*70)

    for t1m, t2m, sm, label in combos:
        total_win = 0
        total_loss = 0
        wins = 0
        n = 0

        for idx in trend_valid.index:
            entry_bar = valid.loc[idx, 'entry_bar_idx']
            entry_price = valid.loc[idx, 'entry_price']
            direction = valid.loc[idx, 'direction']
            zone_w = valid.loc[idx, 'ZoneWidthTicks']
            if pd.isna(zone_w) or zone_w <= 0:
                continue

            t1 = zone_w * t1m
            t2 = zone_w * t2m
            stop = zone_w * sm

            res = simulate_2leg(entry_bar, entry_price, direction,
                               t1_ticks=t1, t2_ticks=t2, stop_ticks=stop, timecap=160)
            net = res['raw_pnl'] - COST_TICKS
            n += 1
            if net > 0:
                total_win += net
                wins += 1
            else:
                total_loss += abs(net)

        pf = total_win / total_loss if total_loss > 0 else float('inf')
        wr = wins / n * 100 if n > 0 else 0
        ev = (total_win - total_loss) / n if n > 0 else 0
        total = total_win - total_loss

        print(f"  {label:22s} | {n:5d} | {wr:5.1f}% | {pf:8.2f} | {ev:8.1f} | {total:10.1f}")


# ── G) Head-to-head comparison table ──────────────────────────────────
print("\n" + "="*70)
print("HEAD-TO-HEAD: Deployed 2-Leg vs Zone-Relative 2-Leg")
print("="*70)

print(f"\n  {'Config':40s} | {'n':5s} | {'WR':6s} | {'PF':8s} | {'EV':8s} | {'Total':10s}")
print("  " + "-"*80)

# Deployed baseline
bl_wins = bl[bl['net_pnl'] > 0]
bl_losses = bl[bl['net_pnl'] <= 0]
bl_gw = bl_wins['net_pnl'].sum()
bl_gl = bl_losses['net_pnl'].abs().sum()
bl_pf = bl_gw / bl_gl if bl_gl > 0 else float('inf')
bl_wr = len(bl_wins) / len(bl) * 100
bl_ev = bl['net_pnl'].mean()
bl_total = bl['net_pnl'].sum()
print(f"  {'Deployed 2L (40/80 CT, 60/80 WT, 190/240)':40s} | {len(bl):5d} | {bl_wr:5.1f}% | {bl_pf:8.2f} | {bl_ev:8.1f} | {bl_total:10.1f}")

# Zone-relative
zr_wins = zr[zr['net_pnl'] > 0]
zr_losses = zr[zr['net_pnl'] <= 0]
zr_gw = zr_wins['net_pnl'].sum()
zr_gl = zr_losses['net_pnl'].abs().sum()
zr_pf = zr_gw / zr_gl if zr_gl > 0 else float('inf')
zr_wr = len(zr_wins) / len(zr) * 100
zr_ev = zr['net_pnl'].mean()
zr_total = zr['net_pnl'].sum()
print(f"  {'Zone-rel 2L (0.5x/1.0x/1.5x, TC=160)':40s} | {len(zr):5d} | {zr_wr:5.1f}% | {zr_pf:8.2f} | {zr_ev:8.1f} | {zr_total:10.1f}")

# Part 1 single-leg for context
sl_wins = sl[sl['net_pnl'] > 0]
sl_losses = sl[sl['net_pnl'] <= 0]
sl_gw = sl_wins['net_pnl'].sum()
sl_gl = sl_losses['net_pnl'].abs().sum()
sl_pf = sl_gw / sl_gl if sl_gl > 0 else float('inf')
sl_wr = len(sl_wins) / len(sl) * 100
sl_ev = sl['net_pnl'].mean()
sl_total = sl['net_pnl'].sum()
print(f"  {'Part1 1L (80t tgt, 190 stp, TC=120)':40s} | {len(sl):5d} | {sl_wr:5.1f}% | {sl_pf:8.2f} | {sl_ev:8.1f} | {sl_total:10.1f}")

# Per-trend breakdown
for trend in ['CT', 'WT']:
    print(f"\n  {trend}:")
    for name, rdf in [("Deployed 2L", bl), ("Zone-rel 2L", zr), ("Part1 1L", sl)]:
        sub = rdf[rdf['trend_label']==trend]
        if len(sub) == 0:
            continue
        w = sub[sub['net_pnl'] > 0]
        l = sub[sub['net_pnl'] <= 0]
        gw = w['net_pnl'].sum()
        gl = l['net_pnl'].abs().sum()
        pf = gw / gl if gl > 0 else float('inf')
        wr = len(w) / len(sub) * 100
        ev = sub['net_pnl'].mean()
        total = sub['net_pnl'].sum()
        print(f"    {name:38s} | {len(sub):5d} | {wr:5.1f}% | {pf:8.2f} | {ev:8.1f} | {total:10.1f}")

print("\nDone.")
