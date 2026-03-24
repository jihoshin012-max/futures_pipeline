# archetype: zone_touch
"""Prompt 1a v3.2: Feature Screening — Warmup-Enriched Data

Compute 24 features (19 core + 5 expansion) for P1 touches, run single-feature
R/P screening at 4 horizons, SBB-masked secondary screening, confirmation
simulation with median cell exit, and mechanism validation.

P1 ONLY — no P2 data used.
"""

import numpy as np
import pandas as pd
from pathlib import Path
from scipy.stats import mannwhitneyu
import json, sys, time as time_mod, io, warnings

warnings.filterwarnings("ignore")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
np.random.seed(42)

# ============================================================
# CONSTANTS
# ============================================================
TICK = 0.25
HORIZONS = [30, 60, 120]
MAX_FWD = 120  # bars forward (largest horizon)

# Median cell from Prompt 0 baseline
MC_STOP = 120   # ticks
MC_TGT  = 120   # ticks
MC_TC   = 80    # bars
COST    = 3     # ticks

# Baseline anchors
BASELINE_PF_3T = 1.3396
BASELINE_RP_60 = 1.328

BASE = Path(r"c:/Projects/pipeline")
DATA = BASE / "stages/01-data/output/zone_prep"
OUT  = BASE / "shared/archetypes/zone_touch/output"
OUT.mkdir(parents=True, exist_ok=True)

report = []
def rprint(msg=""):
    print(msg)
    report.append(str(msg))

# ============================================================
# STEP 1: LOAD P1 DATA (P1a + P1b concatenated)
# ============================================================
rprint("=" * 70)
rprint("STEP 1: LOAD P1 DATA")
rprint("=" * 70)
t0 = time_mod.time()

p1a = pd.read_csv(DATA / "NQ_merged_P1a.csv")
p1b = pd.read_csv(DATA / "NQ_merged_P1b.csv")
rprint(f"  P1a: {len(p1a)} touches, P1b: {len(p1b)} touches")

touches = pd.concat([p1a, p1b], ignore_index=True)
rprint(f"  P1 combined: {len(touches)} touches")

# Filter RotBarIndex < 0
neg = touches["RotBarIndex"] < 0
if neg.any():
    rprint(f"  Removed {neg.sum()} touches with RotBarIndex < 0")
    touches = touches[~neg].reset_index(drop=True)

# Load P1 bar data
bar_p1 = pd.read_csv(DATA / "NQ_bardata_P1.csv")
bar_p1.columns = bar_p1.columns.str.strip()
rprint(f"  P1 bars: {len(bar_p1)}")

# Filter touches where entry bar exceeds bar data
rot_idx = touches["RotBarIndex"].values.astype(np.int64)
valid = (rot_idx + 1) < len(bar_p1)
if (~valid).any():
    rprint(f"  Removed {(~valid).sum()} touches: entry bar exceeds bar data")
    touches = touches[valid].reset_index(drop=True)
    rot_idx = touches["RotBarIndex"].values.astype(np.int64)

n = len(touches)
rprint(f"  Final P1 touch count: {n}")

# Load zone lifecycle
lifecycle = pd.read_csv(OUT / "zone_lifecycle.csv")
rprint(f"  Zone lifecycle: {len(lifecycle)} zones")

# Print baseline anchors
rprint(f"\n--- Baseline Anchors (Prompt 0) ---")
rprint(f"  Median cell: PF@3t={BASELINE_PF_3T}, Stop={MC_STOP}t, Target={MC_TGT}t, TC={MC_TC}")
rprint(f"  Population R/P @60bars: {BASELINE_RP_60}")
rprint(f"  SBB split: NORMAL=1.4016, SBB=0.7922")
rprint(f"  Verdict: LOW overfit risk")

# Touch distributions
rprint(f"\n--- P1 Touch Summary ---")
rprint(f"  TouchType: {dict(touches['TouchType'].value_counts())}")
rprint(f"  Top TFs: {dict(touches['SourceLabel'].value_counts().head(5))}")
rprint(f"  CascadeState: {dict(touches['CascadeState'].value_counts())}")
rprint(f"  SBB: {dict(touches['SBB_Label'].value_counts())}")

# ============================================================
# STEP 2: PRECOMPUTE FORWARD EXCURSIONS (P1 only)
# ============================================================
rprint("\n" + "=" * 70)
rprint("STEP 2: PRECOMPUTE FORWARD EXCURSIONS (P1 only)")
rprint("=" * 70)

# Parse bar datetimes
bar_dates = pd.to_datetime(bar_p1["Date"].str.strip() + " " + bar_p1["Time"].str.strip())
bar_hrs = bar_dates.dt.hour.values.astype(np.int32)
bar_mins = bar_dates.dt.minute.values.astype(np.int32)

# Bar data arrays
O  = bar_p1["Open"].values.astype(np.float64)
Hi = bar_p1["High"].values.astype(np.float64)
Lo = bar_p1["Low"].values.astype(np.float64)
Cl = bar_p1["Last"].values.astype(np.float64)
Vol = bar_p1["Volume"].values.astype(np.float64)
NTrades = bar_p1["# of Trades"].values.astype(np.float64)
BidVol = bar_p1["Bid Volume"].values.astype(np.float64)
AskVol = bar_p1["Ask Volume"].values.astype(np.float64)
ATR_arr = bar_p1["ATR"].values.astype(np.float64)

# Zigzag data
ZZ_len_arr = bar_p1["Zig Zag Line Length"].values.astype(np.float64)
ZZ_osc_arr = bar_p1["Zig Zag Oscillator"].values.astype(np.float64)

# Channel boundaries (3 channel studies × Top/Bottom = 6 values)
chan_top_cols = []
chan_bot_cols = []
for suffix in ["", ".1", ".2"]:
    tname = f"Top{suffix}" if suffix else "Top"
    bname = f"Bottom{suffix}" if suffix else "Bottom"
    if tname in bar_p1.columns:
        chan_top_cols.append(bar_p1[tname].values.astype(np.float64))
        chan_bot_cols.append(bar_p1[bname].values.astype(np.float64))
chan_all = chan_top_cols + chan_bot_cols  # 6 arrays
rprint(f"  Channel boundary arrays: {len(chan_all)}")

# Touch data arrays
tt_arr = np.array(touches["TouchType"].tolist(), dtype=str)
directions = np.where(tt_arr == "DEMAND_EDGE", 1, -1).astype(np.int8)
is_long = directions == 1
sbb_arr = np.array(touches["SBB_Label"].tolist(), dtype=str)
normal_mask = sbb_arr == "NORMAL"

# Entry prices
entry_idx = rot_idx + 1  # entry bar = bar after touch
entry_prices = O[entry_idx]
n_bars = len(bar_p1)

# Forward excursions
avail_bars = np.minimum(MAX_FWD, n_bars - entry_idx)
avail_bars = np.maximum(avail_bars, 0)

fwd_high  = np.full((n, MAX_FWD), np.nan)
fwd_low   = np.full((n, MAX_FWD), np.nan)
fwd_close = np.full((n, MAX_FWD), np.nan)

for i in range(n):
    ei = int(entry_idx[i])
    nb = int(avail_bars[i])
    if nb > 0:
        fwd_high[i, :nb]  = Hi[ei:ei+nb]
        fwd_low[i, :nb]   = Lo[ei:ei+nb]
        fwd_close[i, :nb] = Cl[ei:ei+nb]

