# archetype: zone_touch
"""Prompt 0 v3.2: Baseline Establishment — Warmup-Enriched Data

Run all zone touches through a 120-cell exit grid (5 stops × 6 targets × 4 time caps),
compute the median-cell PF as the honest baseline anchor, then split by 12 structural
dimensions. No parameters are fit — all periods used. Population statistics only.
"""

import numpy as np
import pandas as pd
from pathlib import Path
import json, sys, time as time_mod, io

# Fix Windows encoding for stdout
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

np.random.seed(42)

# ============================================================
# CONSTANTS
# ============================================================
TICK = 0.25
STOPS = np.array([60, 90, 120, 160, 200])        # ticks
TARGETS = np.array([60, 90, 120, 160, 200, 240])  # ticks
TIME_CAPS = np.array([30, 50, 80, 120])            # bars
MAX_FWD = 120  # max forward bars (largest time cap)
N_BOOTSTRAP = 10000

BASE = Path(r"c:/Projects/pipeline")
DATA = BASE / "stages/01-data/output/zone_prep"
OUT  = BASE / "shared/archetypes/zone_touch/output"
OUT.mkdir(parents=True, exist_ok=True)

report_lines = []  # accumulate report text

def rprint(msg=""):
    """Print and accumulate for report."""
    print(msg)
    report_lines.append(msg)

# ============================================================
# STEP 1: LOAD & VERIFY
# ============================================================
rprint("=" * 70)
rprint("STEP 1: LOAD & VERIFY")
rprint("=" * 70)

t0 = time_mod.time()

period_names = ["P1a", "P1b", "P2a", "P2b"]
period_dfs = {}
for p in period_names:
    period_dfs[p] = pd.read_csv(DATA / f"NQ_merged_{p}.csv")
    rprint(f"  {p}: {len(period_dfs[p])} touches loaded")

touches = pd.concat(period_dfs.values(), ignore_index=True)
rprint(f"Total touches loaded: {len(touches)}")

# Load bar data
bar_p1 = pd.read_csv(DATA / "NQ_bardata_P1.csv", skipinitialspace=True)
bar_p2 = pd.read_csv(DATA / "NQ_bardata_P2.csv", skipinitialspace=True)
rprint(f"P1 bars: {len(bar_p1)},  P2 bars: {len(bar_p2)}")

# Load period config
with open(DATA / "period_config.json") as f:
    pconfig = json.load(f)
rprint("\nPeriod config:")
for p, info in pconfig["periods"].items():
    rprint(f"  {p}: {info['start']} to {info['end']}, {info['touches']} touches (parent={info.get('parent','-')})")

# Filter RotBarIndex < 0
neg_mask = touches["RotBarIndex"] < 0
if neg_mask.any():
    for p in period_names:
        cnt = ((touches["Period"] == p) & neg_mask).sum()
        if cnt > 0:
            rprint(f"  Removed {cnt} touches with RotBarIndex < 0 from {p}")
    touches = touches[~neg_mask].reset_index(drop=True)
    rprint(f"After RotBarIndex filter: {len(touches)} touches")
else:
    rprint("No touches with RotBarIndex < 0")

# Filter touches where entry bar would exceed bar data
rot = touches["RotBarIndex"].values.astype(np.int64)
per = touches["Period"].values
bar_lens = {"P1a": len(bar_p1), "P1b": len(bar_p1), "P2a": len(bar_p2), "P2b": len(bar_p2)}
valid = np.array([rot[i] + 1 < bar_lens[per[i]] for i in range(len(touches))])
invalid_cnt = (~valid).sum()
if invalid_cnt > 0:
    rprint(f"Removed {invalid_cnt} touches where entry bar exceeds bar data")
    touches = touches[valid].reset_index(drop=True)

n_total = len(touches)
rprint(f"\nFinal touch count: {n_total}")

# Print per-period distributions
rprint("\n--- Per-Period Summary ---")
for p in period_names:
    sub = touches[touches["Period"] == p]
    rprint(f"\n{p}: {len(sub)} touches")
    rprint(f"  TouchType: {dict(sub['TouchType'].value_counts())}")
    tf_counts = sub["SourceLabel"].value_counts()
    rprint(f"  Top TFs: {dict(tf_counts.head(5))}")
    rprint(f"  CascadeState: {dict(sub['CascadeState'].value_counts())}")
    rprint(f"  SBB: {dict(sub['SBB_Label'].value_counts())}")

# Spot-check bar mapping
rprint("\n--- Spot-Check Bar Mapping (5 per period) ---")
for p in period_names:
    sub = touches[touches["Period"] == p].head(5)
    bars = bar_p1 if p.startswith("P1") else bar_p2
    for _, row in sub.iterrows():
        eidx = int(row["RotBarIndex"]) + 1
        eopen = bars.iloc[eidx]["Open"]
        rprint(f"  {p}: RotBarIdx={int(row['RotBarIndex'])}, entry_bar={eidx}, "
               f"Open={eopen}, TouchPrice={row['TouchPrice']}")

# ============================================================
# STEP 2: PRECOMPUTE FORWARD EXCURSIONS
# ============================================================
rprint("\n" + "=" * 70)
rprint("STEP 2: PRECOMPUTE SIMULATION DATA")
rprint("=" * 70)

n = len(touches)

# Convert bar data to numpy arrays
bars_np = {}
for label, bdf in [("P1", bar_p1), ("P2", bar_p2)]:
    o = bdf["Open"].values.astype(np.float64)
    h = bdf["High"].values.astype(np.float64)
    l = bdf["Low"].values.astype(np.float64)
    c = bdf["Last"].values.astype(np.float64)
    # Parse times for EOD check
    times = pd.to_datetime(bdf["Date"].str.strip() + " " + bdf["Time"].str.strip())
    hrs = times.dt.hour.values.astype(np.int32)
    mins = times.dt.minute.values.astype(np.int32)
    bars_np[label] = {"O": o, "H": h, "L": l, "C": c, "hr": hrs, "mn": mins, "n": len(bdf)}

# Allocate arrays
entry_prices = np.full(n, np.nan, dtype=np.float64)
directions   = np.zeros(n, dtype=np.int8)  # +1 long, -1 short
avail_bars   = np.zeros(n, dtype=np.int32)

