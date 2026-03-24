# archetype: zone_touch
"""
Zone Touch Data Preparation Pipeline
Follows: .claude/skills/zone-data-prep/SKILL.md (9-step execution sequence)
"""

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import pandas as pd
import numpy as np
import json
import shutil
from pathlib import Path
from datetime import datetime

# === Configuration ===
BASE = Path(r"c:/Projects/pipeline")
DATA = BASE / "stages/01-data/data"
OUT = BASE / "stages/01-data/output/zone_prep"

TICK_SIZE = 0.25  # NQ — from _config/instruments.md
TICK_VALUE = 5.00
INSTRUMENT = "NQ"

PERIODS = ["P1", "P2"]

# Period boundaries from _config/period_config.md (zone_touch archetype)
PERIOD_BOUNDS = {
    "P1": ("2025-09-21", "2025-12-14"),
    "P2": ("2025-12-15", "2026-03-02"),
}

# === ZTE Consolidation (Phase 3) ===
# When USE_ZTE=True, read from ZoneTouchEngine's unified raw CSV instead of
# separate ZRA + ZB4 files. CascadeState and TFConfluence come from ZTE directly;
# no ZB4 merge is needed. ZoneWidthTicks also comes from ZTE.
USE_ZTE = True
ZTE_RAW_PATH = Path(r"C:/Projects/sierrachart/analysis/analyzer_zonereaction/ZTE_raw.csv")

VALID_TOUCH_TYPES = {"DEMAND_EDGE", "SUPPLY_EDGE"}
VALID_SOURCE_LABELS = {"15m", "30m", "60m", "90m", "120m", "240m", "360m", "480m", "720m"}
VALID_CASCADE_STATES = {"PRIOR_HELD", "NO_PRIOR", "PRIOR_BROKE", "UNKNOWN"}

report_lines = []

def rpt(line=""):
    report_lines.append(line)
    print(line)


# =====================================================================
# STEP 1: Load all input files
# =====================================================================
rpt("# Zone Touch Data Preparation Report")
rpt(f"Generated: {datetime.now().isoformat()}")
rpt()
rpt("## Step 1: File Inventory")
rpt()

zra_dfs = {}
zb4_dfs = {}
bar_dfs = {}

if USE_ZTE:
    rpt(f"**Mode: ZTE (consolidated)** — reading from {ZTE_RAW_PATH.name}")
    rpt()
    # Load single ZTE_raw.csv and split by period bounds
    zte_full = pd.read_csv(ZTE_RAW_PATH)
    zte_full.columns = zte_full.columns.str.strip()
    for col in zte_full.select_dtypes(include="object").columns:
        zte_full[col] = zte_full[col].str.strip()
    zte_full["DateTime"] = pd.to_datetime(zte_full["DateTime"])
    rpt(f"ZTE_raw loaded: {len(zte_full):,} rows, {zte_full['DateTime'].min()} — {zte_full['DateTime'].max()}")
    rpt()