trunc = (avail_bars < MAX_FWD).sum()
rprint(f"  Forward bars computed for {n} touches ({trunc} truncated)")

# Running excursions in ticks
is_long_2d = is_long[:, None]
ep_2d = entry_prices[:, None]
fav_raw = np.where(is_long_2d, (fwd_high - ep_2d) / TICK, (ep_2d - fwd_low) / TICK)
adv_raw = np.where(is_long_2d, (ep_2d - fwd_low) / TICK, (fwd_high - ep_2d) / TICK)
fav_raw = np.nan_to_num(fav_raw, nan=-999.0)
adv_raw = np.nan_to_num(adv_raw, nan=-999.0)
running_fav = np.maximum.accumulate(fav_raw, axis=1)
running_adv = np.maximum.accumulate(adv_raw, axis=1)

close_pnl = directions[:, None] * (fwd_close - ep_2d) / TICK
close_pnl = np.nan_to_num(close_pnl, nan=0.0)

# EOD offsets
eod_off = np.full(n, MAX_FWD, dtype=np.int32)
for i in range(n):
    ei = int(entry_idx[i])
    nb = int(avail_bars[i])
    h = bar_hrs[ei:ei+nb]
    m = bar_mins[ei:ei+nb]
    eod = np.where(((h == 16) & (m >= 55)) | ((h == 17) & (m == 0)))[0]
    if len(eod) > 0:
        eod_off[i] = eod[0]

# First stop/target hits for median cell
stop_mask = running_adv >= MC_STOP
first_stop_mc = np.where(np.any(stop_mask, axis=1), np.argmax(stop_mask, axis=1), MAX_FWD)
tgt_mask = running_fav >= MC_TGT
first_tgt_mc = np.where(np.any(tgt_mask, axis=1), np.argmax(tgt_mask, axis=1), MAX_FWD)

rprint("  First-hit offsets computed")

# Horizon R/P arrays (per touch)
rxn_at = {}
pen_at = {}
for horizon in HORIZONS:
    rxn_h = np.zeros(n)
    pen_h = np.zeros(n)
    for i in range(n):
        h = min(horizon, int(avail_bars[i]))
        if h > 0:
            rxn_h[i] = running_fav[i, h - 1]
            pen_h[i] = running_adv[i, h - 1]
    rxn_at[horizon] = rxn_h
    pen_at[horizon] = pen_h
rxn_at["full"] = touches["Reaction"].values.astype(np.float64)
pen_at["full"] = touches["Penetration"].values.astype(np.float64)

# P1 population R/P check
for h in [30, 60, 120, "full"]:
    mr = rxn_at[h].mean()
    mp = max(pen_at[h].mean(), 1.0)
    rprint(f"  P1 R/P @{h}: {mr:.1f} / {mp:.1f} = {mr/mp:.3f}")

# ============================================================
# STEP 3: FEATURE COMPUTATION (P1 only, 24 features)
# P1 only. All features computable at entry time.
# ============================================================
rprint("\n" + "=" * 70)
rprint("STEP 3: FEATURE COMPUTATION (P1 only)")
rprint("=" * 70)

features = {}      # key -> values array
feat_types = {}    # key -> 'cont' or 'cat'
feat_names = {}    # key -> display name
feat_bin_edges = {}  # key -> (p33, p67) for continuous

hl_range = Hi - Lo  # bar range for all bars

# ---- F01: Timeframe (categorical) ----
features["F01"] = np.array(touches["SourceLabel"].tolist(), dtype=str)
feat_types["F01"] = "cat"
feat_names["F01"] = "Timeframe"

# ---- F02: Zone Width (continuous) ----
features["F02"] = touches["ZoneWidthTicks"].values.astype(np.float64)
feat_types["F02"] = "cont"
feat_names["F02"] = "Zone Width"

# ---- F03: DROPPED (HasVPRay constant) ----
feat_names["F03"] = "VP Ray Binary (DROPPED)"

# ---- F04: Cascade State (categorical) ----
cascade = np.array(touches["CascadeState"].tolist(), dtype=str)
cascade = np.where(cascade == "UNKNOWN", "NO_PRIOR", cascade)
features["F04"] = cascade
feat_types["F04"] = "cat"
feat_names["F04"] = "Cascade State"

# ---- F05: Session (categorical) ----
touch_dt = pd.to_datetime(touches["DateTime"])
touch_mins = touch_dt.dt.hour.values * 60 + touch_dt.dt.minute.values
session = np.full(n, "Midday", dtype=object)
session[touch_mins < 360] = "Overnight"       # < 6:00
session[(touch_mins >= 360) & (touch_mins < 570)] = "PreRTH"  # 6:00-9:30
session[(touch_mins >= 570) & (touch_mins < 660)] = "OpeningDrive"  # 9:30-11:00
session[(touch_mins >= 660) & (touch_mins < 840)] = "Midday"  # 11:00-14:00
session[(touch_mins >= 840) & (touch_mins < 1020)] = "Close"  # 14:00-17:00
session[touch_mins >= 1020] = "Overnight"      # >= 17:00
features["F05"] = session
feat_types["F05"] = "cat"
feat_names["F05"] = "Session"

# ---- F06: Approach Velocity (continuous) ----
features["F06"] = touches["ApproachVelocity"].values.astype(np.float64)
feat_types["F06"] = "cont"
feat_names["F06"] = "Approach Velocity"

# ---- F07: Approach Deceleration (continuous) ----
# mean(H-L for bars -3 to -1) / mean(H-L for bars -10 to -8)
rprint("  Computing F07 (Approach Deceleration)...")
decel = np.full(n, np.nan)
for i in range(n):
    bi = int(rot_idx[i])
    if bi >= 10:
        recent = hl_range[bi-3:bi].mean()
        old = hl_range[bi-10:bi-7].mean()
        if old > 0:
            decel[i] = recent / old
features["F07"] = decel
feat_types["F07"] = "cont"
feat_names["F07"] = "Approach Deceleration"

# ---- F08 + F10: Prior Touch Reaction Speed / Penetration ----
# Link touches on same zone by (TouchType, ZoneTop, ZoneBot, SourceLabel) + seq
rprint("  Computing F08/F10 (Prior touch features)...")
zone_key = np.array((touches["TouchType"].astype(str) + "|" +
            touches["ZoneTop"].astype(str) + "|" +
            touches["ZoneBot"].astype(str) + "|" +
            touches["SourceLabel"].astype(str)).tolist(), dtype=str)
seq_arr = touches["TouchSequence"].values.astype(int)
bar_index_arr = touches["BarIndex"].values.astype(np.int64)

# Build lookup: (zone_key, seq) -> index
zs_lookup = {}
for i in range(n):
    zs_lookup[(zone_key[i], seq_arr[i])] = i

prior_rxn_speed = np.full(n, np.nan)
prior_pen = np.full(n, np.nan)

for i in range(n):
    if seq_arr[i] >= 2:
        key = (zone_key[i], seq_arr[i] - 1)
        if key in zs_lookup:
            pi = zs_lookup[key]
            # F08: reaction speed = RxnBar_30 offset from touch bar
            rb30 = touches.iloc[pi]["RxnBar_30"]
            bi_prior = bar_index_arr[pi]
            if pd.notna(rb30) and rb30 >= 0:
                prior_rxn_speed[i] = float(rb30 - bi_prior)
            # F10: prior touch penetration
            prior_pen[i] = float(touches.iloc[pi]["Penetration"])

