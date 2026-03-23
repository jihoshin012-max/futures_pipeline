# archetype: zone_touch
"""
Zone Touch Exit Investigation — Part 1 of 3
Section 1: Battleground Profiling (50-150t MAE)
Section 2: Zone-Width-Relative Exits
Output: zone_touch_exit_investigation.csv (312 rows, trade_id join key)
"""
import pandas as pd
import numpy as np
from datetime import time as dtime
import warnings
warnings.filterwarnings('ignore')

# ── Paths ──────────────────────────────────────────────────────────────
BASE = "c:/Projects/pipeline"
TRADE_PATH = f"{BASE}/stages/04-backtest/zone_touch/output/p2_trade_details.csv"
MERGED_P2A = f"{BASE}/stages/01-data/output/zone_prep/NQ_merged_P2a.csv"
MERGED_P2B = f"{BASE}/stages/01-data/output/zone_prep/NQ_merged_P2b.csv"
BARDATA_PATH = f"{BASE}/stages/01-data/output/zone_prep/NQ_bardata_P2.csv"
OUTPUT_PATH = f"{BASE}/stages/04-backtest/zone_touch/output/zone_touch_exit_investigation.csv"

TICK_SIZE = 0.25  # NQ: 1 tick = 0.25 points
COST_TICKS = 3
# Frozen params for seg3_ModeB (all 312 trades)
FIXED_STOP = 190
FIXED_TARGET = 80
FIXED_TIMECAP = 120

# ── Load data ──────────────────────────────────────────────────────────
print("Loading data...")
trades = pd.read_csv(TRADE_PATH)
touches_a = pd.read_csv(MERGED_P2A)
touches_b = pd.read_csv(MERGED_P2B)
touches = pd.concat([touches_a, touches_b], ignore_index=True)

# Strip column names in bar data (leading spaces)
bardata = pd.read_csv(BARDATA_PATH, low_memory=False)
bardata.columns = [c.strip() for c in bardata.columns]
print(f"  Trades: {len(trades)}, Touches: {len(touches)}, Bars: {len(bardata)}")

# ── Parse datetimes ────────────────────────────────────────────────────
trades['dt'] = pd.to_datetime(trades['datetime'])
touches['dt'] = pd.to_datetime(touches['DateTime'])

# Bar data datetime
bardata['dt'] = pd.to_datetime(
    bardata['Date'].str.strip() + ' ' + bardata['Time'].str.strip(),
    format='mixed', dayfirst=False
)

# ── Join trades to touches ─────────────────────────────────────────────
# Strategy: merge_asof with direction filtering, 5-minute tolerance
print("Joining trades to touches...")

# Map trade direction to expected ApproachDir: LONG → -1 (demand), SHORT → 1 (supply)
trades['expected_appdir'] = np.where(trades['direction'] == 'LONG', -1, 1)

touch_cols_keep = ['ZoneWidthTicks', 'TouchSequence', 'SourceLabel',
                   'ZoneTop', 'ZoneBot', 'TouchType', 'RotBarIndex', 'CascadeState',
                   'Penetration', 'BarIndex', 'ApproachDir']

# For each period, do a merge_asof by sorted datetime
merged_parts = []
for period in ['P2a', 'P2b']:
    t_sub = trades[trades['period'] == period].copy().sort_values('dt').reset_index(drop=True)
    # Filter touches to matching period and valid RotBarIndex
    tc_sub = touches[(touches['Period'] == period) & (touches['RotBarIndex'] >= 0)].copy()
    tc_sub = tc_sub.sort_values('dt').reset_index(drop=True)

    if len(t_sub) == 0 or len(tc_sub) == 0:
        merged_parts.append(t_sub)
        continue

    # merge_asof: match nearest touch within 5 minutes
    merge_cols = list(dict.fromkeys(['dt'] + touch_cols_keep))  # deduplicate
    result = pd.merge_asof(
        t_sub, tc_sub[merge_cols],
        on='dt', tolerance=pd.Timedelta('5min'), direction='nearest',
        suffixes=('', '_touch')
    )

    # Validate direction match; clear mismatches
    dir_mismatch = result['ApproachDir'].astype(float) != result['expected_appdir'].astype(float)
    if dir_mismatch.sum() > 0:
        # For mismatches, try to find correct touch manually
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