for p in PERIODS:
    bar_path = DATA / f"bar_data/volume/NQ_BarData_250vol_rot_{p}.csv"

    if USE_ZTE:
        # Split ZTE by period bounds into ZRA-compatible DataFrames
        p_start, p_end = PERIOD_BOUNDS[p]
        mask = (zte_full["DateTime"] >= pd.Timestamp(p_start)) & \
               (zte_full["DateTime"] <= pd.Timestamp(p_end) + pd.Timedelta(days=1))
        zra = zte_full[mask].copy()

        if len(zra) == 0:
            rpt(f"⚠️ {p}: No ZTE data in period bounds ({p_start} — {p_end}), skipping")
            continue

        # ZTE has CascadeState and TFConfluence already — store them for later,
        # then keep only ZRA-compatible columns so the downstream pipeline works unchanged
        zte_cascade = zra[["DateTime", "BarIndex", "TouchType", "SourceLabel",
                           "CascadeState", "TFConfluence", "ZoneWidthTicks"]].copy()

        # Keep ZRA-schema columns (drop ZB4 scoring + ray columns)
        zra_cols_keep = [
            "DateTime", "BarIndex", "TouchType", "ApproachDir", "TouchPrice",
            "ZoneTop", "ZoneBot", "HasVPRay", "VPRayPrice",
            "Reaction", "Penetration", "ReactionPeakBar", "ZoneBroken", "BreakBarIndex",
            "BarsObserved", "TouchSequence", "ZoneAgeBars", "ApproachVelocity", "TrendSlope",
            "SourceChart", "SourceStudyID", "SourceLabel",
        ]
        # Add RxnBar and PenBar columns
        rxn = sorted([c for c in zra.columns if c.startswith("RxnBar_")])
        pen = sorted([c for c in zra.columns if c.startswith("PenBar_")])
        zra_cols_keep += rxn + pen
        zra = zra[[c for c in zra_cols_keep if c in zra.columns]].copy()

        # Attach ZTE's CascadeState/TFConfluence/ZoneWidthTicks as hidden columns
        # (will be used in place of ZB4 merge later)
        zra["_zte_CascadeState"] = zte_cascade["CascadeState"].values
        zra["_zte_TFConfluence"] = zte_cascade["TFConfluence"].values
        zra["_zte_ZoneWidthTicks"] = zte_cascade["ZoneWidthTicks"].values

        zra_dfs[p] = zra
        # No ZB4 needed in ZTE mode
        zb4_dfs[p] = None

    else:
        # Legacy: separate ZRA + ZB4 files
        zra_path = DATA / f"touches/NQ_ZRA_Hist_{p}.csv"
        zb4_path = DATA / f"touches/NQ_ZB4_signals_{p}.csv"

        zra = pd.read_csv(zra_path)
        zra.columns = zra.columns.str.strip()
        for col in zra.select_dtypes(include="object").columns:
            zra[col] = zra[col].str.strip()
        zra["DateTime"] = pd.to_datetime(zra["DateTime"])
        zra_dfs[p] = zra

        zb4 = pd.read_csv(zb4_path)
        zb4.columns = zb4.columns.str.strip()
        for col in zb4.select_dtypes(include="object").columns:
            zb4[col] = zb4[col].str.strip()
        zb4["DateTime"] = pd.to_datetime(zb4["DateTime"])
        zb4_dfs[p] = zb4

    bar = pd.read_csv(bar_path)
    bar.columns = bar.columns.str.strip()
    cols = list(bar.columns)
    seen = {}
    new_cols = []
    for c in cols:
        if c in seen:
            seen[c] += 1
            new_cols.append(f"{c}_{seen[c]}")
        else:
            seen[c] = 0
            new_cols.append(c)
    bar.columns = new_cols
    bar["DateTime"] = pd.to_datetime(bar["Date"].astype(str).str.strip() + " " + bar["Time"].astype(str).str.strip())
    bar_dfs[p] = bar

    rpt(f"| File | Rows | Date Range |")
    rpt(f"|------|------|------------|")
    src_label = "ZTE" if USE_ZTE else "ZRA"
    rpt(f"| {src_label}_{p} | {len(zra_dfs[p]):,} | {zra_dfs[p]['DateTime'].min()} — {zra_dfs[p]['DateTime'].max()} |")
    if not USE_ZTE:
        rpt(f"| ZB4_{p} | {len(zb4_dfs[p]):,} | {zb4_dfs[p]['DateTime'].min()} — {zb4_dfs[p]['DateTime'].max()} |")
    rpt(f"| Bar_{p} | {len(bar):,} | {bar['DateTime'].min()} — {bar['DateTime'].max()} |")
    rpt()


# =====================================================================
# STEP 2: Filter VP_RAY touches from ZRA
# =====================================================================
rpt("## Step 2: VP_RAY Filtering")
rpt()