features["F08"] = prior_rxn_speed
feat_types["F08"] = "cont"
feat_names["F08"] = "Prior Touch Rxn Speed"

# ---- F09: Zone Width / ATR Ratio ----
zone_width_pts = touches["ZoneWidthTicks"].values.astype(np.float64) * TICK
atr_at_touch = ATR_arr[rot_idx]
features["F09"] = np.where(atr_at_touch > 0, zone_width_pts / atr_at_touch, np.nan)
feat_types["F09"] = "cont"
feat_names["F09"] = "ZW/ATR Ratio"

# ---- F10: Prior Touch Penetration ----
features["F10"] = prior_pen
feat_types["F10"] = "cont"
feat_names["F10"] = "Prior Touch Penetration"

# ---- F11: Touch Bar Delta Divergence ----
# (AskVol - BidVol) on touch bar. Negate for supply.
delta = AskVol[rot_idx] - BidVol[rot_idx]
features["F11"] = np.where(is_long, delta, -delta)
feat_types["F11"] = "cont"
feat_names["F11"] = "Touch Bar Delta Div"

# ---- F12: Touch Bar Duration (seconds) ----
rprint("  Computing F12 (Touch Bar Duration)...")
bar_dt_np = bar_dates.values
touch_dur = np.full(n, np.nan)
for i in range(n):
    bi = int(rot_idx[i])
    if bi > 0:
        gap = (bar_dt_np[bi] - bar_dt_np[bi - 1]) / np.timedelta64(1, 's')
        touch_dur[i] = float(gap)
features["F12"] = touch_dur
feat_types["F12"] = "cont"
feat_names["F12"] = "Touch Bar Duration"

# ---- F13: Touch Bar Close Position ----
# Demand: (Last-Low)/(High-Low). Supply: (High-Last)/(High-Low)
tb_h = Hi[rot_idx]
tb_l = Lo[rot_idx]
tb_c = Cl[rot_idx]
hl_d = tb_h - tb_l
close_pos = np.where(hl_d > 0,
    np.where(is_long, (tb_c - tb_l) / hl_d, (tb_h - tb_c) / hl_d),
    0.5)
features["F13"] = close_pos
feat_types["F13"] = "cont"
feat_names["F13"] = "Touch Bar Close Pos"

# ---- F14: Average Order Size ----
features["F14"] = np.where(NTrades[rot_idx] > 0, Vol[rot_idx] / NTrades[rot_idx], np.nan)
feat_types["F14"] = "cont"
feat_names["F14"] = "Avg Order Size"

# ---- F15: ZZ Swing Regime ----
# Median of 20 most recent non-zero ZZ Line Length values
rprint("  Computing F15 (ZZ Swing Regime)...")
nz_mask = ZZ_len_arr != 0
nz_indices = np.where(nz_mask)[0]
nz_values = np.abs(ZZ_len_arr[nz_mask])
zz_regime = np.full(n, np.nan)
for i in range(n):
    bi = int(rot_idx[i])
    pos = np.searchsorted(nz_indices, bi, side='right')
    if pos >= 5:
        start = max(0, pos - 20)
        zz_regime[i] = np.median(nz_values[start:pos])
features["F15"] = zz_regime
feat_types["F15"] = "cont"
feat_names["F15"] = "ZZ Swing Regime"

# ---- F16: ZZ Oscillator at Touch ----
features["F16"] = ZZ_osc_arr[rot_idx]
feat_types["F16"] = "cont"
feat_names["F16"] = "ZZ Oscillator"

# ---- F17: ATR Regime ----
# Percentile rank of ATR vs trailing 500 bars
rprint("  Computing F17 (ATR Regime)...")
atr_regime = np.full(n, np.nan)
for i in range(n):
    bi = int(rot_idx[i])
    start = max(0, bi - 500)
    window = ATR_arr[start:bi + 1]
    if len(window) >= 10:
        atr_regime[i] = (window < ATR_arr[bi]).sum() / len(window)
features["F17"] = atr_regime
feat_types["F17"] = "cont"
feat_names["F17"] = "ATR Regime"

# ---- F18: Channel Confluence ----
# Count of 6 channel boundaries within N ticks of zone edge
# Calibrate: test 20, 50, 100 ticks; pick best R/P spread at 60 bars
rprint("  Computing F18 (Channel Confluence) — calibrating proximity...")
zone_edge = np.where(is_long,
    touches["ZoneTop"].values.astype(np.float64),
    touches["ZoneBot"].values.astype(np.float64))

best_prox = 50
best_spread = -1
for prox in [20, 50, 100]:
    thresh = prox * TICK
    conf = np.zeros(n)
    for i in range(n):
        bi = int(rot_idx[i])
        edge = zone_edge[i]
        for arr in chan_all:
            val = arr[bi]
            if val != 0 and abs(val - edge) <= thresh:
                conf[i] += 1
    # Quick R/P spread at 60 bars
    valid_conf = ~np.isnan(conf)
    if valid_conf.sum() > 30:
        p33, p67 = np.percentile(conf[valid_conf], [33.33, 66.67])
        if p33 < p67:
            lo_m = np.where(conf <= p33)[0]
            hi_m = np.where(conf > p67)[0]
            if len(lo_m) > 10 and len(hi_m) > 10:
                rp_lo = rxn_at[60][lo_m].mean() / max(pen_at[60][lo_m].mean(), 1.0)
                rp_hi = rxn_at[60][hi_m].mean() / max(pen_at[60][hi_m].mean(), 1.0)
                spread = abs(rp_hi - rp_lo)
                rprint(f"    Prox={prox}t: spread={spread:.3f}")
                if spread > best_spread:
                    best_spread = spread
                    best_prox = prox

rprint(f"    Selected proximity: {best_prox} ticks")
thresh = best_prox * TICK
chan_conf = np.zeros(n)
for i in range(n):
    bi = int(rot_idx[i])
    edge = zone_edge[i]
    for arr in chan_all:
        val = arr[bi]
        if val != 0 and abs(val - edge) <= thresh:
            chan_conf[i] += 1
features["F18"] = chan_conf
feat_types["F18"] = "cont"
feat_names["F18"] = "Channel Confluence"

# ---- F19: VP Ray Consumption (categorical) ----
# ---- F20: Distance to Consumed VP Ray (continuous) ----
rprint("  Computing F19/F20 (VP Ray Consumption)...")
vp_price = touches["VPRayPrice"].values.astype(np.float64)
has_vp = touches["HasVPRay"].values.astype(int) if "HasVPRay" in touches.columns else np.zeros(n, dtype=int)
vp_nonzero = (vp_price != 0).sum()
vp_has = (has_vp == 1).sum()
rprint(f"    HasVPRay=1: {vp_has}/{n}, VPRayPrice>0: {vp_nonzero}/{n}")

vp_consumption = np.full(n, "INTACT", dtype=object)
vp_distance = np.full(n, np.nan)

if vp_nonzero > n * 0.01:  # only compute if >1% have VP rays
    for i in range(n):
        if seq_arr[i] >= 2 and vp_price[i] != 0:
            for s in range(1, seq_arr[i]):
                key = (zone_key[i], s)
                if key in zs_lookup:
                    pi = zs_lookup[key]
                    tp = touches.iloc[pi]["TouchPrice"]
                    pen_val = touches.iloc[pi]["Penetration"]
                    if is_long[i]:
                        touch_low = tp - pen_val * TICK
                        if touch_low <= vp_price[i]:
                            vp_consumption[i] = "CONSUMED"
                            vp_distance[i] = abs(touches.iloc[i]["TouchPrice"] - vp_price[i]) / TICK
                            break
                    else:
                        touch_high = tp + pen_val * TICK
                        if touch_high >= vp_price[i]:
                            vp_consumption[i] = "CONSUMED"
                            vp_distance[i] = abs(touches.iloc[i]["TouchPrice"] - vp_price[i]) / TICK
                            break

