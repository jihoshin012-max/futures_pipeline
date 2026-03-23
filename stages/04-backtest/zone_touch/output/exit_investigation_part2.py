# archetype: zone_touch
"""
Zone Touch Exit Investigation — Part 2 of 3
Section 3: Penetration Dynamics
Section 4: Exit Re-Optimization with 5t Entry
Adds columns to zone_touch_exit_investigation.csv (312 rows, trade_id join key)
Saves results to exit_investigation_part2.md
"""
import pandas as pd
import numpy as np
import warnings, sys, io
warnings.filterwarnings('ignore')

# ── Paths ──────────────────────────────────────────────────────────────
BASE = "c:/Projects/pipeline"
TRADE_PATH = f"{BASE}/stages/04-backtest/zone_touch/output/p2_trade_details.csv"
MERGED_P2A = f"{BASE}/stages/01-data/output/zone_prep/NQ_merged_P2a.csv"
MERGED_P2B = f"{BASE}/stages/01-data/output/zone_prep/NQ_merged_P2b.csv"
BARDATA_PATH = f"{BASE}/stages/01-data/output/zone_prep/NQ_bardata_P2.csv"
INVEST_CSV = f"{BASE}/stages/04-backtest/zone_touch/output/zone_touch_exit_investigation.csv"
OUTPUT_MD = f"{BASE}/stages/04-backtest/zone_touch/output/exit_investigation_part2.md"

TICK_SIZE = 0.25
COST_TICKS = 3

# Force UTF-8 on stdout for Windows
import codecs
if hasattr(sys.stdout, 'buffer'):
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, errors='replace')

# Tee output to both console and markdown file
class Tee:
    def __init__(self, *streams):
        self.streams = streams
    def write(self, data):
        for s in self.streams:
            s.write(data)
    def flush(self):
        for s in self.streams:
            s.flush()

md_buffer = io.StringIO()
tee = Tee(sys.stdout, md_buffer)

def out(s=""):
    tee.write(s + "\n")

# ── Load data ──────────────────────────────────────────────────────────
print("Loading data...")
trades = pd.read_csv(TRADE_PATH)
invest = pd.read_csv(INVEST_CSV)
touches_a = pd.read_csv(MERGED_P2A)
touches_b = pd.read_csv(MERGED_P2B)
touches = pd.concat([touches_a, touches_b], ignore_index=True)

bardata = pd.read_csv(BARDATA_PATH, low_memory=False)
bardata.columns = [c.strip() for c in bardata.columns]

# Parse datetimes for touch join
trades['dt'] = pd.to_datetime(trades['datetime'])
touches['dt'] = pd.to_datetime(touches['DateTime'])

print(f"  Trades: {len(trades)}, Invest CSV: {len(invest)}, Bars: {len(bardata)}")
assert len(invest) == 312, f"Expected 312 rows in invest CSV, got {len(invest)}"

# ── Join trades to touches for RotBarIndex ─────────────────────────────
print("Joining trades to touches for RotBarIndex...")
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
print(f"  Matched: {df['RotBarIndex'].notna().sum()}/{len(df)}")

# ── Bar data arrays ────────────────────────────────────────────────────
bar_high = bardata['High'].values.astype(float)
bar_low = bardata['Low'].values.astype(float)
bar_close = bardata['Last'].values.astype(float)
bar_open = bardata['Open'].values.astype(float)
n_bars = len(bardata)

# Entry bar index
df['entry_bar_idx'] = df['RotBarIndex'].apply(lambda x: int(x) + 1 if pd.notna(x) and x >= 0 else -1)

# Add columns from invest CSV that the trade join doesn't carry
df['WL'] = np.where(df['pnl_ticks'] > 0, 'W', 'L')
df['pnl'] = df['pnl_ticks'].astype(float)
df['mae'] = df['mae_ticks'].astype(float)
df['mfe'] = df['mfe_ticks'].astype(float)
df['crossed_opposite_edge'] = invest.set_index('trade_id').loc[df['trade_id'].values, 'crossed_opposite_edge'].values

# ══════════════════════════════════════════════════════════════════════
# SECTION 3: PENETRATION DYNAMICS — BAR-BY-BAR COMPUTATION
# ══════════════════════════════════════════════════════════════════════
print("Computing bar-by-bar adverse/favorable excursions...")

# Pre-allocate per-trade metric columns
new_cols = {}
for col in ['bars_to_25t_adverse', 'bars_to_50t_adverse', 'bars_to_100t_adverse',
            'bars_to_max_adverse', 'pen_speed_10bar', 'pen_speed_25bar',
            'bars_to_20t_favorable', 'bars_to_T1_favorable', 'bars_to_mfe_peak',
            'mfe_at_10bar', 'mfe_at_20bar', 'mfe_at_25bar', 'mfe_at_30bar', 'mfe_at_50bar', 'mfe_at_100bar',
            'mae_at_10bar', 'mae_at_20bar', 'mae_at_25bar', 'mae_at_30bar', 'mae_at_50bar',
            'stall_bars_after_max_pen', 'bounce_25t_after_max',
            'bounce_within_30bars', 'bounce_within_50bars',
            'opp_edge_cross_bar', 'opp_edge_cross_depth']:
    new_cols[col] = np.full(len(df), np.nan)

MAX_WALK = 200  # max bars to walk forward