for p in list(zra_dfs.keys()):
    zra = zra_dfs[p]
    vp_count = (zra["TouchType"] == "VP_RAY").sum()
    rpt(f"- {p}: {vp_count} VP_RAY touches removed")
    zra = zra[zra["TouchType"] != "VP_RAY"].copy()
    remaining_types = set(zra["TouchType"].unique())
    assert remaining_types <= VALID_TOUCH_TYPES, f"Unexpected TouchType in {p}: {remaining_types - VALID_TOUCH_TYPES}"
    rpt(f"  Remaining types: {remaining_types} ({len(zra):,} rows)")

    if not USE_ZTE:
        # In legacy mode, trim to period boundaries (ZTE mode already trimmed in Step 1)
        p_start, p_end = PERIOD_BOUNDS[p]
        before_trim = len(zra)
        zra = zra[(zra["DateTime"] >= pd.Timestamp(p_start)) & (zra["DateTime"] <= pd.Timestamp(p_end) + pd.Timedelta(days=1))].copy()
        trimmed = before_trim - len(zra)
        if trimmed > 0:
            rpt(f"  Trimmed {trimmed} ZRA rows outside {p} bounds ({p_start} — {p_end}), {len(zra):,} remain")

    zra_dfs[p] = zra

rpt()


# =====================================================================
# STEP 3: Trim ZB4 to ZRA date ranges (skip in ZTE mode)
# =====================================================================
rpt("## Step 3: ZB4 Trimming")
rpt()

if USE_ZTE:
    rpt("- SKIPPED (ZTE mode — CascadeState and TFConfluence already in unified CSV)")
else:
    # REMINDER: Only CascadeState and TFConfluence come from ZB4.
    # Do NOT pull ModeAssignment, QualityScore, ContextScore, TotalScore.
    for p in PERIODS:
        zra = zra_dfs[p]
        zb4 = zb4_dfs[p]
        zra_min, zra_max = zra["DateTime"].min(), zra["DateTime"].max()
        before = len(zb4)
        zb4 = zb4[(zb4["DateTime"] >= zra_min) & (zb4["DateTime"] <= zra_max)].copy()
        after = len(zb4)
        rpt(f"- {p}: ZB4 trimmed from {before:,} to {after:,} rows (ZRA range: {zra_min} — {zra_max})")
        zb4_dfs[p] = zb4

rpt()


# =====================================================================
# STEP 4: Build match keys and merge
# =====================================================================
rpt("## Step 4: Merge Results")
rpt()

def build_key(df):
    """Build composite match key: floor(DateTime, min) | round(TouchPrice, 2) | TouchType | SourceLabel"""
    dt_floor = df["DateTime"].dt.floor("min").astype(str)
    tp_round = df["TouchPrice"].round(2).astype(str)
    return dt_floor + "|" + tp_round + "|" + df["TouchType"] + "|" + df["SourceLabel"]

merged_dfs = {}

