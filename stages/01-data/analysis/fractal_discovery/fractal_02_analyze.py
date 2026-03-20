#!/usr/bin/env python3
"""
fractal_02_analyze.py — Full fractal analysis: Parts 1-4, plots, tables, summary.
Reads zigzag_results.pkl from fractal_01_prepare.py.
"""
import numpy as np
import numba as nb
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import Normalize
import matplotlib.cm as cm
from pathlib import Path
from scipy import stats as sp_stats
import pickle
import time
import warnings
warnings.filterwarnings('ignore')

# === CONFIG ===
OUT_DIR = Path(r"C:\Projects\pipeline\stages\01-data\analysis\fractal_discovery")
THRESHOLDS = [3, 5, 7, 10, 15, 25, 50]
PARENT_CHILD = [(50, 25), (25, 15), (25, 10), (15, 7), (10, 5), (7, 3)]
SPLITS = ['RTH', 'ETH', 'Combined']
RTH_START = 34200  # 09:30
BLOCK_LABELS_30 = [
    '09:30', '10:00', '10:30', '11:00', '11:30', '12:00', '12:30',
    '13:00', '13:30', '14:00', '14:30', '15:00', '15:30',
]
BLOCK_LABELS_60 = ['09:30', '10:30', '11:30', '12:30', '13:30', '14:30', '15:30']


# === NUMBA: CHILD-WALK COMPLETION (Part 2d, 2e, Part 4) ===

@nb.njit(cache=True)
def child_walk_completion(c_prices, c_dirs, c_sids, c_time_secs, parent_thresh):
    """Walk child swings tracking displacement from anchor.

    Returns per-attempt arrays:
      is_success, retrace_count, max_fav_frac, anchor_idx, gross_movement, anchor_ts
    """
    n = len(c_prices)
    mx = n // 2 + 1
    o_succ  = np.empty(mx, dtype=nb.boolean)
    o_ret   = np.empty(mx, dtype=np.int32)
    o_fav   = np.empty(mx, dtype=np.float64)
    o_anch  = np.empty(mx, dtype=np.int64)
    o_gross = np.empty(mx, dtype=np.float64)
    o_ts    = np.empty(mx, dtype=np.float32)
    cnt = 0

    i = 0
    while i < n - 1:
        cs = c_sids[i]
        anch_p = c_prices[i]
        anch_ts = c_time_secs[i]

        i += 1
        if c_sids[i] != cs:
            continue

        disp = c_prices[i] - anch_p
        if disp == 0.0:
            continue

        att = np.int8(1) if disp > 0 else np.int8(-1)
        n_ret = np.int32(0)
        max_fav = abs(disp)
        gross = abs(disp)
        prev_p = c_prices[i]

        # Check immediate resolution
        if abs(disp) >= parent_thresh:
            o_succ[cnt] = True; o_ret[cnt] = 0
            o_fav[cnt] = max_fav / parent_thresh
            o_anch[cnt] = i - 1; o_gross[cnt] = gross
            o_ts[cnt] = anch_ts; cnt += 1
            continue

        resolved = False
        while True:
            i += 1
            if i >= n or c_sids[i] != cs:
                break
            mv = abs(c_prices[i] - prev_p)
            gross += mv
            prev_p = c_prices[i]
            disp = c_prices[i] - anch_p
            fav = disp * att
            if fav > max_fav:
                max_fav = fav
            if c_dirs[i] != att:
                n_ret += 1
            if fav >= parent_thresh:
                o_succ[cnt] = True; o_ret[cnt] = n_ret
                o_fav[cnt] = max_fav / parent_thresh
                o_anch[cnt] = i - (n_ret + 1)  # approx anchor
                o_gross[cnt] = gross; o_ts[cnt] = anch_ts
                cnt += 1; resolved = True; break
            elif fav <= -parent_thresh:
                o_succ[cnt] = False; o_ret[cnt] = n_ret
                o_fav[cnt] = max_fav / parent_thresh
                o_anch[cnt] = i - (n_ret + 1)
                o_gross[cnt] = gross; o_ts[cnt] = anch_ts
                cnt += 1; resolved = True; break

    return (o_succ[:cnt], o_ret[:cnt], o_fav[:cnt],
            o_anch[:cnt], o_gross[:cnt], o_ts[:cnt])


# === NUMBA: PARENT-CHILD OVERLAY (Part 2 a-c) ===