for i in range(len(df)):
    entry_bar = df.loc[i, 'entry_bar_idx']
    if entry_bar < 0 or entry_bar >= n_bars:
        continue
    entry_price = df.loc[i, 'entry_price']
    direction = df.loc[i, 'direction']
    bars_held = int(df.loc[i, 'bars_held'])
    trend = df.loc[i, 'trend_label']
    zone_top = df.loc[i, 'ZoneTop']
    zone_bot = df.loc[i, 'ZoneBot']

    end_bar = min(entry_bar + MAX_WALK, n_bars)
    actual_end = min(entry_bar + bars_held + 1, n_bars)

    # T1 for this trade
    t1_ticks = 40 if trend == 'CT' else 60

    # Walk bars
    max_adverse = 0.0
    max_adverse_bar = 0
    max_favorable = 0.0
    max_favorable_bar = 0
    reached_25a = reached_50a = reached_100a = False
    reached_20f = reached_t1f = False

    # For stall detection
    bars_to_25a = bars_to_50a = bars_to_100a = np.nan
    bars_to_20f = bars_to_t1f = np.nan

    # Track adverse/favorable at specific bar offsets
    adverse_at = {}
    favorable_at = {}

    # Opposite edge cross tracking
    opp_cross_bar = np.nan
    opp_cross_depth = 0.0

    for b_offset in range(0, end_bar - entry_bar):
        b = entry_bar + b_offset
        bar_num = b_offset + 1  # 1-indexed bar count

        if direction == 'LONG':
            adverse = (entry_price - bar_low[b]) / TICK_SIZE
            favorable = (bar_high[b] - entry_price) / TICK_SIZE
        else:
            adverse = (bar_high[b] - entry_price) / TICK_SIZE
            favorable = (entry_price - bar_low[b]) / TICK_SIZE

        adverse = max(adverse, 0)
        favorable = max(favorable, 0)

        if adverse > max_adverse:
            max_adverse = adverse
            max_adverse_bar = bar_num

        if favorable > max_favorable:
            max_favorable = favorable
            max_favorable_bar = bar_num

        # Track milestones
        if not reached_25a and adverse >= 25:
            bars_to_25a = bar_num
            reached_25a = True
        if not reached_50a and adverse >= 50:
            bars_to_50a = bar_num
            reached_50a = True
        if not reached_100a and adverse >= 100:
            bars_to_100a = bar_num
            reached_100a = True

        if not reached_20f and favorable >= 20:
            bars_to_20f = bar_num
            reached_20f = True
        if not reached_t1f and favorable >= t1_ticks:
            bars_to_t1f = bar_num
            reached_t1f = True

        # Track running max at specific bar offsets
        for check_bar in [10, 20, 25, 30, 50, 100]:
            if bar_num == check_bar:
                adverse_at[check_bar] = max_adverse  # running max, not instantaneous
                favorable_at[check_bar] = max_favorable

        # Opposite edge cross (only within actual trade bars)
        if b_offset < bars_held and pd.notna(opp_cross_bar) == False and np.isnan(opp_cross_bar):
            if direction == 'LONG' and pd.notna(zone_bot):
                if bar_low[b] < zone_bot:
                    opp_cross_bar = bar_num
                    opp_cross_depth = (zone_bot - bar_low[b]) / TICK_SIZE
            elif direction == 'SHORT' and pd.notna(zone_top):
                if bar_high[b] > zone_top:
                    opp_cross_bar = bar_num
                    opp_cross_depth = (bar_high[b] - zone_top) / TICK_SIZE

    new_cols['bars_to_25t_adverse'][i] = bars_to_25a
    new_cols['bars_to_50t_adverse'][i] = bars_to_50a
    new_cols['bars_to_100t_adverse'][i] = bars_to_100a
    new_cols['bars_to_max_adverse'][i] = max_adverse_bar
    new_cols['bars_to_20t_favorable'][i] = bars_to_20f
    new_cols['bars_to_T1_favorable'][i] = bars_to_t1f
    new_cols['bars_to_mfe_peak'][i] = max_favorable_bar

    # Penetration speed at N bars
    new_cols['pen_speed_10bar'][i] = adverse_at.get(10, 0) / 10.0
    new_cols['pen_speed_25bar'][i] = adverse_at.get(25, 0) / 25.0

    # MFE at specific bars
    for check_bar in [10, 20, 25, 30, 50, 100]:
        col_name = f'mfe_at_{check_bar}bar'
        new_cols[col_name][i] = favorable_at.get(check_bar, np.nan)

    # MAE at specific bars
    for check_bar in [10, 20, 30, 50]:
        col_name = f'mae_at_{check_bar}bar'
        new_cols[col_name][i] = adverse_at.get(check_bar, np.nan)

    new_cols['opp_edge_cross_bar'][i] = opp_cross_bar
    new_cols['opp_edge_cross_depth'][i] = opp_cross_depth

    # Stall detection: after max pen, how many bars to 25t bounce? (uses close prices)
    stall_bars = np.nan
    bounced_25 = False
    if max_adverse_bar > 0:
        max_pen_abs_bar = entry_bar + max_adverse_bar - 1
        # Worst close at max pen bar
        if direction == 'LONG':
            worst_close_at_max = (entry_price - bar_close[max_pen_abs_bar]) / TICK_SIZE
        else:
            worst_close_at_max = (bar_close[max_pen_abs_bar] - entry_price) / TICK_SIZE
        for sb in range(1, min(MAX_WALK, end_bar - max_pen_abs_bar)):
            check_b = max_pen_abs_bar + sb
            if check_b >= end_bar:
                break
            if direction == 'LONG':
                close_adverse = (entry_price - bar_close[check_b]) / TICK_SIZE
            else:
                close_adverse = (bar_close[check_b] - entry_price) / TICK_SIZE
            recovery = worst_close_at_max - close_adverse
            if recovery >= 25:
                stall_bars = sb
                bounced_25 = True
                break
        if not bounced_25:
            stall_bars = min(MAX_WALK, end_bar - max_pen_abs_bar)  # never bounced

    new_cols['stall_bars_after_max_pen'][i] = stall_bars
    new_cols['bounce_25t_after_max'][i] = 1.0 if bounced_25 else 0.0

    # Bounce tracking for no-bounce rules (uses CLOSE prices to avoid intra-bar ambiguity)
    # Check: after reaching 50t adverse, does close price recover 20t from worst close within 30/50 bars?
    if reached_50a and not np.isnan(bars_to_50a):
        bar_50a = entry_bar + int(bars_to_50a) - 1
        bounced_30 = False
        bounced_50 = False
        worst_close_adverse = 0  # worst adverse measured by close price
        for sb in range(0, MAX_WALK):
            check_b = bar_50a + sb
            if check_b >= end_bar:
                break
            if direction == 'LONG':
                close_adverse = (entry_price - bar_close[check_b]) / TICK_SIZE
            else:
                close_adverse = (bar_close[check_b] - entry_price) / TICK_SIZE

            if close_adverse > worst_close_adverse:
                worst_close_adverse = close_adverse

            # Recovery = how much the close has improved from worst close
            recovery = worst_close_adverse - close_adverse

            if not bounced_30 and sb <= 30 and recovery >= 20:
                bounced_30 = True
            if not bounced_50 and sb <= 50 and recovery >= 20:
                bounced_50 = True
            if bounced_50:
                break

        new_cols['bounce_within_30bars'][i] = 1.0 if bounced_30 else 0.0
        new_cols['bounce_within_50bars'][i] = 1.0 if bounced_50 else 0.0
    else:
        new_cols['bounce_within_30bars'][i] = np.nan  # never reached 50t adverse
        new_cols['bounce_within_50bars'][i] = np.nan

print("  Bar-by-bar computation complete.")

# Add new columns to df
for col, vals in new_cols.items():
    df[col] = vals

# ══════════════════════════════════════════════════════════════════════
# SECTION 3 — REPORTING
# ══════════════════════════════════════════════════════════════════════
out("# Zone Touch Exit Investigation — Part 2 of 3")
out()
out("## SECTION 3: PENETRATION DYNAMICS")
out()

winners = df[df['WL'] == 'W']
losers = df[df['WL'] == 'L']

# 3A) Penetration speed profile
out("### 3A) Penetration Speed Profile")
out()
out("| Metric | Winners (n={}) | Losers (n={}) | All (n={}) |".format(len(winners), len(losers), len(df)))
out("|--------|---------|--------|-----|")

def fmt_mean(s):
    v = s.dropna()
    if len(v) == 0:
        return "—"
    return f"{v.mean():.1f}"

def fmt_pct_reached(s):
    v = s.dropna()
    total = len(s)
    return f"{len(v)}/{total} ({len(v)/total*100:.0f}%)" if total > 0 else "—"

metrics_3a = [
    ("Mean bars to reach 25t adverse", 'bars_to_25t_adverse', 'mean'),
    ("Mean bars to reach 50t adverse", 'bars_to_50t_adverse', 'mean'),
    ("Mean bars to reach 100t adverse", 'bars_to_100t_adverse', 'mean'),
    ("Mean bars to reach max adverse", 'bars_to_max_adverse', 'mean'),
    ("Pen speed at 10 bars (t/bar)", 'pen_speed_10bar', 'mean'),
    ("Pen speed at 25 bars (t/bar)", 'pen_speed_25bar', 'mean'),
]

for label, col, agg in metrics_3a:
    w_val = fmt_mean(winners[col])
    l_val = fmt_mean(losers[col])
    a_val = fmt_mean(df[col])
    out(f"| {label} | {w_val} | {l_val} | {a_val} |")

# Also show % that reached each threshold
out()
out("% of trades reaching adverse threshold:")
out()
out("| Threshold | Winners | Losers | All |")
out("|-----------|---------|--------|-----|")
for thr, col in [("25t", 'bars_to_25t_adverse'), ("50t", 'bars_to_50t_adverse'), ("100t", 'bars_to_100t_adverse')]:
    w_pct = fmt_pct_reached(winners[col])
    l_pct = fmt_pct_reached(losers[col])
    a_pct = fmt_pct_reached(df[col])
    out(f"| {thr} | {w_pct} | {l_pct} | {a_pct} |")

# 3B) Speed-based and no-bounce exit rules
out()
out("### 3B) Speed-Based and No-Bounce Exit Rules")
out()

# Need to simulate these rules against bar data
# For each rule, walk bars and check if the rule triggers before the actual exit

current_losers_set = set(df[df['WL'] == 'L']['trade_id'].values)
current_winners_set = set(df[df['WL'] == 'W']['trade_id'].values)

# Compute baseline PF
baseline_gross_win = df[df['pnl'] > 0]['pnl'].sum()
baseline_gross_loss = df[df['pnl'] <= 0]['pnl'].abs().sum()
baseline_pf = baseline_gross_win / baseline_gross_loss if baseline_gross_loss > 0 else float('inf')

def simulate_speed_rule(threshold_ticks, within_bars):
    """TYPE 1: Exit if price reaches threshold_ticks adverse within within_bars bars."""
    trades_exited = 0
    would_have_lost = 0
    would_have_won = 0
    total_gross_win = 0
    total_gross_loss = 0

    for i in range(len(df)):
        entry_bar = df.loc[i, 'entry_bar_idx']
        if entry_bar < 0:
            continue
        entry_price = df.loc[i, 'entry_price']
        direction = df.loc[i, 'direction']
        trade_id = df.loc[i, 'trade_id']
        original_pnl = df.loc[i, 'pnl']

        # Check if rule triggers
        triggered = False
        exit_pnl = original_pnl

        check_end = min(entry_bar + within_bars, n_bars)
        for b in range(entry_bar, check_end):
            if direction == 'LONG':
                adverse = (entry_price - bar_low[b]) / TICK_SIZE
            else:
                adverse = (bar_high[b] - entry_price) / TICK_SIZE
            if adverse >= threshold_ticks:
                triggered = True
                # Exit at the threshold level
                exit_pnl = -threshold_ticks - COST_TICKS
                break

        if triggered:
            trades_exited += 1
            if trade_id in current_losers_set:
                would_have_lost += 1
            else:
                would_have_won += 1
            # Use early exit PnL
            if exit_pnl > 0:
                total_gross_win += exit_pnl
            else:
                total_gross_loss += abs(exit_pnl)
        else:
            # Keep original PnL
            if original_pnl > 0:
                total_gross_win += original_pnl
            else:
                total_gross_loss += abs(original_pnl)

    net_pf = total_gross_win / total_gross_loss if total_gross_loss > 0 else float('inf')
    pf_change = net_pf - baseline_pf
    n_losers = len(current_losers_set)
    n_winners = len(current_winners_set)

    return {
        'trades_exited': trades_exited,
        'would_have_lost': would_have_lost,
        'would_have_won': would_have_won,
        'losers_caught_pct': would_have_lost / n_losers * 100 if n_losers > 0 else 0,
        'winners_killed_pct': would_have_won / n_winners * 100 if n_winners > 0 else 0,
        'net_pf': net_pf,
        'pf_change': pf_change,
    }