merged = pd.concat(merged_parts, ignore_index=True)
# Restore original order by trade_id
merged = merged.sort_values('trade_id').reset_index(drop=True)

unmatched = merged['ZoneWidthTicks'].isna().sum()
print(f"  Matched: {len(merged) - unmatched}/{len(merged)}")
if unmatched > 0:
    unmatched_ids = merged[merged['ZoneWidthTicks'].isna()]['trade_id'].tolist()
    print(f"  Unmatched trade_ids: {unmatched_ids[:20]}{'...' if len(unmatched_ids) > 20 else ''}")

assert len(merged) == 312, f"Expected 312 rows, got {len(merged)}"

# ── Compute features ──────────────────────────────────────────────────
df = merged.copy()

# Basic trade features
df['WL'] = np.where(df['pnl_ticks'] > 0, 'W', 'L')
df['mode'] = df['seg_model_group'].str.extract(r'(Mode[A-Z]|Cluster\d+)')
df['mae'] = df['mae_ticks'].astype(float)
df['mfe'] = df['mfe_ticks'].astype(float)
df['pnl'] = df['pnl_ticks'].astype(float)

# Zone width
df['zone_width'] = df['ZoneWidthTicks'].astype(float)
df['zone_width_ratio'] = df['mae'] / df['zone_width'].replace(0, np.nan)

# Score features
df['score'] = df['acal_score'].astype(float)
# score_margin already exists in trade details

# Session: RTH 09:30-16:15 ET, ETH otherwise
df['hour'] = df['dt'].dt.hour
df['minute'] = df['dt'].dt.minute
df['time_decimal'] = df['hour'] + df['minute'] / 60.0
df['session'] = np.where(
    (df['time_decimal'] >= 9.5) & (df['time_decimal'] < 16.25),
    'RTH', 'ETH'
)

# Touch sequence from merged data
df['touch_sequence'] = df['TouchSequence'].astype(float)

# Cascade state (already in F04_CascadeState)
df['cascade_state'] = df['F04_CascadeState']

# Source label (timeframe) from merged data
df['source_label'] = df['SourceLabel']

# Extract TF minutes from source label
tf_map = {'15m': 15, '30m': 30, '60m': 60, '90m': 90, '120m': 120,
           '240m': 240, '360m': 360, '480m': 480, '720m': 720}
df['tf_minutes'] = df['source_label'].map(tf_map)

# Crossed opposite edge
# LONG at demand zone: adverse goes DOWN, opposite edge = ZoneBot
# SHORT at supply zone: adverse goes UP, opposite edge = ZoneTop
df['mae_points'] = df['mae'] * TICK_SIZE

df['crossed_opposite_edge'] = 'N'
df['depth_past_opposite_edge'] = 0.0

long_mask = df['direction'] == 'LONG'
short_mask = df['direction'] == 'SHORT'

# LONG: crossed if entry - mae_points < ZoneBot
long_adverse_price = df.loc[long_mask, 'entry_price'] - df.loc[long_mask, 'mae_points']
long_crossed = long_adverse_price < df.loc[long_mask, 'ZoneBot']
df.loc[long_mask & long_crossed.reindex(df.index, fill_value=False), 'crossed_opposite_edge'] = 'Y'
df.loc[long_mask, 'depth_past_opposite_edge'] = np.maximum(
    0, (df.loc[long_mask, 'ZoneBot'] - long_adverse_price)
).values / TICK_SIZE

# SHORT: crossed if entry + mae_points > ZoneTop
short_adverse_price = df.loc[short_mask, 'entry_price'] + df.loc[short_mask, 'mae_points']
short_crossed = short_adverse_price > df.loc[short_mask, 'ZoneTop']
df.loc[short_mask & short_crossed.reindex(df.index, fill_value=False), 'crossed_opposite_edge'] = 'Y'
df.loc[short_mask, 'depth_past_opposite_edge'] = np.maximum(
    0, (short_adverse_price - df.loc[short_mask, 'ZoneTop'])
).values / TICK_SIZE

# ── Bars to max penetration (requires bar data walk) ───────────────────
print("Computing bars_to_max_penetration from bar data...")