@nb.njit(cache=True)
def parent_child_overlay(p_prices, p_dirs, p_sids, p_idx,
                         c_prices, c_dirs, c_sids, c_idx):
    """For each parent swing, find children within and compute metrics."""
    np_swings = len(p_prices) - 1
    o_nchild  = np.empty(np_swings, dtype=np.int32)
    o_nwith   = np.empty(np_swings, dtype=np.int32)
    o_nret    = np.empty(np_swings, dtype=np.int32)
    o_waste   = np.empty(np_swings, dtype=np.float64)
    o_valid   = np.empty(np_swings, dtype=nb.boolean)

    c_ptr = np.int64(0)
    nc = len(c_prices)

    for pi in range(np_swings):
        if p_sids[pi] != p_sids[pi + 1]:
            o_valid[pi] = False; continue
        o_valid[pi] = True
        ps = p_idx[pi]; pe = p_idx[pi + 1]
        p_dir = np.int8(1) if p_prices[pi+1] > p_prices[pi] else np.int8(-1)
        p_net = abs(p_prices[pi+1] - p_prices[pi])

        # Advance child pointer
        while c_ptr < nc and c_idx[c_ptr] < ps:
            c_ptr += 1

        gross = 0.0; n_w = 0; n_r = 0; n_mv = 0
        j = c_ptr
        while j < nc - 1 and c_idx[j+1] <= pe and c_sids[j] == p_sids[pi]:
            sz = abs(c_prices[j+1] - c_prices[j])
            d  = np.int8(1) if c_prices[j+1] > c_prices[j] else np.int8(-1)
            gross += sz; n_mv += 1
            if d == p_dir:
                n_w += 1
            else:
                n_r += 1
            j += 1

        o_nchild[pi] = n_mv; o_nwith[pi] = n_w; o_nret[pi] = n_r
        o_waste[pi] = ((gross - p_net) / gross * 100.0) if gross > 0 else 0.0

    return o_nchild, o_nwith, o_nret, o_waste, o_valid


# === LOAD RESULTS ===

def load_results():
    with open(OUT_DIR / 'zigzag_results.pkl', 'rb') as f:
        return pickle.load(f)


# === PART 1: MULTI-THRESHOLD DISTRIBUTIONS ===

def compute_swing_sizes(data):
    """Return swing sizes (consecutive same-session swings)."""
    p = data['price']; s = data['sid']
    sizes = np.abs(np.diff(p))
    same = np.diff(s) == 0
    return sizes[same]


def part1(results):
    """Compute distributions for all splits × thresholds. Return stats dict + raw sizes."""
    print("  Part 1: Multi-threshold distributions...", flush=True)
    all_stats = {}
    all_sizes = {}
    for split in SPLITS:
        rows = []
        for th in THRESHOLDS:
            sz = compute_swing_sizes(results[(split, th)])
            s = {
                'split': split, 'threshold': th,
                'count': len(sz),
                'mean': np.mean(sz) if len(sz) > 0 else 0,
                'median': np.median(sz) if len(sz) > 0 else 0,
                'p75': np.percentile(sz, 75) if len(sz) > 0 else 0,
                'p90': np.percentile(sz, 90) if len(sz) > 0 else 0,
                'std': np.std(sz) if len(sz) > 0 else 0,
                'skewness': float(sp_stats.skew(sz)) if len(sz) > 2 else 0,
            }
            if s['p90'] > 0:
                s['median_p90_ratio'] = s['median'] / s['p90']
            else:
                s['median_p90_ratio'] = 0
            rows.append(s)
            all_sizes[(split, th)] = sz
        all_stats[split] = rows
    return all_stats, all_sizes


def plot_part1(all_sizes):
    """Overlay normalized distributions for RTH (primary)."""
    for split in SPLITS:
        fig, ax = plt.subplots(figsize=(12, 6))
        colors = plt.cm.viridis(np.linspace(0, 1, len(THRESHOLDS)))
        for idx, th in enumerate(THRESHOLDS):
            sz = all_sizes[(split, th)]
            if len(sz) == 0:
                continue
            # Bin by 1-point increments, normalize to %
            mx = min(np.percentile(sz, 99.5), th * 20)
            bins = np.arange(th, mx + 1, 1.0)
            if len(bins) < 3:
                bins = np.linspace(th, mx, 30)
            counts, edges = np.histogram(sz, bins=bins)
            pct = counts / counts.sum() * 100
            centers = (edges[:-1] + edges[1:]) / 2
            # Normalize x-axis to multiples of threshold
            ax.plot(centers / th, pct, label=f'{th}pt', color=colors[idx], alpha=0.8)
        ax.set_xlabel('Swing Size (× threshold)')
        ax.set_ylabel('Frequency (%)')
        ax.set_title(f'Normalized Swing Size Distributions — {split}')
        ax.legend()
        ax.set_xlim(1, 8)
        ax.grid(True, alpha=0.3)
        fig.tight_layout()
        suffix = f'_{split.lower()}' if split != 'RTH' else ''
        fig.savefig(OUT_DIR / f'part1_distributions{suffix}.png', dpi=150)
        plt.close(fig)


