#!/usr/bin/env python3
# archetype: zone_touch
"""
Ray Feature Screening — RETRY on P2a/P2b split.
P1 ray data too sparse. Uses P2's richer ray lifecycle for calibration/validation.
P2a = first half (calibration), P2b = second half (validation).
A-Cal 4-feature model stays frozen from P1. Only ray feature addition calibrated here.
"""

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, time
import warnings
import traceback

warnings.filterwarnings("ignore")

# =============================================================================
# CONSTANTS
# =============================================================================
TICK_SIZE = 0.25
PIPELINE_ROOT = Path(__file__).resolve().parent.parent.parent.parent
DATA_DIR = PIPELINE_ROOT / "stages" / "01-data" / "data"
TOUCH_DIR = DATA_DIR / "touches"
BAR_VOL_DIR = DATA_DIR / "bar_data" / "volume"
BAR_TIME_DIR = DATA_DIR / "bar_data" / "time"
OUTPUT_DIR = Path(__file__).resolve().parent / "output"

PROX_THRESHOLD = 40
RTH_START = time(9, 30)
RTH_END = time(16, 15)

# Frozen A-Cal (from P1)
ACAL_WEIGHTS = {"F10": 10.0, "F04": 5.94, "F01": 3.44, "F21": 4.42}
ACAL_BINS = {"F10": [220.0, 590.0], "F21": [49.0, 831.87]}
ACAL_THRESHOLD = 16.66
ACAL_MAX = 23.8

T1_MULT = 0.5
STOP_MULT = 1.5
STOP_FLOOR = 120


def tf_minutes(s): return int(s.replace("m", ""))
def is_htf(s): return tf_minutes(s) >= 60


# =============================================================================
# MARKDOWN
# =============================================================================
def md_table(headers, rows):
    lines = ["| " + " | ".join(str(h) for h in headers) + " |"]
    lines.append("|" + "|".join(["---"] * len(headers)) + "|")
    for r in rows:
        lines.append("| " + " | ".join(str(v) for v in r) + " |")
    return "\n".join(lines)

def fmt_f(v, d=1):
    if v is None or (isinstance(v, float) and np.isnan(v)): return "N/A"
    return f"{v:.{d}f}"

def fmt_pct(v, t):
    if t == 0: return "N/A"
    return f"{v/t*100:.1f}%"


# =============================================================================
# DATA LOADING
# =============================================================================
def load_bar_data(path):
    df = pd.read_csv(path)
    df.columns = df.columns.str.strip()
    df = df[["Date", "Time", "Open", "High", "Low", "Last", "Volume"]].copy()
    df.rename(columns={"Last": "Close"}, inplace=True)
    df["DateTime"] = pd.to_datetime(df["Date"].str.strip() + " " + df["Time"].str.strip(), format="mixed")
    df.drop(columns=["Date", "Time"], inplace=True)
    return df


def load_p2_data():
    print("Loading P2 data...")
    bars = load_bar_data(BAR_VOL_DIR / "NQ_BarData_250vol_rot_P2.csv")
    bars["BarIdx"] = bars.index

    zte = pd.read_csv(TOUCH_DIR / "NQ_ZTE_raw_P2.csv")
    zte["DateTime_parsed"] = pd.to_datetime(zte["DateTime"])
    zte = zte[zte["TouchType"] != "VP_RAY"].copy()

    ray_ctx = pd.read_csv(TOUCH_DIR / "NQ_ray_context_P2.csv")
    ray_ctx = ray_ctx[ray_ctx["RayTF"].apply(is_htf)].copy()

    ray_ref = pd.read_csv(TOUCH_DIR / "NQ_ray_reference_P2.csv")
    ray_ref["DateTime_parsed"] = pd.to_datetime(ray_ref["DateTime"])

    print(f"  {len(bars)} bars, {len(zte)} touches, {len(ray_ctx)} HTF ray-touch pairs, {len(ray_ref)} ray events")

    # Build 15m bars
    print("  Loading 10-second bars for 15m...")
    b10 = load_bar_data(BAR_TIME_DIR / "NQ_BarData_10sec_rot_P2.csv")
    b10 = b10.set_index("DateTime").sort_index()
    bars_15m = b10.resample("15min").agg({
        "Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"
    }).dropna().reset_index()
    del b10
    print(f"  {len(bars_15m)} 15m bars")

    return bars, zte, ray_ctx, ray_ref, bars_15m


# =============================================================================
# RAY EXTRACTION
# =============================================================================
def extract_rays(zte, ray_ctx, ray_ref, n_bars):
    ref_rays = []
    for _, row in ray_ref.iterrows():
        if row["DemandRayPrice"] > 0 and is_htf(row["SourceLabel"]):
            ref_rays.append({"price": row["DemandRayPrice"], "side": "DEMAND",
                             "creation_bar": row["BaseBarIndex"], "tf": row["SourceLabel"]})
        if row["SupplyRayPrice"] > 0 and is_htf(row["SourceLabel"]):
            ref_rays.append({"price": row["SupplyRayPrice"], "side": "SUPPLY",
                             "creation_bar": row["BaseBarIndex"], "tf": row["SourceLabel"]})

    zte_bi = dict(zip(
        zte["BarIndex"].astype(str) + "_" + zte["TouchType"] + "_" + zte["SourceLabel"],
        zte["BarIndex"]
    ))
    ctx_rays = {}
    for _, row in ray_ctx.iterrows():
        tid = row["TouchID"]
        touch_bar = zte_bi.get(tid)
        if touch_bar is None:
            try: touch_bar = int(tid.split("_", 1)[0])
            except: continue
        key = (row["RayPrice"], row["RaySide"])
        creation = max(0, touch_bar - row["RayAgeBars"])
        if key not in ctx_rays or creation < ctx_rays[key]["creation_bar"]:
            ctx_rays[key] = {"price": row["RayPrice"], "side": row["RaySide"],
                             "creation_bar": creation, "tf": row["RayTF"]}

    all_rays = {}
    for r in ref_rays:
        all_rays[(r["price"], r["side"])] = r
    for k, r in ctx_rays.items():
        if k not in all_rays:
            all_rays[k] = r

    rays_df = pd.DataFrame(all_rays.values()).sort_values("creation_bar").reset_index(drop=True)
    rays_df["tf_min"] = rays_df["tf"].apply(tf_minutes)
    print(f"  {len(rays_df)} unique HTF ray levels")
    return rays_df