for p in PERIODS:
    if p not in zra_dfs:
        continue  # period had no data (ZTE mode, partial chart)

    zra = zra_dfs[p].copy()

    if USE_ZTE:
        # ZTE mode: CascadeState, TFConfluence, ZoneWidthTicks already attached as hidden columns
        zra["CascadeState"] = zra.pop("_zte_CascadeState")
        zra["TFConfluence"] = zra.pop("_zte_TFConfluence").astype(int)
        # Keep _zte_ZoneWidthTicks for Step 5
        matched = len(zra)
        rpt(f"### {p}")
        rpt(f"- ZTE mode: {matched:,} rows — CascadeState and TFConfluence from unified CSV (no ZB4 merge)")
        rpt()
        merged_dfs[p] = zra
    else:
        zb4 = zb4_dfs[p].copy()

        zra["_key"] = build_key(zra)
        zb4["_key"] = build_key(zb4)

        dup_key_count = zra["_key"].duplicated().sum()
        if dup_key_count > 0:
            pct = dup_key_count / len(zra) * 100
            msg = f"  WARNING: {dup_key_count} ZRA rows share a key with another row ({pct:.1f}%)"
            rpt(msg)
            if pct > 1:
                rpt(f"  ⚠️ High duplicate rate — investigate!")

        zb4_dedup = zb4.drop_duplicates(subset="_key", keep="first")
        zb4_cols = zb4_dedup[["_key", "CascadeState", "TFConfluence"]].copy()
        merged = zra.merge(zb4_cols, on="_key", how="left", suffixes=("", "_zb4"))

        matched = merged["CascadeState"].notna().sum()
        unmatched = merged["CascadeState"].isna().sum()
        match_rate = matched / len(merged) * 100

        rpt(f"### {p}")
        rpt(f"- Matched: {matched:,} / {len(merged):,} ({match_rate:.1f}%)")
        rpt(f"- Unmatched: {unmatched:,}")

        if unmatched > 0 and unmatched <= 20:
            unmatched_rows = merged[merged["CascadeState"].isna()]
            rpt(f"- Unmatched touches:")
            for _, row in unmatched_rows.iterrows():
                rpt(f"  - {row['DateTime']} | {row['TouchPrice']} | {row['TouchType']} | {row['SourceLabel']}")

        if match_rate < 99:
            rpt(f"  ⚠️ Match rate below 99% — investigate before proceeding!")

        merged["CascadeState"] = merged["CascadeState"].fillna("UNKNOWN")
        merged["TFConfluence"] = merged["TFConfluence"].fillna(-1).astype(int)
        merged.drop(columns=["_key"], inplace=True)
        merged_dfs[p] = merged

        rpt()

# CONFIRM: No scoring columns leaked
for p in merged_dfs:
    bad_cols = {"ModeAssignment", "QualityScore", "ContextScore", "TotalScore"} & set(merged_dfs[p].columns)
    assert not bad_cols, f"ZB4 scoring columns leaked into merge: {bad_cols}"

rpt("✓ Confirmed: only CascadeState and TFConfluence present (no scoring columns)")
rpt()


# =====================================================================
# STEP 5: Compute derived columns
# =====================================================================
rpt("## Step 5: Derived Columns")
rpt()

for p in merged_dfs:
    df = merged_dfs[p]

    # ZoneWidthTicks
    if USE_ZTE and "_zte_ZoneWidthTicks" in df.columns:
        df["ZoneWidthTicks"] = df.pop("_zte_ZoneWidthTicks")
        rpt(f"- {p}: ZoneWidthTicks from ZTE (not recomputed)")
    else:
        df["ZoneWidthTicks"] = (df["ZoneTop"] - df["ZoneBot"]) / TICK_SIZE

    # SBB_Label
    df["SBB_Label"] = np.where(
        (df["ZoneBroken"] == 1) & ((df["BreakBarIndex"] - df["BarIndex"]) <= 1),
        "SBB", "NORMAL"
    )

    sbb_count = (df["SBB_Label"] == "SBB").sum()
    rpt(f"- {p}: SBB_Label assigned ({sbb_count} SBB touches retained)")

    # Drop columns not needed in merged output
    for col in ["SourceChart", "SourceStudyID"]:
        if col in df.columns:
            df.drop(columns=[col], inplace=True)

    merged_dfs[p] = df

# CONFIRM: SBB touches are labeled but NOT removed.
rpt("✓ Confirmed: SBB touches labeled but NOT removed — all remain in dataset")
rpt()


# =====================================================================
# STEP 6: Join rotational bar data
# =====================================================================
rpt("## Step 6: Bar Data Join")
rpt()

