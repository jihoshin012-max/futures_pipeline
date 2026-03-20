# archetype: rotational
"""V1.4 + 4C Equity Dashboard — comprehensive performance analytics.

Generates equity curve, drawdown, daily PnL distribution, rolling stats,
and summary tables for both P1 and P2b periods using the final validated config.

Saves all outputs to shared/archetypes/rotational/v14_dashboard/

Usage:
    python plot_v14_equity_dashboard.py
"""

import sys
import json
import time
import datetime as dt_mod
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from matplotlib.patches import FancyBboxPatch
import matplotlib.dates as mdates

_REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from shared.data_loader import load_bars
from run_seed_investigation import (
    simulate_daily_flatten, load_data,
    COST_TICKS, TICK_SIZE, RTH_OPEN_TOD, FLATTEN_TOD, RESUME_TOD,
    _P1_START, _P1_END, FLATTEN_CAP, MAX_LEVELS,
)
from run_phase1_sweep import (
    build_zigzag_lookup, make_adaptive_lookup, make_std_lookup, analyze_step2,
)
from run_p2a_validation import (
    build_combined_speedread, build_combined_zigzag_lookup,
    SEED_DIST, STEP_DIST_INIT, ADD_DIST_INIT, SEED_START, SR_THRESHOLD,
    EXCLUDE_HOURS,
)

_OUTPUT_DIR = Path(__file__).parent / "v14_dashboard"


def _to_date_str(val):
    """Safely convert a date/datetime/Timestamp to YYYY-MM-DD string."""
    if hasattr(val, 'date') and callable(val.date):
        return str(val.date())
    return str(val)
_P2_1TICK = _REPO / "stages/01-data/data/bar_data/tick/NQ_BarData_1tick_rot_P2.csv"

# P2b dates
P2B_RTH_FIRST = dt_mod.date(2026, 2, 2)
P2B_RTH_LAST = dt_mod.date(2026, 3, 13)
P2B_DATA_START = dt_mod.date(2026, 2, 1)
P2B_DATA_END = dt_mod.date(2026, 3, 13)

MAX_CAP_WALKS = 2

# P2a dates (loaded from saved JSON — already consumed, cannot re-run)
_P2A_SESSIONS_JSON = Path(__file__).parent / "phase1_results" / "p2a_validation_sessions.json"
_P2A_CYCLES_PARQUET = Path(__file__).parent / "phase1_results" / "p2a_validation_cycles.parquet"

# NQ contract specs
TICK_VALUE_USD = 5.0  # $5 per tick for NQ


def run_sim(prices, tod_secs, sr_roll50, dts, adaptive, std_lu):
    """Run V1.4 + 4C stop."""
    return simulate_daily_flatten(
        prices, tod_secs, sr_roll50, dts,
        seed_dist=SEED_DIST, step_dist=STEP_DIST_INIT, add_dist=ADD_DIST_INIT,
        flatten_reseed_cap=FLATTEN_CAP, max_levels=MAX_LEVELS,
        seed_sr_thresh=SR_THRESHOLD, rev_sr_thresh=SR_THRESHOLD,
        watch_mode='rth_open', cap_action='walk',
        seed_start_tod=SEED_START,
        adaptive_lookup=adaptive,
        max_adverse_sigma=None,
        max_cap_walks=MAX_CAP_WALKS,
        std_lookup=std_lu,
    )


def build_session_df(sim, label):
    """Build session-level DataFrame from simulation output."""
    trades = pd.DataFrame(sim['trade_records'])
    cycles = pd.DataFrame(sim['cycle_records'])
    if len(cycles) == 0:
        return None

    entry_trades = trades[trades['action'].isin(['SEED', 'REVERSAL'])]
    ce = entry_trades.groupby('cycle_id')['datetime'].first().reset_index()
    ce.columns = ['cycle_id', 'entry_dt']
    cycles = cycles.merge(ce, on='cycle_id', how='left')
    cycles['hour'] = pd.to_datetime(cycles['entry_dt']).dt.hour
    cf = cycles[~cycles['hour'].isin(EXCLUDE_HOURS)].copy()

    if len(cf) == 0:
        return None

    valid_ids = set(cf['cycle_id'])
    tf = trades[trades['cycle_id'].isin(valid_ids)]
    cc = tf.groupby('cycle_id')['cost_ticks'].sum()
    cf['cost'] = cf['cycle_id'].map(cc).fillna(0)
    cf['net_1t'] = cf['gross_pnl_ticks'] - cf['cost']

    # Session-level aggregation
    session_pnl = cf.groupby('session_id')['net_1t'].sum()
    session_cycles = cf.groupby('session_id').size()
    session_gross = cf.groupby('session_id')['gross_pnl_ticks'].sum()

    # Get dates
    trades['dt'] = pd.to_datetime(trades['datetime'])
    rth_trades = trades[(trades['dt'].dt.hour >= 9) & (trades['dt'].dt.hour < 17)]
    date_map = (rth_trades.groupby('session_id')['dt']
                .first().apply(lambda x: x.date() if hasattr(x, 'date') and callable(x.date) else x).to_dict())

    all_sids = range(1, sim['total_sessions'] + 1)
    rows = []
    for sid in all_sids:
        rows.append({
            'session_id': sid,
            'date': date_map.get(sid),
            'net_pnl': float(session_pnl.get(sid, 0)),
            'gross_pnl': float(session_gross.get(sid, 0)),
            'cycles': int(session_cycles.get(sid, 0)),
            'period': label,
        })
    return pd.DataFrame(rows), cf