out("**TYPE 1 — Fast penetration (catches deep blowouts):**")
out()
out("| Speed threshold | Trades exited | Would have lost | Would have won | Losers caught % | Winners killed % | Net PF | PF Δ |")
out("|----------------|:---:|:---:|:---:|:---:|:---:|:---:|:---:|")

type1_rules = [
    (50, 5), (50, 10), (75, 5), (75, 10), (100, 10), (100, 20),
]

for thr, bars in type1_rules:
    r = simulate_speed_rule(thr, bars)
    out(f"| {thr}t in {bars} bars | {r['trades_exited']} | {r['would_have_lost']} | {r['would_have_won']} | {r['losers_caught_pct']:.0f}% | {r['winners_killed_pct']:.0f}% | {r['net_pf']:.2f} | {r['pf_change']:+.2f} |")

# TYPE 2 — No-bounce rules
out()
out("**TYPE 2 — Slow no-bounce (catches battleground drifters):**")
out()
out("| Rule | Trades exited | Would have lost | Would have won | Losers caught % | Winners killed % | Net PF | PF Δ |")
out("|------|:---:|:---:|:---:|:---:|:---:|:---:|:---:|")

def simulate_nobounce_rule(adv_threshold, bounce_ticks, check_window):
    """TYPE 2: Exit if adverse >= adv_threshold AND no bounce_ticks bounce within check_window bars."""
    trades_exited = 0
    would_have_lost = 0
    would_have_won = 0
    total_gross_win = 0
    total_gross_loss = 0

    for i in range(len(df)):
        entry_bar = df.loc[i, 'entry_bar_idx']
        if entry_bar < 0:
            continue
        entry_price = df.loc[i, 'entry_price']
        direction = df.loc[i, 'direction']
        trade_id = df.loc[i, 'trade_id']
        original_pnl = df.loc[i, 'pnl']
        bars_held_actual = int(df.loc[i, 'bars_held'])

        triggered = False
        exit_pnl = original_pnl

        trade_end = min(entry_bar + bars_held_actual, n_bars)

        # Find first bar where adverse >= threshold
        first_adv_bar = None
        for b in range(entry_bar, trade_end):
            if direction == 'LONG':
                adverse = (entry_price - bar_low[b]) / TICK_SIZE
            else:
                adverse = (bar_high[b] - entry_price) / TICK_SIZE
            if adverse >= adv_threshold:
                first_adv_bar = b
                break

        if first_adv_bar is not None:
            # Check if CLOSE price bounces back bounce_ticks within check_window bars
            # (uses close prices to avoid intra-bar high-low ambiguity)
            worst_close_adv = 0
            bounced = False
            rule_check_end = min(first_adv_bar + check_window, trade_end)

            for b2 in range(first_adv_bar, rule_check_end):
                if direction == 'LONG':
                    close_adv = (entry_price - bar_close[b2]) / TICK_SIZE
                else:
                    close_adv = (bar_close[b2] - entry_price) / TICK_SIZE

                if close_adv > worst_close_adv:
                    worst_close_adv = close_adv

                recovery = worst_close_adv - close_adv
                if recovery >= bounce_ticks:
                    bounced = True
                    break

            if not bounced:
                triggered = True
                # Exit at close of the check_window bar
                exit_bar_idx = min(rule_check_end - 1, trade_end - 1)
                if exit_bar_idx >= entry_bar:
                    if direction == 'LONG':
                        exit_pnl = (bar_close[exit_bar_idx] - entry_price) / TICK_SIZE - COST_TICKS
                    else:
                        exit_pnl = (entry_price - bar_close[exit_bar_idx]) / TICK_SIZE - COST_TICKS

        if triggered:
            trades_exited += 1
            if trade_id in current_losers_set:
                would_have_lost += 1
            else:
                would_have_won += 1
            if exit_pnl > 0:
                total_gross_win += exit_pnl
            else:
                total_gross_loss += abs(exit_pnl)
        else:
            if original_pnl > 0:
                total_gross_win += original_pnl
            else:
                total_gross_loss += abs(original_pnl)

    net_pf = total_gross_win / total_gross_loss if total_gross_loss > 0 else float('inf')
    pf_change = net_pf - baseline_pf
    n_losers = len(current_losers_set)
    n_winners = len(current_winners_set)

    return {
        'trades_exited': trades_exited,
        'would_have_lost': would_have_lost,
        'would_have_won': would_have_won,
        'losers_caught_pct': would_have_lost / n_losers * 100 if n_losers > 0 else 0,
        'winners_killed_pct': would_have_won / n_winners * 100 if n_winners > 0 else 0,
        'net_pf': net_pf,
        'pf_change': pf_change,
    }

type2_rules = [
    (50, 20, 30, "50t adv, no 20t bounce in 30 bars"),
    (50, 20, 50, "50t adv, no 20t bounce in 50 bars"),
    (75, 25, 30, "75t adv, no 25t bounce in 30 bars"),
    (75, 25, 50, "75t adv, no 25t bounce in 50 bars"),
    (100, 30, 40, "100t adv, no 30t bounce in 40 bars"),
]

for adv, bounce, window, label in type2_rules:
    r = simulate_nobounce_rule(adv, bounce, window)
    out(f"| {label} | {r['trades_exited']} | {r['would_have_lost']} | {r['would_have_won']} | {r['losers_caught_pct']:.0f}% | {r['winners_killed_pct']:.0f}% | {r['net_pf']:.2f} | {r['pf_change']:+.2f} |")

# Halfway timecap rule
def simulate_halfway_rule():
    """Exit if adverse > 50t at bar 60 (halfway to timecap ~120)."""
    trades_exited = 0
    would_have_lost = 0
    would_have_won = 0
    total_gross_win = 0
    total_gross_loss = 0

    for i in range(len(df)):
        entry_bar = df.loc[i, 'entry_bar_idx']
        if entry_bar < 0:
            continue
        entry_price = df.loc[i, 'entry_price']
        direction = df.loc[i, 'direction']
        trade_id = df.loc[i, 'trade_id']
        original_pnl = df.loc[i, 'pnl']

        check_bar = entry_bar + 60
        triggered = False
        exit_pnl = original_pnl

        if check_bar < n_bars:
            if direction == 'LONG':
                adverse = (entry_price - bar_low[check_bar]) / TICK_SIZE
                current_pnl = (bar_close[check_bar] - entry_price) / TICK_SIZE
            else:
                adverse = (bar_high[check_bar] - entry_price) / TICK_SIZE
                current_pnl = (entry_price - bar_close[check_bar]) / TICK_SIZE

            if adverse > 50 and current_pnl < 0:
                triggered = True
                exit_pnl = current_pnl - COST_TICKS

        if triggered:
            trades_exited += 1
            if trade_id in current_losers_set:
                would_have_lost += 1
            else:
                would_have_won += 1
            if exit_pnl > 0:
                total_gross_win += exit_pnl
            else:
                total_gross_loss += abs(exit_pnl)
        else:
            if original_pnl > 0:
                total_gross_win += original_pnl
            else:
                total_gross_loss += abs(original_pnl)

    net_pf = total_gross_win / total_gross_loss if total_gross_loss > 0 else float('inf')
    pf_change = net_pf - baseline_pf
    return {
        'trades_exited': trades_exited,
        'would_have_lost': would_have_lost,
        'would_have_won': would_have_won,
        'losers_caught_pct': would_have_lost / len(current_losers_set) * 100,
        'winners_killed_pct': would_have_won / len(current_winners_set) * 100,
        'net_pf': net_pf,
        'pf_change': pf_change,
    }

r = simulate_halfway_rule()
out(f"| Adverse > 50t at bar 60 (PnL<0) | {r['trades_exited']} | {r['would_have_lost']} | {r['would_have_won']} | {r['losers_caught_pct']:.0f}% | {r['winners_killed_pct']:.0f}% | {r['net_pf']:.2f} | {r['pf_change']:+.2f} |")

out(f"\nBaseline PF = {baseline_pf:.2f}")

# 3C) Opposite edge cross
out()
out("### 3C) Opposite Edge Cross as Live Exit Signal")
out()

# Count how many winners/losers crossed opposite edge
w_crossed = (winners['crossed_opposite_edge'] == 'Y').sum() if 'crossed_opposite_edge' in winners else 0
l_crossed = (losers['crossed_opposite_edge'] == 'Y').sum() if 'crossed_opposite_edge' in losers else 0
out(f"Winners that crossed opposite edge: {w_crossed}/{len(winners)} ({w_crossed/len(winners)*100:.1f}%)")
out(f"Losers that crossed opposite edge: {l_crossed}/{len(losers)} ({l_crossed/len(losers)*100:.1f}%)")
out()