# Build bar data arrays for fast access
bar_open = bardata['Open'].values.astype(float)
bar_high = bardata['High'].values.astype(float)
bar_low = bardata['Low'].values.astype(float)
bar_close = bardata['Last'].values.astype(float)
n_bars = len(bardata)

df['bars_to_max_penetration'] = np.nan
df['penetration_speed'] = np.nan

# Use RotBarIndex to find entry bar
for idx in df.index:
    rot_idx = df.loc[idx, 'RotBarIndex']
    if pd.isna(rot_idx) or rot_idx < 0:
        continue
    entry_bar = int(rot_idx) + 1  # Entry at next bar open
    if entry_bar >= n_bars:
        continue

    entry_price = df.loc[idx, 'entry_price']
    direction = df.loc[idx, 'direction']
    known_mae = df.loc[idx, 'mae']
    bars_held = int(df.loc[idx, 'bars_held'])

    max_adverse = 0.0
    bars_to_max = 0

    end_bar = min(entry_bar + bars_held + 1, n_bars)

    for b in range(entry_bar, end_bar):
        if direction == 'LONG':
            adverse = (entry_price - bar_low[b]) / TICK_SIZE
        else:
            adverse = (bar_high[b] - entry_price) / TICK_SIZE

        if adverse > max_adverse:
            max_adverse = adverse
            bars_to_max = b - entry_bar + 1

    df.loc[idx, 'bars_to_max_penetration'] = bars_to_max
    if bars_to_max > 0:
        df.loc[idx, 'penetration_speed'] = known_mae / bars_to_max

print("  Done.")

# ── Battleground flag ──────────────────────────────────────────────────
df['is_battleground'] = (df['mae'] >= 50) & (df['mae'] <= 150)
bg = df[df['is_battleground']].copy()
print(f"\nBattleground trades (MAE 50-150t): {len(bg)}")
print(f"  Winners: {(bg['WL'] == 'W').sum()}, Losers: {(bg['WL'] == 'L').sum()}")

# ══════════════════════════════════════════════════════════════════════
# SECTION 1: BATTLEGROUND PROFILING
# ══════════════════════════════════════════════════════════════════════
print("\n" + "="*70)
print("SECTION 1: BATTLEGROUND PROFILING (MAE 50-150t)")
print("="*70)

# 1A) Per-trade feature table (printed for battleground trades)
bg_cols = ['trade_id', 'mode', 'direction', 'WL', 'pnl', 'mae', 'mfe',
           'zone_width', 'zone_width_ratio', 'score', 'score_margin',
           'trend_label', 'session', 'touch_sequence', 'cascade_state',
           'source_label', 'crossed_opposite_edge', 'depth_past_opposite_edge',
           'bars_to_max_penetration', 'penetration_speed', 'bars_held', 'exit_type']

print(f"\n1A) Per-trade feature table ({len(bg)} trades):")
print(bg[bg_cols].to_string(index=False, max_rows=None))

# 1B) Loser vs Winner comparison
print(f"\n1B) Loser vs Winner Comparison:")
winners = bg[bg['WL'] == 'W']
losers = bg[bg['WL'] == 'L']
n_w, n_l = len(winners), len(losers)

def pct_val(series, val):
    """Percentage of series equal to val"""
    return f"{(series == val).sum()}/{len(series)} ({(series == val).mean()*100:.0f}%)"

def compare(metric_name, w_val, l_val, sig_note=""):
    print(f"  {metric_name:35s} | W(n={n_w}): {str(w_val):20s} | L(n={n_l}): {str(l_val):20s} | {sig_note}")

print(f"\n  {'Metric':35s} | {'Winners (n='+str(n_w)+')':20s} | {'Losers (n='+str(n_l)+')':20s} | Significant?")
print("  " + "-"*100)

# Mean zone width
w_zw, l_zw = winners['zone_width'].mean(), losers['zone_width'].mean()
compare("Mean zone width", f"{w_zw:.1f}", f"{l_zw:.1f}",
        "YES" if abs(w_zw - l_zw) > 30 else "NO")

# Mean zone_width_ratio
w_zwr, l_zwr = winners['zone_width_ratio'].mean(), losers['zone_width_ratio'].mean()
compare("Mean zone_width_ratio", f"{w_zwr:.2f}", f"{l_zwr:.2f}",
        "YES" if abs(w_zwr - l_zwr) > 0.3 else "NO")