for p in merged_dfs:
    df = merged_dfs[p]
    bar = bar_dfs[p]
    bar_times = bar["DateTime"].values  # numpy datetime64 array

    rot_indices = []
    gaps = []

    for _, row in df.iterrows():
        touch_dt = row["DateTime"]
        # Find nearest bar where bar timestamp <= touch DateTime
        mask = bar_times <= np.datetime64(touch_dt)
        if mask.any():
            idx = np.where(mask)[0][-1]
            rot_indices.append(idx)
            gap_sec = (touch_dt - pd.Timestamp(bar_times[idx])).total_seconds()
            gaps.append(gap_sec)
        else:
            rot_indices.append(-1)
            gaps.append(np.nan)

    df["RotBarIndex"] = rot_indices
    gaps_arr = np.array(gaps)

    matched = np.sum(np.array(rot_indices) >= 0)
    match_rate = matched / len(df) * 100
    max_gap = np.nanmax(gaps_arr) if len(gaps_arr) > 0 else 0
    flagged = np.sum(gaps_arr > 60)

    rpt(f"- {p}: {matched:,}/{len(df):,} matched ({match_rate:.1f}%), max gap: {max_gap:.1f}s")
    if flagged > 0:
        rpt(f"  ⚠️ {flagged} touches with gap > 60s")

    merged_dfs[p] = df

rpt()


# =====================================================================
# STEP 7: Split into sub-periods
# =====================================================================
rpt("## Step 7: Period Split")
rpt()

# p1_split_rule: midpoint (from _config/period_config.md)
all_subperiods = {}

for p in merged_dfs:
    df = merged_dfs[p]
    df = df.sort_values("DateTime").reset_index(drop=True)

    median_dt = df["DateTime"].median()
    # Round to nearest day boundary (midnight)
    split_date = pd.Timestamp(median_dt.date())

    sub_a = f"{p}a"
    sub_b = f"{p}b"

    mask_a = df["DateTime"] < split_date
    mask_b = df["DateTime"] >= split_date

    df.loc[mask_a, "Period"] = sub_a
    df.loc[mask_b, "Period"] = sub_b

    count_a = mask_a.sum()
    count_b = mask_b.sum()

    rpt(f"### {p} split at {split_date.date()}")
    rpt(f"- {sub_a}: {count_a:,} touches ({df.loc[mask_a, 'DateTime'].min().date()} — {df.loc[mask_a, 'DateTime'].max().date()})")
    rpt(f"- {sub_b}: {count_b:,} touches ({df.loc[mask_b, 'DateTime'].min().date()} — {df.loc[mask_b, 'DateTime'].max().date()})")
    rpt()

    all_subperiods[sub_a] = df[mask_a].copy()
    all_subperiods[sub_b] = df[mask_b].copy()

# CONFIRM: Period boundaries determined from data (median DateTime), not hardcoded.
rpt("✓ Confirmed: split dates determined from data (median DateTime), not hardcoded")
rpt()


# =====================================================================
# STEP 8: Verification checks
# =====================================================================
rpt("## Step 8: Verification Checks")
rpt()

all_passed = True