fwd_high  = np.full((n, MAX_FWD), np.nan, dtype=np.float64)
fwd_low   = np.full((n, MAX_FWD), np.nan, dtype=np.float64)
fwd_close = np.full((n, MAX_FWD), np.nan, dtype=np.float64)
fwd_eod   = np.zeros((n, MAX_FWD), dtype=bool)

rot_idx = touches["RotBarIndex"].values.astype(np.int64)
per_arr = touches["Period"].values
tt_arr  = touches["TouchType"].values

for i in range(n):
    bd = bars_np["P1" if per_arr[i].startswith("P1") else "P2"]
    eidx = int(rot_idx[i]) + 1
    entry_prices[i] = bd["O"][eidx]
    directions[i] = 1 if tt_arr[i] == "DEMAND_EDGE" else -1

    end = min(eidx + MAX_FWD, bd["n"])
    nb = end - eidx
    avail_bars[i] = nb

    fwd_high[i, :nb]  = bd["H"][eidx:end]
    fwd_low[i, :nb]   = bd["L"][eidx:end]
    fwd_close[i, :nb] = bd["C"][eidx:end]
    # EOD: 16:55-17:00 ET
    h = bd["hr"][eidx:end]
    m = bd["mn"][eidx:end]
    fwd_eod[i, :nb] = ((h == 16) & (m >= 55)) | ((h == 17) & (m == 0))

trunc = (avail_bars < MAX_FWD).sum()
rprint(f"Forward bars computed for {n} touches ({trunc} truncated at data boundary)")

# --- Running excursions (in ticks) ---
is_long = (directions == 1)[:, None]  # shape (n, 1) for broadcasting

fav_raw = np.where(is_long, (fwd_high - entry_prices[:, None]) / TICK,
                             (entry_prices[:, None] - fwd_low) / TICK)
adv_raw = np.where(is_long, (entry_prices[:, None] - fwd_low) / TICK,
                             (fwd_high - entry_prices[:, None]) / TICK)
# NaN → -999 so accumulate works
fav_raw = np.nan_to_num(fav_raw, nan=-999.0)
adv_raw = np.nan_to_num(adv_raw, nan=-999.0)

running_fav = np.maximum.accumulate(fav_raw, axis=1)
running_adv = np.maximum.accumulate(adv_raw, axis=1)

# Close PnL in ticks at each forward bar
close_pnl = directions[:, None] * (fwd_close - entry_prices[:, None]) / TICK
close_pnl = np.nan_to_num(close_pnl, nan=0.0)

# First EOD bar offset per touch (MAX_FWD if none)
eod_off = np.full(n, MAX_FWD, dtype=np.int32)
for i in range(n):
    where_eod = np.where(fwd_eod[i, :avail_bars[i]])[0]
    if len(where_eod) > 0:
        eod_off[i] = where_eod[0]

# First stop/target bar offsets (MAX_FWD if never hit)
first_stop = np.full((n, len(STOPS)), MAX_FWD, dtype=np.int32)
for si, sv in enumerate(STOPS):
    mask = running_adv >= sv
    hit = np.argmax(mask, axis=1)
    ever = np.any(mask, axis=1)
    first_stop[:, si] = np.where(ever, hit, MAX_FWD)

first_tgt = np.full((n, len(TARGETS)), MAX_FWD, dtype=np.int32)
for ti, tv in enumerate(TARGETS):
    mask = running_fav >= tv
    hit = np.argmax(mask, axis=1)
    ever = np.any(mask, axis=1)
    first_tgt[:, ti] = np.where(ever, hit, MAX_FWD)

rprint("First-hit offsets computed for all stop/target levels")

# ============================================================
# GRID SIMULATION WITH NO-OVERLAP
# ============================================================
rprint("\n" + "=" * 70)
rprint("STEP 2a: 120-CELL EXIT GRID — FULL POPULATION BASELINE")
rprint("=" * 70)

entry_bars_abs = rot_idx + 1  # absolute bar index in respective bar file
p1_mask_bool = np.array([p.startswith("P1") for p in per_arr])
p2_mask_bool = ~p1_mask_bool

# Pre-sort indices within each group by entry bar
p1_idx = np.where(p1_mask_bool)[0]
p1_sort = p1_idx[np.argsort(entry_bars_abs[p1_idx])]
p2_idx = np.where(p2_mask_bool)[0]
p2_sort = p2_idx[np.argsort(entry_bars_abs[p2_idx])]


def compute_cell(si, ti, tci):
    """Compute per-touch outcomes for one grid cell. Returns (pnl_ticks, end_offset)."""
    sv, tv, tc = STOPS[si], TARGETS[ti], TIME_CAPS[tci]

    # Effective end offset (0-indexed): min of (tc-1, eod, avail-1)
    eff_end = np.minimum(tc - 1, eod_off)
    eff_end = np.minimum(eff_end, avail_bars - 1)
    eff_end = np.maximum(eff_end, 0)

    sb = first_stop[:, si]
    tb = first_tgt[:, ti]

    stop_in  = sb <= eff_end
    tgt_in   = tb <= eff_end

    both = stop_in & tgt_in
    tgt_wins  = both & (tb < sb)
    stop_wins = both & ~tgt_wins
    only_stop = stop_in & ~tgt_in
    only_tgt  = tgt_in & ~stop_in
    neither   = ~stop_in & ~tgt_in

    # PnL in ticks (gross, before cost)
    idx_range = np.arange(n)
    pnl_at_end = close_pnl[idx_range, eff_end]

    pnl = np.where(tgt_wins | only_tgt, tv,
          np.where(stop_wins | only_stop, -sv,
                   pnl_at_end))

    end_off_arr = np.where(tgt_wins, tb,
                  np.where(stop_wins | only_stop, sb,
                  np.where(only_tgt, tb, eff_end)))

    return pnl, end_off_arr


def no_overlap_filter(sorted_indices, pnl, end_off):
    """Apply no-overlap within a sorted group. Returns mask of taken trades."""
    taken = np.zeros(n, dtype=bool)
    flat_bar = -1
    for idx in sorted_indices:
        eb = entry_bars_abs[idx]
        if eb > flat_bar:
            taken[idx] = True
            flat_bar = eb + int(end_off[idx])
    return taken