# Mean score margin
w_sm, l_sm = winners['score_margin'].mean(), losers['score_margin'].mean()
compare("Mean score margin", f"{w_sm:.2f}", f"{l_sm:.2f}",
        "YES" if abs(w_sm - l_sm) > 1.0 else "NO")

# % RTH vs ETH
w_rth = f"{(winners['session']=='RTH').mean()*100:.0f}%"
l_rth = f"{(losers['session']=='RTH').mean()*100:.0f}%"
compare("% RTH", w_rth, l_rth,
        "YES" if abs((winners['session']=='RTH').mean() - (losers['session']=='RTH').mean()) > 0.2 else "NO")

# Mean touch_sequence
w_ts, l_ts = winners['touch_sequence'].mean(), losers['touch_sequence'].mean()
compare("Mean touch_sequence", f"{w_ts:.1f}", f"{l_ts:.1f}",
        "YES" if abs(w_ts - l_ts) > 2 else "NO")

# % PRIOR_HELD
w_ph = f"{(winners['cascade_state']=='PRIOR_HELD').mean()*100:.0f}%"
l_ph = f"{(losers['cascade_state']=='PRIOR_HELD').mean()*100:.0f}%"
compare("% PRIOR_HELD", w_ph, l_ph,
        "YES" if abs((winners['cascade_state']=='PRIOR_HELD').mean() - (losers['cascade_state']=='PRIOR_HELD').mean()) > 0.2 else "NO")

# % crossed opposite edge
w_co = f"{(winners['crossed_opposite_edge']=='Y').mean()*100:.0f}%"
l_co = f"{(losers['crossed_opposite_edge']=='Y').mean()*100:.0f}%"
compare("% crossed opposite edge", w_co, l_co,
        "YES" if abs((winners['crossed_opposite_edge']=='Y').mean() - (losers['crossed_opposite_edge']=='Y').mean()) > 0.2 else "NO")

# Mean penetration speed
w_ps, l_ps = winners['penetration_speed'].mean(), losers['penetration_speed'].mean()
compare("Mean penetration_speed", f"{w_ps:.1f}", f"{l_ps:.1f}",
        "YES" if abs(w_ps - l_ps) > 10 else "NO")

# Mean bars_to_max_pen
w_bm, l_bm = winners['bars_to_max_penetration'].mean(), losers['bars_to_max_penetration'].mean()
compare("Mean bars_to_max_pen", f"{w_bm:.1f}", f"{l_bm:.1f}",
        "YES" if abs(w_bm - l_bm) > 5 else "NO")

# % CT vs WT
w_ct = f"{(winners['trend_label']=='CT').mean()*100:.0f}%"
l_ct = f"{(losers['trend_label']=='CT').mean()*100:.0f}%"
compare("% CT", w_ct, l_ct,
        "YES" if abs((winners['trend_label']=='CT').mean() - (losers['trend_label']=='CT').mean()) > 0.2 else "NO")

# Mean TF (minutes)
w_tf, l_tf = winners['tf_minutes'].mean(), losers['tf_minutes'].mean()
compare("Mean TF (minutes)", f"{w_tf:.0f}", f"{l_tf:.0f}",
        "YES" if abs(w_tf - l_tf) > 30 else "NO")

# 1C) Feature thresholds that catch all 9 losers
print(f"\n1C) Feature thresholds to catch all {n_l} losers:")
print(f"  {'Feature':35s} | {'Threshold':20s} | {'Losers caught':15s} | {'Winners caught (FP)':20s}")
print("  " + "-"*100)

def find_threshold(feature, direction='below'):
    """Find threshold that catches all losers, count winner false positives.
    direction='below': losers have LOWER values (threshold = min loser value, catch all below)
    direction='above': losers have HIGHER values (threshold = max loser value, catch all above)
    """
    l_vals = losers[feature].dropna()
    w_vals = winners[feature].dropna()
    if len(l_vals) == 0:
        return None, 0, 0
    if direction == 'below':
        # All losers below threshold → threshold = max loser value
        thresh = l_vals.max()
        fp = (w_vals <= thresh).sum()
    else:
        # All losers above threshold → threshold = min loser value
        thresh = l_vals.min()
        fp = (w_vals >= thresh).sum()
    return thresh, n_l, fp