def simulate_opp_edge_exit(depth_extra_ticks):
    """Exit when price crosses opposite edge + depth_extra_ticks."""
    trades_affected = 0
    losses_saved = 0
    wins_killed = 0
    early_exit_pnls = []
    total_gross_win = 0
    total_gross_loss = 0

    for i in range(len(df)):
        entry_bar = df.loc[i, 'entry_bar_idx']
        if entry_bar < 0:
            continue
        entry_price = df.loc[i, 'entry_price']
        direction = df.loc[i, 'direction']
        trade_id = df.loc[i, 'trade_id']
        original_pnl = df.loc[i, 'pnl']
        zone_top = df.loc[i, 'ZoneTop']
        zone_bot = df.loc[i, 'ZoneBot']
        bars_held_actual = int(df.loc[i, 'bars_held'])

        if pd.isna(zone_top) or pd.isna(zone_bot):
            if original_pnl > 0:
                total_gross_win += original_pnl
            else:
                total_gross_loss += abs(original_pnl)
            continue

        # Determine trigger level
        if direction == 'LONG':
            trigger_price = zone_bot - depth_extra_ticks * TICK_SIZE
        else:
            trigger_price = zone_top + depth_extra_ticks * TICK_SIZE

        triggered = False
        exit_pnl = original_pnl
        trade_end = min(entry_bar + bars_held_actual, n_bars)

        for b in range(entry_bar, trade_end):
            if direction == 'LONG' and bar_low[b] <= trigger_price:
                triggered = True
                exit_pnl = (trigger_price - entry_price) / TICK_SIZE - COST_TICKS
                break
            elif direction == 'SHORT' and bar_high[b] >= trigger_price:
                triggered = True
                exit_pnl = (entry_price - trigger_price) / TICK_SIZE - COST_TICKS
                break

        if triggered:
            trades_affected += 1
            early_exit_pnls.append(exit_pnl)
            if trade_id in current_losers_set:
                losses_saved += 1
            else:
                wins_killed += 1

        use_pnl = exit_pnl if triggered else original_pnl
        if use_pnl > 0:
            total_gross_win += use_pnl
        else:
            total_gross_loss += abs(use_pnl)

    net_pf = total_gross_win / total_gross_loss if total_gross_loss > 0 else float('inf')
    mean_early_pnl = np.mean(early_exit_pnls) if early_exit_pnls else 0

    return {
        'trades_affected': trades_affected,
        'losses_saved': losses_saved,
        'wins_killed': wins_killed,
        'mean_early_pnl': mean_early_pnl,
        'net_pf': net_pf,
    }

out("| Strategy | Trades affected | Losses saved | Wins killed | Mean PnL early exits | Net PF |")
out("|----------|:---:|:---:|:---:|:---:|:---:|")
for depth, label in [(0, "Exit at opposite edge"), (10, "Exit at opp edge + 10t"), (25, "Exit at opp edge + 25t")]:
    r = simulate_opp_edge_exit(depth)
    out(f"| {label} | {r['trades_affected']} | {r['losses_saved']} | {r['wins_killed']} | {r['mean_early_pnl']:.1f} | {r['net_pf']:.2f} |")

# 3D) Penetration stall detection (battleground only)
out()
out("### 3D) Penetration Stall Detection (Battleground, MAE 50-150t)")
out()
out("⚠️ LOW CONFIDENCE: 9 losers = 3 unique touch events × modes")
out()

bg = df[(df['mae'] >= 50) & (df['mae'] <= 150)].copy()
bg_w = bg[bg['WL'] == 'W']
bg_l = bg[bg['WL'] == 'L']

out("| Metric | Winners (n={}) | Losers (n={}) |".format(len(bg_w), len(bg_l)))
out("|--------|---------|--------|")

# Mean/median stall bars after max pen before 25t reversal
w_stall = bg_w['stall_bars_after_max_pen'].dropna()
l_stall = bg_l['stall_bars_after_max_pen'].dropna()
out(f"| Mean bars at max pen before 25t reversal | {w_stall.mean():.1f} | {l_stall.mean():.1f} |")
out(f"| Median bars | {w_stall.median():.1f} | {l_stall.median():.1f} |")

# % stalled > 5 bars
w_stall5 = (w_stall > 5).mean() * 100 if len(w_stall) > 0 else 0
l_stall5 = (l_stall > 5).mean() * 100 if len(l_stall) > 0 else 0
out(f"| % stalled > 5 bars before reversing | {w_stall5:.0f}% | {l_stall5:.0f}% |")

# % that drove through without any stall (bounce_25t_after_max == 0)
w_no_bounce = (bg_w['bounce_25t_after_max'] == 0).mean() * 100 if len(bg_w) > 0 else 0
l_no_bounce = (bg_l['bounce_25t_after_max'] == 0).mean() * 100 if len(bg_l) > 0 else 0
out(f"| % drove through without 25t bounce | {w_no_bounce:.0f}% | {l_no_bounce:.0f}% |")

# 3E) MFE timing profile
out()
out("### 3E) MFE Timing Profile")
out()
out("**All trades:**")
out()
out("| Bars after entry | Mean MFE (winners) | Mean MFE (losers) | % reached T1 (winners) | % reached T1 (losers) |")
out("|:---:|:---:|:---:|:---:|:---:|")

for nb in [10, 20, 30, 50, 100]:
    col = f'mfe_at_{nb}bar'
    w_mfe = winners[col].dropna()
    l_mfe = losers[col].dropna()

    # % reached T1 by this bar: check if MFE >= T1 by bar nb
    # T1 is 40 for CT, 60 for WT — use per-trade
    w_reached_t1 = 0
    w_total_t1 = 0
    l_reached_t1 = 0
    l_total_t1 = 0
    for subset, is_winner in [(winners, True), (losers, False)]:
        for idx in subset.index:
            mfe_val = subset.loc[idx, col]
            t1 = 40 if subset.loc[idx, 'trend_label'] == 'CT' else 60
            if pd.notna(mfe_val):
                if is_winner:
                    w_total_t1 += 1
                    if mfe_val >= t1:
                        w_reached_t1 += 1
                else:
                    l_total_t1 += 1
                    if mfe_val >= t1:
                        l_reached_t1 += 1

    w_t1_pct = w_reached_t1 / w_total_t1 * 100 if w_total_t1 > 0 else 0
    l_t1_pct = l_reached_t1 / l_total_t1 * 100 if l_total_t1 > 0 else 0

    out(f"| {nb} bars | {w_mfe.mean():.1f}t | {l_mfe.mean():.1f}t | {w_t1_pct:.0f}% | {l_t1_pct:.0f}% |")

# Split by CT/WT
for trend in ['CT', 'WT']:
    t1_val = 40 if trend == 'CT' else 60
    tw = df[(df['WL'] == 'W') & (df['trend_label'] == trend)]
    tl = df[(df['WL'] == 'L') & (df['trend_label'] == trend)]

    out(f"\n**{trend} trades (T1={t1_val}t):**")
    out()
    out("| Bars | Mean MFE (W) | Mean MFE (L) | % W reached T1 | % L reached T1 |")
    out("|:---:|:---:|:---:|:---:|:---:|")

    for nb in [10, 20, 30, 50, 100]:
        col = f'mfe_at_{nb}bar'
        w_mfe = tw[col].dropna()
        l_mfe = tl[col].dropna()
        w_t1_pct = (w_mfe >= t1_val).mean() * 100 if len(w_mfe) > 0 else 0
        l_t1_pct = (l_mfe >= t1_val).mean() * 100 if len(l_mfe) > 0 else 0
        out(f"| {nb} | {w_mfe.mean():.1f}t | {l_mfe.mean():.1f}t | {w_t1_pct:.0f}% | {l_t1_pct:.0f}% |")

# ══════════════════════════════════════════════════════════════════════
# SECTION 4: EXIT RE-OPTIMIZATION WITH 5t ENTRY
# ══════════════════════════════════════════════════════════════════════
out()
out("---")
out()
out("## SECTION 4: EXIT RE-OPTIMIZATION WITH 5t ENTRY")
out()

# Compute 5t limit entry for CT
# For CT LONG: limit entry = market_entry - 5*TICK_SIZE (buy lower)
# For CT SHORT: limit entry = market_entry + 5*TICK_SIZE (sell higher)
# Check if limit fills: check if price reaches the limit level on entry bar or subsequent bars

print("Computing 5t limit entries for CT...")

df['entry_5t'] = df['entry_price'].copy()  # default: same as market
df['fills_5t'] = True  # default: fills
df['entry_5t_bar'] = df['entry_bar_idx'].copy()

FILL_WINDOW = 10  # bars to wait for 5t limit fill

ct_mask = df['trend_label'] == 'CT'