# Run all 120 cells
n_cells = len(STOPS) * len(TARGETS) * len(TIME_CAPS)
grid = {}  # key = (si, ti, tci)

rprint(f"Computing {n_cells} grid cells with no-overlap filtering...")
t_grid = time_mod.time()

for si in range(len(STOPS)):
    for ti in range(len(TARGETS)):
        for tci in range(len(TIME_CAPS)):
            pnl, eoff = compute_cell(si, ti, tci)
            tk1 = no_overlap_filter(p1_sort, pnl, eoff)
            tk2 = no_overlap_filter(p2_sort, pnl, eoff)
            taken = tk1 | tk2
            trade_pnl = pnl[taken]
            n_trades = int(taken.sum())

            pfs = {}
            net_pnls = {}
            for cost in [2, 3, 4]:
                net = trade_pnl - cost
                gw = net[net > 0].sum()
                gl = abs(net[net < 0].sum())
                pfs[cost] = gw / max(gl, 0.001)
                net_pnls[cost] = net

            grid[(si, ti, tci)] = {
                "n_trades": n_trades,
                "pf_2t": pfs[2], "pf_3t": pfs[3], "pf_4t": pfs[4],
                "net_pnl_3t": net_pnls[3],
                "taken": taken,
                "gross_pnl": trade_pnl,
            }

rprint(f"Grid computed in {time_mod.time() - t_grid:.1f}s")

# --- Grid summary ---
pf3_all = np.array([grid[k]["pf_3t"] for k in grid])
pf4_all = np.array([grid[k]["pf_4t"] for k in grid])

gt10 = (pf3_all > 1.0).sum()
gt13 = (pf3_all > 1.3).sum()
gt15 = (pf3_all > 1.5).sum()
median_pf = np.median(pf3_all)

best_key = max(grid, key=lambda k: grid[k]["pf_3t"])
worst_key = min(grid, key=lambda k: grid[k]["pf_3t"])
best_pf = grid[best_key]["pf_3t"]
worst_pf = grid[worst_key]["pf_3t"]

rprint(f"\n--- Grid Summary (@3t cost) ---")
rprint(f"  Cells with PF > 1.0: {gt10}/{n_cells} ({100*gt10/n_cells:.1f}%)")
rprint(f"  Cells with PF > 1.3: {gt13}/{n_cells} ({100*gt13/n_cells:.1f}%)")
rprint(f"  Cells with PF > 1.5: {gt15}/{n_cells} ({100*gt15/n_cells:.1f}%)")
rprint(f"  Median PF @3t: {median_pf:.4f}")
rprint(f"  Best  PF @3t: {best_pf:.4f} (Stop={STOPS[best_key[0]]}t, Target={TARGETS[best_key[1]]}t, TC={TIME_CAPS[best_key[2]]})")
rprint(f"  Worst PF @3t: {worst_pf:.4f} (Stop={STOPS[worst_key[0]]}t, Target={TARGETS[worst_key[1]]}t, TC={TIME_CAPS[worst_key[2]]})")

# Find the median cell (cell closest to median PF)
median_key = min(grid, key=lambda k: abs(grid[k]["pf_3t"] - median_pf))
mc = grid[median_key]
mc_stop = STOPS[median_key[0]]
mc_tgt  = TARGETS[median_key[1]]
mc_tc   = TIME_CAPS[median_key[2]]

rprint(f"\nMEDIAN CELL: Stop={mc_stop}t, Target={mc_tgt}t, TimeCap={mc_tc} bars, "
       f"PF @3t = {mc['pf_3t']:.4f}")

# --- Heatmap at TC=80 ---
tc80_idx = np.where(TIME_CAPS == 80)[0][0]
rprint(f"\n--- Stop × Target Heatmap (TC=80 bars, PF @3t) ---")
header = "        " + "  ".join(f"T={t:>3}t" for t in TARGETS)
rprint(header)
for si, sv in enumerate(STOPS):
    row_vals = [grid[(si, ti, tc80_idx)]["pf_3t"] for ti in range(len(TARGETS))]
    row_str = f"S={sv:>3}t " + "  ".join(f"{v:6.3f}" for v in row_vals)
    rprint(row_str)

# --- Median cell detail ---
mc_net = mc["net_pnl_3t"]
mc_gross = mc["gross_pnl"]
mc_trades = mc["n_trades"]
mc_taken = mc["taken"]
mc_wins = (mc_net > 0).sum()
mc_losses = (mc_net < 0).sum()
mc_flat = (mc_net == 0).sum()
mc_winrate = mc_wins / max(mc_trades, 1) * 100
mc_avg_pnl = mc_net.mean()
mc_avg_win = mc_net[mc_net > 0].mean() if mc_wins > 0 else 0
mc_avg_loss = mc_net[mc_net < 0].mean() if mc_losses > 0 else 0

# Max consecutive losses
consec_loss = 0
max_consec = 0
for v in mc_net:
    if v < 0:
        consec_loss += 1
        max_consec = max(max_consec, consec_loss)
    else:
        consec_loss = 0

rprint(f"\n--- Median Cell Risk Profile ---")
rprint(f"  Total trades (after no-overlap): {mc_trades}")
rprint(f"  Trades skipped (overlap): {n_total - mc_trades}")
rprint(f"  Win rate: {mc_winrate:.1f}%")
rprint(f"  Avg trade PnL @3t: {mc_avg_pnl:.2f} ticks")
rprint(f"  Avg winning trade: {mc_avg_win:.2f} ticks")
rprint(f"  Avg losing trade: {mc_avg_loss:.2f} ticks")
rprint(f"  Max consecutive losses: {max_consec}")

# Seq distribution of trades taken at median cell
rprint(f"\n--- Seq Distribution (Median Cell, after no-overlap) ---")
seq_vals = touches["TouchSequence"].values
rprint(f"{'Seq':>5} {'Taken':>7} {'%':>7} {'Skipped':>8}")
for s in [1, 2, 3, 4]:
    if s < 4:
        smask = seq_vals == s
        label = str(s)
    else:
        smask = seq_vals >= 4
        label = "4+"
    total_s = smask.sum()
    taken_s = (smask & mc_taken).sum()
    skip_s = total_s - taken_s
    rprint(f"{label:>5} {taken_s:>7} {100*taken_s/max(mc_trades,1):>6.1f}% {skip_s:>8}")