features_to_test = [
    ('zone_width', 'above', 'zone_width >= '),
    ('zone_width_ratio', 'above', 'zone_width_ratio >= '),
    ('score_margin', 'below', 'score_margin <= '),
    ('touch_sequence', 'above', 'touch_seq >= '),
    ('penetration_speed', 'above', 'pen_speed >= '),
    ('bars_to_max_penetration', 'below', 'bars_to_max <= '),
    ('tf_minutes', 'above', 'tf_minutes >= '),
    ('depth_past_opposite_edge', 'above', 'depth_past >= '),
]

for feat, direction, label in features_to_test:
    thresh, caught, fp = find_threshold(feat, direction)
    if thresh is not None:
        pct_fp = fp / n_w * 100 if n_w > 0 else 0
        print(f"  {label + f'{thresh:.1f}':35s} | {str(thresh):20s} | {caught}/{n_l}           | {fp}/{n_w} ({pct_fp:.0f}%)")

# Also test categorical features
for cat_feat, cat_vals, label in [
    ('cascade_state', losers['cascade_state'].unique(), 'cascade_state in '),
    ('session', losers['session'].unique(), 'session == '),
    ('trend_label', losers['trend_label'].unique(), 'trend_label in '),
]:
    caught = (losers[cat_feat].isin(cat_vals)).sum()
    fp = (winners[cat_feat].isin(cat_vals)).sum()
    pct_fp = fp / n_w * 100 if n_w > 0 else 0
    vals_str = str(list(cat_vals))
    print(f"  {label + vals_str:35s} | {'all':20s} | {caught}/{n_l}           | {fp}/{n_w} ({pct_fp:.0f}%)")


# ══════════════════════════════════════════════════════════════════════
# SECTION 2: ZONE-WIDTH-RELATIVE EXITS
# ══════════════════════════════════════════════════════════════════════
print("\n" + "="*70)
print("SECTION 2: ZONE-WIDTH-RELATIVE EXITS")
print("="*70)

# 2A) Zone width distribution
print("\n2A) Zone Width Distribution (all 312 trades):")
bins = [0, 50, 100, 150, 200, float('inf')]
labels = ['0-50t', '50-100t', '100-150t', '150-200t', '200t+']
df['zone_width_bin'] = pd.cut(df['zone_width'], bins=bins, labels=labels, right=False)

zw_dist = df.groupby('zone_width_bin', observed=True).agg(
    count=('trade_id', 'count'),
    mean_pnl=('pnl', 'mean')
).reset_index()
zw_dist['pct'] = (zw_dist['count'] / zw_dist['count'].sum() * 100).round(1)

print(f"\n  {'Zone width bin':15s} | {'Count':6s} | {'%':6s} | {'Mean PnL':10s}")
print("  " + "-"*50)
for _, row in zw_dist.iterrows():
    print(f"  {str(row['zone_width_bin']):15s} | {row['count']:6d} | {row['pct']:5.1f}% | {row['mean_pnl']:10.1f}")

# ── Bar-level exit simulation engine ───────────────────────────────────
def simulate_exit(entry_bar_idx, entry_price, direction, stop_ticks, target_ticks, time_cap):
    """Simulate a trade with given stop/target/timecap. Returns (exit_type, pnl_ticks, bars_held)."""
    stop_pts = stop_ticks * TICK_SIZE
    target_pts = target_ticks * TICK_SIZE

    end_bar = min(entry_bar_idx + time_cap, n_bars)

    for b in range(entry_bar_idx, end_bar):
        if direction == 'LONG':
            # Check stop (Low <= entry - stop)
            if bar_low[b] <= entry_price - stop_pts:
                return 'STOP', -stop_ticks, b - entry_bar_idx + 1
            # Check target (High >= entry + target)
            if bar_high[b] >= entry_price + target_pts:
                return 'TARGET', target_ticks, b - entry_bar_idx + 1
        else:  # SHORT
            # Check stop (High >= entry + stop)
            if bar_high[b] >= entry_price + stop_pts:
                return 'STOP', -stop_ticks, b - entry_bar_idx + 1
            # Check target (Low <= entry - target)
            if bar_low[b] <= entry_price - target_pts:
                return 'TARGET', target_ticks, b - entry_bar_idx + 1

    # Time cap: exit at close of last bar
    if end_bar > entry_bar_idx:
        if direction == 'LONG':
            pnl = (bar_close[end_bar - 1] - entry_price) / TICK_SIZE
        else:
            pnl = (entry_price - bar_close[end_bar - 1]) / TICK_SIZE
        return 'TIMECAP', pnl, time_cap

    return 'TIMECAP', 0, 0