# === PART 2: HIERARCHICAL DECOMPOSITION ===

def part2(results):
    """Compute parent-child overlay (a-c) and child-walk completion (d-e)."""
    print("  Part 2: Hierarchical decomposition...", flush=True)
    overlay_rows = []
    completion_data = {}
    halfblock_data = {}

    for split in SPLITS:
        for pt, ct in PARENT_CHILD:
            pd_ = results[(split, pt)]
            cd_ = results[(split, ct)]

            # --- Items a-c: parent overlay ---
            nc, nw, nr, waste, valid = parent_child_overlay(
                pd_['price'], pd_['dir'], pd_['sid'], pd_['orig_idx'],
                cd_['price'], cd_['dir'], cd_['sid'], cd_['orig_idx'],
            )
            v = valid
            row = {
                'split': split, 'parent': pt, 'child': ct,
                'n_parent_swings': int(v.sum()),
                'avg_children': float(np.mean(nc[v])) if v.any() else 0,
                'med_children': float(np.median(nc[v])) if v.any() else 0,
                'min_children': int(np.min(nc[v])) if v.any() else 0,
                'max_children': int(np.max(nc[v])) if v.any() else 0,
                'avg_with': float(np.mean(nw[v])) if v.any() else 0,
                'avg_retrace': float(np.mean(nr[v])) if v.any() else 0,
                'with_retrace_ratio': (float(np.sum(nw[v])) / float(np.sum(nr[v]))
                                       if np.sum(nr[v]) > 0 else np.inf),
                'waste_pct': float(np.median(waste[v])) if v.any() else 0,
            }
            overlay_rows.append(row)

            # --- Items d-e: child-walk completion ---
            succ, retc, fav, anch, gross, ts = child_walk_completion(
                cd_['price'], cd_['dir'], cd_['sid'],
                cd_['time_secs'], float(pt),
            )
            # Completion rate by retracement count
            comp = {}
            for rc in range(6):
                if rc < 5:
                    mask = retc == rc
                else:
                    mask = retc >= 5
                label = str(rc) if rc < 5 else '5+'
                n_tot = mask.sum()
                n_suc = succ[mask].sum() if n_tot > 0 else 0
                comp[label] = {'total': int(n_tot), 'success': int(n_suc),
                               'rate': float(n_suc / n_tot) if n_tot > 0 else 0.0}
            completion_data[(split, pt, ct)] = comp

            # Half-block curve
            buckets = np.arange(0.1, 1.01, 0.1)
            hb = []
            n_success_total = succ.sum()
            for b in buckets:
                reached = fav >= b
                n_reached = reached.sum()
                n_comp = succ[reached].sum() if n_reached > 0 else 0
                hb.append({
                    'progress_pct': float(b * 100),
                    'n_reached': int(n_reached),
                    'n_completed': int(n_comp),
                    'completion_rate': float(n_comp / n_reached) if n_reached > 0 else 0,
                })
            halfblock_data[(split, pt, ct)] = hb

    return overlay_rows, completion_data, halfblock_data