for i in df[ct_mask].index:
    entry_bar = df.loc[i, 'entry_bar_idx']
    if entry_bar < 0:
        df.loc[i, 'fills_5t'] = False
        continue
    entry_price = df.loc[i, 'entry_price']
    direction = df.loc[i, 'direction']

    if direction == 'LONG':
        limit_price = entry_price - 5 * TICK_SIZE
    else:
        limit_price = entry_price + 5 * TICK_SIZE

    filled = False
    fill_bar = entry_bar

    # Check entry bar first (intrabar fill)
    for b in range(entry_bar, min(entry_bar + FILL_WINDOW, n_bars)):
        if direction == 'LONG' and bar_low[b] <= limit_price:
            filled = True
            fill_bar = b
            break
        elif direction == 'SHORT' and bar_high[b] >= limit_price:
            filled = True
            fill_bar = b
            break

    df.loc[i, 'fills_5t'] = filled
    if filled:
        df.loc[i, 'entry_5t'] = limit_price
        df.loc[i, 'entry_5t_bar'] = fill_bar
    else:
        df.loc[i, 'fills_5t'] = False

ct_fills = df[ct_mask & df['fills_5t']].copy()
ct_nofill = df[ct_mask & ~df['fills_5t']].copy()
wt_all = df[df['trend_label'] == 'WT'].copy()

out(f"CT trades: {ct_mask.sum()} total, {len(ct_fills)} fill 5t ({len(ct_fills)/ct_mask.sum()*100:.0f}%), {len(ct_nofill)} skipped")
out(f"WT trades: {len(wt_all)} (all at market entry)")
out()

# Helper: run simulation on a set of trades with given params
def run_sim_set(trade_indices, use_5t_entry, t1, t2, stop, tc, is_zone_rel=False, leg_split=True):
    """Run 2-leg (if leg_split) or 1-leg simulation. Returns DataFrame of results."""
    results = []
    for i in trade_indices:
        if use_5t_entry and df.loc[i, 'trend_label'] == 'CT':
            entry_bar = int(df.loc[i, 'entry_5t_bar'])
            entry_price = df.loc[i, 'entry_5t']
        else:
            entry_bar = int(df.loc[i, 'entry_bar_idx'])
            entry_price = df.loc[i, 'entry_price']

        if entry_bar < 0 or entry_bar >= n_bars:
            continue

        direction = df.loc[i, 'direction']
        zone_w = df.loc[i, 'ZoneWidthTicks'] if is_zone_rel else None

        if is_zone_rel:
            if pd.isna(zone_w) or zone_w <= 0:
                continue
            actual_t1 = t1 * zone_w
            actual_t2 = t2 * zone_w if t2 is not None else None
            actual_stop = stop * zone_w
        else:
            actual_t1 = t1
            actual_t2 = t2
            actual_stop = stop

        if leg_split and actual_t2 is not None:
            res = simulate_2leg(entry_bar, entry_price, direction,
                               t1_ticks=actual_t1, t2_ticks=actual_t2,
                               stop_ticks=actual_stop, timecap=tc)
        else:
            res = simulate_1leg(entry_bar, entry_price, direction,
                               target_ticks=actual_t1, stop_ticks=actual_stop, timecap=tc)

        res['trade_id'] = df.loc[i, 'trade_id']
        res['net_pnl'] = res['raw_pnl'] - COST_TICKS
        res['trend_label'] = df.loc[i, 'trend_label']
        results.append(res)
    return pd.DataFrame(results) if results else pd.DataFrame()


def simulate_1leg(entry_bar_idx, entry_price, direction, target_ticks, stop_ticks, timecap):
    target_pts = target_ticks * TICK_SIZE
    stop_pts = stop_ticks * TICK_SIZE
    end_bar = min(entry_bar_idx + timecap, n_bars)
    for b in range(entry_bar_idx, end_bar):
        bh = b - entry_bar_idx + 1
        if direction == 'LONG':
            if bar_low[b] <= entry_price - stop_pts:
                return {'exit_type': 'STOP', 'raw_pnl': -stop_ticks, 'bars_held': bh, 't1_filled': False, 't2_filled': False}
            if bar_high[b] >= entry_price + target_pts:
                return {'exit_type': 'TARGET', 'raw_pnl': target_ticks, 'bars_held': bh, 't1_filled': True, 't2_filled': True}
        else:
            if bar_high[b] >= entry_price + stop_pts:
                return {'exit_type': 'STOP', 'raw_pnl': -stop_ticks, 'bars_held': bh, 't1_filled': False, 't2_filled': False}
            if bar_low[b] <= entry_price - target_pts:
                return {'exit_type': 'TARGET', 'raw_pnl': target_ticks, 'bars_held': bh, 't1_filled': True, 't2_filled': True}
    if end_bar > entry_bar_idx:
        if direction == 'LONG':
            cp = (bar_close[end_bar-1] - entry_price) / TICK_SIZE
        else:
            cp = (entry_price - bar_close[end_bar-1]) / TICK_SIZE
        return {'exit_type': 'TIMECAP', 'raw_pnl': cp, 'bars_held': timecap, 't1_filled': False, 't2_filled': False}
    return {'exit_type': 'TIMECAP', 'raw_pnl': 0, 'bars_held': 0, 't1_filled': False, 't2_filled': False}


def simulate_2leg(entry_bar_idx, entry_price, direction,
                  t1_ticks, t2_ticks, stop_ticks, timecap,
                  leg1_pct=0.67, leg2_pct=0.33):
    t1_pts = t1_ticks * TICK_SIZE
    t2_pts = t2_ticks * TICK_SIZE
    stop_pts = stop_ticks * TICK_SIZE
    t1_filled = False
    end_bar = min(entry_bar_idx + timecap, n_bars)
    for b in range(entry_bar_idx, end_bar):
        bh = b - entry_bar_idx + 1
        if direction == 'LONG':
            if bar_low[b] <= entry_price - stop_pts:
                if t1_filled:
                    return {'exit_type': 'T1+STOP', 'raw_pnl': leg1_pct*t1_ticks + leg2_pct*(-stop_ticks), 'bars_held': bh, 't1_filled': True, 't2_filled': False}
                else:
                    return {'exit_type': 'STOP', 'raw_pnl': -stop_ticks, 'bars_held': bh, 't1_filled': False, 't2_filled': False}
            fav = bar_high[b] - entry_price
        else:
            if bar_high[b] >= entry_price + stop_pts:
                if t1_filled:
                    return {'exit_type': 'T1+STOP', 'raw_pnl': leg1_pct*t1_ticks + leg2_pct*(-stop_ticks), 'bars_held': bh, 't1_filled': True, 't2_filled': False}
                else:
                    return {'exit_type': 'STOP', 'raw_pnl': -stop_ticks, 'bars_held': bh, 't1_filled': False, 't2_filled': False}
            fav = entry_price - bar_low[b]
        if not t1_filled and fav >= t1_pts:
            t1_filled = True
            if fav >= t2_pts:
                return {'exit_type': 'TARGET', 'raw_pnl': leg1_pct*t1_ticks + leg2_pct*t2_ticks, 'bars_held': bh, 't1_filled': True, 't2_filled': True}
        if t1_filled and fav >= t2_pts:
            return {'exit_type': 'TARGET', 'raw_pnl': leg1_pct*t1_ticks + leg2_pct*t2_ticks, 'bars_held': bh, 't1_filled': True, 't2_filled': True}
    if end_bar > entry_bar_idx:
        if direction == 'LONG':
            cp = (bar_close[end_bar-1] - entry_price) / TICK_SIZE
        else:
            cp = (entry_price - bar_close[end_bar-1]) / TICK_SIZE
        raw = (leg1_pct * t1_ticks + leg2_pct * cp) if t1_filled else cp
        return {'exit_type': 'TIMECAP', 'raw_pnl': raw, 'bars_held': timecap, 't1_filled': t1_filled, 't2_filled': False}
    return {'exit_type': 'TIMECAP', 'raw_pnl': 0, 'bars_held': 0, 't1_filled': False, 't2_filled': False}