# Precompute entry bar indices for all trades
df['entry_bar_idx'] = np.nan
for idx in df.index:
    rot_idx = df.loc[idx, 'RotBarIndex']
    if pd.notna(rot_idx) and rot_idx >= 0:
        df.loc[idx, 'entry_bar_idx'] = int(rot_idx) + 1

# 2B) Zone-relative STOP sweep (fixed target = 80t for all since all are ModeB)
print("\n2B) Zone-Relative Stop Sweep (fixed target=80t):")
print("  NOTE: All 312 trades use seg3_ModeB: stop=190, target=80, timecap=120")

stop_multipliers = [1.0, 1.5, 2.0, 2.5, 3.0]

# Current baseline
df['current_pnl_raw'] = df['pnl'] + COST_TICKS  # Add back cost to get raw pnl

# Count current losers (trades where pnl < 0 with current exits)
current_losers = set(df[df['WL'] == 'L']['trade_id'].values)
print(f"  Current total losers: {len(current_losers)}")

def run_stop_sweep(subset_df, subset_label):
    """Run zone-relative stop sweep on a subset of trades."""
    print(f"\n  {subset_label} (n={len(subset_df)}):")
    print(f"  {'Stop mult':12s} | {'Trades stopped':15s} | {'Curr losers caught':20s} | {'Winners killed':15s} | {'Net PF':8s} | {'Net EV':8s}")
    print("  " + "-"*90)

    results = {}
    for mult in stop_multipliers:
        total_gross_win = 0
        total_gross_loss = 0
        trades_stopped = 0
        losers_caught = 0
        winners_killed = 0
        n_trades = 0

        for idx in subset_df.index:
            entry_bar = df.loc[idx, 'entry_bar_idx']
            if pd.isna(entry_bar):
                continue
            entry_bar = int(entry_bar)
            if entry_bar >= n_bars:
                continue

            entry_price = df.loc[idx, 'entry_price']
            direction = df.loc[idx, 'direction']
            zone_w = df.loc[idx, 'zone_width']
            trade_id = df.loc[idx, 'trade_id']

            if pd.isna(zone_w) or zone_w <= 0:
                continue

            zone_stop = zone_w * mult
            # Simulate with zone-relative stop, fixed target
            exit_type, raw_pnl, bh = simulate_exit(
                entry_bar, entry_price, direction,
                stop_ticks=zone_stop, target_ticks=FIXED_TARGET, time_cap=FIXED_TIMECAP
            )

            net_pnl = raw_pnl - COST_TICKS
            n_trades += 1

            if net_pnl > 0:
                total_gross_win += net_pnl
            else:
                total_gross_loss += abs(net_pnl)

            if exit_type == 'STOP' and zone_stop < FIXED_STOP:
                trades_stopped += 1
                if trade_id in current_losers:
                    losers_caught += 1
                else:
                    winners_killed += 1

        pf = total_gross_win / total_gross_loss if total_gross_loss > 0 else float('inf')
        ev = (total_gross_win - total_gross_loss) / n_trades if n_trades > 0 else 0

        results[mult] = {
            'trades_stopped': trades_stopped,
            'losers_caught': losers_caught,
            'winners_killed': winners_killed,
            'pf': pf,
            'ev': ev
        }

        print(f"  {mult:.1f}x zone_w   | {trades_stopped:15d} | {losers_caught:20d} | {winners_killed:15d} | {pf:8.2f} | {ev:8.1f}")

    return results

# Overall sweep
run_stop_sweep(df, "ALL TRADES")

# Split by trend label (CT vs WT)
ct_mask = df['trend_label'] == 'CT'
wt_mask = df['trend_label'] == 'WT'
nt_mask = df['trend_label'] == 'NT'

if ct_mask.sum() > 0:
    run_stop_sweep(df[ct_mask], "CT TRADES")