def plot_part2_completion(completion_data):
    """Bar chart: completion rate vs retracement count for 25→10 pair."""
    for split in SPLITS:
        key = (split, 25, 10)
        if key not in completion_data:
            continue
        comp = completion_data[key]
        labels = list(comp.keys())
        rates = [comp[k]['rate'] * 100 for k in labels]
        totals = [comp[k]['total'] for k in labels]

        fig, ax1 = plt.subplots(figsize=(10, 6))
        x = np.arange(len(labels))
        bars = ax1.bar(x, rates, color='steelblue', alpha=0.8, label='Completion Rate %')
        ax1.set_ylabel('Completion Rate (%)')
        ax1.set_xlabel('Retracement Count')
        ax1.set_xticks(x)
        ax1.set_xticklabels(labels)
        ax1.set_ylim(0, 100)

        # Overlay sample counts
        ax2 = ax1.twinx()
        ax2.plot(x, totals, 'ro-', label='Sample Count', markersize=8)
        ax2.set_ylabel('Sample Count')

        # Add rate labels on bars
        for i, (r, t) in enumerate(zip(rates, totals)):
            ax1.text(i, r + 1, f'{r:.1f}%', ha='center', fontsize=9)

        ax1.set_title(f'Parent 25pt Completion Rate by Child 10pt Retracements — {split}')
        lines1, labels1 = ax1.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        ax1.legend(lines1 + lines2, labels1 + labels2, loc='upper right')
        ax1.grid(True, alpha=0.3, axis='y')
        fig.tight_layout()
        suffix = f'_{split.lower()}' if split != 'RTH' else ''
        fig.savefig(OUT_DIR / f'part2_completion_rates{suffix}.png', dpi=150)
        plt.close(fig)


def plot_part2_halfblock(halfblock_data):
    """Half-block completion curve for 25→10."""
    for split in SPLITS:
        key = (split, 25, 10)
        if key not in halfblock_data:
            continue
        hb = halfblock_data[key]
        pcts = [h['progress_pct'] for h in hb]
        rates = [h['completion_rate'] * 100 for h in hb]
        counts = [h['n_reached'] for h in hb]

        fig, ax1 = plt.subplots(figsize=(10, 6))
        ax1.plot(pcts, rates, 'b-o', linewidth=2, markersize=8, label='P(complete)')
        ax1.set_xlabel('Progress (% of 25pt parent threshold)')
        ax1.set_ylabel('P(completion) %')
        ax1.set_ylim(0, 105)
        ax1.grid(True, alpha=0.3)

        ax2 = ax1.twinx()
        ax2.bar(pcts, counts, width=6, alpha=0.2, color='gray', label='N reached')
        ax2.set_ylabel('Sample Count')

        ax1.set_title(f'Half-Block Completion Curve: 25pt parent / 10pt child — {split}')
        lines1, l1 = ax1.get_legend_handles_labels()
        lines2, l2 = ax2.get_legend_handles_labels()
        ax1.legend(lines1 + lines2, l1 + l2)
        fig.tight_layout()
        suffix = f'_{split.lower()}' if split != 'RTH' else ''
        fig.savefig(OUT_DIR / f'part2_halfblock_curve{suffix}.png', dpi=150)
        plt.close(fig)


# === PART 3: POWER LAW TAIL ANALYSIS ===

def part3(all_sizes):
    """Fit power law to right tail of each threshold distribution."""
    print("  Part 3: Power law tail analysis...", flush=True)
    pl_rows = []
    for split in SPLITS:
        for th in THRESHOLDS:
            sz = all_sizes[(split, th)]
            if len(sz) < 20:
                pl_rows.append({'split': split, 'threshold': th,
                                'exponent': 0, 'r_squared': 0, 'n_tail': 0})
                continue
            med = np.median(sz)
            tail = sz[sz > med]
            if len(tail) < 10:
                pl_rows.append({'split': split, 'threshold': th,
                                'exponent': 0, 'r_squared': 0, 'n_tail': 0})
                continue
            # Binned log-log
            bins = np.logspace(np.log10(med), np.log10(tail.max()), 40)
            counts, edges = np.histogram(tail, bins=bins)
            centers = np.sqrt(edges[:-1] * edges[1:])  # geometric mean
            mask = counts > 0
            if mask.sum() < 3:
                pl_rows.append({'split': split, 'threshold': th,
                                'exponent': 0, 'r_squared': 0, 'n_tail': len(tail)})
                continue
            log_x = np.log10(centers[mask])
            log_y = np.log10(counts[mask].astype(float))
            slope, intercept, r, p, se = sp_stats.linregress(log_x, log_y)
            pl_rows.append({
                'split': split, 'threshold': th,
                'exponent': float(slope), 'r_squared': float(r**2),
                'n_tail': int(len(tail)),
            })
    return pl_rows