# =============================================================================
# INTERACTION DETECTION + 15m CLOSE
# =============================================================================
def detect_interactions(bars, rays_df, bars_15m):
    highs = bars["High"].values.astype(np.float64)
    lows = bars["Low"].values.astype(np.float64)
    closes = bars["Close"].values.astype(np.float64)
    bar_dts = bars["DateTime"].values
    m15_dts = bars_15m["DateTime"].values
    m15_closes = bars_15m["Close"].values
    thresh = PROX_THRESHOLD * TICK_SIZE
    n = len(highs)
    ixns = []

    for ri in range(len(rays_df)):
        rp = rays_df.iloc[ri]["price"]
        cb = max(0, int(rays_df.iloc[ri]["creation_bar"]))
        if cb >= n: continue

        near = (lows[cb:] <= rp + thresh) & (highs[cb:] >= rp - thresh)
        tr = np.diff(near.astype(np.int8), prepend=0)
        enters = np.where(tr == 1)[0]
        exits = np.where(tr == -1)[0]

        for ei, er in enumerate(enters):
            ea = cb + int(er)
            ea_exits = exits[exits > er]
            xa = cb + int(ea_exits[0]) if len(ea_exits) > 0 else n - 1
            dwell = xa - ea + 1

            af = "ABOVE" if (ea > 0 and closes[ea - 1] > rp) else "BELOW"

            # 15m close
            outcome = "UNDETERMINED"
            if ea < len(bar_dts):
                i15 = np.searchsorted(m15_dts, bar_dts[ea], side="right") - 1
                if 0 <= i15 < len(m15_closes):
                    mc = m15_closes[i15]
                    outcome = ("BOUNCE" if mc > rp else "BREAK") if af == "ABOVE" else \
                              ("BOUNCE" if mc < rp else "BREAK")
            if outcome == "UNDETERMINED":
                fc = closes[ea] if ea < n else rp
                outcome = ("BOUNCE" if fc > rp else "BREAK") if af == "ABOVE" else \
                          ("BOUNCE" if fc < rp else "BREAK")

            # Bounce magnitude
            oe = min(ea + 100, n)
            if af == "ABOVE":
                bmag = (np.max(highs[ea:oe]) - rp) / TICK_SIZE
            else:
                bmag = (rp - np.min(lows[ea:oe])) / TICK_SIZE

            # Close type
            fc = closes[ea] if ea < n else rp
            br = max((highs[ea] - lows[ea]) if ea < n else TICK_SIZE, TICK_SIZE)
            cdr = abs(fc - rp) / br
            if outcome == "BOUNCE":
                ct = "strong_rejection" if cdr >= 0.75 else "weak_rejection"
            else:
                if ea + 1 < n:
                    nc = closes[ea + 1]
                    rb = (nc > rp) if af == "ABOVE" else (nc < rp)
                    ct = "failed_acceptance" if rb else "confirmed_acceptance"
                else:
                    ct = "acceptance"

            # Velocity
            vl = 5
            av = abs(closes[ea] - closes[ea - vl]) / TICK_SIZE / vl if ea >= vl else 0

            # Session
            sess = "UNKNOWN"
            if ea < len(bar_dts):
                t = pd.Timestamp(bar_dts[ea]).time()
                sess = "RTH" if RTH_START <= t <= RTH_END else "ETH"

            ixns.append({
                "ray_idx": ri, "enter_bar": ea, "exit_bar": xa, "dwell": dwell,
                "approach_from": af, "outcome": outcome, "bounce_mag": bmag,
                "close_type": ct, "approach_vel": av, "session": sess,
            })

    return pd.DataFrame(ixns)


# =============================================================================
# LIFECYCLE
# =============================================================================
def build_lifecycle(ixns_valid, rays_df):
    lc = {}
    for ri in range(len(rays_df)):
        ris = ixns_valid[ixns_valid["ray_idx"] == ri].sort_values("enter_bar")
        states = [{"bar": max(0, int(rays_df.iloc[ri]["creation_bar"])),
                   "streak": 0, "flips": 0, "mags": [], "ct": "none",
                   "dwell_start": -1, "dwell_end": -1}]
        streak = 0; flips = 0; mags = []
        for _, ix in ris.iterrows():
            if ix["outcome"] == "BOUNCE":
                streak += 1; mags.append(ix["bounce_mag"])
            else:
                flips += 1; streak = 0; mags.append(ix["bounce_mag"])
            states.append({"bar": int(ix["enter_bar"]), "streak": streak, "flips": flips,
                           "mags": list(mags), "ct": ix["close_type"],
                           "dwell_start": int(ix["enter_bar"]), "dwell_end": int(ix["exit_bar"])})
        lc[ri] = states
    return lc


def get_state(lc, ri, bar):
    states = lc.get(ri, [])
    best = None
    for s in states:
        if s["bar"] <= bar: best = s
        else: break
    return best


