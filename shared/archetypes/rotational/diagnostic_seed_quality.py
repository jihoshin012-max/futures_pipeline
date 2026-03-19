# archetype: rotational
"""Post-P2 Diagnostic: Seed entry quality analysis on P1 base cycles.

Four diagnostics:
  1. Distance from seed entry to nearest prior zigzag extreme
  2. Price movement in first 60 seconds after seed entry
  3. % of seeds where price moves against within 30 seconds
  4. Seed entry vs MFE — how much swing was captured vs used for detection

Uses 250-tick bar data for zigzag extremes and post-entry price tracking.
Resolution: ~0.3-0.5s per bar during RTH.
"""

import sys
import time
import datetime as dt_mod
from pathlib import Path

import numpy as np
import pandas as pd

_REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from shared.data_loader import load_bars
from run_seed_investigation import RTH_OPEN_TOD, FLATTEN_TOD, _P1_START, _P1_END

_250TICK_PATH = _REPO / "stages/01-data/data/bar_data/tick/NQ_BarData_250tick_rot_P1.csv"
_CYCLES_PATH = Path(__file__).parent / "phase1_results" / "full_p1_base_cycles.parquet"


def extract_zigzag_extremes(rth_bars):
    """Extract zigzag peaks and troughs from RTH 250-tick bars.

    Returns DataFrame with columns: datetime, type ('peak'/'trough'), price.
    Uses sign changes in 'Zig Zag Line Length' to detect swing completions.
    'Reversal Price' gives the price at the swing tip.
    """
    zzl = rth_bars['Zig Zag Line Length'].values
    rev = rth_bars['Reversal Price'].values
    dts = rth_bars['datetime'].values

    extremes = []
    curr_sign = 0
    curr_price = 0.0
    curr_dt = None

    for i in range(len(zzl)):
        v = zzl[i]
        if v == 0:
            continue
        sign = 1 if v > 0 else -1

        if curr_sign != 0 and sign != curr_sign:
            # Previous swing completed
            if curr_sign > 0:
                extremes.append((curr_dt, 'peak', curr_price))
            else:
                extremes.append((curr_dt, 'trough', curr_price))

        curr_sign = sign
        curr_price = rev[i]
        curr_dt = dts[i]

    return pd.DataFrame(extremes, columns=['datetime', 'type', 'price'])


def identify_seed_cycles(cycles):
    """Identify seed-initiated cycles (first cycle of each session)."""
    cycles = cycles.sort_values('cycle_id').reset_index(drop=True)
    cycles['prev_session'] = cycles['session_id'].shift(1).fillna(-1).astype(int)
    cycles['prev_exit'] = cycles['exit_reason'].shift(1).fillna('')
    cycles['is_seed'] = (
        (cycles['prev_session'] != cycles['session_id']) |
        (cycles['prev_exit'] != 'reversal') |
        (cycles.index == 0)
    )
    return cycles