def plot_part3(all_sizes, pl_rows):
    """Log-log plots with fitted lines."""
    for split in SPLITS:
        fig, axes = plt.subplots(2, 4, figsize=(16, 8))
        axes = axes.flatten()
        split_rows = [r for r in pl_rows if r['split'] == split]
        for idx, (th, row) in enumerate(zip(THRESHOLDS, split_rows)):
            ax = axes[idx]
            sz = all_sizes[(split, th)]
            if len(sz) < 20:
                ax.set_title(f'{th}pt (insufficient data)')
                continue
            med = np.median(sz)
            tail = sz[sz > med]
            bins = np.logspace(np.log10(med), np.log10(max(tail.max(), med+1)), 40)
            counts, edges = np.histogram(tail, bins=bins)
            centers = np.sqrt(edges[:-1] * edges[1:])
            mask = counts > 0
            ax.scatter(np.log10(centers[mask]), np.log10(counts[mask].astype(float)),
                      s=15, alpha=0.7)
            if row['r_squared'] > 0:
                x_fit = np.log10(centers[mask])
                y_fit = row['exponent'] * x_fit + (np.log10(counts[mask].astype(float)).mean() -
                        row['exponent'] * x_fit.mean())
                ax.plot(x_fit, y_fit, 'r-', linewidth=1.5)
            ax.set_title(f"{th}pt: α={row['exponent']:.2f}, R²={row['r_squared']:.2f}")
            ax.set_xlabel('log₁₀(size)')
            ax.set_ylabel('log₁₀(freq)')
            ax.grid(True, alpha=0.3)
        # Hide unused subplot
        if len(THRESHOLDS) < len(axes):
            axes[-1].set_visible(False)
        fig.suptitle(f'Power Law Tail Analysis — {split}', fontsize=14)
        fig.tight_layout()
        suffix = f'_{split.lower()}' if split != 'RTH' else ''
        fig.savefig(OUT_DIR / f'part3_powerlaw{suffix}.png', dpi=150)
        plt.close(fig)


# === PART 4: TIME-OF-DAY ANALYSIS (RTH only) ===

def part4(results):
    """Time-of-day structure using child-walk, RTH only."""
    print("  Part 4: Time-of-day analysis...", flush=True)
    part4_pairs = [(15, 7), (25, 10), (50, 25)]
    rows_30 = []
    rows_60 = []

    for pt, ct in part4_pairs:
        cd_ = results[('RTH', ct)]
        succ, retc, fav, anch, gross, ts = child_walk_completion(
            cd_['price'], cd_['dir'], cd_['sid'],
            cd_['time_secs'], float(pt),
        )
        # Block assignment
        blocks_30 = np.minimum(((ts - RTH_START) / 1800).astype(np.int32), 12)

        # Also compute median child swing size per block
        child_sizes = np.abs(np.diff(cd_['price']))
        child_same_sess = np.diff(cd_['sid']) == 0
        child_sizes = child_sizes[child_same_sess]
        child_ts_mid = cd_['time_secs'][:-1][child_same_sess]
        child_blocks = np.minimum(((child_ts_mid - RTH_START) / 1800).astype(np.int32), 12)

        for b30 in range(13):
            bmask = blocks_30 == b30
            n_samp = int(bmask.sum())

            # Median child swing in this block
            cb_mask = child_blocks == b30
            med_child = float(np.median(child_sizes[cb_mask])) if cb_mask.any() else 0.0

            if n_samp < 30:
                rows_30.append({
                    'block_start': BLOCK_LABELS_30[b30], 'parent_threshold': pt,
                    'sample_count': n_samp, 'completion_0_retrace': 'INSUFFICIENT_SAMPLE',
                    'completion_1_retrace': 'INSUFFICIENT_SAMPLE',
                    'waste_pct': 'INSUFFICIENT_SAMPLE',
                    'median_child_swing': med_child,
                })
                continue

            # Completion at 0 retracements
            m0 = bmask & (retc == 0)
            c0 = float(succ[m0].sum() / m0.sum()) if m0.any() else 0.0

            # Completion at 1 retracement
            m1 = bmask & (retc == 1)
            c1 = float(succ[m1].sum() / m1.sum()) if m1.any() else 0.0

            # Waste % (successes only)
            ms = bmask & succ
            if ms.any():
                g = gross[ms]
                waste_vals = (g - pt) / g * 100
                wpct = float(np.median(waste_vals))
            else:
                wpct = 0.0

            rows_30.append({
                'block_start': BLOCK_LABELS_30[b30], 'parent_threshold': pt,
                'sample_count': n_samp,
                'completion_0_retrace': round(c0 * 100, 1),
                'completion_1_retrace': round(c1 * 100, 1),
                'waste_pct': round(wpct, 1),
                'median_child_swing': round(med_child, 2),
            })

        # 60-min aggregation
        blocks_60 = blocks_30 // 2
        child_blocks_60 = child_blocks // 2
        for b60 in range(7):
            bmask = blocks_60 == b60
            n_samp = int(bmask.sum())
            cb_mask = child_blocks_60 == b60
            med_child = float(np.median(child_sizes[cb_mask])) if cb_mask.any() else 0.0

            if n_samp < 30:
                rows_60.append({
                    'block_start': BLOCK_LABELS_60[b60], 'parent_threshold': pt,
                    'sample_count': n_samp, 'completion_0_retrace': 'INSUFFICIENT_SAMPLE',
                    'completion_1_retrace': 'INSUFFICIENT_SAMPLE',
                    'waste_pct': 'INSUFFICIENT_SAMPLE',
                    'median_child_swing': med_child,
                })
                continue

            m0 = bmask & (retc == 0)
            c0 = float(succ[m0].sum() / m0.sum()) if m0.any() else 0.0
            m1 = bmask & (retc == 1)
            c1 = float(succ[m1].sum() / m1.sum()) if m1.any() else 0.0
            ms = bmask & succ
            wpct = float(np.median((gross[ms] - pt) / gross[ms] * 100)) if ms.any() else 0.0

            rows_60.append({
                'block_start': BLOCK_LABELS_60[b60], 'parent_threshold': pt,
                'sample_count': n_samp,
                'completion_0_retrace': round(c0 * 100, 1),
                'completion_1_retrace': round(c1 * 100, 1),
                'waste_pct': round(wpct, 1),
                'median_child_swing': round(med_child, 2),
            })

    return pd.DataFrame(rows_30), pd.DataFrame(rows_60)


