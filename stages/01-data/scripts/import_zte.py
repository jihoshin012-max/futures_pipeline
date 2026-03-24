# archetype: zone_touch
"""Import ZTE and ray CSVs from Sierra Chart output folder, split by period.

Reads single-file SC exports, splits by P1/P2 date boundaries, writes
per-period files into the pipeline data folder with NQ_ prefix convention.

Usage:
    python import_zte.py --sc-out <SC_OUTPUT_DIR> --dest <TOUCHES_DIR>
    make import-zte  (uses defaults from Makefile)

Input files (from SC):
    ZTE_raw.csv, ray_context.csv, ray_reference.csv

Output files (to pipeline):
    NQ_ZTE_raw_P1.csv, NQ_ZTE_raw_P2.csv
    NQ_ray_context_P1.csv, NQ_ray_context_P2.csv
    NQ_ray_reference_P1.csv, NQ_ray_reference_P2.csv
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

# Add project root to path for shared imports
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from shared.data_loader import parse_period_config

# Period boundaries — read from _config/period_config.md (zone_touch archetype)
PERIOD_BOUNDS = parse_period_config("zone_touch")

# Files to import: (sc_filename, pipeline_prefix, datetime_column)
IMPORT_FILES = [
    ("ZTE_raw.csv",       "NQ_ZTE_raw",       "DateTime"),
    ("ray_context.csv",   "NQ_ray_context",   None),       # no DateTime — uses TouchID
    ("ray_reference.csv", "NQ_ray_reference", "DateTime"),
]


def split_by_period(df, dt_col, period_bounds):
    """Split DataFrame into per-period slices."""
    result = {}
    for p, (start, end) in period_bounds.items():
        mask = (df[dt_col] >= pd.Timestamp(start)) & \
               (df[dt_col] <= pd.Timestamp(end) + pd.Timedelta(days=1))
        chunk = df[mask].copy()
        if len(chunk) > 0:
            result[p] = chunk
    return result


def split_ray_context_by_period(df, zte_df):
    """Split ray_context by matching TouchID bar indices to ZTE period assignment."""
    # TouchID format: "BarIndex_TouchType_SourceLabel"
    # Extract BarIndex, look up which period it belongs to from ZTE
    zte_bar_period = {}
    for _, row in zte_df.iterrows():
        zte_bar_period[str(int(row["BarIndex"]))] = row.get("_period", "")

    result = {}
    for p in PERIOD_BOUNDS:
        mask = df["_period"] == p
        if mask.sum() > 0:
            result[p] = df[mask].drop(columns=["_period"]).copy()
    return result


def main():
    parser = argparse.ArgumentParser(description="Import ZTE data from SC to pipeline")
    parser.add_argument("--sc-out", required=True, help="SC output folder path")
    parser.add_argument("--dest", required=True, help="Pipeline touches folder path")
    args = parser.parse_args()

    sc_out = Path(args.sc_out)
    dest = Path(args.dest)
    dest.mkdir(parents=True, exist_ok=True)

    # First, load and split ZTE_raw (needed for ray_context period assignment)
    zte_path = sc_out / "ZTE_raw.csv"
    if not zte_path.exists():
        print(f"ERROR: {zte_path} not found")
        sys.exit(1)

    print(f"Loading {zte_path}...")
    zte_df = pd.read_csv(zte_path)
    zte_df.columns = zte_df.columns.str.strip()
    for col in zte_df.select_dtypes(include="object").columns:
        zte_df[col] = zte_df[col].str.strip()
    zte_df["DateTime"] = pd.to_datetime(zte_df["DateTime"])
    print(f"  {len(zte_df):,} rows, {zte_df['DateTime'].min()} — {zte_df['DateTime'].max()}")

    # Assign period to each ZTE row
    zte_df["_period"] = ""
    for p, (start, end) in PERIOD_BOUNDS.items():
        mask = (zte_df["DateTime"] >= pd.Timestamp(start)) & \
               (zte_df["DateTime"] <= pd.Timestamp(end) + pd.Timedelta(days=1))
        zte_df.loc[mask, "_period"] = p

    # Build BarIndex → period lookup for ray_context
    bar_to_period = {}
    for _, row in zte_df.iterrows():
        bar_to_period[str(int(row["BarIndex"]))] = row["_period"]

    # Split and write ZTE_raw
    zte_splits = split_by_period(zte_df, "DateTime", PERIOD_BOUNDS)
    for p, chunk in zte_splits.items():
        out_path = dest / f"NQ_ZTE_raw_{p}.csv"
        chunk.drop(columns=["_period"]).to_csv(out_path, index=False)
        print(f"  Wrote {out_path.name}: {len(chunk):,} rows")

    # Split and write ray_reference
    ref_path = sc_out / "ray_reference.csv"
    if ref_path.exists():
        print(f"Loading {ref_path}...")
        ref_df = pd.read_csv(ref_path)
        ref_df.columns = ref_df.columns.str.strip()
        for col in ref_df.select_dtypes(include="object").columns:
            ref_df[col] = ref_df[col].str.strip()
        ref_df["DateTime"] = pd.to_datetime(ref_df["DateTime"])
        ref_splits = split_by_period(ref_df, "DateTime", PERIOD_BOUNDS)
        for p, chunk in ref_splits.items():
            out_path = dest / f"NQ_ray_reference_{p}.csv"
            chunk.to_csv(out_path, index=False)
            print(f"  Wrote {out_path.name}: {len(chunk):,} rows")
    else:
        print(f"  WARNING: {ref_path} not found, skipping")

    # Split and write ray_context (uses BarIndex → period lookup)
    ctx_path = sc_out / "ray_context.csv"
    if ctx_path.exists():
        print(f"Loading {ctx_path}...")
        ctx_df = pd.read_csv(ctx_path)
        ctx_df.columns = ctx_df.columns.str.strip()
        for col in ctx_df.select_dtypes(include="object").columns:
            ctx_df[col] = ctx_df[col].str.strip()
        # Extract BarIndex from TouchID
        ctx_df["_bar"] = ctx_df["TouchID"].str.split("_").str[0]
        ctx_df["_period"] = ctx_df["_bar"].map(bar_to_period).fillna("")
        for p in PERIOD_BOUNDS:
            chunk = ctx_df[ctx_df["_period"] == p].drop(columns=["_bar", "_period"]).copy()
            if len(chunk) > 0:
                out_path = dest / f"NQ_ray_context_{p}.csv"
                chunk.to_csv(out_path, index=False)
                print(f"  Wrote {out_path.name}: {len(chunk):,} rows")
    else:
        print(f"  WARNING: {ctx_path} not found, skipping")

    # Summary
    total = sum(len(c) for c in zte_splits.values())
    outside = len(zte_df[zte_df["_period"] == ""])
    print(f"\nDone. {total:,} touches imported ({outside:,} outside period bounds, dropped).")


if __name__ == "__main__":
    main()