# --- Bootstrap CI ---
rprint(f"\n--- Bootstrap 95% CI (10,000 resamples) ---")


def bootstrap_pf(net_pnl, n_resamp=N_BOOTSTRAP, chunk=2000):
    pfs = []
    nn = len(net_pnl)
    for start in range(0, n_resamp, chunk):
        c = min(chunk, n_resamp - len(pfs))
        idx = np.random.randint(0, nn, size=(c, nn))
        samp = net_pnl[idx]
        w = np.where(samp > 0, samp, 0).sum(axis=1)
        lo = np.abs(np.where(samp < 0, samp, 0).sum(axis=1))
        pfs.extend((w / np.maximum(lo, 0.001)).tolist())
    return np.percentile(pfs, [2.5, 97.5])


mc_ci = bootstrap_pf(mc_net)
rprint(f"  Median cell PF @3t: {mc['pf_3t']:.4f} (95% CI: {mc_ci[0]:.4f} – {mc_ci[1]:.4f})")
rprint(f"  CI excludes 1.0? {'YES' if mc_ci[0] > 1.0 else 'NO'}")

bc_net = grid[best_key]["net_pnl_3t"]
bc_ci = bootstrap_pf(bc_net)
rprint(f"  Best cell PF @3t: {best_pf:.4f} (95% CI: {bc_ci[0]:.4f} – {bc_ci[1]:.4f})")

# ============================================================
# POPULATION R/P RATIOS
# ============================================================
rprint("\n" + "=" * 70)
rprint("POPULATION R/P RATIOS (ALL TOUCHES)")
rprint("=" * 70)

rprint(f"\n--- Horizon-Specific R/P (computed from bar data) ---")
for horizon in [30, 60, 120]:
    # For each touch, compute reaction and penetration over horizon bars from entry
    fav_at_h = np.zeros(n)
    adv_at_h = np.zeros(n)
    trunc_h = 0
    for i in range(n):
        h = min(horizon, avail_bars[i])
        if h < horizon:
            trunc_h += 1
        if h == 0:
            continue
        fav_at_h[i] = running_fav[i, h - 1]  # already in ticks
        adv_at_h[i] = running_adv[i, h - 1]
    mean_rxn = fav_at_h.mean()
    mean_pen = adv_at_h.mean()
    rp = mean_rxn / max(mean_pen, 1.0)
    rprint(f"  {horizon:>3} bars: Mean Reaction={mean_rxn:.1f}t, Mean Penetration={mean_pen:.1f}t, "
           f"R/P={rp:.3f}  (truncated={trunc_h})")

# Full observation R/P from CSV columns
full_rxn = touches["Reaction"].values.astype(np.float64)
full_pen = touches["Penetration"].values.astype(np.float64)
full_rp = full_rxn.mean() / max(full_pen.mean(), 1.0)
rprint(f"  Full obs: Mean Reaction={full_rxn.mean():.1f}t, Mean Penetration={full_pen.mean():.1f}t, "
       f"R/P={full_rp:.3f}")

# ============================================================
# HELPER: run median cell on a subpopulation
# ============================================================


def run_median_cell_on_subset(subset_mask, label=""):
    """Simulate median cell params on a subset of touches WITH no-overlap."""
    si, ti, tci = median_key
    sv, tv, tc = mc_stop, mc_tgt, mc_tc

    eff_end = np.minimum(tc - 1, eod_off)
    eff_end = np.minimum(eff_end, avail_bars - 1)
    eff_end = np.maximum(eff_end, 0)

    sb = first_stop[:, si]
    tb = first_tgt[:, ti]
    stop_in = sb <= eff_end
    tgt_in  = tb <= eff_end

    both = stop_in & tgt_in
    tgt_wins  = both & (tb < sb)
    stop_wins = both & ~tgt_wins
    only_stop = stop_in & ~tgt_in
    only_tgt  = tgt_in & ~stop_in

    idx_range = np.arange(n)
    pnl_at_end = close_pnl[idx_range, eff_end]
    pnl = np.where(tgt_wins | only_tgt, tv,
          np.where(stop_wins | only_stop, -sv, pnl_at_end))

    end_off_arr = np.where(tgt_wins, tb,
                  np.where(stop_wins | only_stop, sb,
                  np.where(only_tgt, tb, eff_end)))

    # Apply no-overlap within subset, still respecting P1/P2 groups
    sub_p1 = np.where(subset_mask & p1_mask_bool)[0]
    sub_p1_sorted = sub_p1[np.argsort(entry_bars_abs[sub_p1])]
    sub_p2 = np.where(subset_mask & p2_mask_bool)[0]
    sub_p2_sorted = sub_p2[np.argsort(entry_bars_abs[sub_p2])]

    taken = np.zeros(n, dtype=bool)
    for sorted_idx in [sub_p1_sorted, sub_p2_sorted]:
        flat_bar = -1
        for idx in sorted_idx:
            if entry_bars_abs[idx] > flat_bar:
                taken[idx] = True
                flat_bar = entry_bars_abs[idx] + int(end_off_arr[idx])

    trade_pnl = pnl[taken]
    nt = int(taken.sum())
    if nt == 0:
        return {"n_trades": 0, "pf_3t": 0, "pf_4t": 0}

    results = {"n_trades": nt}
    for cost in [3, 4]:
        net = trade_pnl - cost
        gw = net[net > 0].sum()
        gl = abs(net[net < 0].sum())
        results[f"pf_{cost}t"] = gw / max(gl, 0.001)
    return results


# R/P at 60 bars for a subset
def rp60_subset(subset_mask):
    valid = subset_mask & (avail_bars >= 60)
    if valid.sum() == 0:
        return 0.0
    rxn = running_fav[valid, 59]
    pen = running_adv[valid, 59]
    return rxn.mean() / max(pen.mean(), 1.0)


# ============================================================
# STEP 2b: SBB SPLIT
# ============================================================
rprint("\n" + "=" * 70)
rprint("STEP 2b: SBB SPLIT BASELINE")
rprint("=" * 70)

sbb_arr = touches["SBB_Label"].values