def plot_part4_heatmaps(df30):
    """Heatmaps: completion rate and waste% by time block × parent scale."""
    parent_scales = [15, 25, 50]

    for metric, title, cmap, vmin, vmax in [
        ('completion_1_retrace', 'Completion Rate @ 1 Retracement (%)', 'RdYlGn', 0, 100),
        ('waste_pct', 'Waste %', 'YlOrRd', 0, 100),
    ]:
        fig, ax = plt.subplots(figsize=(16, 4))
        data = np.full((len(parent_scales), 13), np.nan)
        counts = np.full((len(parent_scales), 13), 0)

        for ri, ps in enumerate(parent_scales):
            sub = df30[df30['parent_threshold'] == ps]
            for _, row in sub.iterrows():
                bi = BLOCK_LABELS_30.index(row['block_start'])
                val = row[metric]
                counts[ri, bi] = row['sample_count']
                if isinstance(val, (int, float)):
                    data[ri, bi] = val

        im = ax.imshow(data, aspect='auto', cmap=cmap, vmin=vmin, vmax=vmax)
        ax.set_xticks(range(13))
        ax.set_xticklabels(BLOCK_LABELS_30, rotation=45, ha='right')
        ax.set_yticks(range(len(parent_scales)))
        ax.set_yticklabels([f'{ps}pt' for ps in parent_scales])
        ax.set_xlabel('Time Block (30-min)')
        ax.set_title(title)

        # Overlay text
        for ri in range(len(parent_scales)):
            for ci in range(13):
                v = data[ri, ci]
                c = counts[ri, ci]
                if np.isnan(v):
                    txt = f'n={c}\nINSUFF'
                else:
                    txt = f'{v:.0f}%\nn={c}'
                ax.text(ci, ri, txt, ha='center', va='center', fontsize=7,
                       color='black' if (np.isnan(v) or v > 50) else 'white')

        plt.colorbar(im, ax=ax, shrink=0.8)
        fig.tight_layout()
        tag = 'completion' if 'completion' in metric else 'waste'
        fig.savefig(OUT_DIR / f'part4_heatmap_{tag}.png', dpi=150)
        plt.close(fig)


# === SUMMARY ===