# =============================================================================
# COMPUTE FEATURES PER TOUCH
# =============================================================================
def compute_features(zte, ray_ctx, rays_df, lc, ixns, bars):
    closes = bars["Close"].values
    bar_dts = bars["DateTime"].values
    highs = bars["High"].values

    rp_map = {}
    for i, row in rays_df.iterrows():
        rp_map[(row["price"], row["side"])] = i

    zte = zte.copy()
    zte["TouchID"] = zte["BarIndex"].astype(str) + "_" + zte["TouchType"] + "_" + zte["SourceLabel"]

    # Init columns
    for c in ["bk_streak", "bk_flips", "bk_dwell", "bk_decay", "bk_vel",
              "bk_dist", "bk_cross_tf", "obs_present", "obs_streak", "obs_dist"]:
        zte[c] = np.nan
    for c in ["bk_session", "bk_ct", "bk_tf", "bk_15m"]:
        zte[c] = pd.NA

    for ti in range(len(zte)):
        touch = zte.iloc[ti]
        bi = int(touch["BarIndex"])
        tt = touch["TouchType"]
        zt = touch["ZoneTop"]; zb = touch["ZoneBot"]
        zw = touch["ZoneWidthTicks"] * TICK_SIZE
        idx = zte.index[ti]

        if tt == "DEMAND_EDGE":
            entry = zt; t1 = entry + T1_MULT * zw
        elif tt == "SUPPLY_EDGE":
            entry = zb; t1 = entry - T1_MULT * zw
        else:
            continue

        nearby = ray_ctx[ray_ctx["TouchID"] == touch["TouchID"]]
        if len(nearby) == 0: continue

        backing = []; obstacle = []
        for _, rr in nearby.iterrows():
            if rr["RayDistTicks"] > 30: continue
            rp = rr["RayPrice"]; rs = rr["RaySide"]; dist = rr["RayDistTicks"]; rtf = rr["RayTF"]
            ri = rp_map.get((rp, rs))

            if tt == "DEMAND_EDGE":
                is_bk = rp <= entry + 5 * TICK_SIZE
                is_ob = rp > entry + 5 * TICK_SIZE and rp < t1
            else:
                is_bk = rp >= entry - 5 * TICK_SIZE
                is_ob = rp < entry - 5 * TICK_SIZE and rp > t1

            if is_bk: backing.append((dist, ri, rp, rs, rtf))
            if is_ob: obstacle.append((dist, ri, rp, rs, rtf))

        if backing:
            backing.sort()
            bd, bri, bp, bs, btf = backing[0]
            zte.at[idx, "bk_dist"] = float(bd)
            zte.at[idx, "bk_tf"] = str(btf)

            if bri is not None:
                st = get_state(lc, bri, bi)
                if st:
                    zte.at[idx, "bk_streak"] = float(st["streak"])
                    zte.at[idx, "bk_flips"] = float(st["flips"])
                    zte.at[idx, "bk_ct"] = str(st["ct"])
                    mags = st.get("mags", [])
                    if len(mags) >= 6:
                        e = np.mean(mags[:3]); r = np.mean(mags[-3:])
                        zte.at[idx, "bk_decay"] = r / e if e > 0 else 1.0
                    ds = st.get("dwell_start", -1); de = st.get("dwell_end", -1)
                    zte.at[idx, "bk_dwell"] = float(bi - ds) if ds >= 0 and de >= bi else 0.0

            vl = 5
            if bi >= vl:
                zte.at[idx, "bk_vel"] = abs(closes[bi] - closes[bi - vl]) / TICK_SIZE / vl
            if bi < len(bar_dts):
                t = pd.Timestamp(bar_dts[bi]).time()
                zte.at[idx, "bk_session"] = "RTH" if RTH_START <= t <= RTH_END else "ETH"

            if bri is not None:
                rix = ixns[(ixns["ray_idx"] == bri) & (ixns["enter_bar"] <= bi) & (ixns["exit_bar"] >= bi)]
                if len(rix) > 0:
                    zte.at[idx, "bk_15m"] = str(rix.iloc[-1]["outcome"])

            xtf = nearby[(abs(nearby["RayPrice"] - bp) <= 20 * TICK_SIZE) & (nearby["RayTF"] != btf)]["RayTF"].nunique()
            zte.at[idx, "bk_cross_tf"] = float(xtf)

        if obstacle:
            obstacle.sort()
            od, ori, op, os_, otf = obstacle[0]
            zte.at[idx, "obs_present"] = 1.0
            zte.at[idx, "obs_dist"] = float(od)
            if ori is not None:
                st = get_state(lc, ori, bi)
                if st:
                    zte.at[idx, "obs_streak"] = float(st["streak"])
        else:
            zte.at[idx, "obs_present"] = 0.0

    return zte


# =============================================================================
# A-CAL SCORING (frozen from P1)
# =============================================================================
def bin_numeric(v, p33, p67, w, nan=False):
    if nan: return 0.0
    if v <= p33: return w
    if v >= p67: return 0.0
    return w / 2.0

def score_f04(c, w=5.94):
    if c == "NO_PRIOR": return w
    if c == "PRIOR_HELD": return w / 2.0
    return 0.0

def score_f01(t, w=3.44):
    if t == "30m": return w
    if t == "480m": return 0.0
    if t: return w / 2.0
    return 0.0

def acal_score(row, zh):
    seq = int(row.get("TouchSequence", 0))
    pp = None
    if seq > 1:
        key = (row["ZoneTop"], row["ZoneBot"], row["SourceLabel"])
        for prev in reversed(zh.get(key, [])):
            if int(prev["BarIndex"]) < int(row["BarIndex"]) and int(prev.get("TouchSequence", 0)) == seq - 1:
                try: pp = float(prev["Penetration"])
                except: pass
                break

    f10 = bin_numeric(pp or 0, 220.0, 590.0, 10.0, pp is None)
    f04 = score_f04(str(row.get("CascadeState", "")).strip())
    f01 = score_f01(str(row.get("SourceLabel", "")).strip())
    f21 = bin_numeric(float(row.get("ZoneAgeBars", 0)), 49.0, 831.87, 4.42)
    return f10 + f04 + f01 + f21