for lbl in ["ALL", "NORMAL", "SBB"]:
    if lbl == "ALL":
        mask = np.ones(n, dtype=bool)
    elif lbl == "NORMAL":
        mask = sbb_arr == "NORMAL"
    else:
        mask = sbb_arr == "SBB"
    res = run_median_cell_on_subset(mask, lbl)
    pct = 100 * mask.sum() / n
    rprint(f"  {lbl:>8}: PF@3t={res['pf_3t']:.4f}  PF@4t={res['pf_4t']:.4f}  "
           f"Trades={res['n_trades']}  ({pct:.1f}% of pop)")

# ============================================================
# STEP 2c: PER-PERIOD STABILITY
# ============================================================
rprint("\n" + "=" * 70)
rprint("STEP 2c: PER-PERIOD STABILITY")
rprint("=" * 70)

for p in period_names + ["Combined"]:
    if p == "Combined":
        mask = np.ones(n, dtype=bool)
    else:
        mask = per_arr == p
    res = run_median_cell_on_subset(mask, p)
    rprint(f"  {p:>10}: PF@3t={res['pf_3t']:.4f}  PF@4t={res['pf_4t']:.4f}  Trades={res['n_trades']}")

# ============================================================
# STEP 2d: DIRECTION SPLIT
# ============================================================
rprint("\n" + "=" * 70)
rprint("STEP 2d: DIRECTION SPLIT")
rprint("=" * 70)

for d in ["DEMAND_EDGE", "SUPPLY_EDGE", "Combined"]:
    if d == "Combined":
        mask = np.ones(n, dtype=bool)
    else:
        mask = tt_arr == d
    lbl = {"DEMAND_EDGE": "Demand (long)", "SUPPLY_EDGE": "Supply (short)"}.get(d, d)
    res = run_median_cell_on_subset(mask, lbl)
    rprint(f"  {lbl:>16}: PF@3t={res['pf_3t']:.4f}  PF@4t={res['pf_4t']:.4f}  Trades={res['n_trades']}")

# ============================================================
# STEP 2e: SESSION SPLIT
# ============================================================
rprint("\n" + "=" * 70)
rprint("STEP 2e: SESSION SPLIT")
rprint("=" * 70)

touch_dt = pd.to_datetime(touches["DateTime"])
touch_mins = touch_dt.dt.hour * 60 + touch_dt.dt.minute
is_rth = ((touch_mins >= 510) & (touch_mins < 1020)).values  # 8:30-17:00

for lbl, mask in [("RTH (8:30-17:00)", is_rth),
                   ("Overnight", ~is_rth),
                   ("Combined", np.ones(n, dtype=bool))]:
    res = run_median_cell_on_subset(mask, lbl)
    rprint(f"  {lbl:>20}: PF@3t={res['pf_3t']:.4f}  PF@4t={res['pf_4t']:.4f}  Trades={res['n_trades']}")

# ============================================================
# STEP 2f: CASCADE STATE SPLIT
# ============================================================
rprint("\n" + "=" * 70)
rprint("STEP 2f: CASCADE STATE SPLIT")
rprint("=" * 70)

cs_arr = touches["CascadeState"].values
for cs in ["PRIOR_HELD", "PRIOR_BROKE", "NO_PRIOR", "Combined"]:
    if cs == "Combined":
        mask = np.ones(n, dtype=bool)
    else:
        mask = cs_arr == cs
    res = run_median_cell_on_subset(mask, cs)
    rp = rp60_subset(mask)
    rprint(f"  {cs:>12}: PF@3t={res['pf_3t']:.4f}  PF@4t={res['pf_4t']:.4f}  "
           f"Trades={res['n_trades']}  ({100*mask.sum()/n:.1f}%)  R/P@60={rp:.3f}")

# ============================================================
# STEP 2g: TIMEFRAME SPLIT
# ============================================================
rprint("\n" + "=" * 70)
rprint("STEP 2g: TIMEFRAME SPLIT")
rprint("=" * 70)

sl_arr = touches["SourceLabel"].values
tf_order = ["15m", "30m", "60m", "90m", "120m", "240m", "360m", "480m", "720m"]
rprint(f"{'TF':>6} {'PF@3t':>8} {'PF@4t':>8} {'Trades':>7} {'SBB%':>6} {'R/P@60':>7}")
for tf in tf_order:
    mask = sl_arr == tf
    if mask.sum() == 0:
        continue
    res = run_median_cell_on_subset(mask, tf)
    sbb_rate = (sbb_arr[mask] == "SBB").sum() / max(mask.sum(), 1) * 100
    rp = rp60_subset(mask)
    rprint(f"{tf:>6} {res['pf_3t']:>8.4f} {res['pf_4t']:>8.4f} {res['n_trades']:>7} "
           f"{sbb_rate:>5.1f}% {rp:>7.3f}")

# Combined
res = run_median_cell_on_subset(np.ones(n, dtype=bool))
rprint(f"{'Comb':>6} {res['pf_3t']:>8.4f} {res['pf_4t']:>8.4f} {res['n_trades']:>7}")

# ============================================================
# STEP 2h: TOUCH SEQUENCE SPLIT
# ============================================================
rprint("\n" + "=" * 70)
rprint("STEP 2h: TOUCH SEQUENCE SPLIT")
rprint("=" * 70)

seq_arr = touches["TouchSequence"].values
rprint(f"{'Seq':>5} {'PF@3t':>8} {'PF@4t':>8} {'Trades':>7} {'R/P@60':>7}")
for s in [1, 2, 3, 4, 5]:
    if s < 5:
        mask = seq_arr == s
        label = str(s)
    else:
        mask = seq_arr >= 5
        label = "5+"
    if mask.sum() == 0:
        continue
    res = run_median_cell_on_subset(mask, label)
    rp = rp60_subset(mask)
    rprint(f"{label:>5} {res['pf_3t']:>8.4f} {res['pf_4t']:>8.4f} {res['n_trades']:>7} {rp:>7.3f}")

# ============================================================
# ZONE LIFECYCLE CONSTRUCTION
# ============================================================
rprint("\n" + "=" * 70)
rprint("ZONE LIFECYCLE CONSTRUCTION")
rprint("=" * 70)

t_lc = touches.copy()
t_lc["dt_parsed"] = pd.to_datetime(t_lc["DateTime"])
t_lc = t_lc.sort_values("dt_parsed").reset_index(drop=True)