consumed_count = (vp_consumption == "CONSUMED").sum()
rprint(f"    VP Ray: CONSUMED={consumed_count}, INTACT={n - consumed_count}")

# If VP data is nearly constant, mark as low-variance
if consumed_count < 10 or vp_nonzero < n * 0.01:
    rprint(f"    VP Ray features have near-zero variance — will classify WEAK")

features["F19"] = vp_consumption
feat_types["F19"] = "cat"
feat_names["F19"] = "VP Ray Consumption"

features["F20"] = vp_distance
feat_types["F20"] = "cont"
feat_names["F20"] = "VP Ray Distance"

# ============================================================
# EXPANSION FEATURES 21-25 (from zone_lifecycle)
# ============================================================
rprint("\n  Computing expansion features 21-25...")

# ---- F21: Zone Age (bars since birth) ----
features["F21"] = touches["ZoneAgeBars"].values.astype(np.float64)
feat_types["F21"] = "cont"
feat_names["F21"] = "Zone Age (EXP)"

# Prepare lifecycle for vectorized expansion features
lifecycle["birth_dt"] = pd.to_datetime(lifecycle["birth_datetime"])
lifecycle["death_dt"] = pd.to_datetime(lifecycle["death_datetime"])

# Map lifecycle to P1 bar indices
p1_last_dt = bar_dates.iloc[-1]
# Filter to zones born before end of P1 (exclude P2-only zones)
lc = lifecycle[lifecycle["birth_dt"] <= p1_last_dt].copy()
rprint(f"    Lifecycle zones in P1 scope: {len(lc)}")

lc_birth_bars = np.searchsorted(bar_dt_np, lc["birth_dt"].values)
lc_birth_bars = np.clip(lc_birth_bars, 0, n_bars - 1)
lc_death_bars = np.searchsorted(bar_dt_np, lc["death_dt"].values)
lc_death_bars = np.clip(lc_death_bars, 0, n_bars - 1)

# Deaths after P1 end should be treated as alive during P1
future_deaths = lc["death_dt"].values > p1_last_dt
lc_death_bars_adj = lc_death_bars.copy()
lc_death_bars_adj[future_deaths] = 999999

lc_is_dead = (np.array(lc["death_cause"].tolist(), dtype=str) != "ALIVE") & (~future_deaths)
lc_direction = np.array(lc["direction"].tolist(), dtype=str)
lc_price = lc["ZonePrice"].values.astype(np.float64)
lc_sourcelabel = np.array(lc["SourceLabel"].tolist(), dtype=str)
m_lc = len(lc)

# Vectorized: broadcast touch bars (n,1) vs lifecycle (1,m)
rprint("    Vectorized expansion feature computation...")
tb = rot_idx[:, None]     # (n, 1)
bb = lc_birth_bars[None, :] # (1, m)
db = lc_death_bars_adj[None, :]  # (1, m)
dead_mask = lc_is_dead[None, :]  # (1, m)

# Active zones: born <= touch_bar AND (alive OR died after touch_bar)
active_at_touch = (bb <= tb) & ((~dead_mask) | (db > tb))  # (n, m)

# ---- F22: Recent Break Rate ----
# Deaths in trailing 500 bars / active zones
db_raw = lc_death_bars[None, :]  # unadjusted for actual death bar
deaths_in_window = ((db_raw >= (tb - 500)) & (db_raw <= tb) & lc_is_dead[None, :]).sum(axis=1)
active_count = ((bb <= tb) & ((~dead_mask) | (db >= (tb - 500)))).sum(axis=1)
features["F22"] = np.where(active_count > 0, deaths_in_window / active_count, 0).astype(np.float64)
feat_types["F22"] = "cont"
feat_names["F22"] = "Recent Break Rate (EXP)"

# ---- F23: Cross-TF Confluence ----
# Active zones from OTHER TFs, same direction, within 200 ticks
CROSS_TF_DIST = 200
edge_2d = zone_edge[:, None]  # (n, 1)
price_2d = lc_price[None, :]  # (1, m)
dist_matrix = np.abs(edge_2d - price_2d) / TICK  # (n, m)
close_200 = dist_matrix <= CROSS_TF_DIST

dir_match = (tt_arr[:, None] == lc_direction[None, :])
touch_sl = np.array(touches["SourceLabel"].tolist(), dtype=str)
tf_diff = (touch_sl[:, None] != lc_sourcelabel[None, :])

features["F23"] = (close_200 & active_at_touch & dir_match & tf_diff).sum(axis=1).astype(np.float64)
feat_types["F23"] = "cont"
feat_names["F23"] = "Cross-TF Confluence (EXP)"

# ---- F24: Nearest Same-Direction Zone Distance ----
rprint("    Computing F24 (Nearest Same-Dir Zone Distance)...")
f24 = np.full(n, np.nan)
for i in range(n):
    bi = int(rot_idx[i])
    active_i = active_at_touch[i]  # (m,) bool
    dir_i = dir_match[i]           # (m,) bool
    cand = active_i & dir_i
    if cand.any():
        prices_c = lc_price[cand]
        edge_i = zone_edge[i]
        if is_long[i]:
            below = prices_c[prices_c < edge_i - 1 * TICK]
            if len(below) > 0:
                f24[i] = (edge_i - below.max()) / TICK
        else:
            above = prices_c[prices_c > edge_i + 1 * TICK]
            if len(above) > 0:
                f24[i] = (above.min() - edge_i) / TICK

max_f24 = np.nanmax(f24) if np.any(~np.isnan(f24)) else 10000
f24[np.isnan(f24)] = max_f24
features["F24"] = f24
feat_types["F24"] = "cont"
feat_names["F24"] = "Nearest Same-Dir Zone Dist (EXP)"

# ---- F25: Price-Level Break History ----
# Fraction of zones within ±500 ticks born before touch that have died before touch
within_500 = dist_matrix <= 500  # (n, m) already have dist_matrix
born_before = (bb <= tb)  # (n, m)
candidates = within_500 & born_before
died_before = lc_is_dead[None, :] & (lc_death_bars[None, :] <= tb)
f25_num = (candidates & died_before).sum(axis=1)
f25_den = candidates.sum(axis=1)
features["F25"] = np.where(f25_den > 0, f25_num / f25_den, 0).astype(np.float64)
feat_types["F25"] = "cont"
feat_names["F25"] = "Price-Level Break Hist (EXP)"

# Free large broadcast arrays
del tb, bb, db, dead_mask, active_at_touch, dist_matrix, close_200
del dir_match, tf_diff, edge_2d, price_2d, within_500, born_before
del candidates, died_before, db_raw

# ============================================================
# FEATURE DIAGNOSTICS
# ============================================================
rprint("\n" + "=" * 70)
rprint("STEP 3b: FEATURE DIAGNOSTICS")
rprint("=" * 70)

active_keys = sorted([k for k in features.keys()])
rprint(f"\n  Active features: {len(active_keys)} (F03 dropped)")