def simulate_2leg_be(entry_bar_idx, entry_price, direction,
                     t1_ticks, t2_ticks, stop_ticks, timecap,
                     be_trigger_ticks,
                     leg1_pct=0.67, leg2_pct=0.33):
    """2-leg with BE step-up: after MFE >= be_trigger, stop moves to entry."""
    t1_pts = t1_ticks * TICK_SIZE
    t2_pts = t2_ticks * TICK_SIZE
    stop_pts = stop_ticks * TICK_SIZE
    be_pts = be_trigger_ticks * TICK_SIZE
    t1_filled = False
    be_active = False
    end_bar = min(entry_bar_idx + timecap, n_bars)

    for b in range(entry_bar_idx, end_bar):
        bh = b - entry_bar_idx + 1

        if direction == 'LONG':
            fav = bar_high[b] - entry_price
            adv_price = bar_low[b]
        else:
            fav = entry_price - bar_low[b]
            adv_price = bar_high[b]

        # Check if BE activates
        if not be_active and fav >= be_pts:
            be_active = True

        # Determine current stop level
        if be_active:
            current_stop_price = entry_price  # BE = entry
        else:
            if direction == 'LONG':
                current_stop_price = entry_price - stop_pts
            else:
                current_stop_price = entry_price + stop_pts

        # Check stop
        if direction == 'LONG':
            if adv_price <= current_stop_price:
                if be_active and current_stop_price == entry_price:
                    stop_pnl = 0  # BE exit
                else:
                    stop_pnl = -stop_ticks
                if t1_filled:
                    return {'exit_type': 'T1+BE' if be_active else 'T1+STOP',
                            'raw_pnl': leg1_pct*t1_ticks + leg2_pct*stop_pnl,
                            'bars_held': bh, 't1_filled': True, 't2_filled': False, 'be_fired': be_active}
                else:
                    return {'exit_type': 'BE' if be_active else 'STOP',
                            'raw_pnl': stop_pnl, 'bars_held': bh,
                            't1_filled': False, 't2_filled': False, 'be_fired': be_active}
        else:
            if adv_price >= current_stop_price:
                if be_active and current_stop_price == entry_price:
                    stop_pnl = 0
                else:
                    stop_pnl = -stop_ticks
                if t1_filled:
                    return {'exit_type': 'T1+BE' if be_active else 'T1+STOP',
                            'raw_pnl': leg1_pct*t1_ticks + leg2_pct*stop_pnl,
                            'bars_held': bh, 't1_filled': True, 't2_filled': False, 'be_fired': be_active}
                else:
                    return {'exit_type': 'BE' if be_active else 'STOP',
                            'raw_pnl': stop_pnl, 'bars_held': bh,
                            't1_filled': False, 't2_filled': False, 'be_fired': be_active}

        # Check targets
        if not t1_filled and fav >= t1_pts:
            t1_filled = True
            if fav >= t2_pts:
                return {'exit_type': 'TARGET', 'raw_pnl': leg1_pct*t1_ticks + leg2_pct*t2_ticks,
                        'bars_held': bh, 't1_filled': True, 't2_filled': True, 'be_fired': be_active}
        if t1_filled and fav >= t2_pts:
            return {'exit_type': 'TARGET', 'raw_pnl': leg1_pct*t1_ticks + leg2_pct*t2_ticks,
                    'bars_held': bh, 't1_filled': True, 't2_filled': True, 'be_fired': be_active}

    # Timecap
    if end_bar > entry_bar_idx:
        if direction == 'LONG':
            cp = (bar_close[end_bar-1] - entry_price) / TICK_SIZE
        else:
            cp = (entry_price - bar_close[end_bar-1]) / TICK_SIZE
        raw = (leg1_pct*t1_ticks + leg2_pct*cp) if t1_filled else cp
        return {'exit_type': 'TIMECAP', 'raw_pnl': raw, 'bars_held': timecap,
                't1_filled': t1_filled, 't2_filled': False, 'be_fired': be_active}
    return {'exit_type': 'TIMECAP', 'raw_pnl': 0, 'bars_held': 0,
            't1_filled': False, 't2_filled': False, 'be_fired': False}


def simulate_2leg_trail(entry_bar_idx, entry_price, direction,
                        t1_ticks, stop_ticks, timecap,
                        trail_ticks, t2_cap_ticks=None,
                        leg1_pct=0.67, leg2_pct=0.33):
    """2-leg with trail after T1: after T1 fills, trail remaining 33% with trail_ticks drawdown.
    If t2_cap_ticks is set, also exit at that fixed target (whichever comes first).
    """
    t1_pts = t1_ticks * TICK_SIZE
    stop_pts = stop_ticks * TICK_SIZE
    trail_pts = trail_ticks * TICK_SIZE
    t2_cap_pts = t2_cap_ticks * TICK_SIZE if t2_cap_ticks else None
    t1_filled = False
    high_water = 0.0  # max favorable since T1 fill (in points)
    end_bar = min(entry_bar_idx + timecap, n_bars)

    for b in range(entry_bar_idx, end_bar):
        bh = b - entry_bar_idx + 1

        if direction == 'LONG':
            fav = bar_high[b] - entry_price
            adv_price = bar_low[b]
        else:
            fav = entry_price - bar_low[b]
            adv_price = bar_high[b]

        # Pre-T1: check stop and T1
        if not t1_filled:
            if direction == 'LONG':
                if adv_price <= entry_price - stop_pts:
                    return {'exit_type': 'STOP', 'raw_pnl': -stop_ticks, 'bars_held': bh, 't1_filled': False, 't2_filled': False}
            else:
                if adv_price >= entry_price + stop_pts:
                    return {'exit_type': 'STOP', 'raw_pnl': -stop_ticks, 'bars_held': bh, 't1_filled': False, 't2_filled': False}

            if fav >= t1_pts:
                t1_filled = True
                high_water = fav

                # Check T2 cap on same bar
                if t2_cap_pts and fav >= t2_cap_pts:
                    return {'exit_type': 'TARGET', 'raw_pnl': leg1_pct*t1_ticks + leg2_pct*(t2_cap_ticks), 'bars_held': bh, 't1_filled': True, 't2_filled': True}
        else:
            # Post-T1: trail the remaining position
            if fav > high_water:
                high_water = fav

            # Trail stop: exit if price drops trail_pts from high water
            drawdown = high_water - fav
            if drawdown >= trail_pts:
                trail_exit_pnl = (high_water - trail_pts) / TICK_SIZE  # in ticks from entry
                # But we need to use actual bar price for the stop
                if direction == 'LONG':
                    trail_stop_price = entry_price + high_water - trail_pts
                    if bar_low[b] <= trail_stop_price:
                        pnl_ticks = (trail_stop_price - entry_price) / TICK_SIZE
                        return {'exit_type': 'TRAIL', 'raw_pnl': leg1_pct*t1_ticks + leg2_pct*pnl_ticks, 'bars_held': bh, 't1_filled': True, 't2_filled': False}
                else:
                    trail_stop_price = entry_price - high_water + trail_pts
                    if bar_high[b] >= trail_stop_price:
                        pnl_ticks = (entry_price - trail_stop_price) / TICK_SIZE
                        return {'exit_type': 'TRAIL', 'raw_pnl': leg1_pct*t1_ticks + leg2_pct*pnl_ticks, 'bars_held': bh, 't1_filled': True, 't2_filled': False}

            # Also check original stop (protects against gap through trail)
            if direction == 'LONG':
                if adv_price <= entry_price - stop_pts:
                    return {'exit_type': 'T1+STOP', 'raw_pnl': leg1_pct*t1_ticks + leg2_pct*(-stop_ticks), 'bars_held': bh, 't1_filled': True, 't2_filled': False}
            else:
                if adv_price >= entry_price + stop_pts:
                    return {'exit_type': 'T1+STOP', 'raw_pnl': leg1_pct*t1_ticks + leg2_pct*(-stop_ticks), 'bars_held': bh, 't1_filled': True, 't2_filled': False}

            # Check T2 cap
            if t2_cap_pts and fav >= t2_cap_pts:
                return {'exit_type': 'TARGET', 'raw_pnl': leg1_pct*t1_ticks + leg2_pct*t2_cap_ticks, 'bars_held': bh, 't1_filled': True, 't2_filled': True}

    # Timecap
    if end_bar > entry_bar_idx:
        if direction == 'LONG':
            cp = (bar_close[end_bar-1] - entry_price) / TICK_SIZE
        else:
            cp = (entry_price - bar_close[end_bar-1]) / TICK_SIZE
        raw = (leg1_pct*t1_ticks + leg2_pct*cp) if t1_filled else cp
        return {'exit_type': 'TIMECAP', 'raw_pnl': raw, 'bars_held': timecap, 't1_filled': t1_filled, 't2_filled': False}
    return {'exit_type': 'TIMECAP', 'raw_pnl': 0, 'bars_held': 0, 't1_filled': False, 't2_filled': False}


def report_line(label, rdf):
    if len(rdf) == 0:
        return f"| {label} | 0 | — | — | — | — |"
    w = rdf[rdf['net_pnl'] > 0]
    l = rdf[rdf['net_pnl'] <= 0]
    gw = w['net_pnl'].sum()
    gl = l['net_pnl'].abs().sum()
    pf = gw / gl if gl > 0 else float('inf')
    wr = len(w) / len(rdf) * 100
    ev = rdf['net_pnl'].mean()
    return f"| {label} | {len(rdf)} | {wr:.1f}% | {pf:.2f} | {ev:.1f} | {rdf['net_pnl'].sum():.0f} |"


# ── 4A) Single-leg sweep (FIXED) ─────────────────────────────────────
out("### 4A) Single-Leg Sweep — FIXED Framework (5t CT entry)")
out()
out("| Target | Stop | TC | CT WR | CT PF | CT n | WT WR | WT PF | WT n |")
out("|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|")

ct_5t_idx = df[ct_mask & df['fills_5t']].index
wt_idx = df[df['trend_label'] == 'WT'].index