# Zone key: direction + price bounds + timeframe
t_lc["zone_key"] = (t_lc["TouchType"] + "_" +
                     t_lc["ZoneTop"].astype(str) + "_" +
                     t_lc["ZoneBot"].astype(str) + "_" +
                     t_lc["SourceLabel"])

# Instance ID: cumsum of seq==1 within each zone_key
t_lc["new_zone"] = t_lc["TouchSequence"] == 1
t_lc["zone_inst"] = t_lc.groupby("zone_key")["new_zone"].cumsum()
t_lc["ZoneID"] = t_lc["zone_key"] + "#" + t_lc["zone_inst"].astype(str)

# Build lifecycle table
zone_records = []
for zid, grp in t_lc.groupby("ZoneID"):
    birth = grp["dt_parsed"].iloc[0]
    direction = grp["TouchType"].iloc[0]
    zprice = grp["TouchPrice"].iloc[0]
    zwidth = grp["ZoneWidthTicks"].iloc[0]
    src = grp["SourceLabel"].iloc[0]
    period = grp["Period"].iloc[0]  # first period seen

    # Death: first touch with SBB or Penetration > ZoneWidthTicks
    death_mask = (grp["SBB_Label"] == "SBB") | (grp["Penetration"] > grp["ZoneWidthTicks"])
    if death_mask.any():
        death_row = grp[death_mask].iloc[0]
        death_dt = death_row["dt_parsed"]
        death_cause = "SBB" if death_row["SBB_Label"] == "SBB" else "PENETRATION"
        death_rot = int(death_row["RotBarIndex"])
        death_per = death_row["Period"]
    else:
        death_dt = None
        death_cause = "ALIVE"
        death_rot = -1
        death_per = None

    zone_records.append({
        "ZoneID": zid, "direction": direction, "ZonePrice": zprice,
        "ZoneWidthTicks": zwidth, "SourceLabel": src,
        "birth_datetime": birth, "death_datetime": death_dt,
        "death_cause": death_cause, "birth_period": period,
        "death_rot_bar": death_rot, "death_period": death_per,
    })

zl_df = pd.DataFrame(zone_records)
zl_df["birth_ts"] = pd.to_datetime(zl_df["birth_datetime"])
zl_df["death_ts"] = pd.to_datetime(zl_df["death_datetime"])

n_zones = len(zl_df)
n_dead = (zl_df["death_cause"] != "ALIVE").sum()
rprint(f"Zone lifecycle: {n_zones} unique zones, {n_dead} dead, {n_zones - n_dead} alive")
rprint(f"  Death causes: {dict(zl_df['death_cause'].value_counts())}")

# Save zone lifecycle
zl_out = zl_df[["ZoneID", "direction", "ZonePrice", "ZoneWidthTicks", "SourceLabel",
                 "birth_datetime", "death_datetime", "death_cause"]].copy()
zl_out.to_csv(OUT / "zone_lifecycle.csv", index=False)
rprint(f"  Saved zone_lifecycle.csv ({n_zones} rows)")

# Map ZoneID back to touches for density/contagion
# t_lc is sorted by datetime; map back via original index isn't trivial.
# Instead, join on merge columns.
touches_with_zid = t_lc[["ZoneID", "dt_parsed", "RotBarIndex", "Period",
                          "TouchType", "TouchPrice", "ZoneWidthTicks",
                          "SourceLabel", "SBB_Label", "Penetration",
                          "CascadeState", "TouchSequence"]].copy()

# ============================================================
# STEP 2i: ZONE DENSITY SPLIT
# ============================================================
rprint("\n" + "=" * 70)
rprint("STEP 2i: ZONE DENSITY SPLIT")
rprint("=" * 70)

# For each touch, count active same-direction zones within 500 ticks (125 pts)
DENSITY_RADIUS_PTS = 500 * TICK  # 125 points

# Split lifecycle by direction for faster lookup
zl_demand = zl_df[zl_df["direction"] == "DEMAND_EDGE"].copy()
zl_supply = zl_df[zl_df["direction"] == "SUPPLY_EDGE"].copy()

density_counts = np.zeros(n, dtype=np.int32)
# Use the original touches order, not t_lc order
# We need to match touches (original) to ZoneIDs somehow.
# Easiest: iterate t_lc (sorted), compute density, then map back.

density_by_tlc = np.zeros(len(t_lc), dtype=np.int32)
for i in range(len(t_lc)):
    row = t_lc.iloc[i]
    dt = row["dt_parsed"]
    direction = row["TouchType"]
    price = row["TouchPrice"]
    zid = row["ZoneID"]

    zl = zl_demand if direction == "DEMAND_EDGE" else zl_supply
    active = (
        (zl["birth_ts"] <= dt) &
        ((zl["death_ts"].isna()) | (zl["death_ts"] > dt)) &
        (np.abs(zl["ZonePrice"] - price) <= DENSITY_RADIUS_PTS) &
        (zl["ZoneID"] != zid)
    )
    density_by_tlc[i] = active.sum()

rprint(f"Density computed for {len(t_lc)} touches")

# Classify: Isolated (0), Sparse (1), Clustered (2+)
# Map back to original touches order via t_lc sort
# t_lc was sorted by dt_parsed. We need to map density back to the original 'touches' df.
# Since we used t_lc = touches.copy() then sorted, we lost the original index.
# Let me re-do: use the index mapping

# Actually, for the split analysis, we need a mask on the original 'touches' df.
# Let me create a series mapping original index to density.
# t_lc was built from touches.copy(), but then reset_index. The original touch indices
# are lost. Let me rebuild this mapping.

# Approach: store original index before sorting
t_lc2 = touches.copy()
t_lc2["orig_idx"] = np.arange(n)
t_lc2["dt_parsed"] = pd.to_datetime(t_lc2["DateTime"])
t_lc2 = t_lc2.sort_values("dt_parsed").reset_index(drop=True)
t_lc2["zone_key"] = (t_lc2["TouchType"] + "_" +
                      t_lc2["ZoneTop"].astype(str) + "_" +
                      t_lc2["ZoneBot"].astype(str) + "_" +
                      t_lc2["SourceLabel"])