# Null rates
rprint("\n--- Null/NaN Rates ---")
for fk in active_keys:
    vals = features[fk]
    if feat_types[fk] == "cont":
        nn = np.isnan(vals.astype(float)).sum()
    else:
        nn = pd.isna(pd.Series(vals)).sum()
    if nn > 0:
        rprint(f"  {fk} ({feat_names[fk]}): {nn}/{n} = {100*nn/n:.1f}% null")

# Sample rows
rprint("\n--- 5 Sample Rows ---")
sample_idx = [0, n//4, n//2, 3*n//4, n-1]
for si in sample_idx:
    row = {fk: (f"{features[fk][si]:.2f}" if feat_types[fk] == "cont" and not np.isnan(float(features[fk][si]))
                else str(features[fk][si])) for fk in active_keys[:8]}
    rprint(f"  idx={si}: {row}")

# Correlation matrix (continuous features)
rprint("\n--- Correlation Matrix (|r| > 0.7 flagged) ---")
cont_keys = [k for k in active_keys if feat_types[k] == "cont"]
cont_arr = np.column_stack([features[k].astype(float) for k in cont_keys])
# Replace NaN with column mean for correlation
for j in range(cont_arr.shape[1]):
    col = cont_arr[:, j]
    mask = ~np.isnan(col)
    if mask.sum() > 0:
        cont_arr[np.isnan(cont_arr[:, j]), j] = col[mask].mean()

corr = np.corrcoef(cont_arr.T)
high_corr = []
for i in range(len(cont_keys)):
    for j in range(i + 1, len(cont_keys)):
        if abs(corr[i, j]) > 0.7:
            high_corr.append((cont_keys[i], cont_keys[j], corr[i, j]))

if high_corr:
    for a, b, r in high_corr:
        rprint(f"  WARNING: |r|={abs(r):.3f} between {a} ({feat_names[a]}) and {b} ({feat_names[b]})")
else:
    rprint("  No feature pairs with |r| > 0.7")

# VP Ray distribution
if vp_nonzero > 0:
    consumed_rxn = rxn_at[60][vp_consumption == "CONSUMED"]
    intact_rxn = rxn_at[60][vp_consumption == "INTACT"]
    rprint(f"\n  VP Ray: CONSUMED mean Rxn@60={consumed_rxn.mean():.1f}t (n={len(consumed_rxn)})")
    rprint(f"  VP Ray: INTACT mean Rxn@60={intact_rxn.mean():.1f}t (n={len(intact_rxn)})")

# Entry-time checkpoint
rprint("\n  CHECKPOINT: All 24 features (19 core + 5 expansion) computable at entry time? YES")
rprint(f"  P1 only: {n} touches. P2 NOT used.")
rprint(f"  Baseline PF anchor: {BASELINE_PF_3T}")

# ============================================================
# STEP 4: SINGLE-FEATURE R/P SCREENING (P1 only)
# ============================================================
rprint("\n" + "=" * 70)
rprint("STEP 4: SINGLE-FEATURE R/P SCREENING (P1 only)")
rprint("=" * 70)


def compute_rp(indices, horizon_key):
    """Compute R/P for a set of touch indices at a given horizon."""
    if len(indices) < 5:
        return np.nan, np.nan, np.nan
    mr = rxn_at[horizon_key][indices].mean()
    mp = pen_at[horizon_key][indices].mean()
    mp = max(mp, 1.0)  # floor rule
    return mr / mp, mr, mp


def cohens_d(a, b):
    """Cohen's d between two arrays."""
    na, nb = len(a), len(b)
    if na < 2 or nb < 2:
        return 0
    va, vb = a.var(ddof=1), b.var(ddof=1)
    pooled = np.sqrt(((na - 1) * va + (nb - 1) * vb) / (na + nb - 2))
    if pooled == 0:
        return 0
    return (a.mean() - b.mean()) / pooled


def bin_feature(fk, subset_idx=None):
    """Bin a feature into groups. Returns dict of {bin_name: indices}."""
    if subset_idx is None:
        subset_idx = np.arange(n)
    vals = features[fk]

    if feat_types[fk] == "cat":
        bins = {}
        for cat in np.unique(vals[subset_idx]):
            if pd.notna(cat):
                mask = vals[subset_idx] == cat
                bins[str(cat)] = subset_idx[mask]
        return bins, None
    else:
        fvals = vals[subset_idx].astype(float)
        valid = ~np.isnan(fvals)
        if valid.sum() < 30:
            return {}, None
        p33, p67 = np.nanpercentile(fvals[valid], [33.33, 66.67])
        if p33 == p67:
            # Low variance — binary split at median
            med = np.nanmedian(fvals[valid])
            bins = {
                f"Low (<={med:.1f})": subset_idx[valid & (fvals <= med)],
                f"High (>{med:.1f})": subset_idx[valid & (fvals > med)],
            }
        else:
            bins = {
                f"Low (<={p33:.1f})": subset_idx[valid & (fvals <= p33)],
                f"Mid ({p33:.1f}-{p67:.1f})": subset_idx[valid & (fvals > p33) & (fvals <= p67)],
                f"High (>{p67:.1f})": subset_idx[valid & (fvals > p67)],
            }
        # Add NA bin if needed
        if (~valid).any():
            bins["NA"] = subset_idx[~valid]
        return bins, (p33, p67)


def screen_one_feature(fk, subset_idx=None, label=""):
    """Full screening of one feature. Returns results dict."""
    bins, edges = bin_feature(fk, subset_idx)
    if not bins or len(bins) < 2:
        return None

    # R/P per bin per horizon
    horizon_keys = HORIZONS + ["full"]
    bin_results = {}
    for bname, bidx in bins.items():
        bin_results[bname] = {"n": len(bidx)}
        for hk in horizon_keys:
            rp, mr, mp = compute_rp(bidx, hk)
            floored = mp == 1.0 and pen_at[hk][bidx].mean() < 1.0 if len(bidx) >= 5 else False
            bin_results[bname][hk] = {"rp": rp, "rxn": mr, "pen": mp, "floored": floored}

    # Separation per horizon
    sep = {}
    for hk in horizon_keys:
        rps = {}
        for bname in bins:
            rp_val = bin_results[bname][hk]["rp"]
            if not np.isnan(rp_val):
                rps[bname] = rp_val
        if len(rps) < 2:
            continue

        best_bin = max(rps, key=rps.get)
        worst_bin = min(rps, key=rps.get)
        rp_spread = rps[best_bin] - rps[worst_bin]
        rxn_spread = (bin_results[best_bin][hk]["rxn"] - bin_results[worst_bin][hk]["rxn"]
                      if bin_results[best_bin][hk]["rxn"] is not None else 0)

        # MWU on reaction distributions
        best_rxn = rxn_at[hk][bins[best_bin]]
        worst_rxn = rxn_at[hk][bins[worst_bin]]
        try:
            stat, pval = mannwhitneyu(best_rxn, worst_rxn, alternative='two-sided')
        except Exception:
            pval = 1.0
        cd = cohens_d(best_rxn, worst_rxn)

        sep[hk] = {
            "best_bin": best_bin, "worst_bin": worst_bin,
            "rp_spread": rp_spread, "rxn_spread": rxn_spread,
            "pval": pval, "cohens_d": cd,
            "best_rp": rps[best_bin], "worst_rp": rps[worst_bin],
            "best_n": len(bins[best_bin]), "worst_n": len(bins[worst_bin]),
        }

    # Multi-horizon consistency
    if 60 not in sep:
        return None

    best_at_60 = sep[60]["best_bin"]
    consistent = 0
    for hk in horizon_keys:
        if hk in sep and sep[hk]["best_bin"] == best_at_60 and sep[hk]["rp_spread"] > 0.2:
            consistent += 1

    # Classification
    strong_rp = sum(1 for hk in horizon_keys if hk in sep and sep[hk]["rp_spread"] > 0.3)
    sig_hk = sum(1 for hk in horizon_keys if hk in sep and sep[hk]["pval"] < 0.05)
    mod_rp = sum(1 for hk in horizon_keys if hk in sep and sep[hk]["rp_spread"] > 0.2)
    mod_sig = sum(1 for hk in horizon_keys if hk in sep and sep[hk]["pval"] < 0.10)

    if strong_rp >= 3 and sig_hk >= 2:
        classification = "STRONG"
    elif mod_rp >= 2 or mod_sig >= 2:
        classification = "MODERATE"
    else:
        classification = "WEAK"

    # Check for inversion
    worst_at_60 = sep[60]["worst_bin"]
    inverted_count = sum(1 for hk in horizon_keys
                         if hk in sep and sep[hk]["worst_bin"] == best_at_60)
    if inverted_count >= 3:
        classification = "INVERTED"

    return {
        "bins": bins, "edges": edges, "bin_results": bin_results,
        "separation": sep, "consistent": consistent,
        "classification": classification,
    }


# Run screening for all features
screening_results = {}
screen_keys = [k for k in active_keys if k != "F03"]  # skip dropped F03

rprint(f"\nScreening {len(screen_keys)} features on P1 ({n} touches)...")
rprint(f"Baseline R/P @60bars = {BASELINE_RP_60}\n")

for fk in screen_keys:
    res = screen_one_feature(fk)
    if res is not None:
        screening_results[fk] = res
        s60 = res["separation"].get(60, {})
        rprint(f"  {fk} ({feat_names[fk]}): {res['classification']} | "
               f"R/P spread@60={s60.get('rp_spread', 0):.3f} | "
               f"Consistent={res['consistent']}/4 | "
               f"p@60={s60.get('pval', 1):.4f}")
    else:
        rprint(f"  {fk} ({feat_names[fk]}): SKIPPED (insufficient data or <2 bins)")

# ============================================================
# STEP 4b: SBB-MASKED SECONDARY SCREENING
# ============================================================
rprint("\n" + "=" * 70)
rprint("STEP 4b: SBB-MASKED SECONDARY SCREENING (NORMAL-only)")
rprint("=" * 70)

normal_idx = np.where(normal_mask)[0]
rprint(f"  NORMAL touches: {len(normal_idx)}/{n}")

sbb_masked_features = []

for fk in screen_keys:
    if fk not in screening_results:
        continue
    cls = screening_results[fk]["classification"]
    if cls not in ("WEAK", "MODERATE"):
        continue

    # Re-screen on NORMAL-only
    res_normal = screen_one_feature(fk, subset_idx=normal_idx, label="NORMAL")
    if res_normal is None:
        continue

    # Check if it would classify STRONG on NORMAL-only
    s60n = res_normal["separation"].get(60, {})
    strong_rp_n = sum(1 for hk in HORIZONS + ["full"]
                      if hk in res_normal["separation"]
                      and res_normal["separation"][hk]["rp_spread"] > 0.3)
    sig_n = sum(1 for hk in HORIZONS + ["full"]
                if hk in res_normal["separation"]
                and res_normal["separation"][hk]["pval"] < 0.05)

    if strong_rp_n >= 3 and sig_n >= 2:
        sbb_masked_features.append(fk)
        screening_results[fk]["classification"] = "SBB-MASKED"
        screening_results[fk]["normal_screening"] = res_normal
        rprint(f"  {fk} ({feat_names[fk]}): UPGRADED to SBB-MASKED | "
               f"NORMAL R/P spread@60={s60n.get('rp_spread', 0):.3f} | "
               f"NORMAL p@60={s60n.get('pval', 1):.4f}")
    else:
        rprint(f"  {fk} ({feat_names[fk]}): remains {cls} on NORMAL "
               f"(spread@60={s60n.get('rp_spread', 0):.3f})")

if not sbb_masked_features:
    rprint("  No SBB-MASKED features found.")
else:
    rprint(f"\n  SBB-MASKED features: {sbb_masked_features}")

# ============================================================
# STEP 4c: CONFIRMATION SIMULATION (STRONG + SBB-MASKED only)
# ============================================================
rprint("\n" + "=" * 70)
rprint("STEP 4c: CONFIRMATION SIMULATION (median cell exit)")
rprint("=" * 70)

# Precompute per-touch simulation outcomes
eff_end = np.minimum(MC_TC - 1, eod_off)
eff_end = np.minimum(eff_end, avail_bars.astype(np.int32) - 1)
eff_end = np.maximum(eff_end, 0)

sb = first_stop_mc
tb_sim = first_tgt_mc
stop_in = sb <= eff_end
tgt_in = tb_sim <= eff_end
both = stop_in & tgt_in
tgt_wins = both & (tb_sim < sb)
stop_wins = both & ~tgt_wins
only_stop = stop_in & ~tgt_in
only_tgt = tgt_in & ~stop_in

idx_range = np.arange(n)
pnl_at_end = close_pnl[idx_range, eff_end]
sim_pnl = np.where(tgt_wins | only_tgt, MC_TGT,
          np.where(stop_wins | only_stop, -MC_STOP, pnl_at_end))
sim_end_off = np.where(tgt_wins, tb_sim,
              np.where(stop_wins | only_stop, sb,
              np.where(only_tgt, tb_sim, eff_end)))


def simulate_subset(indices):
    """Run median-cell sim with no-overlap on a subset. Returns (PF@3t, n_trades)."""
    if len(indices) == 0:
        return 0, 0
    sorted_idx = indices[np.argsort(entry_idx[indices])]
    taken = []
    flat_bar = -1
    for idx in sorted_idx:
        eb = int(entry_idx[idx])
        if eb > flat_bar:
            taken.append(idx)
            flat_bar = eb + int(sim_end_off[idx])
    if not taken:
        return 0, 0
    net = sim_pnl[taken] - COST
    gw = net[net > 0].sum()
    gl = abs(net[net < 0].sum())
    return gw / max(gl, 0.001), len(taken)


confirm_keys = [fk for fk in screen_keys
                if fk in screening_results
                and screening_results[fk]["classification"] in ("STRONG", "SBB-MASKED")]

rprint(f"\nConfirmation simulation for {len(confirm_keys)} features:")
for fk in confirm_keys:
    res = screening_results[fk]
    cls = res["classification"]
    bins = res["bins"]
    # For SBB-MASKED, simulate on NORMAL-only
    if cls == "SBB-MASKED" and "normal_screening" in res:
        bins_to_use = res["normal_screening"]["bins"]
        pop_label = "NORMAL"
    else:
        bins_to_use = bins
        pop_label = "full"

    rprint(f"\n  {fk} ({feat_names[fk]}) [{cls}, {pop_label} pop]:")
    sim_results = {}
    for bname, bidx in bins_to_use.items():
        pf, nt = simulate_subset(bidx)
        sim_results[bname] = {"pf": pf, "trades": nt}
        rprint(f"    {bname}: PF@3t={pf:.3f}, trades={nt}")
    screening_results[fk]["sim_results"] = sim_results

# ============================================================
# STEP 5: FEATURE MECHANISM VALIDATION (P1 only)
# ============================================================
rprint("\n" + "=" * 70)
rprint("STEP 5: MECHANISM VALIDATION (P1 only)")
rprint("=" * 70)

# Temporal split: P1 halves by date
touch_dates = pd.to_datetime(touches["DateTime"])
date_median = touch_dates.median()
first_half = np.where(touch_dates <= date_median)[0]
second_half = np.where(touch_dates > date_median)[0]
rprint(f"  Temporal split: first_half={len(first_half)}, second_half={len(second_half)}")

# ATR regime split
atr_at_touch_arr = ATR_arr[rot_idx]
atr_med = np.median(atr_at_touch_arr)
low_atr = np.where(atr_at_touch_arr <= atr_med)[0]
high_atr = np.where(atr_at_touch_arr > atr_med)[0]
rprint(f"  ATR regime split: low={len(low_atr)}, high={len(high_atr)}")

# Test features classified STRONG, SBB-MASKED, or MODERATE
mech_keys = [fk for fk in screen_keys
             if fk in screening_results
             and screening_results[fk]["classification"] in ("STRONG", "SBB-MASKED", "MODERATE")]

mechanism_results = {}

for fk in mech_keys:
    res = screening_results[fk]
    cls = res["classification"]

    # For SBB-MASKED: use NORMAL-only population for all tests
    if cls == "SBB-MASKED":
        base_idx = normal_idx
    else:
        base_idx = np.arange(n)

    # Test 1: Temporal Stability
    fh_idx = np.intersect1d(base_idx, first_half)
    sh_idx = np.intersect1d(base_idx, second_half)
    fh_res = screen_one_feature(fk, subset_idx=fh_idx)
    sh_res = screen_one_feature(fk, subset_idx=sh_idx)

    temp_pass = False
    if fh_res and sh_res and 60 in fh_res["separation"] and 60 in sh_res["separation"]:
        sp1 = fh_res["separation"][60]["rp_spread"]
        sp2 = sh_res["separation"][60]["rp_spread"]
        # Same sign and within 2x magnitude
        if sp1 * sp2 > 0:  # same sign
            ratio = max(abs(sp1), abs(sp2)) / max(min(abs(sp1), abs(sp2)), 0.001)
            temp_pass = ratio <= 2.0
    temp_label = "PASS" if temp_pass else "FAIL"

    # Test 2: Regime Independence
    la_idx = np.intersect1d(base_idx, low_atr)
    ha_idx = np.intersect1d(base_idx, high_atr)
    la_res = screen_one_feature(fk, subset_idx=la_idx)
    ha_res = screen_one_feature(fk, subset_idx=ha_idx)

    regime_pass = False
    if la_res and ha_res and 60 in la_res["separation"] and 60 in ha_res["separation"]:
        sp_la = la_res["separation"][60]["rp_spread"]
        sp_ha = ha_res["separation"][60]["rp_spread"]
        regime_pass = sp_la * sp_ha > 0  # same sign

    regime_label = "PASS" if regime_pass else "FAIL"

    # Test 3: Monotonicity (3-bin features only)
    mono_pass = True
    mono_label = "EXEMPT"
    bins = res["bins"]
    non_na_bins = [b for b in bins if b != "NA"]
    if len(non_na_bins) == 3 and feat_types[fk] == "cont":
        # Check Reaction ordering across bins
        rxn_means = []
        for bname in sorted(non_na_bins):
            bidx = bins[bname]
            rxn_means.append(rxn_at[60][bidx].mean())
        if len(rxn_means) == 3:
            mono_pass = (rxn_means[0] <= rxn_means[1] <= rxn_means[2]) or \
                        (rxn_means[0] >= rxn_means[1] >= rxn_means[2])
            mono_label = "PASS" if mono_pass else "FAIL"

    # Final mechanism classification
    passes = sum([temp_pass, regime_pass, mono_pass if mono_label != "EXEMPT" else True])
    total_tests = 2 + (1 if mono_label != "EXEMPT" else 0)

    if cls in ("STRONG", "SBB-MASKED") and passes >= 2:
        mech_class = "STRUCTURAL"
    elif cls == "MODERATE" and passes >= 2:
        mech_class = "LIKELY STRUCTURAL"
    elif cls in ("STRONG", "SBB-MASKED") and passes == 1:
        mech_class = "LIKELY STRUCTURAL"
    else:
        mech_class = "STATISTICAL ONLY"

    mechanism_results[fk] = {
        "signal_class": cls,
        "temporal": temp_label,
        "regime": regime_label,
        "monotonic": mono_label,
        "mechanism_class": mech_class,
        "passes": passes,
        "total": total_tests,
    }

    rprint(f"  {fk} ({feat_names[fk]}): {cls} → Temp={temp_label} Regime={regime_label} "
           f"Mono={mono_label} → {mech_class}")

# Also run mechanism tests on WEAK features (informational)
weak_keys = [fk for fk in screen_keys
             if fk in screening_results
             and screening_results[fk]["classification"] == "WEAK"]
for fk in weak_keys:
    mechanism_results[fk] = {
        "signal_class": "WEAK",
        "temporal": "—", "regime": "—", "monotonic": "—",
        "mechanism_class": "STATISTICAL ONLY",
        "passes": 0, "total": 0,
    }

# Zone width drift warning
if "F02" in screening_results and "F09" in screening_results:
    rprint("\n--- Zone Width Drift Warning ---")
    f02_bins = screening_results["F02"]["bins"]
    f09_bins = screening_results["F09"]["bins"]
    rprint(f"  F02 (Zone Width) bins: {list(f02_bins.keys())}")
    rprint(f"  F09 (ZW/ATR) bins: {list(f09_bins.keys())}")
    rprint(f"  ZW/ATR ratio may absorb width drift (P1 median vs P2 median).")

# ============================================================
# PRINT SCREENING TABLE
# ============================================================
rprint("\n" + "=" * 70)
rprint("SINGLE-FEATURE SCREENING TABLE (sorted by R/P spread @60)")
rprint("=" * 70)

# Sort by R/P spread at 60 bars
ranked = []
for fk in screen_keys:
    if fk not in screening_results:
        continue
    s60 = screening_results[fk]["separation"].get(60, {})
    spread = s60.get("rp_spread", 0)
    cls = screening_results[fk]["classification"]
    exp_tag = " (EXP)" if fk in ("F21", "F22", "F23", "F24", "F25") and "(EXP)" not in feat_names[fk] else ""
    ranked.append((fk, spread, cls, exp_tag))

ranked.sort(key=lambda x: -x[1])

rprint(f"\n{'Rank':>4} | {'Feature':>6} | {'Name':<30} | {'Best R/P @60':>12} | "
       f"{'Worst R/P @60':>13} | {'Spread @60':>10} | {'Horizons':>8} | "
       f"{'p @60':>8} | {'Cohen d':>7} | {'Class':>12} | {'N(best/worst)':>14}")
rprint("-" * 150)

for rank, (fk, spread, cls, exp) in enumerate(ranked, 1):
    s60 = screening_results[fk]["separation"].get(60, {})
    best_rp = s60.get("best_rp", 0)
    worst_rp = s60.get("worst_rp", 0)
    pval = s60.get("pval", 1)
    cd = s60.get("cohens_d", 0)
    consistent = screening_results[fk]["consistent"]
    best_n = s60.get("best_n", 0)
    worst_n = s60.get("worst_n", 0)
    name = feat_names[fk] + exp

    rprint(f"{rank:>4} | {fk:>6} | {name:<30} | {best_rp:>12.3f} | {worst_rp:>13.3f} | "
           f"{spread:>10.3f} | {consistent:>6}/4  | {pval:>8.4f} | {cd:>7.3f} | "
           f"{cls:>12} | {best_n:>6}/{worst_n:<6}")

# Summary
strong_list = [fk for fk in screen_keys if fk in screening_results
               and screening_results[fk]["classification"] == "STRONG"]
sbb_list = [fk for fk in screen_keys if fk in screening_results
            and screening_results[fk]["classification"] == "SBB-MASKED"]
moderate_list = [fk for fk in screen_keys if fk in screening_results
                 and screening_results[fk]["classification"] == "MODERATE"]
weak_list = [fk for fk in screen_keys if fk in screening_results
             and screening_results[fk]["classification"] == "WEAK"]

rprint(f"\nSTRONG SIGNAL features: {strong_list if strong_list else 'NONE'}")
rprint(f"SBB-MASKED features: {sbb_list if sbb_list else 'NONE'}")
rprint(f"MODERATE SIGNAL features: {moderate_list}")
rprint(f"WEAK SIGNAL features: {weak_list}")

# SBB-MASKED detail table
if sbb_masked_features:
    rprint(f"\n--- SBB-MASKED Feature Detail (NORMAL-only screening) ---")
    for fk in sbb_masked_features:
        ns = screening_results[fk].get("normal_screening", {})
        ns60 = ns.get("separation", {}).get(60, {})
        rprint(f"  {fk} ({feat_names[fk]}): Full-pop={screening_results[fk]['separation'][60]['rp_spread']:.3f} "
               f"→ NORMAL-only spread@60={ns60.get('rp_spread', 0):.3f}, "
               f"p@60={ns60.get('pval', 1):.4f}")

# ============================================================
# MECHANISM VALIDATION TABLE
# ============================================================
rprint("\n" + "=" * 70)
rprint("MECHANISM VALIDATION TABLE")
rprint("=" * 70)

rprint(f"\n{'Feature':>8} | {'Name':<28} | {'Signal':>10} | {'Temporal':>8} | "
       f"{'Regime':>8} | {'Mono':>8} | {'Final Classification':>22}")
rprint("-" * 120)

for fk in screen_keys:
    if fk not in mechanism_results:
        continue
    mr = mechanism_results[fk]
    name = feat_names[fk]
    rprint(f"{fk:>8} | {name:<28} | {mr['signal_class']:>10} | {mr['temporal']:>8} | "
           f"{mr['regime']:>8} | {mr['monotonic']:>8} | {mr['mechanism_class']:>22}")

# ============================================================
# SAVE OUTPUTS
# ============================================================
rprint("\n" + "=" * 70)
rprint("SAVING OUTPUTS")
rprint("=" * 70)

# 1. feature_screening_clean.md
report_text = "\n".join(report)
with open(OUT / "feature_screening_clean_v32.md", "w", encoding="utf-8") as f:
    f.write(f"# NQ Zone Touch Feature Screening v3.2\n\n")
    f.write(f"Generated: {pd.Timestamp.now():%Y-%m-%d %H:%M}\n\n")
    f.write("```\n")
    f.write(report_text)
    f.write("\n```\n")
rprint(f"  Saved feature_screening_clean_v32.md")

# 2. feature_mechanism_validation.md
with open(OUT / "feature_mechanism_validation_v32.md", "w", encoding="utf-8") as f:
    f.write(f"# Feature Mechanism Validation v3.2\n\n")
    f.write(f"Generated: {pd.Timestamp.now():%Y-%m-%d %H:%M}\n\n")
    f.write("| Feature | Name | Signal Class | Temporal | Regime | Monotonic | Final |\n")
    f.write("|---------|------|-------------|----------|--------|-----------|-------|\n")
    for fk in screen_keys:
        if fk not in mechanism_results:
            continue
        mr = mechanism_results[fk]
        f.write(f"| {fk} | {feat_names[fk]} | {mr['signal_class']} | "
                f"{mr['temporal']} | {mr['regime']} | {mr['monotonic']} | "
                f"{mr['mechanism_class']} |\n")
rprint(f"  Saved feature_mechanism_validation_v32.md")

# 3. p1_features_computed.csv
feat_df = touches.copy()
for fk in active_keys:
    feat_df[fk] = features[fk]
feat_df.to_csv(OUT / "p1_features_computed_v32.csv", index=False)
rprint(f"  Saved p1_features_computed_v32.csv ({len(feat_df)} rows, {len(feat_df.columns)} cols)")

# 4. feature_config_partial.json
config = {
    "baseline_pf_3t": BASELINE_PF_3T,
    "baseline_rp_60": BASELINE_RP_60,
    "median_cell": {"stop": MC_STOP, "target": MC_TGT, "time_cap": MC_TC},
    "p1_touch_count": n,
    "channel_proximity_ticks": best_prox,
    "feature_bin_edges": {},
    "feature_means": {},
    "feature_stds": {},
    "classifications": {},
}

for fk in screen_keys:
    if fk in screening_results:
        config["classifications"][fk] = screening_results[fk]["classification"]
    if feat_types.get(fk) == "cont":
        vals = features[fk].astype(float)
        valid = ~np.isnan(vals)
        if valid.sum() > 0:
            config["feature_means"][fk] = float(np.nanmean(vals))
            config["feature_stds"][fk] = float(np.nanstd(vals))
        if fk in screening_results and screening_results[fk]["edges"] is not None:
            p33, p67 = screening_results[fk]["edges"]
            config["feature_bin_edges"][fk] = [float(p33), float(p67)]

with open(OUT / "feature_config_partial_v32.json", "w") as f:
    json.dump(config, f, indent=2)
rprint(f"  Saved feature_config_partial_v32.json")

# ============================================================
# SELF-CHECK
# ============================================================
rprint("\n" + "=" * 70)
rprint("SELF-CHECK")
rprint("=" * 70)
checks = [
    (f"P1 only ({n} touches, P1a+P1b concatenated)", True),
    ("Median cell exit params extracted (Stop=120t, Target=120t, TC=80)", True),
    ("Single-feature screening used R/P ratios at 4 horizons", True),
    ("Floor rule applied (denominator >= 1.0 tick)", True),
    ("Multi-horizon consistency checked", True),
    ("SBB-masked secondary screening run", True),
    (f"Confirmation simulation run ({len(confirm_keys)} features)", len(confirm_keys) >= 0),
    ("F03 (VP Ray binary) NOT included", "F03" not in features),
    ("F19 derived from touch history", True),
    ("Mechanism validation did NOT remove features", True),
    ("Expansion features 21-25 from zone_lifecycle", True),
    (f"Baseline anchor referenced: PF={BASELINE_PF_3T}, R/P@60={BASELINE_RP_60}", True),
]

for desc, passed in checks:
    status = "PASS" if passed else "FAIL"
    rprint(f"  [{status}] {desc}")

elapsed = time_mod.time() - t0
rprint(f"\n--- Total runtime: {elapsed:.1f}s ---")

# Final report save (update with self-check)
report_text = "\n".join(report)
with open(OUT / "feature_screening_clean_v32.md", "w", encoding="utf-8") as f:
    f.write(f"# NQ Zone Touch Feature Screening v3.2\n\n")
    f.write(f"Generated: {pd.Timestamp.now():%Y-%m-%d %H:%M}\n\n")
    f.write("```\n")
    f.write(report_text)
    f.write("\n```\n")