fixed_sweeps = [
    (40, 100, 160), (40, 120, 160), (40, 150, 160), (40, 190, 160),
    (60, 100, 160), (60, 120, 160), (60, 150, 160),
    (80, 100, 160), (80, 150, 160),
]

for tgt, stp, tc in fixed_sweeps:
    # CT with 5t entry
    ct_results = []
    for i in ct_5t_idx:
        entry_bar = int(df.loc[i, 'entry_5t_bar'])
        entry_price = df.loc[i, 'entry_5t']
        direction = df.loc[i, 'direction']
        if entry_bar < 0 or entry_bar >= n_bars:
            continue
        res = simulate_1leg(entry_bar, entry_price, direction, tgt, stp, tc)
        res['net_pnl'] = res['raw_pnl'] - COST_TICKS
        ct_results.append(res)
    ct_df = pd.DataFrame(ct_results) if ct_results else pd.DataFrame()

    # WT at market
    wt_results = []
    for i in wt_idx:
        entry_bar = int(df.loc[i, 'entry_bar_idx'])
        entry_price = df.loc[i, 'entry_price']
        direction = df.loc[i, 'direction']
        if entry_bar < 0 or entry_bar >= n_bars:
            continue
        res = simulate_1leg(entry_bar, entry_price, direction, tgt, stp, tc)
        res['net_pnl'] = res['raw_pnl'] - COST_TICKS
        wt_results.append(res)
    wt_df = pd.DataFrame(wt_results) if wt_results else pd.DataFrame()

    def stats(rdf):
        if len(rdf) == 0:
            return 0, 0, 0
        w = rdf[rdf['net_pnl'] > 0]
        l = rdf[rdf['net_pnl'] <= 0]
        wr = len(w)/len(rdf)*100
        pf = w['net_pnl'].sum() / l['net_pnl'].abs().sum() if l['net_pnl'].abs().sum() > 0 else float('inf')
        return wr, pf, len(rdf)

    ct_wr, ct_pf, ct_n = stats(ct_df)
    wt_wr, wt_pf, wt_n = stats(wt_df)
    out(f"| {tgt}t | {stp}t | {tc} | {ct_wr:.1f}% | {ct_pf:.2f} | {ct_n} | {wt_wr:.1f}% | {wt_pf:.2f} | {wt_n} |")

# ── 4A2) Single-leg sweep (ZONE-RELATIVE) ────────────────────────────
out()
out("### 4A2) Single-Leg Sweep — ZONE-RELATIVE Framework (5t CT entry)")
out()
out("| Target | Stop | TC | CT WR | CT PF | CT n | WT WR | WT PF | WT n |")
out("|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|")

zr_sweeps = [
    (0.5, 1.0), (0.5, 1.5), (0.5, 2.0),
    (0.75, 1.5), (0.75, 2.0),
    (1.0, 1.5), (1.0, 2.0), (1.0, 2.5),
]

for tgt_m, stp_m in zr_sweeps:
    ct_results = []
    for i in ct_5t_idx:
        entry_bar = int(df.loc[i, 'entry_5t_bar'])
        entry_price = df.loc[i, 'entry_5t']
        direction = df.loc[i, 'direction']
        zw = df.loc[i, 'ZoneWidthTicks']
        if entry_bar < 0 or entry_bar >= n_bars or pd.isna(zw) or zw <= 0:
            continue
        res = simulate_1leg(entry_bar, entry_price, direction, tgt_m*zw, stp_m*zw, 160)
        res['net_pnl'] = res['raw_pnl'] - COST_TICKS
        ct_results.append(res)
    ct_df = pd.DataFrame(ct_results) if ct_results else pd.DataFrame()

    wt_results = []
    for i in wt_idx:
        entry_bar = int(df.loc[i, 'entry_bar_idx'])
        entry_price = df.loc[i, 'entry_price']
        direction = df.loc[i, 'direction']
        zw = df.loc[i, 'ZoneWidthTicks']
        if entry_bar < 0 or entry_bar >= n_bars or pd.isna(zw) or zw <= 0:
            continue
        res = simulate_1leg(entry_bar, entry_price, direction, tgt_m*zw, stp_m*zw, 160)
        res['net_pnl'] = res['raw_pnl'] - COST_TICKS
        wt_results.append(res)
    wt_df = pd.DataFrame(wt_results) if wt_results else pd.DataFrame()

    ct_wr, ct_pf, ct_n = stats(ct_df)
    wt_wr, wt_pf, wt_n = stats(wt_df)
    out(f"| {tgt_m}x zw | {stp_m}x zw | 160 | {ct_wr:.1f}% | {ct_pf:.2f} | {ct_n} | {wt_wr:.1f}% | {wt_pf:.2f} | {wt_n} |")

# ── 4B) BE step-up ────────────────────────────────────────────────────
out()
out("### 4B) Breakeven Step-Up")
out()

def run_be_sweep(trade_indices, use_5t, t1, t2, stop, tc, be_triggers, is_zone_rel, label_prefix):
    """Run BE sweep and print results."""
    # First run baseline (no BE)
    baseline_results = []
    for i in trade_indices:
        if use_5t and df.loc[i, 'trend_label'] == 'CT':
            eb = int(df.loc[i, 'entry_5t_bar'])
            ep = df.loc[i, 'entry_5t']
        else:
            eb = int(df.loc[i, 'entry_bar_idx'])
            ep = df.loc[i, 'entry_price']
        if eb < 0 or eb >= n_bars:
            continue
        direction = df.loc[i, 'direction']
        zw = df.loc[i, 'ZoneWidthTicks']
        if is_zone_rel and (pd.isna(zw) or zw <= 0):
            continue
        at1 = t1 * zw if is_zone_rel else t1
        at2 = t2 * zw if is_zone_rel else t2
        astp = stop * zw if is_zone_rel else stop
        res = simulate_2leg(eb, ep, direction, at1, at2, astp, tc)
        res['net_pnl'] = res['raw_pnl'] - COST_TICKS
        res['trend_label'] = df.loc[i, 'trend_label']
        baseline_results.append(res)
    bl_df = pd.DataFrame(baseline_results) if baseline_results else pd.DataFrame()

    if len(bl_df) == 0:
        return

    bl_w = bl_df[bl_df['net_pnl'] > 0]
    bl_l = bl_df[bl_df['net_pnl'] <= 0]
    bl_pf = bl_w['net_pnl'].sum() / bl_l['net_pnl'].abs().sum() if bl_l['net_pnl'].abs().sum() > 0 else float('inf')

    out(f"**{label_prefix}** (baseline PF = {bl_pf:.2f}):")
    out()
    out("| BE trigger | BE fires | Stopped at BE | Hit target | Net PF | PF Δ |")
    out("|:---:|:---:|:---:|:---:|:---:|:---:|")

    for be_trig in be_triggers:
        be_results = []
        for i in trade_indices:
            if use_5t and df.loc[i, 'trend_label'] == 'CT':
                eb = int(df.loc[i, 'entry_5t_bar'])
                ep = df.loc[i, 'entry_5t']
            else:
                eb = int(df.loc[i, 'entry_bar_idx'])
                ep = df.loc[i, 'entry_price']
            if eb < 0 or eb >= n_bars:
                continue
            direction = df.loc[i, 'direction']
            zw = df.loc[i, 'ZoneWidthTicks']
            if is_zone_rel and (pd.isna(zw) or zw <= 0):
                continue
            at1 = t1 * zw if is_zone_rel else t1
            at2 = t2 * zw if is_zone_rel else t2
            astp = stop * zw if is_zone_rel else stop
            abe = be_trig * zw if is_zone_rel else be_trig
            res = simulate_2leg_be(eb, ep, direction, at1, at2, astp, tc, abe)
            res['net_pnl'] = res['raw_pnl'] - COST_TICKS
            res['trend_label'] = df.loc[i, 'trend_label']
            be_results.append(res)
        be_df = pd.DataFrame(be_results) if be_results else pd.DataFrame()
        if len(be_df) == 0:
            continue

        be_fired = be_df[be_df.get('be_fired', False) == True] if 'be_fired' in be_df else pd.DataFrame()
        be_stopped = be_df[be_df['exit_type'].isin(['BE', 'T1+BE'])]
        targets = be_df[be_df['exit_type'] == 'TARGET']

        w = be_df[be_df['net_pnl'] > 0]
        l = be_df[be_df['net_pnl'] <= 0]
        pf = w['net_pnl'].sum() / l['net_pnl'].abs().sum() if l['net_pnl'].abs().sum() > 0 else float('inf')
        pf_delta = pf - bl_pf

        if is_zone_rel:
            trig_label = f"{be_trig}x zw"
        else:
            trig_label = f"{be_trig}t"
        out(f"| {trig_label} | {len(be_fired)} | {len(be_stopped)} | {len(targets)} | {pf:.2f} | {pf_delta:+.2f} |")
    out()


# 5t CT + market WT combined
all_5t_idx = list(ct_5t_idx) + list(wt_idx)