def write_summary(part1_stats, overlay_rows, completion_data, halfblock_data, pl_rows,
                  df30, df60):
    """Write fractal_summary.md."""
    lines = ['# NQ Fractal Structure Discovery — Summary\n']
    lines.append(f'Data: NQ 1-tick bars, P1+P2 (~60.9M rows, Sept 2025 – Mar 2026)\n')

    # Part 1
    lines.append('\n## Part 1: Multi-Threshold Swing Distributions\n')
    for split in SPLITS:
        lines.append(f'\n### {split}\n')
        lines.append('| Threshold | Count | Mean | Median | P75 | P90 | StdDev | Skewness | Med/P90 |')
        lines.append('|-----------|-------|------|--------|-----|-----|--------|----------|---------|')
        for s in part1_stats[split]:
            lines.append(
                f"| {s['threshold']:>2}pt | {s['count']:>8,} | {s['mean']:.1f} | "
                f"{s['median']:.1f} | {s['p75']:.1f} | {s['p90']:.1f} | "
                f"{s['std']:.1f} | {s['skewness']:.2f} | {s['median_p90_ratio']:.3f} |"
            )

    lines.append('\n**Self-similarity assessment:** ')
    rth_stats = part1_stats['RTH']
    ratios = [s['median_p90_ratio'] for s in rth_stats if s['p90'] > 0]
    skews = [s['skewness'] for s in rth_stats]
    if ratios:
        lines.append(f'Median/P90 ratio range: {min(ratios):.3f}–{max(ratios):.3f} '
                     f'(stable ratio suggests self-similarity). '
                     f'Skewness range: {min(skews):.2f}–{max(skews):.2f}.\n')

    # Part 2
    lines.append('\n## Part 2: Hierarchical Decomposition\n')
    lines.append('\n### Items a-c: Parent-Child Overlay\n')
    lines.append('| Split | Parent→Child | N Parents | Avg Children | Avg With | Avg Retrace | W:R Ratio | Waste% |')
    lines.append('|-------|-------------|-----------|--------------|----------|-------------|-----------|--------|')
    for r in overlay_rows:
        lines.append(
            f"| {r['split']} | {r['parent']}→{r['child']} | {r['n_parent_swings']:,} | "
            f"{r['avg_children']:.1f} | {r['avg_with']:.1f} | {r['avg_retrace']:.1f} | "
            f"{r['with_retrace_ratio']:.2f} | {r['waste_pct']:.1f}% |"
        )

    lines.append('\n### Item d: Completion Rate (Child-Walk Method)\n')
    for split in SPLITS:
        lines.append(f'\n**{split}:**\n')
        lines.append('| Parent→Child | 0 ret | 1 ret | 2 ret | 3 ret | 4 ret | 5+ ret |')
        lines.append('|-------------|-------|-------|-------|-------|-------|--------|')
        for pt, ct in PARENT_CHILD:
            key = (split, pt, ct)
            if key not in completion_data:
                continue
            comp = completion_data[key]
            vals = []
            for rc in ['0', '1', '2', '3', '4', '5+']:
                c = comp.get(rc, {'rate': 0, 'total': 0})
                vals.append(f"{c['rate']*100:.1f}% ({c['total']})")
            lines.append(f"| {pt}→{ct} | {' | '.join(vals)} |")

    lines.append('\n### Item e: Half-Block Completion Curve (25→10, RTH)\n')
    hb = halfblock_data.get(('RTH', 25, 10), [])
    if hb:
        lines.append('| Progress | N Reached | N Completed | P(complete) |')
        lines.append('|----------|-----------|-------------|-------------|')
        for h in hb:
            lines.append(f"| {h['progress_pct']:.0f}% | {h['n_reached']:,} | "
                        f"{h['n_completed']:,} | {h['completion_rate']*100:.1f}% |")

    # Part 3
    lines.append('\n## Part 3: Power Law Tail Analysis\n')
    for split in SPLITS:
        lines.append(f'\n### {split}\n')
        lines.append('| Threshold | Exponent (α) | R² | N Tail |')
        lines.append('|-----------|-------------|-----|--------|')
        for r in pl_rows:
            if r['split'] == split:
                lines.append(f"| {r['threshold']:>2}pt | {r['exponent']:.3f} | "
                            f"{r['r_squared']:.3f} | {r['n_tail']:,} |")

    split_rows = [r for r in pl_rows if r['split'] == 'RTH']
    exps = [r['exponent'] for r in split_rows if r['r_squared'] > 0.5]
    if exps:
        lines.append(f'\n**RTH exponents (R²>0.5):** range {min(exps):.3f} to {max(exps):.3f}. ')
        if max(exps) - min(exps) < 0.5:
            lines.append('Relatively stable — suggestive of scale-free fractal structure.\n')
        else:
            lines.append('Moderate variation — different scales may have different tail behavior.\n')

    # Part 4
    lines.append('\n## Part 4: Time-of-Day Structure (RTH)\n')
    lines.append('\nSee part4_timeofday_30min.csv and part4_timeofday_60min.csv for full data.\n')
    lines.append('Heatmaps saved as part4_heatmap_completion.png and part4_heatmap_waste.png.\n')

    # Key takeaways
    lines.append('\n## Key Takeaways\n')
    # Auto-generate some insights
    rth_25_10 = completion_data.get(('RTH', 25, 10), {})
    if rth_25_10:
        r0 = rth_25_10.get('0', {}).get('rate', 0) * 100
        r1 = rth_25_10.get('1', {}).get('rate', 0) * 100
        r2 = rth_25_10.get('2', {}).get('rate', 0) * 100
        lines.append(f'- **25→10 completion rates (RTH):** {r0:.1f}% at 0 retracements, '
                     f'{r1:.1f}% at 1, {r2:.1f}% at 2.\n')
    hb_rth = halfblock_data.get(('RTH', 25, 10), [])
    if hb_rth:
        for h in hb_rth:
            if h['completion_rate'] >= 0.75:
                lines.append(f"- **Safe zone:** Once a 25pt move reaches {h['progress_pct']:.0f}% "
                            f"progress, completion probability is {h['completion_rate']*100:.0f}%.\n")
                break

    with open(OUT_DIR / 'fractal_summary.md', 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))