def build_zh(zte):
    zh = {}
    for _, r in zte.iterrows():
        k = (r["ZoneTop"], r["ZoneBot"], r["SourceLabel"])
        zh.setdefault(k, []).append(r.to_dict())
    for k in zh: zh[k].sort(key=lambda x: int(x["BarIndex"]))
    return zh


# =============================================================================
# SCREENING HELPERS
# =============================================================================
def screen_feature(valid, col, bins_spec):
    rows = []; rps = []; ns = []
    for label, mask_fn in bins_spec:
        sub = valid[mask_fn(valid)]
        n = len(sub)
        rp = sub["RP"].median() if n > 0 else None
        rxn = sub["Reaction"].mean() if n > 0 else None
        pen = sub["Penetration"].mean() if n > 0 else None
        flag = " ⚠️" if 0 < n < 15 else ""
        rows.append([label, n, fmt_f(rxn), fmt_f(pen), fmt_f(rp, 2), f"{n}{flag}"])
        rps.append(rp); ns.append(n)

    vr = [r for r in rps if r is not None]
    spread = max(vr) - min(vr) if len(vr) >= 2 else 0
    mono = True
    if len(vr) >= 3:
        mono = all(vr[i] <= vr[i+1] for i in range(len(vr)-1)) or \
               all(vr[i] >= vr[i+1] for i in range(len(vr)-1))
    mn = min(ns) if ns else 0
    return rows, spread, mono, mn