def diagnostic_1_zigzag_distance(seeds, rth_bars):
    """Distance from seed entry to the origin of the current zigzag swing.

    Uses the zigzag state at the 250-tick bar nearest to entry time:
    - ZZL > 0 (upswing): origin (trough) = RevP - ZZL
    - ZZL < 0 (downswing): origin (peak) = RevP + |ZZL|

    For Long seeds: reports distance from the trough origin to entry price.
    For Short seeds: reports distance from the peak origin to entry price.
    A larger distance = more of the swing was consumed before seed detection.
    """
    print("\n" + "=" * 70)
    print("DIAGNOSTIC 1: Seed entry distance to zigzag swing origin")
    print("=" * 70)

    bar_dts = rth_bars['datetime'].values.astype('datetime64[ns]').astype('int64')
    bar_zzl = rth_bars['Zig Zag Line Length'].values
    bar_rev = rth_bars['Reversal Price'].values

    results = []
    for _, s in seeds.iterrows():
        entry_ns = pd.Timestamp(s['entry_time']).value
        entry_price = s['entry_price']
        direction = s['direction']

        # Find the bar at/before entry with ZZL != 0
        bar_idx = np.searchsorted(bar_dts, entry_ns, side='right') - 1
        if bar_idx < 0:
            continue

        # Walk backward to find a bar with active ZZL
        found = False
        for offset in range(min(20, bar_idx + 1)):
            bi = bar_idx - offset
            if bar_zzl[bi] != 0:
                zzl_val = bar_zzl[bi]
                rev_val = bar_rev[bi]
                found = True
                break

        if not found:
            continue

        # Compute swing origin
        if zzl_val > 0:
            # Upswing: origin = trough
            origin_price = rev_val - zzl_val
            origin_type = 'trough'
        else:
            # Downswing: origin = peak
            origin_price = rev_val + abs(zzl_val)
            origin_type = 'peak'

        if direction == 'Long':
            dist = entry_price - origin_price
            expected_origin = 'trough'
        else:
            dist = origin_price - entry_price
            expected_origin = 'peak'

        results.append({
            'entry_time': s['entry_time'],
            'direction': direction,
            'entry_price': entry_price,
            'origin_price': origin_price,
            'origin_type': origin_type,
            'dist_to_origin': dist,
            'swing_length': abs(zzl_val),
            'mfe': s['mfe'],
            'seeddist_used': s['seeddist_used'],
            'aligned': origin_type == expected_origin,
        })

    df = pd.DataFrame(results)

    print(f"\n  Seed entries analyzed: {len(df)}")

    aligned = df[df['aligned']]
    misaligned = df[~df['aligned']]
    print(f"  Aligned (seed dir matches ZZ swing): {len(aligned)}")
    print(f"  Misaligned (seed against ZZ swing):  {len(misaligned)}")

    if len(aligned) > 0:
        dist = aligned['dist_to_origin'].values
        print(f"\n  ALIGNED seeds — distance from swing origin to entry (pts):")
        print(f"    Mean:   {dist.mean():.2f}")
        print(f"    Median: {np.median(dist):.2f}")
        print(f"    P25:    {np.percentile(dist, 25):.2f}")
        print(f"    P75:    {np.percentile(dist, 75):.2f}")
        print(f"    Min:    {dist.min():.2f}")
        print(f"    Max:    {dist.max():.2f}")

        # What fraction of the swing had already elapsed at entry?
        swing = aligned['swing_length'].values
        frac_elapsed = np.where(swing > 0, dist / swing, 0)
        print(f"\n  Fraction of zigzag swing elapsed at seed entry:")
        print(f"    Mean:   {frac_elapsed.mean():.2%}")
        print(f"    Median: {np.median(frac_elapsed):.2%}")
        print(f"    => seed entered after {frac_elapsed.mean():.0%} of the ZZ swing")
        print(f"    => {(1 - frac_elapsed.mean()):.0%} of swing remaining to capture")

    if len(misaligned) > 0:
        print(f"\n  MISALIGNED seeds (seed direction opposite to zigzag swing):")
        print(f"    These seeds triggered against the current ZZ trend.")
        print(f"    Count: {len(misaligned)} ({len(misaligned)/len(df):.0%})")
        m_pnl = misaligned.merge(
            seeds[['entry_time', 'gross_pnl_ticks']], on='entry_time', how='left')
        if 'gross_pnl_ticks' in m_pnl.columns:
            print(f"    Mean gross PnL: {m_pnl['gross_pnl_ticks'].mean():+.1f} ticks")

    return df