if wt_mask.sum() > 0:
    run_stop_sweep(df[wt_mask], "WT TRADES")
if nt_mask.sum() > 0:
    run_stop_sweep(df[nt_mask], "NT TRADES")

# Split by zone width bin
for zw_bin in labels:
    bin_mask = df['zone_width_bin'] == zw_bin
    if bin_mask.sum() > 5:
        run_stop_sweep(df[bin_mask], f"Zone width {zw_bin}")

# 2C) Zone-relative TARGET sweep (fixed stop = 190t for all)
print("\n\n2C) Zone-Relative Target Sweep (fixed stop=190t):")

target_multipliers = [0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 2.5, 3.0]

def run_target_sweep(subset_df, subset_label):
    """Run zone-relative target sweep on a subset of trades."""
    print(f"\n  {subset_label} (n={len(subset_df)}):")
    print(f"  {'Target mult':12s} | {'Avg tgt ticks':15s} | {'Targets hit':12s} | {'Hit rate':8s} | {'Net PF':8s} | {'Net EV':8s}")
    print("  " + "-"*80)

    for mult in target_multipliers:
        total_gross_win = 0
        total_gross_loss = 0
        targets_hit = 0
        n_trades = 0
        tgt_ticks_sum = 0

        for idx in subset_df.index:
            entry_bar = df.loc[idx, 'entry_bar_idx']
            if pd.isna(entry_bar):
                continue
            entry_bar = int(entry_bar)
            if entry_bar >= n_bars:
                continue

            entry_price = df.loc[idx, 'entry_price']
            direction = df.loc[idx, 'direction']
            zone_w = df.loc[idx, 'zone_width']

            if pd.isna(zone_w) or zone_w <= 0:
                continue

            zone_target = zone_w * mult
            tgt_ticks_sum += zone_target

            # Simulate with fixed stop, zone-relative target
            exit_type, raw_pnl, bh = simulate_exit(
                entry_bar, entry_price, direction,
                stop_ticks=FIXED_STOP, target_ticks=zone_target, time_cap=FIXED_TIMECAP
            )

            net_pnl = raw_pnl - COST_TICKS
            n_trades += 1

            if net_pnl > 0:
                total_gross_win += net_pnl
            else:
                total_gross_loss += abs(net_pnl)

            if exit_type == 'TARGET':
                targets_hit += 1

        pf = total_gross_win / total_gross_loss if total_gross_loss > 0 else float('inf')
        ev = (total_gross_win - total_gross_loss) / n_trades if n_trades > 0 else 0
        avg_tgt = tgt_ticks_sum / n_trades if n_trades > 0 else 0
        hit_rate = targets_hit / n_trades * 100 if n_trades > 0 else 0

        print(f"  {mult:.2f}x zone_w  | {avg_tgt:15.1f} | {targets_hit:12d} | {hit_rate:6.1f}%  | {pf:8.2f} | {ev:8.1f}")

# Overall
run_target_sweep(df, "ALL TRADES")

# CT vs WT
if ct_mask.sum() > 0:
    run_target_sweep(df[ct_mask], "CT TRADES")
if wt_mask.sum() > 0:
    run_target_sweep(df[wt_mask], "WT TRADES")

# By zone width bin
for zw_bin in labels:
    bin_mask = df['zone_width_bin'] == zw_bin
    if bin_mask.sum() > 5:
        run_target_sweep(df[bin_mask], f"Zone width {zw_bin}")

# 2D) Best combined: best stop × best target
# This will be filled in after reviewing 2B and 2C results
# For now, compute a grid of interesting combinations
print("\n\n2D) Combined Zone-Relative Stop × Target Grid:")
print("  (Testing best combinations identified from 2B and 2C)")

combo_stops = [1.0, 1.5, 2.0, 2.5]
combo_targets = [0.5, 0.75, 1.0, 1.5]

print(f"\n  {'Stop×Target':20s} | {'Avg stop':10s} | {'Avg tgt':10s} | {'Win%':6s} | {'Net PF':8s} | {'Net EV':8s} | {'Profit':10s}")
print("  " + "-"*90)