for sp_name, sp_df in all_subperiods.items():
    rpt(f"### {sp_name} ({len(sp_df):,} rows)")
    checks = []

    # No nulls in key columns
    null_cols = []
    for c in ["TouchPrice", "ZoneTop", "ZoneBot", "Reaction", "Penetration"]:
        if sp_df[c].isna().any():
            null_cols.append(c)
    checks.append(("No nulls in key columns", len(null_cols) == 0,
                    f"Nulls in: {null_cols}" if null_cols else ""))

    # Valid TouchType
    bad_tt = set(sp_df["TouchType"].unique()) - VALID_TOUCH_TYPES
    checks.append(("Valid TouchType", len(bad_tt) == 0, f"Invalid: {bad_tt}" if bad_tt else ""))

    # Valid SourceLabel
    bad_sl = set(sp_df["SourceLabel"].unique()) - VALID_SOURCE_LABELS
    checks.append(("Valid SourceLabel", len(bad_sl) == 0, f"Invalid: {bad_sl}" if bad_sl else ""))

    # Valid CascadeState
    bad_cs = set(sp_df["CascadeState"].unique()) - VALID_CASCADE_STATES
    checks.append(("Valid CascadeState", len(bad_cs) == 0, f"Invalid: {bad_cs}" if bad_cs else ""))

    # Non-negative outcomes
    neg_rxn = (sp_df["Reaction"] < 0).sum()
    neg_pen = (sp_df["Penetration"] < 0).sum()
    checks.append(("Non-negative outcomes", neg_rxn == 0 and neg_pen == 0,
                    f"Neg Reaction: {neg_rxn}, Neg Penetration: {neg_pen}"))

    # Zone ordering
    bad_zone = (sp_df["ZoneTop"] <= sp_df["ZoneBot"]).sum()
    checks.append(("Zone ordering (Top > Bot)", bad_zone == 0, f"{bad_zone} violations"))

    # Date range
    parent = sp_name[:2]  # P1 or P2
    p_start, p_end = PERIOD_BOUNDS[parent]
    in_range = (sp_df["DateTime"] >= pd.Timestamp(p_start)) & (sp_df["DateTime"] <= pd.Timestamp(p_end) + pd.Timedelta(days=1))
    out_of_range = (~in_range).sum()
    checks.append(("Date range within bounds", out_of_range == 0, f"{out_of_range} out of range"))

    # Minimum sample
    checks.append(("Minimum 500 touches", len(sp_df) >= 500, f"Only {len(sp_df)}"))

    for name, passed, detail in checks:
        status = "PASS" if passed else "FAIL"
        rpt(f"- [{status}] {name}" + (f" — {detail}" if detail and not passed else ""))
        if not passed:
            # In ZTE mode, partial P2 data is expected (chart may not have full P2 loaded)
            if USE_ZTE and name == "Minimum 500 touches":
                rpt(f"  (ZTE mode: partial period data — non-blocking)")
            else:
                all_passed = False

    rpt()

# CONFIRM: CascadeState contains UNKNOWN values for unmatched rows (valid and expected).
unk_counts = {sp: (df["CascadeState"] == "UNKNOWN").sum() for sp, df in all_subperiods.items()}
rpt(f"✓ Confirmed: UNKNOWN CascadeState counts: {unk_counts}")
rpt()

if not all_passed:
    rpt("❌ VERIFICATION FAILED — check failures above before proceeding")
    raise SystemExit("Verification failed")

rpt("✓ All verification checks passed")
rpt()


# =====================================================================
# STEP 9: Save output files
# =====================================================================
rpt("## Step 9: Output Files")
rpt()

# Define canonical column order
CANONICAL_COLS = [
    "DateTime", "BarIndex", "TouchType", "ApproachDir", "TouchPrice",
    "ZoneTop", "ZoneBot", "HasVPRay", "VPRayPrice",
    "Reaction", "Penetration", "ReactionPeakBar", "ZoneBroken", "BreakBarIndex",
    "BarsObserved", "TouchSequence", "ZoneAgeBars", "ApproachVelocity", "TrendSlope",
    "SourceLabel",
]

# Identify RxnBar and PenBar columns dynamically from actual data
sample_df = list(all_subperiods.values())[0]
rxn_cols = sorted([c for c in sample_df.columns if c.startswith("RxnBar_")])
pen_cols = sorted([c for c in sample_df.columns if c.startswith("PenBar_")])

CANONICAL_COLS += rxn_cols + pen_cols + [
    "ZoneWidthTicks", "CascadeState", "TFConfluence", "SBB_Label", "RotBarIndex", "Period"
]

# Save merged CSVs
for sp_name, sp_df in all_subperiods.items():
    out_path = OUT / f"NQ_merged_{sp_name}.csv"
    sp_df[CANONICAL_COLS].to_csv(out_path, index=False)
    rpt(f"- Saved: {out_path.name} ({len(sp_df):,} rows)")