def diagnostic_2_price_after_entry(seeds, rth_bars):
    """Price movement in first 60 seconds after seed entry.

    Measures price change at 10s, 30s, 60s relative to entry price.
    Uses 250-tick bar resolution (~0.3-0.5s per bar during RTH).
    """
    print("\n" + "=" * 70)
    print("DIAGNOSTIC 2: Price movement in first 60 seconds after entry")
    print("=" * 70)

    bar_dts = rth_bars['datetime'].values.astype('datetime64[ns]').astype('int64')
    bar_last = rth_bars['Last'].values
    bar_high = rth_bars['High'].values
    bar_low = rth_bars['Low'].values

    windows = [10, 30, 60]  # seconds
    results = []

    for _, s in seeds.iterrows():
        entry_ts = pd.Timestamp(s['entry_time'])
        entry_ns = entry_ts.value
        entry_price = s['entry_price']
        direction = s['direction']
        sign = 1.0 if direction == 'Long' else -1.0

        # Find the first bar at or after entry
        bar_idx = np.searchsorted(bar_dts, entry_ns, side='left')
        if bar_idx >= len(bar_dts):
            continue

        row = {'entry_time': s['entry_time'], 'direction': direction,
               'entry_price': entry_price}

        for w in windows:
            end_ns = entry_ns + w * 10**9
            end_idx = np.searchsorted(bar_dts, end_ns, side='right')
            window_slice = slice(bar_idx, min(end_idx, len(bar_dts)))

            if window_slice.start >= window_slice.stop:
                row[f'move_{w}s'] = np.nan
                row[f'max_fav_{w}s'] = np.nan
                row[f'max_adv_{w}s'] = np.nan
                continue

            lasts = bar_last[window_slice]
            highs = bar_high[window_slice]
            lows = bar_low[window_slice]

            # Price at end of window
            price_at_w = lasts[-1]
            move = (price_at_w - entry_price) * sign
            row[f'move_{w}s'] = move

            # Max favorable (use highs for longs, lows for shorts)
            if direction == 'Long':
                max_fav = highs.max() - entry_price
                max_adv = entry_price - lows.min()
            else:
                max_fav = entry_price - lows.min()
                max_adv = highs.max() - entry_price

            row[f'max_fav_{w}s'] = max_fav
            row[f'max_adv_{w}s'] = max_adv

        results.append(row)

    df = pd.DataFrame(results)
    if len(df) == 0:
        print("  No data for price movement analysis.")
        return df

    for w in windows:
        col = f'move_{w}s'
        if col not in df.columns:
            continue
        vals = df[col].dropna().values
        if len(vals) == 0:
            continue
        print(f"\n  Price movement at {w}s (directional, pts):")
        print(f"    Mean:     {vals.mean():+.2f}")
        print(f"    Median:   {np.median(vals):+.2f}")
        print(f"    % favorable: {(vals > 0).mean():.0%}")
        print(f"    % adverse:   {(vals < 0).mean():.0%}")
        print(f"    Mean when favorable: {vals[vals > 0].mean():+.2f}" if (vals > 0).any() else "")
        print(f"    Mean when adverse:   {vals[vals < 0].mean():+.2f}" if (vals < 0).any() else "")

    # Max adverse in windows
    for w in windows:
        col = f'max_adv_{w}s'
        if col not in df.columns:
            continue
        vals = df[col].dropna().values
        if len(vals) == 0:
            continue
        print(f"\n  Max adverse excursion within {w}s (pts):")
        print(f"    Mean: {vals.mean():.2f}")
        print(f"    P75:  {np.percentile(vals, 75):.2f}")
        print(f"    P90:  {np.percentile(vals, 90):.2f}")
        print(f"    Max:  {vals.max():.2f}")

    return df


def diagnostic_3_immediate_reversal(seeds, rth_bars):
    """% of seeds where price moves against within 30 seconds of entry.

    An immediate reversal suggests the seed entered at a local extreme
    (the swing was already turning when the seed triggered).
    """
    print("\n" + "=" * 70)
    print("DIAGNOSTIC 3: Immediate adverse movement after seed entry")
    print("=" * 70)

    bar_dts = rth_bars['datetime'].values.astype('datetime64[ns]').astype('int64')
    bar_high = rth_bars['High'].values
    bar_low = rth_bars['Low'].values

    thresholds = [0.0, 1.0, 2.0, 5.0]  # points adverse
    windows = [10, 30, 60]  # seconds

    results = {(w, t): 0 for w in windows for t in thresholds}
    total = 0

    for _, s in seeds.iterrows():
        entry_ts = pd.Timestamp(s['entry_time'])
        entry_ns = entry_ts.value
        entry_price = s['entry_price']
        direction = s['direction']

        bar_idx = np.searchsorted(bar_dts, entry_ns, side='left')
        if bar_idx >= len(bar_dts):
            continue
        total += 1

        for w in windows:
            end_ns = entry_ns + w * 10**9
            end_idx = np.searchsorted(bar_dts, end_ns, side='right')
            window_slice = slice(bar_idx, min(end_idx, len(bar_dts)))

            if window_slice.start >= window_slice.stop:
                continue

            if direction == 'Long':
                max_adv = entry_price - bar_low[window_slice].min()
            else:
                max_adv = bar_high[window_slice].max() - entry_price

            for t in thresholds:
                if max_adv > t:
                    results[(w, t)] += 1

    print(f"\n  Seed entries analyzed: {total}")
    print(f"\n  % of seeds with adverse movement > threshold within window:")
    print(f"  {'Window':<10}", end="")
    for t in thresholds:
        print(f"  {'>' + str(t) + 'pt':>8}", end="")
    print()
    print(f"  {'-' * (10 + 10 * len(thresholds))}")
    for w in windows:
        print(f"  {str(w) + 's':<10}", end="")
        for t in thresholds:
            pct = results[(w, t)] / total if total > 0 else 0
            print(f"  {pct:>7.0%}", end="")
        print()