def main():
    t0 = time.time()
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # ================================================================
    # 1. Run P1 simulation (V1.4 + 4C stops)
    # ================================================================
    print("=" * 60)
    print("Loading P1 data and running V1.4 + 4C simulation...")
    print("=" * 60)

    prices_p1, tod_p1, sr_p1, dts_p1 = load_data(period='full_p1', use_speedread=True)
    zz_p1 = build_zigzag_lookup()
    adaptive_p1 = make_adaptive_lookup(zz_p1, 5, 2)
    std_p1 = make_std_lookup(zz_p1)

    cs = np.cumsum(np.insert(sr_p1, 0, 0))
    w = 50
    sr_roll50_p1 = np.empty_like(sr_p1)
    sr_roll50_p1[:w] = cs[1:w + 1] / np.arange(1, w + 1)
    sr_roll50_p1[w:] = (cs[w + 1:] - cs[1:len(sr_p1) - w + 1]) / w

    sim_p1 = run_sim(prices_p1, tod_p1, sr_roll50_p1, dts_p1, adaptive_p1, std_p1)
    p1_df, p1_cycles = build_session_df(sim_p1, "P1")
    print(f"  P1: {len(p1_df)} sessions, {len(p1_cycles)} cycles")

    # ================================================================
    # 2. Run FULL P2 simulation (V1.4 + 4C stops — same final config)
    # ================================================================
    print("\n" + "=" * 60)
    print("Loading full P2 data and running V1.4 + 4C simulation...")
    print("  (Final config applied uniformly — no splicing)")
    print("=" * 60)

    sr_bar_dts, sr_composite = build_combined_speedread()
    zz_lookup = build_combined_zigzag_lookup()
    adaptive = make_adaptive_lookup(zz_lookup, 5, 2)
    std_lu = make_std_lookup(zz_lookup)

    # Load ALL P2 tick data (no date filter — full P2 file)
    print("  Loading P2 1-tick data (full file)...")
    tick_bars = load_bars(str(_P2_1TICK))
    tick_data = tick_bars.reset_index(drop=True)
    print(f"    Total P2 ticks: {len(tick_data):,}")

    prices = tick_data['Last'].values.astype(np.float64)
    dts = tick_data['datetime'].values
    hours = tick_data['datetime'].dt.hour.values.astype(np.int32)
    minutes = tick_data['datetime'].dt.minute.values.astype(np.int32)
    seconds = tick_data['datetime'].dt.second.values.astype(np.int32)
    tod_secs = hours * 3600 + minutes * 60 + seconds

    sr_ts = sr_bar_dts.astype('int64') // 10**9
    sr_comp = sr_composite.astype(np.float64)
    tick_ts = dts.astype('int64') // 10**9
    sr_idx = np.clip(np.searchsorted(sr_ts, tick_ts, side='right') - 1,
                     0, len(sr_comp) - 1)
    tick_sr = sr_comp[sr_idx]
    tick_sr = np.nan_to_num(tick_sr, nan=-1.0)

    cs2 = np.cumsum(np.insert(tick_sr, 0, 0))
    sr_roll50 = np.empty_like(tick_sr)
    sr_roll50[:w] = cs2[1:w + 1] / np.arange(1, w + 1)
    sr_roll50[w:] = (cs2[w + 1:] - cs2[1:len(tick_sr) - w + 1]) / w

    print(f"    Date range: {tick_data['datetime'].iloc[0]} to {tick_data['datetime'].iloc[-1]}")

    sim_p2 = run_sim(prices, tod_secs, sr_roll50, dts, adaptive, std_lu)
    p2_full_df, p2_full_cycles = build_session_df(sim_p2, "P2")
    print(f"  P2 (full): {len(p2_full_df)} sessions, {len(p2_full_cycles)} cycles")
    print(f"  4C stops: {sim_p2.get('stops_4c', 'N/A')}")

    # Split P2 into P2a/P2b date ranges for labeling
    P2A_CUTOFF = pd.Timestamp('2026-02-01')
    p2_full_df['date'] = pd.to_datetime(p2_full_df['date'])
    p2_full_df.loc[p2_full_df['date'] < P2A_CUTOFF, 'period'] = 'P2a'
    p2_full_df.loc[p2_full_df['date'] >= P2A_CUTOFF, 'period'] = 'P2b'

    # Split cycles by entry datetime for period stats
    if 'entry_dt' in p2_full_cycles.columns:
        p2_full_cycles['_entry_dt'] = pd.to_datetime(p2_full_cycles['entry_dt'])
    elif 'start_bar' in p2_full_cycles.columns:
        # Map cycle to session date via session_id
        sid_date = p2_full_df.set_index('session_id')['date'].to_dict()
        p2_full_cycles['_entry_dt'] = p2_full_cycles['session_id'].map(sid_date)
    else:
        p2_full_cycles['_entry_dt'] = pd.NaT

    p2a_mask_c = p2_full_cycles['_entry_dt'] < P2A_CUTOFF
    p2a_df = p2_full_df[p2_full_df['period'] == 'P2a'].copy()
    p2b_df = p2_full_df[p2_full_df['period'] == 'P2b'].copy()
    p2a_cycles = p2_full_cycles[p2a_mask_c].copy()
    p2b_cycles = p2_full_cycles[~p2a_mask_c].copy()

    print(f"    P2a ({p2a_df['date'].min().date()} to {p2a_df['date'].max().date()}): "
          f"{len(p2a_df)} sessions, {len(p2a_cycles)} cycles")
    print(f"    P2b ({p2b_df['date'].min().date()} to {p2b_df['date'].max().date()}): "
          f"{len(p2b_df)} sessions, {len(p2b_cycles)} cycles")

    # ================================================================
    # 3. Combine into single timeline (P1 + P2)
    # ================================================================
    combined = pd.concat([p1_df, p2_full_df], ignore_index=True)
    combined['date'] = pd.to_datetime(combined['date'])
    combined = combined.sort_values('date').reset_index(drop=True)
    combined['cum_pnl'] = combined['net_pnl'].cumsum()
    combined['cum_pnl_usd'] = combined['cum_pnl'] * TICK_VALUE_USD

    # Running max and drawdown
    combined['running_max'] = combined['cum_pnl'].cummax()
    combined['drawdown'] = combined['cum_pnl'] - combined['running_max']
    combined['drawdown_usd'] = combined['drawdown'] * TICK_VALUE_USD

    # ================================================================
    # 5. Compute analytics
    # ================================================================
    def period_stats(df, cycles_df, label):
        """Compute comprehensive stats for a period."""
        pnl = df['net_pnl'].values
        cum = np.cumsum(pnl)
        running_max = np.maximum.accumulate(cum)
        dd = cum - running_max

        # Drawdown analysis
        max_dd = float(dd.min())
        max_dd_idx = int(np.argmin(dd))
        peak_before_dd = int(np.argmax(running_max[:max_dd_idx + 1])) if max_dd_idx > 0 else 0

        # Recovery from max DD
        recovered = False
        recovery_idx = None
        for j in range(max_dd_idx + 1, len(cum)):
            if cum[j] >= running_max[max_dd_idx]:
                recovered = True
                recovery_idx = j
                break

        # Peak before settling
        final_cum = cum[-1]
        peak_cum = float(cum.max())
        peak_idx = int(np.argmax(cum))

        # Winning/losing streaks
        wins = pnl > 0
        streaks_w, streaks_l = [], []
        c_w, c_l = 0, 0
        for w in wins:
            if w:
                c_w += 1
                if c_l > 0:
                    streaks_l.append(c_l)
                    c_l = 0
            else:
                c_l += 1
                if c_w > 0:
                    streaks_w.append(c_w)
                    c_w = 0
        if c_w > 0: streaks_w.append(c_w)
        if c_l > 0: streaks_l.append(c_l)

        # Daily swing stats
        daily_abs = np.abs(pnl)

        # Cycle-level stats
        cycle_pnl = cycles_df['net_1t'].values if 'net_1t' in cycles_df.columns else cycles_df['net_pnl_ticks'].values
        win_cycles = cycle_pnl > 0
        lose_cycles = cycle_pnl <= 0

        stopped = cycles_df[cycles_df['exit_reason'] == 'stop_4c'] if 'exit_reason' in cycles_df.columns else pd.DataFrame()

        return {
            'label': label,
            'sessions': len(df),
            'cycles': len(cycles_df),
            'net_pnl_ticks': float(cum[-1]),
            'net_pnl_usd': float(cum[-1]) * TICK_VALUE_USD,
            'gross_pnl_ticks': float(df['gross_pnl'].sum()),
            'mean_daily_ticks': float(pnl.mean()),
            'std_daily_ticks': float(pnl.std()),
            'median_daily_ticks': float(np.median(pnl)),
            'sharpe_daily': float(pnl.mean() / pnl.std()) if pnl.std() > 0 else 0,
            'session_win_pct': float(wins.mean()),
            'best_day_ticks': float(pnl.max()),
            'best_day_date': _to_date_str(df.loc[df['net_pnl'].idxmax(), 'date']),
            'worst_day_ticks': float(pnl.min()),
            'worst_day_date': _to_date_str(df.loc[df['net_pnl'].idxmin(), 'date']),
            'max_dd_ticks': max_dd,
            'max_dd_usd': max_dd * TICK_VALUE_USD,
            'max_dd_peak_date': _to_date_str(df.iloc[peak_before_dd]['date']),
            'max_dd_trough_date': _to_date_str(df.iloc[max_dd_idx]['date']),
            'max_dd_recovered': recovered,
            'max_dd_recovery_date': _to_date_str(df.iloc[recovery_idx]['date']) if recovered else None,
            'max_dd_recovery_sessions': (recovery_idx - max_dd_idx) if recovered else None,
            'peak_pnl_ticks': peak_cum,
            'peak_date': _to_date_str(df.iloc[peak_idx]['date']),
            'final_vs_peak_ticks': float(final_cum - peak_cum),
            'typical_daily_swing_ticks': float(daily_abs.mean()),
            'p10_daily': float(np.percentile(pnl, 10)),
            'p25_daily': float(np.percentile(pnl, 25)),
            'p50_daily': float(np.percentile(pnl, 50)),
            'p75_daily': float(np.percentile(pnl, 75)),
            'p90_daily': float(np.percentile(pnl, 90)),
            'max_win_streak': max(streaks_w) if streaks_w else 0,
            'max_lose_streak': max(streaks_l) if streaks_l else 0,
            'avg_win_day_ticks': float(pnl[pnl > 0].mean()) if (pnl > 0).any() else 0,
            'avg_lose_day_ticks': float(pnl[pnl <= 0].mean()) if (pnl <= 0).any() else 0,
            'profit_factor': float(pnl[pnl > 0].sum() / abs(pnl[pnl <= 0].sum())) if (pnl <= 0).any() else float('inf'),
            'cycle_win_pct': float(win_cycles.mean()),
            'avg_win_cycle': float(cycle_pnl[win_cycles].mean()) if win_cycles.any() else 0,
            'avg_lose_cycle': float(cycle_pnl[lose_cycles].mean()) if lose_cycles.any() else 0,
            'stopped_4c': len(stopped),
            'cycles_per_session': float(len(cycles_df) / len(df)),
        }

    stats_p1 = period_stats(p1_df, p1_cycles, "P1 (IS)")
    stats_p2a = period_stats(p2a_df, p2a_cycles, "P2a (OOS)")
    stats_p2b = period_stats(p2b_df, p2b_cycles, "P2b (OOS)")

    # Combined stats
    stats_all = period_stats(combined, pd.concat([p1_cycles, p2_full_cycles]), "Combined")

    # ================================================================
    # 5. Generate plots
    # ================================================================
    print("\nGenerating dashboard plots...")

    # Color scheme
    C_P1 = '#2196F3'      # blue
    C_P2A = '#E91E63'     # pink/magenta — regime dip
    C_P2B = '#FF9800'     # orange
    C_GREEN = '#4CAF50'
    C_RED = '#F44336'
    C_BG = '#1a1a2e'
    C_PANEL = '#16213e'
    C_TEXT = '#e0e0e0'
    C_GRID = '#333355'

    plt.rcParams.update({
        'figure.facecolor': C_BG,
        'axes.facecolor': C_PANEL,
        'axes.edgecolor': C_GRID,
        'axes.labelcolor': C_TEXT,
        'text.color': C_TEXT,
        'xtick.color': C_TEXT,
        'ytick.color': C_TEXT,
        'grid.color': C_GRID,
        'grid.alpha': 0.3,
        'font.family': 'monospace',
        'font.size': 9,
    })

    # --- FIGURE 1: Main equity + drawdown + daily bars ---
    fig = plt.figure(figsize=(18, 14))
    gs = gridspec.GridSpec(4, 1, height_ratios=[3, 1.2, 1.5, 1], hspace=0.25)

    # 1a. Equity curve
    ax1 = fig.add_subplot(gs[0])
    dates = combined['date']

    # Period masks and boundaries
    p1_mask = combined['period'] == 'P1'
    p2a_mask = combined['period'] == 'P2a'
    p2b_mask = combined['period'] == 'P2b'
    p2a_start = combined.loc[p2a_mask, 'date'].iloc[0] if p2a_mask.any() else None
    p2b_start = combined.loc[p2b_mask, 'date'].iloc[0] if p2b_mask.any() else None

    ax1.fill_between(dates, 0, combined['cum_pnl'], alpha=0.15, color=C_GREEN,
                     where=combined['cum_pnl'] >= 0)
    ax1.fill_between(dates, 0, combined['cum_pnl'], alpha=0.15, color=C_RED,
                     where=combined['cum_pnl'] < 0)
    ax1.plot(dates[p1_mask], combined.loc[p1_mask, 'cum_pnl'], color=C_P1,
             linewidth=2, label='P1 (IS)', zorder=3)
    ax1.plot(dates[p2a_mask], combined.loc[p2a_mask, 'cum_pnl'], color=C_P2A,
             linewidth=2, label='P2a (OOS)', linestyle='-', zorder=3)
    ax1.plot(dates[p2b_mask], combined.loc[p2b_mask, 'cum_pnl'], color=C_P2B,
             linewidth=2, label='P2b (OOS)', zorder=3)

    # Running max (high-water mark)
    ax1.plot(dates, combined['running_max'], color='#aaa', linewidth=0.8,
             linestyle='--', alpha=0.5, label='High-Water Mark')

    # Period boundary lines
    if p2a_start is not None:
        ax1.axvline(p2a_start, color=C_P2A, linestyle=':', alpha=0.5, linewidth=1)
        ax1.text(p2a_start, combined['cum_pnl'].max() * 0.95, '  P2a',
                 color=C_P2A, fontsize=8, alpha=0.7)
    if p2b_start is not None:
        ax1.axvline(p2b_start, color=C_P2B, linestyle=':', alpha=0.5, linewidth=1)
        ax1.text(p2b_start, combined['cum_pnl'].max() * 0.95, '  P2b',
                 color=C_P2B, fontsize=8, alpha=0.7)

    ax1.set_title('V1.4 + 4C Stop (Final Config) — Cumulative Net PnL (ticks, cost=1t/trade)',
                  fontsize=14, fontweight='bold', pad=10)
    ax1.set_ylabel('Cumulative PnL (ticks)')
    ax1.legend(loc='upper left', fontsize=9)
    ax1.grid(True, alpha=0.3)
    ax1.axhline(0, color='white', linewidth=0.5, alpha=0.3)

    # Add USD scale on right
    ax1r = ax1.twinx()
    ax1r.set_ylabel('USD (per 1-lot)')
    ymin, ymax = ax1.get_ylim()
    ax1r.set_ylim(ymin * TICK_VALUE_USD, ymax * TICK_VALUE_USD)
    ax1r.tick_params(axis='y', colors=C_TEXT)

    # 1b. Drawdown
    ax2 = fig.add_subplot(gs[1], sharex=ax1)
    ax2.fill_between(dates, combined['drawdown'], 0, color=C_RED, alpha=0.4)
    ax2.plot(dates, combined['drawdown'], color=C_RED, linewidth=1)
    ax2.set_ylabel('Drawdown (ticks)')
    ax2.set_title('Drawdown from High-Water Mark', fontsize=10, pad=5)
    ax2.grid(True, alpha=0.3)

    # Mark max DD point
    max_dd_idx = combined['drawdown'].idxmin()
    ax2.annotate(f"Max DD: {combined.loc[max_dd_idx, 'drawdown']:,.0f}t\n"
                 f"(${combined.loc[max_dd_idx, 'drawdown_usd']:,.0f})",
                 xy=(combined.loc[max_dd_idx, 'date'], combined.loc[max_dd_idx, 'drawdown']),
                 xytext=(20, -15), textcoords='offset points',
                 fontsize=8, color=C_RED,
                 arrowprops=dict(arrowstyle='->', color=C_RED, lw=1))

    # 1c. Daily PnL bars
    ax3 = fig.add_subplot(gs[2], sharex=ax1)
    colors = [C_GREEN if v >= 0 else C_RED for v in combined['net_pnl']]
    ax3.bar(dates, combined['net_pnl'], color=colors, alpha=0.7, width=1.5)
    ax3.axhline(0, color='white', linewidth=0.5, alpha=0.3)
    ax3.set_ylabel('Daily PnL (ticks)')
    ax3.set_title('Daily Session PnL', fontsize=10, pad=5)
    ax3.grid(True, alpha=0.3)

    if p2a_start is not None:
        ax3.axvline(p2a_start, color=C_P2A, linestyle=':', alpha=0.5, linewidth=1)
    if p2b_start is not None:
        ax3.axvline(p2b_start, color=C_P2B, linestyle=':', alpha=0.5, linewidth=1)

    # 1d. Rolling 10-session stats
    ax4 = fig.add_subplot(gs[3], sharex=ax1)
    roll_window = min(10, len(combined) - 1)
    if roll_window >= 2:
        rolling_mean = combined['net_pnl'].rolling(roll_window, min_periods=2).mean()
        rolling_wr = (combined['net_pnl'] > 0).rolling(roll_window, min_periods=2).mean()
        ax4.plot(dates, rolling_mean, color='#00BCD4', linewidth=1.5, label=f'{roll_window}-session avg PnL')
        ax4.axhline(0, color='white', linewidth=0.5, alpha=0.3)
        ax4.set_ylabel('Rolling Avg PnL')
        ax4.set_xlabel('Date')
        ax4.legend(loc='upper left', fontsize=8)
        ax4.grid(True, alpha=0.3)

        ax4r = ax4.twinx()
        ax4r.plot(dates, rolling_wr * 100, color='#FFEB3B', linewidth=1, alpha=0.6,
                  label=f'{roll_window}-session win%')
        ax4r.set_ylabel('Win Rate %')
        ax4r.set_ylim(0, 100)
        ax4r.legend(loc='upper right', fontsize=8)
        ax4r.tick_params(axis='y', colors='#FFEB3B')

    if p2a_start is not None:
        ax4.axvline(p2a_start, color=C_P2A, linestyle=':', alpha=0.5, linewidth=1)
    if p2b_start is not None:
        ax4.axvline(p2b_start, color=C_P2B, linestyle=':', alpha=0.5, linewidth=1)

    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%b %d'))
    fig.autofmt_xdate(rotation=30)

    fig.savefig(str(_OUTPUT_DIR / "equity_curve.png"), dpi=150, bbox_inches='tight',
                facecolor=C_BG, edgecolor='none')
    plt.close(fig)
    print("  Saved equity_curve.png")

    # --- FIGURE 2: Distribution + comparison panels ---
    fig2, axes = plt.subplots(2, 3, figsize=(18, 10))

    # 2a. Daily PnL histogram (P1 vs P2a vs P2b)
    ax = axes[0, 0]
    all_pnl = pd.concat([p1_df['net_pnl'], p2a_df['net_pnl'], p2b_df['net_pnl']])
    bins = np.linspace(all_pnl.min() - 100, all_pnl.max() + 100, 30)
    ax.hist(p1_df['net_pnl'], bins=bins, alpha=0.5, color=C_P1, label='P1', edgecolor='none')
    ax.hist(p2a_df['net_pnl'], bins=bins, alpha=0.5, color=C_P2A, label='P2a', edgecolor='none')
    ax.hist(p2b_df['net_pnl'], bins=bins, alpha=0.5, color=C_P2B, label='P2b', edgecolor='none')
    ax.axvline(0, color='white', linewidth=0.8, alpha=0.5)
    ax.axvline(p1_df['net_pnl'].mean(), color=C_P1, linewidth=1.5, linestyle='--', alpha=0.8)
    ax.axvline(p2a_df['net_pnl'].mean(), color=C_P2A, linewidth=1.5, linestyle='--', alpha=0.8)
    ax.axvline(p2b_df['net_pnl'].mean(), color=C_P2B, linewidth=1.5, linestyle='--', alpha=0.8)
    ax.set_title('Daily PnL Distribution (ticks)', fontsize=11, fontweight='bold')
    ax.set_xlabel('Net PnL (ticks)')
    ax.set_ylabel('Sessions')
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)

    # 2b. Cycle PnL histogram
    ax = axes[0, 1]
    p1_cpnl = p1_cycles['net_1t'].values if 'net_1t' in p1_cycles.columns else p1_cycles['net_pnl_ticks'].values
    p2b_cpnl = p2b_cycles['net_1t'].values
    clip_lo, clip_hi = np.percentile(np.concatenate([p1_cpnl, p2b_cpnl]), [2, 98])
    cbins = np.linspace(clip_lo - 10, clip_hi + 10, 40)
    ax.hist(p1_cpnl, bins=cbins, alpha=0.6, color=C_P1, label='P1', edgecolor='none')
    ax.hist(p2b_cpnl, bins=cbins, alpha=0.6, color=C_P2B, label='P2b', edgecolor='none')
    ax.axvline(0, color='white', linewidth=0.8, alpha=0.5)
    ax.set_title('Cycle PnL Distribution (ticks)', fontsize=11, fontweight='bold')
    ax.set_xlabel('Net PnL (ticks)')
    ax.set_ylabel('Cycles')
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)

    # 2c. Win/Loss day sizes
    ax = axes[0, 2]
    categories = ['Avg Win\nDay', 'Avg Loss\nDay', 'Best\nDay', 'Worst\nDay']
    p1_vals = [stats_p1['avg_win_day_ticks'], stats_p1['avg_lose_day_ticks'],
               stats_p1['best_day_ticks'], stats_p1['worst_day_ticks']]
    p2a_vals = [stats_p2a['avg_win_day_ticks'], stats_p2a['avg_lose_day_ticks'],
                stats_p2a['best_day_ticks'], stats_p2a['worst_day_ticks']]
    p2b_vals = [stats_p2b['avg_win_day_ticks'], stats_p2b['avg_lose_day_ticks'],
                stats_p2b['best_day_ticks'], stats_p2b['worst_day_ticks']]
    x = np.arange(len(categories))
    w_bar = 0.25
    ax.bar(x - w_bar, p1_vals, w_bar, color=C_P1, alpha=0.8, label='P1')
    ax.bar(x, p2a_vals, w_bar, color=C_P2A, alpha=0.8, label='P2a')
    ax.bar(x + w_bar, p2b_vals, w_bar, color=C_P2B, alpha=0.8, label='P2b')
    ax.set_xticks(x)
    ax.set_xticklabels(categories, fontsize=8)
    ax.axhline(0, color='white', linewidth=0.5, alpha=0.3)
    ax.set_title('Win/Loss Day Comparison (ticks)', fontsize=11, fontweight='bold')
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3, axis='y')

    # 2d. Cumulative PnL by day-of-week
    ax = axes[1, 0]
    combined['dow'] = combined['date'].dt.dayofweek
    dow_names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri']
    offsets = {'P1': -0.25, 'P2a': 0.0, 'P2b': 0.25}
    for period, color, lbl in [('P1', C_P1, 'P1'), ('P2a', C_P2A, 'P2a'), ('P2b', C_P2B, 'P2b')]:
        subset = combined[combined['period'] == period]
        dow_pnl = subset.groupby('dow')['net_pnl'].mean()
        vals = [dow_pnl.get(i, 0) for i in range(5)]
        ax.bar(np.arange(5) + offsets[period], vals, 0.22,
               color=color, alpha=0.8, label=lbl)
    ax.set_xticks(range(5))
    ax.set_xticklabels(dow_names)
    ax.axhline(0, color='white', linewidth=0.5, alpha=0.3)
    ax.set_title('Avg PnL by Day of Week', fontsize=11, fontweight='bold')
    ax.set_ylabel('Avg PnL (ticks)')
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3, axis='y')

    # 2e. Drawdown duration histogram
    ax = axes[1, 1]
    dd_vals = combined['drawdown'].values
    in_dd = dd_vals < 0
    dd_durations = []
    dd_depths = []
    count = 0
    depth = 0
    for i in range(len(in_dd)):
        if in_dd[i]:
            count += 1
            depth = min(depth, dd_vals[i])
        else:
            if count > 0:
                dd_durations.append(count)
                dd_depths.append(depth)
            count = 0
            depth = 0
    if count > 0:
        dd_durations.append(count)
        dd_depths.append(depth)

    if dd_durations:
        ax.bar(range(len(dd_durations)), [-d for d in dd_depths], color=C_RED, alpha=0.6)
        ax2_twin = ax.twinx()
        ax2_twin.plot(range(len(dd_durations)), dd_durations, 'o-', color='#FFEB3B',
                      markersize=4, linewidth=1, alpha=0.8)
        ax2_twin.set_ylabel('Duration (sessions)', color='#FFEB3B')
        ax2_twin.tick_params(axis='y', colors='#FFEB3B')
    ax.set_title('Drawdown Episodes (depth vs duration)', fontsize=11, fontweight='bold')
    ax.set_xlabel('Episode #')
    ax.set_ylabel('Depth (ticks)')
    ax.grid(True, alpha=0.3, axis='y')

    # 2f. Monthly PnL heatmap-style bar
    ax = axes[1, 2]
    combined['month'] = combined['date'].dt.to_period('M')
    monthly = combined.groupby('month').agg(
        net_pnl=('net_pnl', 'sum'),
        sessions=('net_pnl', 'count'),
        win_rate=('net_pnl', lambda x: (x > 0).mean()),
    )
    month_labels = [str(m) for m in monthly.index]
    colors_monthly = [C_GREEN if v >= 0 else C_RED for v in monthly['net_pnl']]
    bars = ax.bar(range(len(monthly)), monthly['net_pnl'], color=colors_monthly, alpha=0.7)
    for i, (bar, wr) in enumerate(zip(bars, monthly['win_rate'])):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 50,
                f'{wr:.0%}', ha='center', va='bottom', fontsize=7, color=C_TEXT)
    ax.set_xticks(range(len(monthly)))
    ax.set_xticklabels(month_labels, rotation=30, fontsize=8)
    ax.axhline(0, color='white', linewidth=0.5, alpha=0.3)
    ax.set_title('Monthly Net PnL (ticks) + Win Rate', fontsize=11, fontweight='bold')
    ax.set_ylabel('Net PnL (ticks)')
    ax.grid(True, alpha=0.3, axis='y')

    fig2.suptitle('V1.4 + 4C — Performance Breakdown', fontsize=14, fontweight='bold', y=1.01)
    fig2.tight_layout()
    fig2.savefig(str(_OUTPUT_DIR / "performance_breakdown.png"), dpi=150, bbox_inches='tight',
                 facecolor=C_BG, edgecolor='none')
    plt.close(fig2)
    print("  Saved performance_breakdown.png")

    # --- FIGURE 3: Summary stats table ---
    fig3, ax = plt.subplots(figsize=(20, 14))
    ax.axis('off')

    # Helper for 5-column rows
    def R(metric, p1, p2a, p2b, comb):
        return (metric, p1, p2a, p2b, comb)

    s1, s2a, s2b, sa = stats_p1, stats_p2a, stats_p2b, stats_all

    rows_data = [
        R("OVERVIEW", "", "", "", ""),
        R("Sessions", f"{s1['sessions']}", f"{s2a['sessions']}", f"{s2b['sessions']}", f"{sa['sessions']}"),
        R("Cycles", f"{s1['cycles']:,}", f"{s2a['cycles']:,}", f"{s2b['cycles']:,}", f"{sa['cycles']:,}"),
        R("Cycles/Session", f"{s1['cycles_per_session']:.1f}", f"{s2a['cycles_per_session']:.1f}", f"{s2b['cycles_per_session']:.1f}", f"{sa['cycles_per_session']:.1f}"),
        R("4C Stops", f"{s1['stopped_4c']}", f"{s2a['stopped_4c']}", f"{s2b['stopped_4c']}", f"{sa['stopped_4c']}"),
        R("", "", "", "", ""),
        R("PNL", "", "", "", ""),
        R("Net PnL (ticks)", f"{s1['net_pnl_ticks']:+,.0f}", f"{s2a['net_pnl_ticks']:+,.0f}", f"{s2b['net_pnl_ticks']:+,.0f}", f"{sa['net_pnl_ticks']:+,.0f}"),
        R("Net PnL (USD)", f"${s1['net_pnl_usd']:+,.0f}", f"${s2a['net_pnl_usd']:+,.0f}", f"${s2b['net_pnl_usd']:+,.0f}", f"${sa['net_pnl_usd']:+,.0f}"),
        R("Session PF", f"{s1['profit_factor']:.3f}", f"{s2a['profit_factor']:.3f}", f"{s2b['profit_factor']:.3f}", f"{sa['profit_factor']:.3f}"),
        R("", "", "", "", ""),
        R("DAILY STATS", "", "", "", ""),
        R("Mean Daily (ticks)", f"{s1['mean_daily_ticks']:+,.1f}", f"{s2a['mean_daily_ticks']:+,.1f}", f"{s2b['mean_daily_ticks']:+,.1f}", f"{sa['mean_daily_ticks']:+,.1f}"),
        R("Median Daily (ticks)", f"{s1['median_daily_ticks']:+,.1f}", f"{s2a['median_daily_ticks']:+,.1f}", f"{s2b['median_daily_ticks']:+,.1f}", f"{sa['median_daily_ticks']:+,.1f}"),
        R("Std Daily (ticks)", f"{s1['std_daily_ticks']:,.1f}", f"{s2a['std_daily_ticks']:,.1f}", f"{s2b['std_daily_ticks']:,.1f}", f"{sa['std_daily_ticks']:,.1f}"),
        R("Daily Sharpe", f"{s1['sharpe_daily']:.3f}", f"{s2a['sharpe_daily']:.3f}", f"{s2b['sharpe_daily']:.3f}", f"{sa['sharpe_daily']:.3f}"),
        R("Typ. Daily Swing", f"{s1['typical_daily_swing_ticks']:,.0f}", f"{s2a['typical_daily_swing_ticks']:,.0f}", f"{s2b['typical_daily_swing_ticks']:,.0f}", f"{sa['typical_daily_swing_ticks']:,.0f}"),
        R("Session Win %", f"{s1['session_win_pct']:.1%}", f"{s2a['session_win_pct']:.1%}", f"{s2b['session_win_pct']:.1%}", f"{sa['session_win_pct']:.1%}"),
        R("", "", "", "", ""),
        R("EXTREMES", "", "", "", ""),
        R("Best Day", f"{s1['best_day_ticks']:+,.0f} ({s1['best_day_date']})", f"{s2a['best_day_ticks']:+,.0f} ({s2a['best_day_date']})", f"{s2b['best_day_ticks']:+,.0f} ({s2b['best_day_date']})", ""),
        R("Worst Day", f"{s1['worst_day_ticks']:+,.0f} ({s1['worst_day_date']})", f"{s2a['worst_day_ticks']:+,.0f} ({s2a['worst_day_date']})", f"{s2b['worst_day_ticks']:+,.0f} ({s2b['worst_day_date']})", ""),
        R("Max Win Streak", f"{s1['max_win_streak']}d", f"{s2a['max_win_streak']}d", f"{s2b['max_win_streak']}d", ""),
        R("Max Lose Streak", f"{s1['max_lose_streak']}d", f"{s2a['max_lose_streak']}d", f"{s2b['max_lose_streak']}d", ""),
        R("Avg Win Day", f"{s1['avg_win_day_ticks']:+,.0f}", f"{s2a['avg_win_day_ticks']:+,.0f}", f"{s2b['avg_win_day_ticks']:+,.0f}", f"{sa['avg_win_day_ticks']:+,.0f}"),
        R("Avg Lose Day", f"{s1['avg_lose_day_ticks']:+,.0f}", f"{s2a['avg_lose_day_ticks']:+,.0f}", f"{s2b['avg_lose_day_ticks']:+,.0f}", f"{sa['avg_lose_day_ticks']:+,.0f}"),
        R("", "", "", "", ""),
        R("DRAWDOWN", "", "", "", ""),
        R("Max DD (ticks)", f"{s1['max_dd_ticks']:,.0f}", f"{s2a['max_dd_ticks']:,.0f}", f"{s2b['max_dd_ticks']:,.0f}", f"{sa['max_dd_ticks']:,.0f}"),
        R("Max DD (USD)", f"${s1['max_dd_usd']:,.0f}", f"${s2a['max_dd_usd']:,.0f}", f"${s2b['max_dd_usd']:,.0f}", f"${sa['max_dd_usd']:,.0f}"),
        R("DD Peak Date", s1['max_dd_peak_date'], s2a['max_dd_peak_date'], s2b['max_dd_peak_date'], sa['max_dd_peak_date']),
        R("DD Trough Date", s1['max_dd_trough_date'], s2a['max_dd_trough_date'], s2b['max_dd_trough_date'], sa['max_dd_trough_date']),
        R("DD Recovered?", 'Yes' if s1['max_dd_recovered'] else 'No', 'Yes' if s2a['max_dd_recovered'] else 'No', 'Yes' if s2b['max_dd_recovered'] else 'No', 'Yes' if sa['max_dd_recovered'] else 'No'),
        R("Recovery Sessions", f"{s1['max_dd_recovery_sessions'] or 'N/A'}", f"{s2a['max_dd_recovery_sessions'] or 'N/A'}", f"{s2b['max_dd_recovery_sessions'] or 'N/A'}", f"{sa['max_dd_recovery_sessions'] or 'N/A'}"),
        R("Final vs Peak", f"{s1['final_vs_peak_ticks']:+,.0f}", f"{s2a['final_vs_peak_ticks']:+,.0f}", f"{s2b['final_vs_peak_ticks']:+,.0f}", f"{sa['final_vs_peak_ticks']:+,.0f}"),
        R("", "", "", "", ""),
        R("DISTRIBUTION", "", "", "", ""),
        R("P10", f"{s1['p10_daily']:+,.0f}", f"{s2a['p10_daily']:+,.0f}", f"{s2b['p10_daily']:+,.0f}", f"{sa['p10_daily']:+,.0f}"),
        R("P25", f"{s1['p25_daily']:+,.0f}", f"{s2a['p25_daily']:+,.0f}", f"{s2b['p25_daily']:+,.0f}", f"{sa['p25_daily']:+,.0f}"),
        R("P50 (Median)", f"{s1['p50_daily']:+,.0f}", f"{s2a['p50_daily']:+,.0f}", f"{s2b['p50_daily']:+,.0f}", f"{sa['p50_daily']:+,.0f}"),
        R("P75", f"{s1['p75_daily']:+,.0f}", f"{s2a['p75_daily']:+,.0f}", f"{s2b['p75_daily']:+,.0f}", f"{sa['p75_daily']:+,.0f}"),
        R("P90", f"{s1['p90_daily']:+,.0f}", f"{s2a['p90_daily']:+,.0f}", f"{s2b['p90_daily']:+,.0f}", f"{sa['p90_daily']:+,.0f}"),
        R("", "", "", "", ""),
        R("CYCLE LEVEL", "", "", "", ""),
        R("Cycle Win %", f"{s1['cycle_win_pct']:.1%}", f"{s2a['cycle_win_pct']:.1%}", f"{s2b['cycle_win_pct']:.1%}", f"{sa['cycle_win_pct']:.1%}"),
        R("Avg Win Cycle", f"{s1['avg_win_cycle']:+,.1f}", f"{s2a['avg_win_cycle']:+,.1f}", f"{s2b['avg_win_cycle']:+,.1f}", f"{sa['avg_win_cycle']:+,.1f}"),
        R("Avg Lose Cycle", f"{s1['avg_lose_cycle']:+,.1f}", f"{s2a['avg_lose_cycle']:+,.1f}", f"{s2b['avg_lose_cycle']:+,.1f}", f"{sa['avg_lose_cycle']:+,.1f}"),
    ]

    col_labels = ['Metric', 'P1 (IS)', 'P2a (OOS)', 'P2b (OOS)', 'Combined']
    table = ax.table(
        cellText=[r for r in rows_data],
        colLabels=col_labels,
        loc='center',
        cellLoc='left',
    )

    table.auto_set_font_size(False)
    table.set_fontsize(8)
    table.scale(1, 1.2)

    # Style the table
    for (row, col), cell in table.get_celld().items():
        cell.set_edgecolor(C_GRID)
        if row == 0:
            cell.set_facecolor('#0a3d62')
            cell.set_text_props(color='white', fontweight='bold', fontsize=9)
        else:
            text = cell.get_text().get_text()
            if text in ('OVERVIEW', 'PNL', 'DAILY STATS', 'EXTREMES', 'DRAWDOWN',
                       'DISTRIBUTION', 'CYCLE LEVEL'):
                cell.set_facecolor('#0a3d62')
                cell.set_text_props(fontweight='bold', color='#00BCD4', fontsize=9)
            elif text == '':
                cell.set_facecolor(C_PANEL)
                cell.set_height(0.005)
            else:
                cell.set_facecolor(C_PANEL)
                cell.set_text_props(color=C_TEXT)
            if col == 0:
                cell.set_text_props(fontweight='bold')

    fig3.suptitle('V1.4 + 4C — Complete Performance Summary',
                  fontsize=14, fontweight='bold', y=0.98)
    fig3.savefig(str(_OUTPUT_DIR / "stats_table.png"), dpi=150, bbox_inches='tight',
                 facecolor=C_BG, edgecolor='none')
    plt.close(fig3)
    print("  Saved stats_table.png")

    # ================================================================
    # 6. Save JSON analytics
    # ================================================================
    analytics = {
        'generated': dt_mod.datetime.now().isoformat(),
        'config': 'V1.4 + 4C stop (max_cap_walks=2)',
        'p1': stats_p1,
        'p2a': stats_p2a,
        'p2b': stats_p2b,
        'combined': stats_all,
        'session_data': combined[['date', 'net_pnl', 'gross_pnl', 'cycles', 'period',
                                   'cum_pnl', 'drawdown']].to_dict(orient='records'),
    }
    # Convert dates for JSON
    for rec in analytics['session_data']:
        rec['date'] = _to_date_str(rec['date'])

    with open(_OUTPUT_DIR / "v14_analytics.json", 'w') as f:
        json.dump(analytics, f, indent=2, default=str)
    print("  Saved v14_analytics.json")

    # ================================================================
    # Print summary
    # ================================================================
    print(f"\n{'=' * 60}")
    print(f"DASHBOARD COMPLETE — saved to: {_OUTPUT_DIR}")
    print(f"{'=' * 60}")
    print(f"\n  Files:")
    print(f"    equity_curve.png          — Equity + drawdown + daily bars + rolling stats")
    print(f"    performance_breakdown.png — Distributions, day-of-week, monthly, DD episodes")
    print(f"    stats_table.png           — Full comparison table P1 vs P2b vs Combined")
    print(f"    v14_analytics.json        — All analytics in machine-readable format")

    print(f"\n  Key metrics:")
    print(f"    {'':20} {'P1 (IS)':>14} {'P2a (OOS)':>14} {'P2b (OOS)':>14} {'Combined':>14}")
    print(f"    {'-' * 78}")
    print(f"    {'Net PnL (ticks)':20} {stats_p1['net_pnl_ticks']:>+14,.0f} {stats_p2a['net_pnl_ticks']:>+14,.0f} {stats_p2b['net_pnl_ticks']:>+14,.0f} {stats_all['net_pnl_ticks']:>+14,.0f}")
    p1_usd = f"${stats_p1['net_pnl_usd']:+,.0f}"
    p2a_usd = f"${stats_p2a['net_pnl_usd']:+,.0f}"
    p2b_usd = f"${stats_p2b['net_pnl_usd']:+,.0f}"
    all_usd = f"${stats_all['net_pnl_usd']:+,.0f}"
    print(f"    {'Net PnL (USD)':20} {p1_usd:>14} {p2a_usd:>14} {p2b_usd:>14} {all_usd:>14}")
    print(f"    {'Session Win %':20} {stats_p1['session_win_pct']:>14.1%} {stats_p2a['session_win_pct']:>14.1%} {stats_p2b['session_win_pct']:>14.1%} {stats_all['session_win_pct']:>14.1%}")
    print(f"    {'Daily Sharpe':20} {stats_p1['sharpe_daily']:>14.3f} {stats_p2a['sharpe_daily']:>14.3f} {stats_p2b['sharpe_daily']:>14.3f} {stats_all['sharpe_daily']:>14.3f}")
    print(f"    {'Max DD (ticks)':20} {stats_p1['max_dd_ticks']:>14,.0f} {stats_p2a['max_dd_ticks']:>14,.0f} {stats_p2b['max_dd_ticks']:>14,.0f} {stats_all['max_dd_ticks']:>14,.0f}")
    p1_dd = f"${stats_p1['max_dd_usd']:,.0f}"
    p2a_dd = f"${stats_p2a['max_dd_usd']:,.0f}"
    p2b_dd = f"${stats_p2b['max_dd_usd']:,.0f}"
    all_dd = f"${stats_all['max_dd_usd']:,.0f}"
    print(f"    {'Max DD (USD)':20} {p1_dd:>14} {p2a_dd:>14} {p2b_dd:>14} {all_dd:>14}")

    print(f"\n  Total time: {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