# =============================================================================
# MAIN
# =============================================================================
def main():
    start = datetime.now()
    print(f"Ray Feature Screening P2a/P2b — {start.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 64)

    bars, zte, ray_ctx, ray_ref, bars_15m = load_p2_data()
    out = []
    out.append("# Ray Feature Screening — RETRY on P2a/P2b Split")
    out.append(f"Generated: {start.strftime('%Y-%m-%d %H:%M')}")
    out.append("A-Cal: frozen 4-feature model from P1 (weights/threshold unchanged)")
    out.append("Ray feature calibration: P2a | Validation: P2b | 60m+ rays only")
    out.append("")

    # =========================================================================
    # STEP 1: P2a/P2b SPLIT
    # =========================================================================
    out.append("=" * 64)
    out.append("STEP 1: P2a/P2b DATE BOUNDARY")
    out.append("=" * 64)
    out.append("")

    dates = zte["DateTime_parsed"]
    d_min = dates.min(); d_max = dates.max()
    d_mid = d_min + (d_max - d_min) / 2
    print(f"  P2 range: {d_min.date()} to {d_max.date()}, midpoint: {d_mid.date()}")

    mask_a = zte["DateTime_parsed"] <= d_mid
    mask_b = zte["DateTime_parsed"] > d_mid
    zte_a = zte[mask_a].copy()
    zte_b = zte[mask_b].copy()

    # Ray events split
    ref_a = ray_ref[ray_ref["DateTime_parsed"] <= d_mid]
    ref_b = ray_ref[ray_ref["DateTime_parsed"] > d_mid]

    # Bar split (by date)
    bar_mid_idx = bars[bars["DateTime"] <= d_mid].index.max()

    # Active rays at start of each half
    rays_a_start = len(ray_ref[ray_ref["BaseBarIndex"] <= 0])  # at very start
    rays_b_start = len(ray_ref[ray_ref["BaseBarIndex"] <= bar_mid_idx])

    out.append(md_table(
        ["Period", "Date range", "Touches", "Ray events", "Active rays at start"],
        [
            ["P2a (cal)", f"{d_min.date()} → {d_mid.date()}", len(zte_a),
             len(ref_a), rays_a_start],
            ["P2b (val)", f"{d_mid.date()} → {d_max.date()}", len(zte_b),
             len(ref_b), rays_b_start],
        ]
    ))
    out.append("")

    # =========================================================================
    # STEP 2: LIFECYCLE ON P2a
    # =========================================================================
    out.append("=" * 64)
    out.append("STEP 2: LIFECYCLE COMPUTATION ON P2a")
    out.append("=" * 64)
    out.append("")

    # Extract rays (from full P2 — rays created in P2a are active in P2a)
    print("  Extracting rays...")
    rays_df = extract_rays(zte, ray_ctx, ray_ref, len(bars))

    # Detect interactions on FULL P2 bar data (lifecycle builds over time)
    print("  Detecting interactions on P2 bar data...")
    ixns = detect_interactions(bars, rays_df, bars_15m)
    ixns_valid = ixns[ixns["outcome"].isin(["BOUNCE", "BREAK"])]
    print(f"  {len(ixns_valid)} valid interactions")

    # Build lifecycle
    print("  Building lifecycle...")
    lc = build_lifecycle(ixns_valid, rays_df)

    # Compute features for P2a touches
    print("  Computing features for P2a...")
    # Filter ray_ctx to P2a touches only
    p2a_touch_ids = set(
        zte_a["BarIndex"].astype(str) + "_" + zte_a["TouchType"] + "_" + zte_a["SourceLabel"]
    )
    rc_a = ray_ctx[ray_ctx["TouchID"].isin(p2a_touch_ids)]
    zte_a_feat = compute_features(zte_a, rc_a, rays_df, lc, ixns, bars)

    # Coverage report
    feat_cols = ["bk_streak", "bk_flips", "bk_dwell", "bk_decay", "bk_vel",
                 "bk_dist", "bk_cross_tf", "bk_session", "bk_ct", "bk_15m",
                 "obs_present", "obs_streak"]
    cov_rows = []
    for c in feat_cols:
        if c in zte_a_feat.columns:
            nn = zte_a_feat[c].isna().sum()
            cov_rows.append([c, f"{nn}/{len(zte_a_feat)}", fmt_pct(nn, len(zte_a_feat))])
    out.append(md_table(["Feature", "NULL count", "% NULL"], cov_rows))
    out.append("")

    # Key coverage checks
    streak_nn = zte_a_feat["bk_streak"].notna().sum()
    streak_gt0 = (zte_a_feat["bk_streak"] > 0).sum()
    out.append(f"Touches with backing ray: {streak_nn}")
    out.append(f"Touches with bounce streak > 0: {streak_gt0}")
    out.append("")

    # Coverage gate
    null_pct = zte_a_feat["bk_streak"].isna().sum() / len(zte_a_feat) * 100
    adequate = null_pct < 20 and streak_gt0 >= 50
    if adequate:
        out.append(f"**COVERAGE ADEQUATE.** NULL={null_pct:.1f}% (<20%), streak>0={streak_gt0} (≥50). Proceeding to screening.")
    else:
        out.append(f"**COVERAGE CHECK:** NULL={null_pct:.1f}%, streak>0={streak_gt0}")
        if null_pct >= 20:
            out.append(f"⚠️ NULL rate {null_pct:.1f}% ≥ 20% threshold.")
        if streak_gt0 < 50:
            out.append(f"⚠️ Only {streak_gt0} touches with streak>0 (need ≥50).")
        out.append("Proceeding with available data — results may have limited power.")
    out.append("")

    # Save enriched P2a
    zte_a_feat.to_csv(OUTPUT_DIR / "p2a_touches_with_ray_features.csv", index=False)

    # =========================================================================
    # SECTIONS 1-2: SCREENING ON P2a
    # =========================================================================
    out.append("=" * 64)
    out.append("SECTION 1: INDIVIDUAL FEATURE SCREENING (P2a)")
    out.append("=" * 64)
    out.append("")

    valid = zte_a_feat[(zte_a_feat["Reaction"] > 0) & (zte_a_feat["Penetration"] > 0)].copy()
    valid["RP"] = valid["Reaction"] / valid["Penetration"]
    valid["Win"] = (valid["Reaction"] > valid["Penetration"]).astype(int)
    zh = build_zh(zte_a_feat)
    valid["acal"] = valid.apply(lambda r: acal_score(r, zh), axis=1)

    features = {}

    # A) bk_streak
    out.append("### A) bk_streak (bounce streak)\n")
    bins = [
        ("0", lambda d: d["bk_streak"] == 0),
        ("1", lambda d: d["bk_streak"] == 1),
        ("2", lambda d: d["bk_streak"] == 2),
        ("3+", lambda d: d["bk_streak"] >= 3),
        ("NULL", lambda d: d["bk_streak"].isna()),
    ]
    rows, sp, mono, mn = screen_feature(valid, "bk_streak", bins)
    out.append(md_table(["Streak", "n", "Mean Rxn", "Mean Pen", "R/P", "n"], rows))
    out.append(f"\nSpread: {fmt_f(sp, 2)} | Mono: {mono} | Min n: {mn}\n")
    features["A_streak"] = {"spread": sp, "mono": mono, "min_n": mn, "col": "bk_streak"}

    # B) bk_dwell
    out.append("### B) bk_dwell\n")
    bins = [
        ("1-2 bars", lambda d: (d["bk_dwell"] >= 1) & (d["bk_dwell"] <= 2)),
        ("3-5", lambda d: (d["bk_dwell"] >= 3) & (d["bk_dwell"] <= 5)),
        ("6+", lambda d: d["bk_dwell"] >= 6),
        ("Not dwelling", lambda d: d["bk_dwell"] == 0),
        ("NULL", lambda d: d["bk_dwell"].isna()),
    ]
    rows, sp, mono, mn = screen_feature(valid, "bk_dwell", bins)
    out.append(md_table(["Dwell", "n", "Mean Rxn", "Mean Pen", "R/P", "n"], rows))
    out.append(f"\nSpread: {fmt_f(sp, 2)} | Mono: {mono} | Min n: {mn}\n")
    features["B_dwell"] = {"spread": sp, "mono": mono, "min_n": mn, "col": "bk_dwell"}

    # C) bk_session
    out.append("### C) bk_session\n")
    bins = [
        ("RTH", lambda d: d["bk_session"] == "RTH"),
        ("ETH", lambda d: d["bk_session"] == "ETH"),
    ]
    rows, sp, mono, mn = screen_feature(valid, "bk_session", bins)
    out.append(md_table(["Session", "n", "Mean Rxn", "Mean Pen", "R/P", "n"], rows))
    # Correlation check
    vb = valid[valid["bk_session"].isin(["RTH", "ETH"])].copy()
    vb["s_num"] = (vb["bk_session"] == "RTH").astype(int)
    vb["sc_num"] = (vb["SessionClass"].astype(float) <= 2).astype(int)
    corr = vb["s_num"].corr(vb["sc_num"]) if len(vb) > 10 else 0
    out.append(f"\nCorrelation w/ SessionClass: {fmt_f(corr, 2)}")
    if abs(corr) > 0.9:
        out.append("→ **DROPPED: redundant with SessionClass.**")
        features["C_session"] = {"spread": sp, "mono": mono, "min_n": mn, "col": "bk_session", "dropped": True}
    else:
        features["C_session"] = {"spread": sp, "mono": mono, "min_n": mn, "col": "bk_session"}
    out.append("")

    # D) bk_flips
    out.append("### D) bk_flips (flip count)\n")
    bins = [
        ("0", lambda d: d["bk_flips"] == 0),
        ("1-2", lambda d: (d["bk_flips"] >= 1) & (d["bk_flips"] <= 2)),
        ("3-5", lambda d: (d["bk_flips"] >= 3) & (d["bk_flips"] <= 5)),
        ("6+", lambda d: d["bk_flips"] >= 6),
        ("NULL", lambda d: d["bk_flips"].isna()),
    ]
    rows, sp, mono, mn = screen_feature(valid, "bk_flips", bins)
    out.append(md_table(["Flips", "n", "Mean Rxn", "Mean Pen", "R/P", "n"], rows))
    out.append(f"\nSpread: {fmt_f(sp, 2)} | Mono: {mono} | Min n: {mn}\n")
    features["D_flips"] = {"spread": sp, "mono": mono, "min_n": mn, "col": "bk_flips"}

    # E) bk_ct (close type)
    out.append("### E) bk_ct (close type)\n")
    bins = [
        ("Strong rejection", lambda d: d["bk_ct"] == "strong_rejection"),
        ("Weak rejection", lambda d: d["bk_ct"] == "weak_rejection"),
        ("Failed acceptance", lambda d: d["bk_ct"] == "failed_acceptance"),
        ("Confirmed acceptance", lambda d: d["bk_ct"] == "confirmed_acceptance"),
        ("None", lambda d: d["bk_ct"].isin(["none", "acceptance"]) | d["bk_ct"].isna()),
    ]
    rows, sp, mono, mn = screen_feature(valid, "bk_ct", bins)
    out.append(md_table(["Close type", "n", "Mean Rxn", "Mean Pen", "R/P", "n"], rows))
    out.append(f"\nSpread: {fmt_f(sp, 2)} | Mono: {mono} | Min n: {mn}\n")
    features["E_ct"] = {"spread": sp, "mono": mono, "min_n": mn, "col": "bk_ct"}

    # F) bk_decay
    out.append("### F) bk_decay\n")
    bins = [
        ("> 1.0 (strengthening)", lambda d: d["bk_decay"] > 1.0),
        ("0.8-1.0 (stable)", lambda d: (d["bk_decay"] >= 0.8) & (d["bk_decay"] <= 1.0)),
        ("< 0.8 (decaying)", lambda d: d["bk_decay"] < 0.8),
        ("NULL", lambda d: d["bk_decay"].isna()),
    ]
    rows, sp, mono, mn = screen_feature(valid, "bk_decay", bins)
    out.append(md_table(["Decay", "n", "Mean Rxn", "Mean Pen", "R/P", "n"], rows))
    out.append(f"\nSpread: {fmt_f(sp, 2)} | Mono: {mono} | Min n: {mn}\n")
    features["F_decay"] = {"spread": sp, "mono": mono, "min_n": mn, "col": "bk_decay"}

    # G) bk_vel
    out.append("### G) bk_vel (approach velocity)\n")
    bins = [
        ("Fast (>5)", lambda d: d["bk_vel"] > 5),
        ("Medium (2-5)", lambda d: (d["bk_vel"] >= 2) & (d["bk_vel"] <= 5)),
        ("Slow (<2)", lambda d: d["bk_vel"] < 2),
        ("NULL", lambda d: d["bk_vel"].isna()),
    ]
    rows, sp, mono, mn = screen_feature(valid, "bk_vel", bins)
    out.append(md_table(["Velocity", "n", "Mean Rxn", "Mean Pen", "R/P", "n"], rows))
    out.append(f"\nSpread: {fmt_f(sp, 2)} | Mono: {mono} | Min n: {mn}\n")
    features["G_vel"] = {"spread": sp, "mono": mono, "min_n": mn, "col": "bk_vel"}

    # H) obstacle (3+ streak)
    out.append("### H) strong_obstacle\n")
    valid["strong_obs"] = (valid["obs_present"] == 1) & (valid["obs_streak"] >= 3)
    bins = [
        ("Yes", lambda d: d["strong_obs"] == True),
        ("No", lambda d: d["strong_obs"] == False),
    ]
    rows, sp, mono, mn = screen_feature(valid, "strong_obs", bins)
    out.append(md_table(["Obstacle?", "n", "Mean Rxn", "Mean Pen", "R/P", "n"], rows))
    out.append(f"\nSpread: {fmt_f(sp, 2)} | Min n: {mn}\n")
    features["H_obs"] = {"spread": sp, "mono": mono, "min_n": mn, "col": "strong_obs"}

    # I) bk_cross_tf
    out.append("### I) bk_cross_tf\n")
    bins = [
        ("0-1", lambda d: d["bk_cross_tf"] <= 1),
        ("2", lambda d: d["bk_cross_tf"] == 2),
        ("3+", lambda d: d["bk_cross_tf"] >= 3),
        ("NULL", lambda d: d["bk_cross_tf"].isna()),
    ]
    rows, sp, mono, mn = screen_feature(valid, "bk_cross_tf", bins)
    out.append(md_table(["Cross-TF", "n", "Mean Rxn", "Mean Pen", "R/P", "n"], rows))
    out.append(f"\nSpread: {fmt_f(sp, 2)} | Mono: {mono} | Min n: {mn}\n")
    features["I_xtf"] = {"spread": sp, "mono": mono, "min_n": mn, "col": "bk_cross_tf"}

    # J) bk_15m
    out.append("### J) bk_15m (15m close at ray)\n")
    bins = [
        ("Rejection", lambda d: d["bk_15m"] == "BOUNCE"),
        ("Acceptance", lambda d: d["bk_15m"] == "BREAK"),
        ("No interaction", lambda d: d["bk_15m"].isna()),
    ]
    rows, sp, mono, mn = screen_feature(valid, "bk_15m", bins)
    out.append(md_table(["15m close", "n", "Mean Rxn", "Mean Pen", "R/P", "n"], rows))
    out.append(f"\nSpread: {fmt_f(sp, 2)} | Min n: {mn}\n")
    features["J_15m"] = {"spread": sp, "mono": mono, "min_n": mn, "col": "bk_15m"}

    # K) bk_dist
    out.append("### K) bk_dist\n")
    bins = [
        ("<10t", lambda d: d["bk_dist"] < 10),
        ("10-20t", lambda d: (d["bk_dist"] >= 10) & (d["bk_dist"] < 20)),
        ("20-30t", lambda d: (d["bk_dist"] >= 20) & (d["bk_dist"] <= 30)),
        ("30t+/NULL", lambda d: (d["bk_dist"] > 30) | d["bk_dist"].isna()),
    ]
    rows, sp, mono, mn = screen_feature(valid, "bk_dist", bins)
    out.append(md_table(["Distance", "n", "Mean Rxn", "Mean Pen", "R/P", "n"], rows))
    out.append(f"\nSpread: {fmt_f(sp, 2)} | Mono: {mono} | Min n: {mn}\n")
    features["K_dist"] = {"spread": sp, "mono": mono, "min_n": mn, "col": "bk_dist"}

    # =========================================================================
    # SECTION 2: RANKING
    # =========================================================================
    out.append("=" * 64)
    out.append("SECTION 2: RANKING AND SELECTION")
    out.append("=" * 64)
    out.append("")

    ranked = sorted(features.items(), key=lambda x: x[1]["spread"], reverse=True)
    advance = []; marginal = []
    rank_rows = []
    for rk, (name, info) in enumerate(ranked, 1):
        sp = info["spread"]; mono = info["mono"]; mn = info["min_n"]
        dropped = info.get("dropped", False)
        if dropped:
            status = "DROP (redundant)"
        elif sp > 0.5 and mono and mn >= 15:
            status = "ADVANCE"; advance.append(name)
        elif sp > 0.3:
            status = "MARGINAL"; marginal.append(name)
        else:
            status = "DROP"
        rank_rows.append([rk, name, fmt_f(sp, 2), "Y" if mono else "N", mn, status])

    out.append(md_table(["Rank", "Feature", "Spread", "Mono?", "Min n", "Status"], rank_rows))
    out.append(f"\n**ADVANCE:** {', '.join(advance) or 'None'}")
    out.append(f"**MARGINAL:** {', '.join(marginal) or 'None'}")
    out.append("")

    # =========================================================================
    # SECTION 3: COMBINATION TESTING
    # =========================================================================
    out.append("=" * 64)
    out.append("SECTION 3: COMBINATION TESTING (P2a)")
    out.append("=" * 64)
    out.append("")

    # Baseline quintiles
    out.append("### Baseline: 4-feature A-Cal\n")
    try:
        valid["q5b"] = pd.qcut(valid["acal"], 5, labels=False, duplicates="drop")
        for q in sorted(valid["q5b"].unique()):
            sub = valid[valid["q5b"] == q]
            out.append(f"Q{int(q)+1}: n={len(sub)}, R/P={fmt_f(sub['RP'].median(), 2)}, "
                       f"WR={fmt_f(sub['Win'].mean()*100)}%")
        q1b = valid[valid["q5b"] == valid["q5b"].min()]["RP"].median()
        q5b = valid[valid["q5b"] == valid["q5b"].max()]["RP"].median()
        q5q1_base = q5b / q1b if q1b and q1b > 0 else 0
        out.append(f"\nBaseline Q5/Q1 = {fmt_f(q5q1_base, 2)}")
    except Exception as e:
        q5q1_base = 0
        out.append(f"Baseline quintile error: {e}")
    out.append("")

    test_list = advance + marginal
    best_feat = None; best_w = None; best_q5q1 = q5q1_base

    for fname in test_list:
        col = features[fname]["col"]
        if col not in valid.columns: continue

        out.append(f"### Testing: {fname}\n")
        fv = valid[col].copy()

        # Numeric encoding
        if fv.dtype == object or fv.dtype.name == "string":
            cats = fv.dropna().unique()
            crp = {c: valid[valid[col] == c]["RP"].median() for c in cats if len(valid[valid[col] == c]) > 0}
            sc = sorted(crp.keys(), key=lambda x: crp.get(x, 0))
            cm = {c: i / max(len(sc) - 1, 1) for i, c in enumerate(sc)}
            fn = fv.map(cm).fillna(0.5)
        elif set(fv.dropna().unique()).issubset({0, 1, True, False, 0.0, 1.0}):
            fn = fv.astype(float).fillna(0.5)
        else:
            fmn = fv.min(); fmx = fv.max()
            fn = ((fv - fmn) / (fmx - fmn)).fillna(0.5) if fmx > fmn else fv.fillna(0.5)

        w_rows = []
        bw = None; br = 0
        for pct in [5, 10, 15, 20, 25]:
            rw = ACAL_MAX * pct / 100
            comb = valid["acal"] + fn * rw
            try:
                q5c = pd.qcut(comb, 5, labels=False, duplicates="drop")
                q1r = valid[q5c == q5c.min()]["RP"].median()
                q5r = valid[q5c == q5c.max()]["RP"].median()
                ratio = q5r / q1r if q1r and q1r > 0 else 0
            except:
                ratio = 0
            w_rows.append([f"{pct}%", fmt_f(ratio, 2)])
            if ratio > br: br = ratio; bw = pct

        out.append(md_table(["Weight", "Q5/Q1"], w_rows))
        out.append(f"\nBest: {bw}% → Q5/Q1={fmt_f(br, 2)} (baseline: {fmt_f(q5q1_base, 2)})")

        if br > best_q5q1:
            out.append(f"→ **IMPROVES** by {fmt_f(br - q5q1_base, 2)}")
            best_feat = fname; best_w = bw; best_q5q1 = br
        else:
            out.append("→ No improvement.")
        out.append("")

    out.append("### Summary\n")
    if best_feat:
        out.append(f"**Best ray feature:** {best_feat} at {best_w}% weight")
        out.append(f"**Q5/Q1:** {fmt_f(q5q1_base, 2)} → {fmt_f(best_q5q1, 2)}")
    else:
        out.append("**No ray feature improves the model on P2a.**")
    out.append("")

    # =========================================================================
    # SECTION 4: P2b VALIDATION
    # =========================================================================
    out.append("=" * 64)
    out.append("SECTION 4: P2b VALIDATION")
    out.append("=" * 64)
    out.append("")

    if best_feat is None:
        out.append("**No feature passed P2a screening. Skipping P2b validation.**")
        out.append("The 4-feature A-Cal model continues unchanged.")
        out.append("")
    else:
        out.append(f"Validating {best_feat} at {best_w}% weight on P2b...\n")

        # Compute features for P2b
        print("  Computing features for P2b...")
        p2b_tids = set(
            zte_b["BarIndex"].astype(str) + "_" + zte_b["TouchType"] + "_" + zte_b["SourceLabel"]
        )
        rc_b = ray_ctx[ray_ctx["TouchID"].isin(p2b_tids)]
        zte_b_feat = compute_features(zte_b, rc_b, rays_df, lc, ixns, bars)
        zte_b_feat.to_csv(OUTPUT_DIR / "p2b_touches_with_ray_features.csv", index=False)

        val = zte_b_feat[(zte_b_feat["Reaction"] > 0) & (zte_b_feat["Penetration"] > 0)].copy()
        val["RP"] = val["Reaction"] / val["Penetration"]
        val["Win"] = (val["Reaction"] > val["Penetration"]).astype(int)
        zh_b = build_zh(zte_b_feat)
        val["acal"] = val.apply(lambda r: acal_score(r, zh_b), axis=1)

        col = features[best_feat]["col"]
        fv = val[col].copy()
        if fv.dtype == object or fv.dtype.name == "string":
            cats = fv.dropna().unique()
            crp = {c: val[val[col] == c]["RP"].median() for c in cats if len(val[val[col] == c]) > 0}
            sc = sorted(crp.keys(), key=lambda x: crp.get(x, 0))
            cm = {c: i / max(len(sc) - 1, 1) for i, c in enumerate(sc)}
            fn = fv.map(cm).fillna(0.5)
        elif set(fv.dropna().unique()).issubset({0, 1, True, False, 0.0, 1.0}):
            fn = fv.astype(float).fillna(0.5)
        else:
            fmn = fv.min(); fmx = fv.max()
            fn = ((fv - fmn) / (fmx - fmn)).fillna(0.5) if fmx > fmn else fv.fillna(0.5)

        rw = ACAL_MAX * best_w / 100
        comb_v = val["acal"] + fn * rw

        try:
            q5v = pd.qcut(comb_v, 5, labels=False, duplicates="drop")
            q1rv = val[q5v == q5v.min()]["RP"].median()
            q5rv = val[q5v == q5v.max()]["RP"].median()
            q5q1_v = q5rv / q1rv if q1rv and q1rv > 0 else 0

            # Baseline on P2b
            q5bv = pd.qcut(val["acal"], 5, labels=False, duplicates="drop")
            q1bv = val[q5bv == q5bv.min()]["RP"].median()
            q5bv_r = val[q5bv == q5bv.max()]["RP"].median()
            q5q1_bv = q5bv_r / q1bv if q1bv and q1bv > 0 else 0

            out.append(md_table(
                ["Metric", "P2a (cal)", "P2b (val)"],
                [
                    ["Touches", len(valid), len(val)],
                    ["Q5/Q1 with ray", fmt_f(best_q5q1, 2), fmt_f(q5q1_v, 2)],
                    ["Q5/Q1 baseline", fmt_f(q5q1_base, 2), fmt_f(q5q1_bv, 2)],
                    ["Q5 R/P", "—", fmt_f(q5rv, 2)],
                    ["Q1 R/P", "—", fmt_f(q1rv, 2)],
                ]
            ))
            out.append("")

            passes = True
            if q5q1_v < best_q5q1 * 0.5:
                out.append(f"⚠️ FAIL: P2b Q5/Q1 ({fmt_f(q5q1_v, 2)}) < 50% of P2a ({fmt_f(best_q5q1 * 0.5, 2)})")
                passes = False
            if q5q1_v <= q5q1_bv:
                out.append(f"⚠️ FAIL: Ray does not improve P2b ({fmt_f(q5q1_v, 2)} vs baseline {fmt_f(q5q1_bv, 2)})")
                passes = False

            if passes:
                out.append("**PASS:** Ray feature improves P2b. Advance to implementation.")
            else:
                out.append("**FAIL:** Ray feature does not pass P2b validation.")
                out.append("The 4-feature A-Cal model continues unchanged.")

        except Exception as e:
            out.append(f"P2b validation error: {e}")

    out.append("")

    # =========================================================================
    # SECTION 5: IMPLEMENTATION SPEC
    # =========================================================================
    out.append("=" * 64)
    out.append("SECTION 5: IMPLEMENTATION SPECIFICATION")
    out.append("=" * 64)
    out.append("")
    if best_feat and "PASS" in "\n".join(out):
        out.append(f"Feature: {best_feat} (col: {features[best_feat]['col']})")
        out.append(f"Weight: {best_w}% of A-Cal max ({ACAL_MAX * best_w / 100:.2f} points)")
        out.append(f"P2a Q5/Q1: {fmt_f(best_q5q1, 2)}")
        out.append("")
        out.append("Path classification and full spec require human review.")
    else:
        out.append("**No ray feature passed validation.**")
        out.append("The 4-feature A-Cal model continues to paper trading unchanged.")
        out.append("")
        out.append("**Path 2 (trade management):** The stall-detection finding (130t/trade on 10%)")
        out.append("remains viable as a separate exit management investigation.")
        out.append("It does not require A-Cal changes.")

    # Write
    output_path = OUTPUT_DIR / "ray_feature_screening_p2.md"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(out))

    elapsed = datetime.now() - start
    print(f"\n{'=' * 64}")
    print(f"Screening complete in {elapsed}")
    print(f"Results saved to: {output_path}")


if __name__ == "__main__":
    main()