t_lc2["new_zone"] = t_lc2["TouchSequence"] == 1
t_lc2["zone_inst"] = t_lc2.groupby("zone_key")["new_zone"].cumsum()
t_lc2["ZoneID"] = t_lc2["zone_key"] + "#" + t_lc2["zone_inst"].astype(str)

# Now density_by_tlc was computed on t_lc (same sort order as t_lc2)
# Map back to original index
orig_density = np.zeros(n, dtype=np.int32)
for i in range(len(t_lc2)):
    orig_density[int(t_lc2.iloc[i]["orig_idx"])] = density_by_tlc[i]

rprint(f"\n{'Density':>12} {'PF@3t':>8} {'PF@4t':>8} {'Trades':>7} {'R/P@60':>7}")
for label, lo, hi in [("Isolated", 0, 0), ("Sparse", 1, 1), ("Clustered", 2, 999)]:
    mask = (orig_density >= lo) & (orig_density <= hi)
    if mask.sum() == 0:
        rprint(f"{label:>12}  (no touches)")
        continue
    res = run_median_cell_on_subset(mask, label)
    rp = rp60_subset(mask)
    rprint(f"{label:>12} {res['pf_3t']:>8.4f} {res['pf_4t']:>8.4f} {res['n_trades']:>7} {rp:>7.3f}")

# Combined
res = run_median_cell_on_subset(np.ones(n, dtype=bool))
rprint(f"{'Combined':>12} {res['pf_3t']:>8.4f} {res['pf_4t']:>8.4f} {res['n_trades']:>7}")

# ============================================================
# STEP 2j: BREAK CONTAGION ANALYSIS
# ============================================================
rprint("\n" + "=" * 70)
rprint("STEP 2j: BREAK CONTAGION ANALYSIS")
rprint("=" * 70)

# For each zone death event, find nearby active same-dir zones at death time,
# check if they also died within 200 bars.
# We use RotBarIndex and process P1/P2 separately.

dead_zones = zl_df[zl_df["death_cause"] != "ALIVE"].copy()

contagion_stats = {"total_deaths": 0, "nearby_at_risk": 0, "nearby_died_200": 0}

for parent_period in ["P1", "P2"]:
    # Filter to zones that have a death in this period group
    dz = dead_zones[dead_zones["death_period"].str.startswith(parent_period)].copy()
    # All zones for lifecycle check
    all_z = zl_df.copy()

    for _, drow in dz.iterrows():
        death_dt = drow["death_ts"]
        death_bar = drow["death_rot_bar"]
        direction = drow["direction"]
        price = drow["ZonePrice"]
        zid = drow["ZoneID"]

        if death_bar < 0:
            continue

        contagion_stats["total_deaths"] += 1

        # Find active same-direction zones within 500 ticks at death time
        nearby = all_z[
            (all_z["direction"] == direction) &
            (all_z["ZoneID"] != zid) &
            (all_z["birth_ts"] <= death_dt) &
            ((all_z["death_ts"].isna()) | (all_z["death_ts"] > death_dt)) &
            (np.abs(all_z["ZonePrice"] - price) <= DENSITY_RADIUS_PTS)
        ]

        n_nearby = len(nearby)
        contagion_stats["nearby_at_risk"] += n_nearby

        # Check if each nearby zone died within 200 bars
        # We need the death RotBarIndex of nearby zones.
        # Look up from the death events in t_lc2.
        for _, nrow in nearby.iterrows():
            nzid = nrow["ZoneID"]
            if pd.isna(nrow["death_ts"]):
                continue
            # Find the death touch for this zone
            ndeath = dead_zones[dead_zones["ZoneID"] == nzid]
            if len(ndeath) == 0:
                continue
            ndeath_bar = ndeath.iloc[0]["death_rot_bar"]
            ndeath_per = ndeath.iloc[0]["death_period"]
            # Same parent period and within 200 bars
            if (ndeath_per is not None and
                str(ndeath_per).startswith(parent_period) and
                ndeath_bar >= 0 and
                ndeath_bar - death_bar <= 200 and
                ndeath_bar >= death_bar):
                contagion_stats["nearby_died_200"] += 1

# Base rate: for all touches, how many nearby active same-dir zones die within 200 bars?
# This is computationally expensive, so use a sampled approach
rprint(f"\n  Total zone death events: {contagion_stats['total_deaths']}")
rprint(f"  Nearby zones at risk: {contagion_stats['nearby_at_risk']}")
rprint(f"  Nearby died within 200 bars: {contagion_stats['nearby_died_200']}")

cond_rate = (contagion_stats["nearby_died_200"] /
             max(contagion_stats["nearby_at_risk"], 1))
rprint(f"  Conditional break rate: {cond_rate:.4f}")