# === MAIN ===

def main():
    t0 = time.time()
    print("Loading zigzag results...", flush=True)
    results = load_results()
    print(f"  Loaded in {time.time()-t0:.1f}s\n", flush=True)

    # Warm up numba
    _p = np.array([100., 103., 100., 104., 99., 105., 98.], dtype=np.float64)
    _d = np.array([-1, 1, -1, 1, -1, 1, -1], dtype=np.int8)
    _s = np.array([0, 0, 0, 0, 0, 0, 0], dtype=np.int32)
    _t = np.array([34200., 34300., 34400., 34500., 34600., 34700., 34800.], dtype=np.float32)
    _i = np.array([0, 10, 20, 30, 40, 50, 60], dtype=np.int64)
    _ = child_walk_completion(_p, _d, _s, _t, 25.0)
    _ = parent_child_overlay(_p, _d, _s, _i, _p, _d, _s, _i)
    del _p, _d, _s, _t, _i
    print("Numba warmup done.\n", flush=True)

    # Part 1
    part1_stats, all_sizes = part1(results)
    plot_part1(all_sizes)
    print("  Part 1 plots done.", flush=True)

    # Part 2
    overlay_rows, completion_data, halfblock_data = part2(results)
    plot_part2_completion(completion_data)
    plot_part2_halfblock(halfblock_data)
    print("  Part 2 plots done.", flush=True)

    # Save Part 2 decomposition table
    pd.DataFrame(overlay_rows).to_csv(OUT_DIR / 'part2_decomposition_table.csv', index=False)

    # Save completion rate data as CSV
    comp_rows = []
    for (split, pt, ct), comp in completion_data.items():
        for rc, vals in comp.items():
            comp_rows.append({
                'split': split, 'parent': pt, 'child': ct,
                'retrace_count': rc, **vals
            })
    pd.DataFrame(comp_rows).to_csv(OUT_DIR / 'part2_completion_rates.csv', index=False)

    # Part 3
    pl_rows = part3(all_sizes)
    plot_part3(all_sizes, pl_rows)
    pd.DataFrame(pl_rows).to_csv(OUT_DIR / 'part3_powerlaw_fits.csv', index=False)
    print("  Part 3 done.", flush=True)

    # Part 4
    df30, df60 = part4(results)
    df30.to_csv(OUT_DIR / 'part4_timeofday_30min.csv', index=False)
    df60.to_csv(OUT_DIR / 'part4_timeofday_60min.csv', index=False)
    plot_part4_heatmaps(df30)
    print("  Part 4 done.", flush=True)

    # Save Part 1 stats
    all_p1 = []
    for split, rows in part1_stats.items():
        all_p1.extend(rows)
    pd.DataFrame(all_p1).to_csv(OUT_DIR / 'part1_distribution_stats.csv', index=False)

    # Summary
    write_summary(part1_stats, overlay_rows, completion_data, halfblock_data,
                  pl_rows, df30, df60)
    print(f"\n  All outputs saved to {OUT_DIR}")
    print(f"  Total analysis time: {time.time()-t0:.1f}s", flush=True)


if __name__ == '__main__':
    main()