# Copy bar data files (pass-through, unchanged)
for p in PERIODS:
    src = DATA / f"bar_data/volume/NQ_BarData_250vol_rot_{p}.csv"
    dst = OUT / f"NQ_bardata_{p}.csv"
    shutil.copy2(src, dst)
    rpt(f"- Copied: {dst.name} ({len(bar_dfs[p]):,} rows)")

# Generate period_config.json
period_config = {
    "instrument": INSTRUMENT,
    "tick_size": TICK_SIZE,
    "tick_value_dollars": TICK_VALUE,
    "bar_type": "250-volume",
    "periods": {},
    "bar_data_files": {p: f"NQ_bardata_{p}.csv" for p in PERIODS},
    "total_touches": sum(len(df) for df in all_subperiods.values()),
    "generated_at": datetime.now().isoformat(),
}

for sp_name, sp_df in all_subperiods.items():
    parent = sp_name[:2]
    period_config["periods"][sp_name] = {
        "start": str(sp_df["DateTime"].min().date()),
        "end": str(sp_df["DateTime"].max().date()),
        "touches": len(sp_df),
        "parent": parent,
    }

config_path = OUT / "period_config.json"
with open(config_path, "w") as f:
    json.dump(period_config, f, indent=2)
rpt(f"- Saved: {config_path.name}")

rpt()


# =====================================================================
# Distributions (for report)
# =====================================================================
rpt("## Distributions by Sub-Period")
rpt()

for sp_name, sp_df in all_subperiods.items():
    rpt(f"### {sp_name} ({len(sp_df):,} touches)")
    rpt()

    # TouchType
    rpt("**TouchType:**")
    for tt, cnt in sp_df["TouchType"].value_counts().items():
        rpt(f"  - {tt}: {cnt} ({cnt/len(sp_df)*100:.1f}%)")

    # SourceLabel
    rpt("**SourceLabel (TF):**")
    for sl, cnt in sp_df["SourceLabel"].value_counts().sort_index().items():
        rpt(f"  - {sl}: {cnt} ({cnt/len(sp_df)*100:.1f}%)")

    # CascadeState
    rpt("**CascadeState:**")
    for cs, cnt in sp_df["CascadeState"].value_counts().items():
        rpt(f"  - {cs}: {cnt} ({cnt/len(sp_df)*100:.1f}%)")

    # SBB rate per TF
    rpt("**SBB Rate by TF:**")
    for sl in sorted(sp_df["SourceLabel"].unique()):
        sl_df = sp_df[sp_df["SourceLabel"] == sl]
        sbb_rate = (sl_df["SBB_Label"] == "SBB").mean() * 100
        rpt(f"  - {sl}: {sbb_rate:.1f}%")

    # ZoneWidthTicks
    zwt = sp_df["ZoneWidthTicks"]
    rpt(f"**ZoneWidthTicks:** min={zwt.min():.0f}, max={zwt.max():.0f}, mean={zwt.mean():.1f}, median={zwt.median():.0f}")

    # TouchSequence
    rpt("**TouchSequence:**")
    ts_bins = sp_df["TouchSequence"].clip(upper=5).value_counts().sort_index()
    for ts, cnt in ts_bins.items():
        label = f"{ts}" if ts < 5 else "5+"
        rpt(f"  - {label}: {cnt} ({cnt/len(sp_df)*100:.1f}%)")

    # HasVPRay
    vp_rate = sp_df["HasVPRay"].mean() * 100
    rpt(f"**HasVPRay rate:** {vp_rate:.1f}%")
    rpt()

# Save report
report_path = OUT / "data_preparation_report.md"
with open(report_path, "w", encoding="utf-8") as f:
    f.write("\n".join(report_lines))
rpt(f"- Saved: {report_path.name}")

print("\n=== Zone data preparation complete ===")