def diagnostic_4_swing_capture(seeds):
    """Seed entry vs MFE — how much swing captured vs used for detection.

    For each seed:
    - seed_dist = distance from watch price to entry (detection cost)
    - MFE = max favorable from entry (profit opportunity captured)
    - total_swing = seed_dist + MFE (approximation of the full move)
    - capture_ratio = MFE / total_swing (fraction captured as profit)

    Also compares MFE to stepdist_used — how often does the cycle actually
    reach the step distance (reversal trigger)?
    """
    print("\n" + "=" * 70)
    print("DIAGNOSTIC 4: Swing capture efficiency")
    print("=" * 70)

    seed_d = seeds['seeddist_used'].values
    mfe = seeds['mfe'].values
    mae = seeds['mae'].values
    sd_used = seeds['stepdist_used'].values

    total_swing = seed_d + mfe
    capture_ratio = np.where(total_swing > 0, mfe / total_swing, 0)

    print(f"\n  Seed entries analyzed: {len(seeds)}")

    print(f"\n  Seed distance (detection cost, pts):")
    print(f"    Mean: {seed_d.mean():.2f}")
    print(f"    Min/Max: {seed_d.min():.2f} / {seed_d.max():.2f}")

    print(f"\n  MFE from entry (favorable capture, pts):")
    print(f"    Mean:   {mfe.mean():.2f}")
    print(f"    Median: {np.median(mfe):.2f}")
    print(f"    P25:    {np.percentile(mfe, 25):.2f}")
    print(f"    P75:    {np.percentile(mfe, 75):.2f}")

    print(f"\n  Estimated total swing (seed_dist + MFE, pts):")
    print(f"    Mean:   {total_swing.mean():.2f}")
    print(f"    Median: {np.median(total_swing):.2f}")

    print(f"\n  Capture ratio (MFE / total_swing):")
    print(f"    Mean:   {capture_ratio.mean():.2%}")
    print(f"    Median: {np.median(capture_ratio):.2%}")
    print(f"    P25:    {np.percentile(capture_ratio, 25):.2%}")
    print(f"    P75:    {np.percentile(capture_ratio, 75):.2%}")
    print(f"    => On average, {(1 - capture_ratio.mean()):.0%} of the swing is"
          f" consumed by seed detection")

    # MFE vs StepDist — does the cycle reach reversal trigger?
    reached_step = mfe >= sd_used
    print(f"\n  MFE vs StepDist (reversal trigger):")
    print(f"    Seeds where MFE >= StepDist: {reached_step.sum()} / {len(seeds)}"
          f" ({reached_step.mean():.0%})")
    print(f"    Seeds where MFE < StepDist:  {(~reached_step).sum()} / {len(seeds)}"
          f" ({(~reached_step).mean():.0%})")
    print(f"    => {(~reached_step).mean():.0%} of seed-initiated cycles never"
          f" reach the reversal trigger")

    # MFE shortfall for those that didn't reach
    shortfall = sd_used[~reached_step] - mfe[~reached_step]
    if len(shortfall) > 0:
        print(f"\n  Shortfall for non-reaching seeds (StepDist - MFE, pts):")
        print(f"    Mean: {shortfall.mean():.2f}")
        print(f"    Median: {np.median(shortfall):.2f}")

    # MAE for seed cycles — how deep do they go against?
    print(f"\n  MAE for seed-initiated cycles (pts):")
    print(f"    Mean:   {mae.mean():.2f}")
    print(f"    Median: {np.median(mae):.2f}")
    print(f"    P75:    {np.percentile(mae, 75):.2f}")
    print(f"    P90:    {np.percentile(mae, 90):.2f}")

    # Directional breakdown
    for d in ['Long', 'Short']:
        mask = seeds['direction'] == d
        n = mask.sum()
        if n == 0:
            continue
        d_mfe = mfe[mask]
        d_mae = mae[mask]
        d_ratio = capture_ratio[mask]
        print(f"\n  {d} seeds (n={n}):")
        print(f"    MFE mean: {d_mfe.mean():.2f}, MAE mean: {d_mae.mean():.2f}")
        print(f"    Capture ratio: {d_ratio.mean():.2%}")
        print(f"    Reached StepDist: {reached_step[mask].mean():.0%}")