# Base rate: compute from a sample of all touches (every 10th touch for speed)
base_at_risk = 0
base_died = 0
sample_step = max(1, len(t_lc2) // 500)  # ~500 samples
for i in range(0, len(t_lc2), sample_step):
    row = t_lc2.iloc[i]
    dt = row["dt_parsed"]
    direction = row["TouchType"]
    price = row["TouchPrice"]
    period = row["Period"]
    parent_p = "P1" if period.startswith("P1") else "P2"
    rot_bar = int(row["RotBarIndex"])

    zl = zl_demand if direction == "DEMAND_EDGE" else zl_supply
    nearby = zl[
        (zl["birth_ts"] <= dt) &
        ((zl["death_ts"].isna()) | (zl["death_ts"] > dt)) &
        (np.abs(zl["ZonePrice"] - price) <= DENSITY_RADIUS_PTS)
    ]
    base_at_risk += len(nearby)

    for _, nrow in nearby.iterrows():
        if pd.isna(nrow["death_ts"]):
            continue
        ndeath = dead_zones[dead_zones["ZoneID"] == nrow["ZoneID"]]
        if len(ndeath) == 0:
            continue
        ndeath_bar = ndeath.iloc[0]["death_rot_bar"]
        ndeath_per = ndeath.iloc[0]["death_period"]
        if (ndeath_per is not None and
            str(ndeath_per).startswith(parent_p) and
            ndeath_bar >= 0 and
            ndeath_bar - rot_bar <= 200 and
            ndeath_bar >= rot_bar):
            base_died += 1

base_rate = base_died / max(base_at_risk, 1)
contagion_ratio = cond_rate / max(base_rate, 0.0001)
rprint(f"  Base rate (sampled): {base_rate:.4f}")
rprint(f"  Contagion ratio: {contagion_ratio:.2f}")

if contagion_ratio > 2.0:
    rprint("  => Breaks cascade strongly (ratio > 2.0)")
elif contagion_ratio > 1.0:
    rprint("  => Mild break clustering (ratio 1.0-2.0)")
else:
    rprint("  => Breaks are independent (ratio ~1.0)")

# ============================================================
# STEP 2k: TIME CAP SENSITIVITY
# ============================================================
rprint("\n" + "=" * 70)
rprint("STEP 2k: TIME CAP SENSITIVITY (median cell stop/target, all time caps)")
rprint("=" * 70)

si_med, ti_med = median_key[0], median_key[1]
rprint(f"{'TimeCap':>8} {'PF@3t':>8} {'Trades':>7}")
for tci in range(len(TIME_CAPS)):
    key = (si_med, ti_med, tci)
    rprint(f"{TIME_CAPS[tci]:>7}b {grid[key]['pf_3t']:>8.4f} {grid[key]['n_trades']:>7}")

# ============================================================
# STEP 2l: BASELINE VERDICT
# ============================================================
rprint("\n" + "=" * 70)
rprint("STEP 2l: BASELINE VERDICT")
rprint("=" * 70)

pct_gt1 = 100 * gt10 / n_cells

# Determine risk level
if pct_gt1 > 70 and mc_ci[0] > 1.0:
    verdict = "LOW"
    verdict_text = ("Zone touches have a statistically confirmed inherent edge. "
                    "Features refine it. LOW overfit risk.")
elif pct_gt1 >= 30 or mc_ci[0] <= 1.0:
    verdict = "MODERATE"
    verdict_text = ("Moderate/uncertain edge. Features needed to select profitable subset. "
                    "MODERATE overfit risk.")
else:
    verdict = "HIGH"
    verdict_text = ("No robust unfiltered edge. Features must create the entire edge. "
                    "HIGH overfit risk — but viable if screening finds strong features.")

rprint(f"\nVERDICT: {verdict} overfit risk")
rprint(verdict_text)

# Cost robustness
median_pf_4t = np.median(pf4_all)
rprint(f"\nCost robustness: Median PF @4t = {median_pf_4t:.4f} "
       f"({'> 1.0 OK' if median_pf_4t > 1.0 else '< 1.0 -- fragile'})")

# --- Collect split results for summary ---
def get_pf(sub_mask):
    r = run_median_cell_on_subset(sub_mask)
    return r["pf_3t"]

# Full baseline summary string
rp60_pop = rp60_subset(np.ones(n, dtype=bool))

# Per-period PFs
pp = {}
for p in period_names:
    pp[p] = get_pf(per_arr == p)

# Direction PFs
dem_pf = get_pf(tt_arr == "DEMAND_EDGE")
sup_pf = get_pf(tt_arr == "SUPPLY_EDGE")

# Session PFs
rth_pf = get_pf(is_rth)
ovn_pf = get_pf(~is_rth)

# Cascade PFs
held_pf = get_pf(cs_arr == "PRIOR_HELD")
broke_pf = get_pf(cs_arr == "PRIOR_BROKE")
nopr_pf = get_pf(cs_arr == "NO_PRIOR")

# TF PFs
tf_pfs = {}
for tf in tf_order:
    m = sl_arr == tf
    if m.sum() > 0:
        tf_pfs[tf] = get_pf(m)
    else:
        tf_pfs[tf] = 0.0

# Seq PFs
seq_pfs = {}
for s in [1, 2, 3, 4]:
    if s < 4:
        m = seq_arr == s
    else:
        m = seq_arr >= 4
    seq_pfs[s] = get_pf(m)

# Density PFs
iso_pf = get_pf((orig_density == 0))
spr_pf = get_pf((orig_density == 1))
clu_pf = get_pf((orig_density >= 2))

# SBB PFs
norm_pf = get_pf(sbb_arr == "NORMAL")
sbb_pf = get_pf(sbb_arr == "SBB")

summary = (
    f"RAW BASELINE: Median PF @3t = {mc['pf_3t']:.4f} "
    f"(95% CI: {mc_ci[0]:.4f}–{mc_ci[1]:.4f}) across {n_cells} grid cells. "
    f"Best cell PF = {best_pf:.4f}. {pct_gt1:.1f}% of cells > 1.0. "
    f"Population R/P @60bars = {rp60_pop:.3f}. "
    f"SBB split: NORMAL={norm_pf:.4f}, SBB={sbb_pf:.4f}. "
    f"Per-period: P1a={pp['P1a']:.4f}, P1b={pp['P1b']:.4f}, "
    f"P2a={pp['P2a']:.4f}, P2b={pp['P2b']:.4f}. "
    f"Direction: Demand={dem_pf:.4f}, Supply={sup_pf:.4f}. "
    f"Session: RTH={rth_pf:.4f}, Overnight={ovn_pf:.4f}. "
    f"Cascade: HELD={held_pf:.4f}, BROKE={broke_pf:.4f}, NO_PRIOR={nopr_pf:.4f}. "
    f"TF: " + ", ".join(f"{tf}={tf_pfs[tf]:.4f}" for tf in tf_order) + ". "
    f"Seq: " + ", ".join(f"{s}={seq_pfs[s]:.4f}" for s in [1,2,3,4]) + " (4=4+). "
    f"Density: Isolated={iso_pf:.4f}, Sparse={spr_pf:.4f}, Clustered={clu_pf:.4f}. "
    f"Break contagion ratio={contagion_ratio:.2f}."
)

rprint(f"\n{summary}")

elapsed = time_mod.time() - t0
rprint(f"\n--- Total runtime: {elapsed:.1f}s ---")

# ============================================================
# SAVE REPORT
# ============================================================
report_text = "\n".join(report_lines)
with open(OUT / "baseline_report_clean.md", "w") as f:
    f.write(f"# NQ Zone Touch Baseline Report v3.2\n\n")
    f.write(f"Generated: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}\n\n")
    f.write("```\n")
    f.write(report_text)
    f.write("\n```\n")

rprint(f"\nSaved: baseline_report_clean.md")
rprint(f"Saved: zone_lifecycle.csv")
print("\nDONE: Prompt 0 complete.")