# FIXED framework BE
out("#### FIXED Framework")
out()
run_be_sweep(all_5t_idx, True, 40, 80, 190, 160, [10, 20, 30, 40], False, "ALL (CT: 40/80/190, WT: 60/80/240)")

# Split CT/WT for fixed
out("CT only:")
out()
run_be_sweep(list(ct_5t_idx), True, 40, 80, 190, 160, [10, 20, 30, 40], False, "CT (40/80/190)")
out("WT only:")
out()
run_be_sweep(list(wt_idx), False, 60, 80, 240, 160, [10, 20, 30, 40], False, "WT (60/80/240)")

# ZONE-REL framework BE
out("#### ZONE-RELATIVE Framework")
out()
run_be_sweep(all_5t_idx, True, 0.5, 1.0, 1.5, 160, [0.1, 0.2, 0.25, 0.5], True, "ALL (0.5x/1.0x/1.5x)")
out("CT only:")
out()
run_be_sweep(list(ct_5t_idx), True, 0.5, 1.0, 1.5, 160, [0.1, 0.2, 0.25, 0.5], True, "CT (0.5x/1.0x/1.5x)")
out("WT only:")
out()
run_be_sweep(list(wt_idx), False, 0.5, 1.0, 1.5, 160, [0.1, 0.2, 0.25, 0.5], True, "WT (0.5x/1.0x/1.5x)")

# ── 4C) Trail after T1 ───────────────────────────────────────────────
out("### 4C) Trail After T1")
out()

def run_trail_sweep(trade_indices, use_5t, t1, stop, tc, trail_configs, is_zone_rel, label_prefix):
    """Run trail sweep and print results."""
    # Baseline: fixed T2
    t2_fixed = t1 * 2 if is_zone_rel else (80 if t1 <= 40 else 80)  # T2 = 80t fixed or 1.0x zw for zone-rel

    baseline_results = []
    for i in trade_indices:
        if use_5t and df.loc[i, 'trend_label'] == 'CT':
            eb = int(df.loc[i, 'entry_5t_bar'])
            ep = df.loc[i, 'entry_5t']
        else:
            eb = int(df.loc[i, 'entry_bar_idx'])
            ep = df.loc[i, 'entry_price']
        if eb < 0 or eb >= n_bars:
            continue
        direction = df.loc[i, 'direction']
        zw = df.loc[i, 'ZoneWidthTicks']
        if is_zone_rel and (pd.isna(zw) or zw <= 0):
            continue
        at1 = t1 * zw if is_zone_rel else t1
        at2 = t2_fixed * zw if is_zone_rel else t2_fixed
        astp = stop * zw if is_zone_rel else stop
        res = simulate_2leg(eb, ep, direction, at1, at2, astp, tc)
        res['net_pnl'] = res['raw_pnl'] - COST_TICKS
        baseline_results.append(res)
    bl_df = pd.DataFrame(baseline_results) if baseline_results else pd.DataFrame()
    if len(bl_df) == 0:
        return

    bl_t1_hits = bl_df[bl_df['t1_filled'] == True]
    bl_t2_hits = bl_df[bl_df['t2_filled'] == True]
    bl_t2_rate = len(bl_t2_hits)/len(bl_t1_hits)*100 if len(bl_t1_hits) > 0 else 0
    bl_leg2_pnl = bl_df['net_pnl'].mean()  # overall avg
    bl_gw = bl_df[bl_df['net_pnl']>0]['net_pnl'].sum()
    bl_gl = bl_df[bl_df['net_pnl']<=0]['net_pnl'].abs().sum()
    bl_pf = bl_gw / bl_gl if bl_gl > 0 else float('inf')

    if is_zone_rel:
        base_label = f"Fixed T2={t2_fixed}x zw"
    else:
        base_label = f"Fixed T2={t2_fixed}t"

    out(f"**{label_prefix}** (baseline PF={bl_pf:.2f}):")
    out()
    out("| Trail type | T2/Trail fills | Mean PnL | Net PF | vs baseline |")
    out("|:---:|:---:|:---:|:---:|:---:|")
    out(f"| {base_label} (baseline) | {bl_t2_rate:.0f}% | {bl_leg2_pnl:.1f} | {bl_pf:.2f} | — |")

    for trail_ticks_or_mult, t2_cap_or_mult, label in trail_configs:
        trail_results = []
        for i in trade_indices:
            if use_5t and df.loc[i, 'trend_label'] == 'CT':
                eb = int(df.loc[i, 'entry_5t_bar'])
                ep = df.loc[i, 'entry_5t']
            else:
                eb = int(df.loc[i, 'entry_bar_idx'])
                ep = df.loc[i, 'entry_price']
            if eb < 0 or eb >= n_bars:
                continue
            direction = df.loc[i, 'direction']
            zw = df.loc[i, 'ZoneWidthTicks']
            if is_zone_rel and (pd.isna(zw) or zw <= 0):
                continue
            at1 = t1 * zw if is_zone_rel else t1
            astp = stop * zw if is_zone_rel else stop
            atrail = trail_ticks_or_mult * zw if is_zone_rel else trail_ticks_or_mult
            at2cap = t2_cap_or_mult * zw if (is_zone_rel and t2_cap_or_mult is not None) else t2_cap_or_mult

            res = simulate_2leg_trail(eb, ep, direction, at1, astp, tc, atrail, at2cap)
            res['net_pnl'] = res['raw_pnl'] - COST_TICKS
            trail_results.append(res)

        tr_df = pd.DataFrame(trail_results) if trail_results else pd.DataFrame()
        if len(tr_df) == 0:
            continue

        t1_hits = tr_df[tr_df['t1_filled'] == True]
        t2_hits = tr_df[tr_df['t2_filled'] == True]
        trail_hits = tr_df[tr_df['exit_type'] == 'TRAIL']
        fill_rate = (len(t2_hits) + len(trail_hits)) / len(t1_hits) * 100 if len(t1_hits) > 0 else 0
        mean_pnl = tr_df['net_pnl'].mean()
        gw = tr_df[tr_df['net_pnl']>0]['net_pnl'].sum()
        gl = tr_df[tr_df['net_pnl']<=0]['net_pnl'].abs().sum()
        pf = gw / gl if gl > 0 else float('inf')
        vs = f"{pf - bl_pf:+.2f}"

        out(f"| {label} | {fill_rate:.0f}% | {mean_pnl:.1f} | {pf:.2f} | {vs} |")
    out()

# FIXED framework trail
out("#### FIXED Framework")
out()

fixed_trail_configs = [
    (20, 80, "Trail 20t from HW, cap 80t"),
    (30, 80, "Trail 30t from HW, cap 80t"),
    (40, 80, "Trail 40t from HW, cap 80t"),
    (50, 80, "Trail 50t from HW, cap 80t"),
    (30, None, "Trail 30t, no cap"),
]

run_trail_sweep(list(ct_5t_idx), True, 40, 190, 160, fixed_trail_configs, False, "CT (T1=40t, Stop=190t)")
run_trail_sweep(list(wt_idx), False, 60, 240, 160, fixed_trail_configs, False, "WT (T1=60t, Stop=240t)")

# ZONE-REL framework trail
out("#### ZONE-RELATIVE Framework")
out()

zr_trail_configs = [
    (0.1, 1.0, "Trail 0.10x zw, cap 1.0x"),
    (0.15, 1.0, "Trail 0.15x zw, cap 1.0x"),
    (0.2, 1.0, "Trail 0.20x zw, cap 1.0x"),
    (0.25, 1.0, "Trail 0.25x zw, cap 1.0x"),
    (0.15, None, "Trail 0.15x zw, no cap"),
]

run_trail_sweep(list(ct_5t_idx), True, 0.5, 1.5, 160, zr_trail_configs, True, "CT (T1=0.5x, Stop=1.5x)")
run_trail_sweep(list(wt_idx), False, 0.5, 1.5, 160, zr_trail_configs, True, "WT (T1=0.5x, Stop=1.5x)")


# ══════════════════════════════════════════════════════════════════════
# SAVE UPDATED CSV
# ══════════════════════════════════════════════════════════════════════
print("\nSaving updated CSV...")

# Add new columns to invest CSV by joining on trade_id
new_col_names = list(new_cols.keys()) + ['fills_5t', 'entry_5t', 'entry_5t_bar']
for col in new_col_names:
    if col in df.columns:
        invest[col] = df.set_index('trade_id').loc[invest['trade_id'].values, col].values

assert len(invest) == 312, f"Expected 312 rows, got {len(invest)}"
invest.to_csv(INVEST_CSV, index=False)
print(f"  Saved {len(invest)} rows, {len(invest.columns)} columns to {INVEST_CSV}")
print(f"  New columns added: {new_col_names}")

# Save markdown
with open(OUTPUT_MD, 'w', encoding='utf-8') as f:
    f.write(md_buffer.getvalue())
print(f"  Results saved to {OUTPUT_MD}")

print("\nDone — Part 2 of 3 complete.")