for s_mult in combo_stops:
    for t_mult in combo_targets:
        total_gross_win = 0
        total_gross_loss = 0
        wins = 0
        n_trades = 0

        for idx in df.index:
            entry_bar = df.loc[idx, 'entry_bar_idx']
            if pd.isna(entry_bar):
                continue
            entry_bar = int(entry_bar)
            if entry_bar >= n_bars:
                continue

            entry_price = df.loc[idx, 'entry_price']
            direction = df.loc[idx, 'direction']
            zone_w = df.loc[idx, 'zone_width']

            if pd.isna(zone_w) or zone_w <= 0:
                continue

            zone_stop = zone_w * s_mult
            zone_target = zone_w * t_mult

            exit_type, raw_pnl, bh = simulate_exit(
                entry_bar, entry_price, direction,
                stop_ticks=zone_stop, target_ticks=zone_target, time_cap=FIXED_TIMECAP
            )

            net_pnl = raw_pnl - COST_TICKS
            n_trades += 1

            if net_pnl > 0:
                total_gross_win += net_pnl
                wins += 1
            else:
                total_gross_loss += abs(net_pnl)

        if n_trades == 0:
            continue
        pf = total_gross_win / total_gross_loss if total_gross_loss > 0 else float('inf')
        ev = (total_gross_win - total_gross_loss) / n_trades
        wr = wins / n_trades * 100
        profit = total_gross_win - total_gross_loss

        # Compute average stop/target in ticks
        valid = df[df['entry_bar_idx'].notna() & (df['zone_width'] > 0)]
        avg_s = (valid['zone_width'] * s_mult).mean()
        avg_t = (valid['zone_width'] * t_mult).mean()

        print(f"  {s_mult:.1f}x/{t_mult:.2f}x        | {avg_s:10.0f} | {avg_t:10.0f} | {wr:5.1f}% | {pf:8.2f} | {ev:8.1f} | {profit:10.1f}")

# ── Compare to current baseline ──────────────────────────────────────
print("\n  Current baseline (fixed 190/80):")
baseline_win = df[df['WL'] == 'W']['pnl'].sum()
baseline_loss = df[df['WL'] == 'L']['pnl'].abs().sum()
baseline_pf = baseline_win / baseline_loss if baseline_loss > 0 else float('inf')
baseline_ev = df['pnl'].mean()
baseline_wr = (df['WL'] == 'W').mean() * 100
print(f"  190/80 fixed        |        190 |         80 | {baseline_wr:5.1f}% | {baseline_pf:8.2f} | {baseline_ev:8.1f} | {df['pnl'].sum():10.1f}")


# ══════════════════════════════════════════════════════════════════════
# SAVE OUTPUT CSV
# ══════════════════════════════════════════════════════════════════════
print("\n" + "="*70)
print("Saving zone_touch_exit_investigation.csv...")

# Select columns for output (all 312 rows)
output_cols = [
    'trade_id', 'seg_model_group', 'period', 'datetime', 'direction',
    'mode', 'WL', 'pnl', 'mae', 'mfe', 'entry_price', 'exit_price',
    'exit_type', 'bars_held', 'trend_label', 'SBB_label',
    # Scoring
    'score', 'score_margin', 'acal_threshold',
    # Features
    'F10_PriorPenetration', 'F04_CascadeState', 'F01_Timeframe', 'F21_ZoneAge',
    # Zone structure
    'zone_width', 'zone_width_ratio', 'ZoneTop', 'ZoneBot',
    # Session
    'session',
    # Touch info
    'touch_sequence', 'cascade_state', 'source_label', 'tf_minutes',
    # Penetration analysis
    'crossed_opposite_edge', 'depth_past_opposite_edge',
    'bars_to_max_penetration', 'penetration_speed',
    # Battleground flag
    'is_battleground',
    # Zone width bin
    'zone_width_bin',
]

out_df = df[output_cols].copy()

# Ensure battleground-specific columns are null for non-battleground trades
# (Actually all these columns are computed for all trades, just filtered for analysis)
# The is_battleground flag lets Parts 2 & 3 filter as needed

assert len(out_df) == 312, f"Expected 312 rows, got {len(out_df)}"
out_df.to_csv(OUTPUT_PATH, index=False)
print(f"  Saved {len(out_df)} rows to {OUTPUT_PATH}")
print(f"  Columns: {len(output_cols)}")
print("  Join key: trade_id")
print("\nDone — Part 1 of 3 complete.")
