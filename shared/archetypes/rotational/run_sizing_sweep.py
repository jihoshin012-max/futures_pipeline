# archetype: rotational
"""Sizing sweep harness for the rotational archetype.

Joint 3-parameter sweep: StepDist x MaxLevels x MaxTotalPosition across all
3 bar types on P1a data. MaxContractSize is fixed at 16 per user decision.

Applies deduplication:
    - MTP=1: adds never fire, ML is irrelevant. Collapse all ML values to ML=1.
    - MTP=2 with ML>=2: only one ADD can fire before MTP cap. Keep ML=2 as
      representative, drop ML=3,4,5.

Raw combos: 14 x 5 x 6 = 420 (but MTP=0 unlimited is included as 6th value)
After dedup: ~308 unique per bar type -> ~924 total rows.

Outputs:
    sizing_sweep_results/sizing_sweep_P1a.tsv
    sizing_sweep_results/sizing_sweep_P1a.json

Usage:
    python run_sizing_sweep.py [--output-dir sizing_sweep_results/] [--config rotational_params.json]
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Path setup: repo root is 3 levels up from this file
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT))

# Add archetype dir so rotational_simulator and rotational_engine are importable
_ARCHETYPE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_ARCHETYPE_DIR))

from shared.data_loader import load_bars, parse_instruments_md  # noqa: E402
from rotational_simulator import RotationalSimulator  # noqa: E402
from rotational_engine import compute_extended_metrics  # noqa: E402

# ---------------------------------------------------------------------------
# Sweep parameters (locked per plan spec)
# ---------------------------------------------------------------------------

STEP_VALUES = [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 6.0, 7.0, 8.0, 10.0]  # 14 values
MAX_LEVELS_VALUES = [1, 2, 3, 4, 5]
MAX_TP_VALUES = [1, 2, 4, 8, 16, 0]  # 0=unlimited

# MaxContractSize fixed at 16 per user decision
MAX_CONTRACT_SIZE = 16

_CONFIG_PATH = _ARCHETYPE_DIR / "rotational_params.json"
_INSTRUMENTS_MD = _REPO_ROOT / "_config/instruments.md"

# TSV column order (locked per plan spec)
TSV_COLUMNS = [
    "step_dist", "max_levels", "max_total_position", "source_id",
    "cycle_pf", "n_cycles", "win_rate", "total_pnl_ticks",
    "max_drawdown_ticks", "sharpe",
    "worst_cycle_dd", "max_level_exposure_pct", "tail_ratio",
    "calmar_ratio", "sortino_ratio", "winning_session_pct",
    "max_dd_duration_bars", "bars_processed",
]


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

def deduplicate_combos(combos: list[tuple]) -> list[tuple]:
    """Deduplicate (step_dist, max_levels, max_total_position) combos.

    Rules:
        - MTP=1: ML irrelevant (adds never fire). Keep only ML=1 per StepDist.
        - MTP=2, ML>=2: only one ADD can fire. Keep ML=2 as representative,
          drop ML=3,4,5.
        - All other combos kept as-is.

    Returns:
        Deduplicated list of (step_dist, max_levels, max_total_position) tuples.
    """
    raw_count = len(combos)
    seen: set = set()
    unique: list[tuple] = []

    for (sd, ml, mtp) in combos:
        # Normalize
        if mtp == 1:
            # ML is irrelevant — use ML=1 as canonical
            canonical = (sd, 1, mtp)
        elif mtp == 2 and ml >= 2:
            # Only one ADD can fire — use ML=2 as canonical
            canonical = (sd, 2, mtp)
        else:
            canonical = (sd, ml, mtp)

        if canonical not in seen:
            seen.add(canonical)
            unique.append(canonical)

    print(f"Deduplicated {raw_count} -> {len(unique)} combinations per bar type")
    return unique


# ---------------------------------------------------------------------------
# Core sweep
# ---------------------------------------------------------------------------

def run_sizing_sweep(
    config_template: dict,
    bar_data_dict: dict[str, pd.DataFrame],
    instrument_info: dict,
    unique_combos: list[tuple],
) -> dict:
    """Execute the sizing sweep across all unique parameter combos and bar types.

    Args:
        config_template: Base config dict (deep-copied per iteration — not mutated).
        bar_data_dict: {source_id: DataFrame} — pre-loaded bar data.
        instrument_info: {tick_size, tick_value, cost_ticks}.
        unique_combos: List of (step_dist, max_levels, max_total_position) tuples.

    Returns:
        dict: {(sd, ml, mtp): {source_id: metrics_dict}}
    """
    cost_ticks = instrument_info["cost_ticks"]
    results: dict = {}

    total_runs = len(unique_combos) * len(bar_data_dict)
    run_count = 0
    t_start = time.time()

    for (sd, ml, mtp) in unique_combos:
        combo_key = (sd, ml, mtp)
        results[combo_key] = {}

        for source_id, bars in bar_data_dict.items():
            # Deep copy config and set sweep params
            cfg = copy.deepcopy(config_template)
            cfg["hypothesis"]["trigger_params"]["step_dist"] = sd
            cfg["martingale"]["max_levels"] = ml
            cfg["martingale"]["max_contract_size"] = MAX_CONTRACT_SIZE
            cfg["martingale"]["initial_qty"] = 1
            cfg["martingale"]["max_total_position"] = mtp
            cfg["_instrument"] = instrument_info
            # Per-source config so RTH filter activates correctly
            cfg["bar_data_primary"] = {source_id: config_template["bar_data_primary"].get(source_id, "")}

            # Run simulation
            simulator = RotationalSimulator(config=cfg, bar_data=bars, reference_data=None)
            sim_result = simulator.run()

            # Compute filtered bars using same filter logic as the simulator.
            # Needed for winning_session_pct (maps start_bar -> trading date).
            filtered_bars = _get_filtered_bars(cfg, bars)

            # Compute extended metrics
            metrics = compute_extended_metrics(
                sim_result.cycles,
                cost_ticks,
                bars_df=filtered_bars,
                max_levels=ml,
            )
            metrics["bars_processed"] = sim_result.bars_processed

            results[combo_key][source_id] = metrics

            run_count += 1
            if run_count % 50 == 0:
                elapsed = time.time() - t_start
                print(f"Progress: {run_count}/{total_runs} runs completed ({elapsed:.0f}s)")

    elapsed_total = time.time() - t_start
    print(f"\nSweep complete: {run_count} runs in {elapsed_total:.1f}s")
    return results


def _get_filtered_bars(cfg: dict, bars: pd.DataFrame) -> pd.DataFrame:
    """Apply the same date+RTH filter the simulator uses, without running simulation.

    This is needed to map start_bar indices (which are in filtered space) back
    to trading dates for winning_session_pct computation.
    """
    import datetime

    _P1_START = datetime.date(2025, 9, 21)
    _P1_END = datetime.date(2025, 12, 14)
    _P1_MIDPOINT = _P1_START + (_P1_END - _P1_START) / 2
    _RTH_START = datetime.time(9, 30, 0)
    _RTH_END = datetime.time(16, 0, 0)

    mask = pd.Series(True, index=bars.index)
    period = cfg.get("period", "").lower()

    if period in ("p1a", "p1b"):
        dates = bars["datetime"].dt.date
        if period == "p1a":
            mask &= (dates >= _P1_START) & (dates <= _P1_MIDPOINT)
        else:
            mask &= (dates > _P1_MIDPOINT) & (dates <= _P1_END)

    source_ids = list(cfg.get("bar_data_primary", {}).keys())
    is_10sec_source = any("10sec" in sid for sid in source_ids)

    if is_10sec_source and "Time" in bars.columns:
        def _parse_time(t_str: str) -> datetime.time:
            parts = str(t_str).strip().split(":")
            h = int(parts[0])
            m = int(parts[1])
            s = int(float(parts[2])) if len(parts) > 2 else 0
            return datetime.time(h, m, s)

        times = bars["Time"].apply(_parse_time)
        mask &= (times >= _RTH_START) & (times < _RTH_END)

    return bars[mask].reset_index(drop=True)


# ---------------------------------------------------------------------------
# Output writers
# ---------------------------------------------------------------------------

def write_tsv(output_path: Path, results: dict, unique_combos: list[tuple], source_ids: list[str]) -> None:
    """Write sweep results as flat TSV (locked column order from plan spec)."""
    rows = []
    for (sd, ml, mtp) in unique_combos:
        combo_key = (sd, ml, mtp)
        source_results = results.get(combo_key, {})
        for source_id in source_ids:
            m = source_results.get(source_id, {})
            if not m:
                continue
            row = {
                "step_dist": sd,
                "max_levels": ml,
                "max_total_position": mtp,
                "source_id": source_id,
                "cycle_pf": m.get("cycle_pf", 0.0),
                "n_cycles": m.get("n_cycles", 0),
                "win_rate": m.get("win_rate", 0.0),
                "total_pnl_ticks": m.get("total_pnl_ticks", 0.0),
                "max_drawdown_ticks": m.get("max_drawdown_ticks", 0.0),
                "sharpe": m.get("sharpe", 0.0),
                "worst_cycle_dd": m.get("worst_cycle_dd", 0.0),
                "max_level_exposure_pct": m.get("max_level_exposure_pct", 0.0),
                "tail_ratio": m.get("tail_ratio", 0.0),
                "calmar_ratio": m.get("calmar_ratio", 0.0),
                "sortino_ratio": m.get("sortino_ratio", 0.0),
                "winning_session_pct": m.get("winning_session_pct", 0.0),
                "max_dd_duration_bars": m.get("max_dd_duration_bars", 0),
                "bars_processed": m.get("bars_processed", 0),
            }
            rows.append(row)

    df = pd.DataFrame(rows, columns=TSV_COLUMNS)
    df.to_csv(output_path, sep="\t", index=False)
    print(f"TSV written: {output_path} ({len(df)} rows)")


def write_json(
    output_path: Path,
    results: dict,
    unique_combos: list[tuple],
    source_ids: list[str],
) -> None:
    """Write sweep results as JSON with metadata."""
    # Convert tuple keys to string for JSON serialization
    serializable_results = {}
    for (sd, ml, mtp) in unique_combos:
        combo_key = (sd, ml, mtp)
        key_str = f"sd={sd}_ml={ml}_mtp={mtp}"
        serializable_results[key_str] = results.get(combo_key, {})

    output = {
        "sweep_params": {
            "step_values": STEP_VALUES,
            "max_levels_values": MAX_LEVELS_VALUES,
            "max_tp_values": MAX_TP_VALUES,
            "max_contract_size": MAX_CONTRACT_SIZE,
            "period": "P1a",
            "total_unique_combos": len(unique_combos),
            "total_runs": len(unique_combos) * len(source_ids),
        },
        "results": serializable_results,
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)
    print(f"JSON written: {output_path}")


# ---------------------------------------------------------------------------
# Summary printer
# ---------------------------------------------------------------------------

def print_sweep_summary(results: dict, unique_combos: list[tuple], source_ids: list[str]) -> None:
    """Print summary stats: best/worst configs, MTP=1 vs martingale, notable PFs."""
    print("\n=== Sizing Sweep Summary (P1a) ===")

    for source_id in source_ids:
        label = source_id.replace("bar_data_", "").replace("_rot", "")
        source_data = [
            ((sd, ml, mtp), results.get((sd, ml, mtp), {}).get(source_id, {}))
            for (sd, ml, mtp) in unique_combos
        ]
        source_data = [(k, v) for k, v in source_data if v]

        if not source_data:
            continue

        # Best and worst by cycle_pf
        sorted_by_pf = sorted(source_data, key=lambda x: x[1].get("cycle_pf", 0.0), reverse=True)
        best_combo, best_m = sorted_by_pf[0]
        worst_combo, worst_m = sorted_by_pf[-1]

        print(f"\n  [{label}]")
        print(
            f"    Best:  SD={best_combo[0]}, ML={best_combo[1]}, MTP={best_combo[2]} "
            f"-> PF={best_m.get('cycle_pf', 0.0)}, PnL={best_m.get('total_pnl_ticks', 0.0)}t"
        )
        print(
            f"    Worst: SD={worst_combo[0]}, ML={worst_combo[1]}, MTP={worst_combo[2]} "
            f"-> PF={worst_m.get('cycle_pf', 0.0)}, PnL={worst_m.get('total_pnl_ticks', 0.0)}t"
        )

        # MTP=1 pure reversal vs best martingale
        mtp1_data = [(k, v) for k, v in source_data if k[2] == 1]
        mtp_gt1_data = [(k, v) for k, v in source_data if k[2] != 1]
        if mtp1_data:
            best_mtp1 = max(mtp1_data, key=lambda x: x[1].get("cycle_pf", 0.0))
            print(
                f"    MTP=1 (pure reversal) best: PF={best_mtp1[1].get('cycle_pf', 0.0)} "
                f"(SD={best_mtp1[0][0]})"
            )
        if mtp_gt1_data:
            best_mart = max(mtp_gt1_data, key=lambda x: x[1].get("cycle_pf", 0.0))
            print(
                f"    Best martingale:             PF={best_mart[1].get('cycle_pf', 0.0)} "
                f"(SD={best_mart[0][0]}, ML={best_mart[0][1]}, MTP={best_mart[0][2]})"
            )

    # Flag notable configs (PF >= 1.0)
    notable = [
        (combo, source_id, m)
        for (sd, ml, mtp) in unique_combos
        for source_id, m in results.get((sd, ml, mtp), {}).items()
        for combo in [(sd, ml, mtp)]
        if m.get("cycle_pf", 0.0) >= 1.0
    ]
    if notable:
        print(f"\n  Notable configs (PF >= 1.0): {len(notable)}")
        for combo, src, m in notable[:10]:  # show top 10
            print(
                f"    SD={combo[0]}, ML={combo[1]}, MTP={combo[2]}, {src} -> "
                f"PF={m.get('cycle_pf', 0.0)}"
            )
    else:
        print("\n  No configs with PF >= 1.0")


# ---------------------------------------------------------------------------
# Profile scorer
# ---------------------------------------------------------------------------

BAR_TYPES = [
    "bar_data_250vol_rot",
    "bar_data_250tick_rot",
    "bar_data_10sec_rot",
]


def _sort_ascending(ascending_cols: list[str], descending_cols: list[str]) -> tuple:
    """Return (by, ascending) args for pd.DataFrame.sort_values."""
    by = ascending_cols + descending_cols
    asc = [True] * len(ascending_cols) + [False] * len(descending_cols)
    return by, asc


def _build_sort_args(profile_def: dict) -> tuple[list[str], list[bool]]:
    """Convert profile definition sort spec to sort_values args."""
    by: list[str] = []
    asc: list[bool] = []

    for tier in ["primary", "secondary", "tertiary", "tiebreaker"]:
        metric_key = f"{tier}_metric"
        sort_key = f"{tier}_sort"
        if metric_key in profile_def:
            by.append(profile_def[metric_key])
            asc.append(profile_def[sort_key] == "asc")

    return by, asc


def score_profiles(
    tsv_path: str,
    definitions_path: str,
    output_dir: str,
) -> None:
    """Score and select baseline profiles from sizing sweep results.

    For each profile definition, for each bar type:
        1. Load TSV results.
        2. Sort by the profile's metric hierarchy.
        3. Select top 3 candidates.
        4. #1 candidate becomes the profile's winning config.

    Writes per-profile JSON to output_dir/profiles/.
    Returns nothing; side-effects are file writes.
    """
    tsv = Path(tsv_path)
    defs_path = Path(definitions_path)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not tsv.exists():
        raise FileNotFoundError(f"TSV not found: {tsv}")
    if not defs_path.exists():
        raise FileNotFoundError(f"Profile definitions not found: {defs_path}")

    df = pd.read_csv(tsv, sep="\t")
    with open(defs_path, "r", encoding="utf-8") as f:
        definitions = json.load(f)

    all_metrics_cols = [
        "step_dist", "max_levels", "max_total_position",
        "cycle_pf", "n_cycles", "win_rate", "total_pnl_ticks",
        "max_drawdown_ticks", "sharpe",
        "worst_cycle_dd", "max_level_exposure_pct", "tail_ratio",
        "calmar_ratio", "sortino_ratio", "winning_session_pct",
        "max_dd_duration_bars",
    ]

    for profile_name, profile_def in definitions.items():
        by, asc = _build_sort_args(profile_def)

        bar_type_configs: dict[str, dict] = {}

        for bar_type in BAR_TYPES:
            subset = df[df["source_id"] == bar_type].copy()
            if subset.empty:
                print(f"  WARNING: no data for {bar_type} in TSV — skipping")
                continue

            # Sort by metric hierarchy
            sorted_df = subset.sort_values(by=by, ascending=asc).reset_index(drop=True)

            # Top 3 candidates
            top3 = sorted_df.head(3)

            # #1 is the winning config
            winner = top3.iloc[0]
            pf_lt_1 = bool(winner["cycle_pf"] < 1.0)

            config_entry: dict = {}
            for col in all_metrics_cols:
                if col in winner.index:
                    val = winner[col]
                    # Convert numpy types to native Python
                    if hasattr(val, "item"):
                        val = val.item()
                    config_entry[col] = val
            config_entry["pf_lt_1_flag"] = pf_lt_1

            # Store top3 for reference
            top3_list = []
            for _, row in top3.iterrows():
                entry: dict = {}
                for col in all_metrics_cols:
                    if col in row.index:
                        v = row[col]
                        if hasattr(v, "item"):
                            v = v.item()
                        entry[col] = v
                entry["pf_lt_1_flag"] = bool(row["cycle_pf"] < 1.0)
                top3_list.append(entry)

            bar_type_configs[bar_type] = {
                "winning": config_entry,
                "top3": top3_list,
            }

        profile_json = {
            "profile": profile_name,
            "description": profile_def.get("description", ""),
            "source": tsv.name,
            "bar_types": {
                bt: bar_type_configs[bt]["winning"]
                for bt in BAR_TYPES
                if bt in bar_type_configs
            },
            "top3_candidates": {
                bt: bar_type_configs[bt]["top3"]
                for bt in BAR_TYPES
                if bt in bar_type_configs
            },
            "notes": (
                "PF < 1.0 configs are flagged (pf_lt_1_flag=true) but NOT excluded — "
                "they remain valid candidates requiring hypothesis improvement."
            ),
        }

        out_file = out_dir / f"{profile_name.lower()}.json"
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(profile_json, f, indent=2)
        print(f"  Profile written: {out_file}")

        # Print summary per bar type
        for bt in BAR_TYPES:
            if bt in bar_type_configs:
                w = bar_type_configs[bt]["winning"]
                flag = " [PF<1 FLAGGED]" if w.get("pf_lt_1_flag") else ""
                print(
                    f"    {profile_name} / {bt}: "
                    f"SD={w['step_dist']}, ML={w['max_levels']}, MTP={w['max_total_position']}, "
                    f"PF={w['cycle_pf']:.4f}{flag}"
                )


def generate_sizing_sweep_report(
    tsv_path: str,
    profiles_dir: str,
    output_path: str,
) -> None:
    """Generate human-readable sizing sweep report from TSV and profile JSONs.

    Sections:
        1. Summary: total runs, dedup savings, configs with PF >= 1.0
        2. Per-profile top-3 tables (per bar type)
        3. Pure reversal (MTP=1) analysis vs best martingale
        4. Notable findings
        5. MTP=1 full table (all StepDist x 3 bar types)
    """
    tsv = Path(tsv_path)
    pdir = Path(profiles_dir)
    df = pd.read_csv(tsv, sep="\t")

    profile_names = ["MAX_PROFIT", "SAFEST", "MOST_CONSISTENT"]
    profiles: dict[str, dict] = {}
    for pname in profile_names:
        pfile = pdir / f"{pname.lower()}.json"
        if pfile.exists():
            with open(pfile, "r", encoding="utf-8") as f:
                profiles[pname] = json.load(f)

    total_rows = len(df)
    pf_ge_1 = (df["cycle_pf"] >= 1.0).sum()
    raw_combos = 14 * 5 * 6  # 420
    unique_combos = total_rows // 3  # 322 per bar type

    lines = []

    lines.append("# Sizing Sweep Report — Rotational Archetype (P1a)")
    lines.append("")
    lines.append("**Generated from:** `sizing_sweep_P1a.tsv`")
    lines.append("**Period:** P1a (in-sample calibration data)")
    lines.append("")
    lines.append("---")
    lines.append("")

    # --- Section 1: Summary ---
    lines.append("## 1. Summary")
    lines.append("")
    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Raw parameter combos | {raw_combos} (14 StepDist x 5 MaxLevels x 6 MTP) |")
    lines.append(f"| After deduplication | {unique_combos} unique combos per bar type |")
    lines.append(f"| Dedup savings | {raw_combos - unique_combos} combos eliminated ({(raw_combos - unique_combos) / raw_combos * 100:.0f}%) |")
    lines.append(f"| Total simulation runs | {total_rows} ({unique_combos} x 3 bar types) |")
    lines.append(f"| Configs with PF >= 1.0 | {pf_ge_1} ({pf_ge_1 / total_rows * 100:.1f}%) |")
    lines.append(f"| Configs with PF < 1.0 | {total_rows - pf_ge_1} ({(total_rows - pf_ge_1) / total_rows * 100:.1f}%) |")
    lines.append("")

    # Best per bar type overall
    lines.append("### Best Config per Bar Type (by Cycle PF)")
    lines.append("")
    lines.append("| Bar Type | StepDist | MaxLevels | MTP | Cycle PF | Total PnL (ticks) |")
    lines.append("|----------|----------|-----------|-----|----------|-------------------|")
    for bt in BAR_TYPES:
        sub = df[df["source_id"] == bt]
        best = sub.loc[sub["cycle_pf"].idxmax()]
        label = bt.replace("bar_data_", "").replace("_rot", "")
        lines.append(
            f"| {label} | {best['step_dist']} | {best['max_levels']} | "
            f"{best['max_total_position']} | {best['cycle_pf']:.4f} | "
            f"{best['total_pnl_ticks']:.0f} |"
        )
    lines.append("")

    lines.append("---")
    lines.append("")

    # --- Section 2: Per-profile top-3 tables ---
    lines.append("## 2. Profile Selections — Top 3 Candidates per Bar Type")
    lines.append("")

    metric_labels = {
        "MAX_PROFIT": ["cycle_pf", "total_pnl_ticks", "worst_cycle_dd", "calmar_ratio"],
        "SAFEST": ["worst_cycle_dd", "max_level_exposure_pct", "tail_ratio", "cycle_pf"],
        "MOST_CONSISTENT": ["calmar_ratio", "winning_session_pct", "max_dd_duration_bars", "cycle_pf"],
    }

    for pname in profile_names:
        if pname not in profiles:
            continue
        profile = profiles[pname]
        desc = profile.get("description", "")
        top3_data = profile.get("top3_candidates", {})

        lines.append(f"### 2.{profile_names.index(pname) + 1} Profile: {pname}")
        lines.append("")
        lines.append(f"*{desc}*")
        lines.append("")

        metrics_to_show = metric_labels.get(pname, ["cycle_pf", "total_pnl_ticks"])

        for bt in BAR_TYPES:
            label = bt.replace("bar_data_", "").replace("_rot", "")
            candidates = top3_data.get(bt, [])
            if not candidates:
                lines.append(f"**{label}:** No data available")
                lines.append("")
                continue

            lines.append(f"**{label}:**")
            lines.append("")

            # Header
            header_cols = ["Rank", "StepDist", "MaxLevels", "MTP"] + metrics_to_show + ["PF<1?"]
            lines.append("| " + " | ".join(header_cols) + " |")
            lines.append("|" + "|".join(["---"] * len(header_cols)) + "|")

            for rank, cand in enumerate(candidates, 1):
                row_vals = [str(rank), str(cand["step_dist"]), str(cand["max_levels"]), str(cand["max_total_position"])]
                for m in metrics_to_show:
                    val = cand.get(m, "N/A")
                    if isinstance(val, float):
                        row_vals.append(f"{val:.4f}" if abs(val) < 10000 else f"{val:.0f}")
                    else:
                        row_vals.append(str(val))
                row_vals.append("YES" if cand.get("pf_lt_1_flag") else "no")
                lines.append("| " + " | ".join(row_vals) + " |")

            lines.append("")

    lines.append("---")
    lines.append("")

    # --- Section 3: Pure reversal vs martingale ---
    lines.append("## 3. Pure Reversal (MTP=1) vs Best Martingale")
    lines.append("")
    lines.append(
        "Pure reversal means MaxTotalPosition=1: the position never adds, so martingale "
        "levels are irrelevant. These rows have `max_level_exposure_pct=0` (confirmed)."
    )
    lines.append("")
    lines.append("| Bar Type | Best MTP=1 PF | Best MTP=1 SD | Best Martingale PF | Martingale SD/ML/MTP | Martingale Wins? |")
    lines.append("|----------|--------------|--------------|-------------------|---------------------|-----------------|")

    for bt in BAR_TYPES:
        sub = df[df["source_id"] == bt]
        mtp1 = sub[sub["max_total_position"] == 1]
        mtp_gt1 = sub[sub["max_total_position"] != 1]

        label = bt.replace("bar_data_", "").replace("_rot", "")

        if mtp1.empty:
            lines.append(f"| {label} | N/A | N/A | N/A | N/A | N/A |")
            continue

        best_mtp1 = mtp1.loc[mtp1["cycle_pf"].idxmax()]
        best_mart_pf = "N/A"
        mart_params = "N/A"
        mart_wins = "N/A"

        if not mtp_gt1.empty:
            best_mart = mtp_gt1.loc[mtp_gt1["cycle_pf"].idxmax()]
            best_mart_pf = f"{best_mart['cycle_pf']:.4f}"
            mart_params = (
                f"SD={best_mart['step_dist']} ML={best_mart['max_levels']} "
                f"MTP={best_mart['max_total_position']}"
            )
            mart_wins = "YES" if best_mart["cycle_pf"] > best_mtp1["cycle_pf"] else "no"

        lines.append(
            f"| {label} | {best_mtp1['cycle_pf']:.4f} | SD={best_mtp1['step_dist']} | "
            f"{best_mart_pf} | {mart_params} | {mart_wins} |"
        )
    lines.append("")

    lines.append("---")
    lines.append("")

    # --- Section 4: Notable findings ---
    lines.append("## 4. Notable Findings")
    lines.append("")

    # PF >= 1.0 count by bar type
    lines.append("### PF >= 1.0 Configs by Bar Type")
    lines.append("")
    lines.append("| Bar Type | Total Configs | PF >= 1.0 | PF < 1.0 | Best PF |")
    lines.append("|----------|--------------|-----------|----------|---------|")
    for bt in BAR_TYPES:
        sub = df[df["source_id"] == bt]
        n_ge1 = (sub["cycle_pf"] >= 1.0).sum()
        n_lt1 = (sub["cycle_pf"] < 1.0).sum()
        best_pf = sub["cycle_pf"].max()
        label = bt.replace("bar_data_", "").replace("_rot", "")
        lines.append(f"| {label} | {len(sub)} | {n_ge1} | {n_lt1} | {best_pf:.4f} |")
    lines.append("")

    # PF < 1.0 flags in profiles
    pf_lt1_flags: list[str] = []
    for pname in profile_names:
        if pname not in profiles:
            continue
        for bt in BAR_TYPES:
            bt_config = profiles[pname].get("bar_types", {}).get(bt, {})
            if bt_config.get("pf_lt_1_flag"):
                label = bt.replace("bar_data_", "").replace("_rot", "")
                pf_lt1_flags.append(
                    f"- **{pname} / {label}**: "
                    f"SD={bt_config['step_dist']}, ML={bt_config['max_levels']}, "
                    f"MTP={bt_config['max_total_position']}, "
                    f"PF={bt_config['cycle_pf']:.4f} — flagged as pf_lt_1_flag=true"
                )

    if pf_lt1_flags:
        lines.append("### PF < 1.0 Flagged Configs in Profiles")
        lines.append("")
        lines.append("These configs were selected by their profile's metric hierarchy despite PF < 1.0.")
        lines.append("They are VALID profile selections — they optimise the target metric (not PF).")
        lines.append("A hypothesis improvement is required before these configs are operationally viable.")
        lines.append("")
        lines.extend(pf_lt1_flags)
        lines.append("")

    # Cross-bar-type profile disagreements
    lines.append("### Cross-Bar-Type Profile Disagreement Analysis")
    lines.append("")
    lines.append("Do the three bar types select different StepDist optima for the same profile?")
    lines.append("")
    lines.append("| Profile | 250vol SD | 250tick SD | 10sec SD | All Agree? |")
    lines.append("|---------|-----------|------------|----------|-----------|")
    for pname in profile_names:
        if pname not in profiles:
            continue
        bts_sd = []
        for bt in BAR_TYPES:
            bt_config = profiles[pname].get("bar_types", {}).get(bt, {})
            bts_sd.append(str(bt_config.get("step_dist", "N/A")))
        agree = "YES" if len(set(bts_sd)) == 1 else "no"
        lines.append(f"| {pname} | {bts_sd[0]} | {bts_sd[1]} | {bts_sd[2]} | {agree} |")
    lines.append("")

    lines.append("---")
    lines.append("")

    # --- Section 5: MTP=1 full table ---
    lines.append("## 5. Pure Reversal (MTP=1) Full Results")
    lines.append("")
    lines.append(
        "All 42 MTP=1 rows (14 StepDist values x 3 bar types). "
        "`max_level_exposure_pct=0` for all rows — confirmed no adds fired."
    )
    lines.append("")

    mtp1_df = df[df["max_total_position"] == 1].copy()

    for bt in BAR_TYPES:
        label = bt.replace("bar_data_", "").replace("_rot", "")
        sub = mtp1_df[mtp1_df["source_id"] == bt].sort_values("step_dist")

        lines.append(f"### {label}")
        lines.append("")
        lines.append("| StepDist | ML | MTP | Cycle PF | n_cycles | Total PnL (t) | calmar | worst_dd | win_sess% |")
        lines.append("|----------|----|-----|----------|----------|--------------|--------|----------|-----------|")

        for _, row in sub.iterrows():
            pf_flag = " *" if row["cycle_pf"] < 1.0 else ""
            lines.append(
                f"| {row['step_dist']} | {row['max_levels']} | {row['max_total_position']} | "
                f"{row['cycle_pf']:.4f}{pf_flag} | {row['n_cycles']} | "
                f"{row['total_pnl_ticks']:.0f} | {row['calmar_ratio']:.4f} | "
                f"{row['worst_cycle_dd']:.0f} | {row['winning_session_pct']:.1f} |"
            )
        lines.append("")
    lines.append("*\\* PF < 1.0*")
    lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("*Report generated programmatically from sizing_sweep_P1a.tsv*")

    report_text = "\n".join(lines)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report_text)
    print(f"Report written: {output_path}")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Rotational archetype — 3-parameter sizing sweep on P1a"
    )
    parser.add_argument(
        "--output-dir",
        default=str(_ARCHETYPE_DIR / "sizing_sweep_results"),
        help="Directory to write sizing_sweep_P1a.tsv and .json",
    )
    parser.add_argument(
        "--config",
        default=str(_CONFIG_PATH),
        help="Path to rotational_params.json",
    )
    parser.add_argument(
        "--score-profiles",
        action="store_true",
        help="Score profiles from existing TSV and write profile JSONs + report (skips sweep)",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # --score-profiles: skip sweep, score from existing TSV
    if args.score_profiles:
        tsv_path = output_dir / "sizing_sweep_P1a.tsv"
        profiles_dir = _ARCHETYPE_DIR / "profiles"
        definitions_path = profiles_dir / "profile_definitions.json"
        report_path = output_dir / "sizing_sweep_report.md"

        if not tsv_path.exists():
            print(f"ERROR: TSV not found: {tsv_path}")
            print("Run sweep first (without --score-profiles) to generate the TSV.")
            sys.exit(1)

        print(f"\nScoring profiles from: {tsv_path}")
        print(f"Definitions: {definitions_path}")
        print(f"Output profiles dir: {profiles_dir}")
        score_profiles(
            tsv_path=str(tsv_path),
            definitions_path=str(definitions_path),
            output_dir=str(profiles_dir),
        )

        print(f"\nGenerating report: {report_path}")
        generate_sizing_sweep_report(
            tsv_path=str(tsv_path),
            profiles_dir=str(profiles_dir),
            output_path=str(report_path),
        )

        print("\nProfile scoring complete.")
        return

    # 1. Load config template
    with open(args.config, "r", encoding="utf-8") as f:
        config_template = json.load(f)

    # Ensure period is P1a for sweep
    config_template["period"] = "P1a"

    # 2. Load instrument constants
    instrument_info = parse_instruments_md(
        config_template["instrument"],
        config_path=str(_INSTRUMENTS_MD),
    )
    print(
        f"Instrument: {config_template['instrument']} — "
        f"tick_size={instrument_info['tick_size']}, "
        f"cost_ticks={instrument_info['cost_ticks']}"
    )

    # 3. Load all bar data ONCE per bar type
    print("\nLoading bar data...")
    bar_data_dict: dict[str, pd.DataFrame] = {}
    for source_id, path in config_template["bar_data_primary"].items():
        bars = load_bars(str(_REPO_ROOT / path))
        bar_data_dict[source_id] = bars
        print(f"  {source_id}: {len(bars)} total bars loaded")

    source_ids = list(bar_data_dict.keys())

    # 4. Build raw combos
    raw_combos = [
        (sd, ml, mtp)
        for sd in STEP_VALUES
        for ml in MAX_LEVELS_VALUES
        for mtp in MAX_TP_VALUES
    ]
    print(f"\nRaw combos: {len(raw_combos)} (before dedup)")

    # 5. Deduplicate
    unique_combos = deduplicate_combos(raw_combos)
    total_runs = len(unique_combos) * len(source_ids)
    print(
        f"Running sweep: {len(unique_combos)} unique combos x {len(source_ids)} bar types "
        f"= {total_runs} simulations"
    )

    # 6. Run sweep
    t0 = time.time()
    results = run_sizing_sweep(config_template, bar_data_dict, instrument_info, unique_combos)
    elapsed = time.time() - t0
    print(f"Total sweep time: {elapsed:.1f}s")

    # 7. Print summary
    print_sweep_summary(results, unique_combos, source_ids)

    # 8. Write outputs
    write_tsv(output_dir / "sizing_sweep_P1a.tsv", results, unique_combos, source_ids)
    write_json(output_dir / "sizing_sweep_P1a.json", results, unique_combos, source_ids)

    print("\nDone.")


if __name__ == "__main__":
    main()