def main():
    t0 = time.time()

    print("=" * 70)
    print("POST-P2 DIAGNOSTIC: Seed Entry Quality (P1 Base Cycles)")
    print("=" * 70)

    # Load cycle data
    print("\nLoading P1 base cycle data...")
    cycles = pd.read_parquet(str(_CYCLES_PATH))
    cycles = identify_seed_cycles(cycles)
    seeds = cycles[cycles['is_seed']].copy()
    print(f"  Total cycles: {len(cycles):,}")
    print(f"  Seed-initiated: {len(seeds)}")
    print(f"  Reversal-initiated: {(~cycles['is_seed']).sum()}")
    print(f"  Long seeds: {(seeds['direction'] == 'Long').sum()}")
    print(f"  Short seeds: {(seeds['direction'] == 'Short').sum()}")

    # Load 250-tick data
    print("\nLoading 250-tick bar data...")
    bars = load_bars(str(_250TICK_PATH))
    bars = bars[(bars['datetime'].dt.date >= _P1_START) &
                (bars['datetime'].dt.date <= _P1_END)].copy()
    tod = bars['datetime'].dt.hour * 3600 + bars['datetime'].dt.minute * 60
    rth_bars = bars[(tod >= RTH_OPEN_TOD) & (tod < FLATTEN_TOD)].copy()
    print(f"  RTH 250-tick bars: {len(rth_bars):,}")

    # Extract zigzag extremes
    print("\nExtracting zigzag extremes...")
    extremes = extract_zigzag_extremes(rth_bars)
    n_peaks = (extremes['type'] == 'peak').sum()
    n_troughs = (extremes['type'] == 'trough').sum()
    print(f"  Peaks: {n_peaks:,}, Troughs: {n_troughs:,}")

    # Run diagnostics
    d1 = diagnostic_1_zigzag_distance(seeds, rth_bars)
    d2 = diagnostic_2_price_after_entry(seeds, rth_bars)
    diagnostic_3_immediate_reversal(seeds, rth_bars)
    diagnostic_4_swing_capture(seeds)

    # Cross-diagnostic: do seeds with larger zigzag distance have worse outcomes?
    print("\n" + "=" * 70)
    print("CROSS-DIAGNOSTIC: Zigzag distance vs cycle outcome")
    print("=" * 70)

    if d1 is not None and len(d1) > 0:
        merged = d1.merge(
            seeds[['entry_time', 'gross_pnl_ticks', 'net_pnl_ticks', 'exit_reason',
                   'stepdist_used']],
            on='entry_time', how='left')

        # Split by distance quartiles
        merged['dist_q'] = pd.qcut(merged['dist_to_origin'], 4,
                                   labels=['Q1_close', 'Q2', 'Q3', 'Q4_far'],
                                   duplicates='drop')
        print(f"\n  By distance quartile (Q1=closest to extreme, Q4=farthest):")
        print(f"  {'Quartile':<12} {'N':>4} {'Mean dist':>10} {'Mean MFE':>10}"
              f" {'MFE/SD':>8} {'Mean PnL':>10}")
        for q in merged['dist_q'].cat.categories:
            qm = merged[merged['dist_q'] == q]
            n = len(qm)
            md = qm['dist_to_origin'].mean()
            mf = qm['mfe'].mean()
            sd = qm['stepdist_used'].mean()
            pnl = qm['gross_pnl_ticks'].mean()
            print(f"  {q:<12} {n:>4} {md:>10.2f} {mf:>10.2f}"
                  f" {mf / sd:>8.2%} {pnl:>+10.1f}")

    print(f"\nTotal diagnostic time: {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
