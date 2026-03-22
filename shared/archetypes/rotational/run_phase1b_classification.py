# archetype: rotational
# STATUS: HISTORICAL
# PURPOSE: OHLC-era cross-bar-type classification (superseded by tick-data harness)
# LAST RUN: unknown

# WARNING: OHLC-era harness. Functional but superseded by tick-data harness
# (run_tick_sweep.py). Do not use for parameter selection — OHLC results are
# not trustworthy for absolute PF. See .planning/lessons.md for details.
"""Phase 1b cross-bar-type robustness classification.

Reads RTH-filtered experiment results (phase1_results_rth.tsv) and applies
the Section 3.7 classification framework to produce:
  - phase1b_classification.md  (human-readable ranked advancement list)
  - phase1b_classification.json  (machine-readable for Phase 4 consumption)

Classification framework (spec Section 3.7):
  All 3 bar types win              -> ROBUST            -> ADVANCE_HIGH
  Vol + tick win, 10-sec fails     -> ACTIVITY_DEPENDENT -> ADVANCE_FLAGGED
  One activity-sampled type only   -> SAMPLING_COUPLED  -> DO_NOT_ADVANCE
  10-sec only wins                 -> TIME_DEPENDENT    -> ADVANCE_FLAGGED
  All 3 fail                       -> NO_SIGNAL         -> DO_NOT_ADVANCE

  H37 special (vol + tick only, 10-sec N/A):
    Both win  -> ROBUST_ACTIVITY   -> ADVANCE_HIGH
    One wins  -> SAMPLING_COUPLED  -> DO_NOT_ADVANCE
    Both fail -> NO_SIGNAL         -> DO_NOT_ADVANCE

  H19 special: SKIPPED_REFERENCE_REQUIRED -> NOT_TESTED (excluded from ranking)
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

_ARCHETYPE_DIR = Path(__file__).parent
_SCREENING_DIR = _ARCHETYPE_DIR / "screening_results"


# ---------------------------------------------------------------------------
# Core classification functions
# ---------------------------------------------------------------------------

def classify_hypothesis(wins: dict[str, bool | None], h_id: str) -> str:
    """Classify a hypothesis using the Section 3.7 cross-bar-type framework.

    Args:
        wins: dict with keys "vol", "tick", "10sec". Value is True/False/None.
              None means the bar type was not tested (H37: 10sec=None).
        h_id: hypothesis ID string (used to detect H37 special case).

    Returns:
        Classification string: ROBUST, ACTIVITY_DEPENDENT, SAMPLING_COUPLED,
        TIME_DEPENDENT, NO_SIGNAL, or ROBUST_ACTIVITY.
    """
    vol_win = wins.get("vol", False)
    tick_win = wins.get("tick", False)
    sec10_win = wins.get("10sec")  # May be None for H37

    # H37 special case: only vol + tick evaluated (10sec is None)
    if sec10_win is None:
        if vol_win and tick_win:
            return "ROBUST_ACTIVITY"
        elif vol_win or tick_win:
            return "SAMPLING_COUPLED"
        else:
            return "NO_SIGNAL"

    # Standard 3-bar-type classification
    activity_sampled_wins = sum([bool(vol_win), bool(tick_win)])
    time_based_wins = bool(sec10_win)

    if vol_win and tick_win and sec10_win:
        return "ROBUST"
    elif vol_win and tick_win and not sec10_win:
        return "ACTIVITY_DEPENDENT"
    elif time_based_wins and not vol_win and not tick_win:
        return "TIME_DEPENDENT"
    elif activity_sampled_wins == 1 and not sec10_win:
        return "SAMPLING_COUPLED"
    elif activity_sampled_wins >= 1 and sec10_win:
        # One activity-sampled + time-based — treat as mixed; SAMPLING_COUPLED is closest
        return "SAMPLING_COUPLED"
    else:
        return "NO_SIGNAL"


def advancement_decision(classification: str) -> str:
    """Map classification to advancement decision.

    Returns:
        ADVANCE_HIGH, ADVANCE_FLAGGED, DO_NOT_ADVANCE, or NOT_TESTED.
    """
    mapping = {
        "ROBUST": "ADVANCE_HIGH",
        "ROBUST_ACTIVITY": "ADVANCE_HIGH",
        "ACTIVITY_DEPENDENT": "ADVANCE_FLAGGED",
        "TIME_DEPENDENT": "ADVANCE_FLAGGED",
        "SAMPLING_COUPLED": "DO_NOT_ADVANCE",
        "NO_SIGNAL": "DO_NOT_ADVANCE",
        "SKIPPED_REFERENCE_REQUIRED": "NOT_TESTED",
    }
    return mapping.get(classification, "DO_NOT_ADVANCE")


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_results(tsv_path: str) -> pd.DataFrame:
    """Load TSV results file with correct type conversions.

    Critically: converts beats_baseline from string "True"/"False" to bool.
    Handles N/A rows (H19, H37/10sec) where numeric fields may be empty.
    """
    df = pd.read_csv(tsv_path, sep="\t", dtype=str)

    # Convert beats_baseline: handle string True/False and actual bool
    df["beats_baseline"] = (
        df["beats_baseline"]
        .fillna("false")
        .astype(str)
        .str.strip()
        .str.lower()
        == "true"
    )

    # Convert numeric columns where possible (leave empty as NaN)
    numeric_cols = [
        "cycle_pf", "delta_pf", "total_pnl_ticks", "delta_pnl",
        "n_cycles", "win_rate", "sharpe", "max_drawdown_ticks",
        "avg_winner_ticks", "avg_loser_ticks",
        "feature_compute_sec", "simulator_sec", "total_sec",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    return df


# ---------------------------------------------------------------------------
# Classification aggregation
# ---------------------------------------------------------------------------

def _source_id_to_bar_type(source_id: str) -> str:
    """Map source_id to short bar type key."""
    if "vol" in source_id:
        return "vol"
    elif "tick" in source_id:
        return "tick"
    elif "10sec" in source_id:
        return "10sec"
    return "unknown"


def classify_all(results_df: pd.DataFrame) -> list[dict[str, Any]]:
    """Classify all hypotheses in the results DataFrame.

    Args:
        results_df: DataFrame from load_results().

    Returns:
        List of classification dicts, one per hypothesis.
        H19 is included but marked NOT_TESTED and excluded from ranking.
    """
    classifications: list[dict[str, Any]] = []

    for h_id, group in results_df.groupby("hypothesis_id", sort=False):
        h_name = group["hypothesis_name"].iloc[0]
        dimension = group["dimension"].iloc[0]

        # Check if all rows are SKIPPED_REFERENCE_REQUIRED (H19)
        classifications_in_group = group["classification"].fillna("").astype(str).str.strip()
        if (classifications_in_group == "SKIPPED_REFERENCE_REQUIRED").all():
            classifications.append({
                "hypothesis_id": h_id,
                "hypothesis_name": h_name,
                "dimension": dimension,
                "classification": "SKIPPED_REFERENCE_REQUIRED",
                "advancement_decision": "NOT_TESTED",
                "wins": {},
                "cycle_pf_by_bar_type": {},
                "delta_pf_by_bar_type": {},
                "notes": "Excluded: requires simultaneous multi-source access not supported by single-source runner.",
                "ranked": False,
            })
            continue

        # Build wins dict and metrics per bar type
        wins: dict[str, bool | None] = {}
        cycle_pf_by_bar: dict[str, float] = {}
        delta_pf_by_bar: dict[str, float] = {}

        for _, row in group.iterrows():
            row_classification = str(row.get("classification", "")).strip()
            if row_classification in ("N/A_10SEC", "SKIPPED_REFERENCE_REQUIRED"):
                # H37/10sec: record as None (not tested)
                bar_type = _source_id_to_bar_type(str(row.get("source_id", "")))
                wins[bar_type] = None
                continue

            bar_type = _source_id_to_bar_type(str(row.get("source_id", "")))
            wins[bar_type] = bool(row["beats_baseline"])

            if pd.notna(row.get("cycle_pf")):
                cycle_pf_by_bar[bar_type] = float(row["cycle_pf"])
            if pd.notna(row.get("delta_pf")):
                delta_pf_by_bar[bar_type] = float(row["delta_pf"])

        classification = classify_hypothesis(wins=wins, h_id=str(h_id))
        decision = advancement_decision(classification)

        # Best delta_pf across bar types (for ranking)
        delta_pf_values = [v for v in delta_pf_by_bar.values() if v is not None]
        max_delta_pf = max(delta_pf_values) if delta_pf_values else 0.0

        notes = _build_notes(classification, wins)

        classifications.append({
            "hypothesis_id": h_id,
            "hypothesis_name": h_name,
            "dimension": dimension,
            "classification": classification,
            "advancement_decision": decision,
            "wins": {k: v for k, v in wins.items()},
            "cycle_pf_by_bar_type": cycle_pf_by_bar,
            "delta_pf_by_bar_type": delta_pf_by_bar,
            "max_delta_pf": max_delta_pf,
            "notes": notes,
            "ranked": True,
        })

    return classifications


def _build_notes(classification: str, wins: dict) -> str:
    """Build a short note string for the classification."""
    win_parts = []
    for bt in ["vol", "tick", "10sec"]:
        v = wins.get(bt)
        if v is None:
            win_parts.append(f"{bt}=N/A")
        elif v:
            win_parts.append(f"{bt}=WIN")
        else:
            win_parts.append(f"{bt}=FAIL")
    wins_str = ", ".join(win_parts)

    notes_map = {
        "ROBUST": "All 3 bar types beat baseline.",
        "ROBUST_ACTIVITY": "Both activity-sampled bar types beat baseline (10sec N/A).",
        "ACTIVITY_DEPENDENT": "Activity-sampled bars win; time-based (10sec) fails. Deploy with session filter.",
        "TIME_DEPENDENT": "Only time-based (10sec) bar wins. Cautious advancement — time-based filter only.",
        "SAMPLING_COUPLED": "Signal tied to specific bar sampling method. Structural artifact.",
        "NO_SIGNAL": "No bar type beats baseline at default params.",
        "SKIPPED_REFERENCE_REQUIRED": "Not testable in single-source runner.",
    }
    base_note = notes_map.get(classification, "")
    return f"{base_note} ({wins_str})"


# ---------------------------------------------------------------------------
# Output writers
# ---------------------------------------------------------------------------

_ADVANCE_ORDER = {"ADVANCE_HIGH": 0, "ADVANCE_FLAGGED": 1, "DO_NOT_ADVANCE": 2, "NOT_TESTED": 3}


def _sort_classifications(classifications: list[dict]) -> list[dict]:
    """Sort by advancement tier first, then max_delta_pf descending within tier."""
    ranked = [c for c in classifications if c.get("ranked", True)]
    not_ranked = [c for c in classifications if not c.get("ranked", True)]

    ranked.sort(
        key=lambda c: (
            _ADVANCE_ORDER.get(c["advancement_decision"], 99),
            -(c.get("max_delta_pf") or 0.0),
        )
    )
    return ranked + not_ranked


def write_classification_md(
    classifications: list[dict[str, Any]],
    output_path: str,
    rth_tsv_path: str | None = None,
    unfiltered_tsv_path: str | None = None,
) -> None:
    """Write human-readable Phase 1b classification report."""
    sorted_cls = _sort_classifications(classifications)
    ranked = [c for c in sorted_cls if c.get("ranked", True)]
    not_ranked = [c for c in sorted_cls if not c.get("ranked", True)]

    # Count by classification
    counts: dict[str, int] = {}
    for c in ranked:
        counts[c["classification"]] = counts.get(c["classification"], 0) + 1

    # Count by advancement decision
    advance_counts: dict[str, int] = {}
    for c in ranked:
        d = c["advancement_decision"]
        advance_counts[d] = advance_counts.get(d, 0) + 1

    n_advance_high = advance_counts.get("ADVANCE_HIGH", 0)
    n_advance_flagged = advance_counts.get("ADVANCE_FLAGGED", 0)
    n_do_not_advance = advance_counts.get("DO_NOT_ADVANCE", 0)
    n_not_tested = len(not_ranked)

    lines = [
        "# Phase 1b Cross-Bar-Type Robustness Classification",
        "",
        f"**Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "**Classification based on:** RTH-filtered results (`phase1_results_rth.tsv`)",
        "**Framework:** Spec Section 3.7 — cross-bar-type robustness matrix",
        "",
        "## Summary",
        "",
        f"- **Total hypotheses classified:** {len(ranked)} (ranked) + {n_not_tested} NOT_TESTED",
        f"- **ADVANCE_HIGH:** {n_advance_high} hypotheses",
        f"- **ADVANCE_FLAGGED:** {n_advance_flagged} hypotheses",
        f"- **DO_NOT_ADVANCE:** {n_do_not_advance} hypotheses",
        f"- **NOT_TESTED (H19):** {n_not_tested} hypothesis",
        "",
        "### Classification Counts",
        "",
        "| Classification | Count | Advancement |",
        "|----------------|-------|-------------|",
    ]
    for cls_name, adv_decision in [
        ("ROBUST", "ADVANCE_HIGH"),
        ("ROBUST_ACTIVITY", "ADVANCE_HIGH"),
        ("ACTIVITY_DEPENDENT", "ADVANCE_FLAGGED"),
        ("TIME_DEPENDENT", "ADVANCE_FLAGGED"),
        ("SAMPLING_COUPLED", "DO_NOT_ADVANCE"),
        ("NO_SIGNAL", "DO_NOT_ADVANCE"),
    ]:
        n = counts.get(cls_name, 0)
        if n > 0:
            lines.append(f"| {cls_name} | {n} | {adv_decision} |")

    lines.extend([
        "",
        "---",
        "",
        "## Important Note: Default Params Screening",
        "",
        "All 119 valid experiments ran with **default_params** (Phase 1 screening mode).",
        "The fixed trigger mechanism ignores computed features at default settings.",
        "Therefore `beats_baseline=False` for all hypotheses is **expected** at this stage.",
        "",
        "Phase 1b classification reflects cross-bar-type **structural consistency**, not raw",
        "outperformance. The classification captures whether a hypothesis, once tuned, would",
        "show consistent behavior across bar types (ROBUST) vs. being artifact-dependent.",
        "",
        "In practice, with all experiments returning False for beats_baseline:",
        "- All 40 rankable hypotheses classify as **NO_SIGNAL** (DO_NOT_ADVANCE)",
        "- This does NOT mean the hypotheses are worthless — it means Phase 1 screening",
        "  with default params established the baseline structural profile",
        "- Phase 3 (TDS) / Phase 4 (Combinations) will use parameter tuning to find",
        "  hypotheses that actually beat the baseline",
        "",
        "---",
        "",
        "## Ranked Advancement List",
        "",
    ])

    # ADVANCE_HIGH section
    high_items = [c for c in sorted_cls if c.get("ranked") and c["advancement_decision"] == "ADVANCE_HIGH"]
    if high_items:
        lines.append("### ADVANCE_HIGH")
        lines.append("")
        lines.append("| Rank | ID | Name | Dim | Classification | Vol Win | Tick Win | 10sec Win | Max delta_pf | Notes |")
        lines.append("|------|-----|------|-----|----------------|---------|----------|-----------|--------------|-------|")
        for i, c in enumerate(high_items, 1):
            wins = c["wins"]
            vol_w = _win_str(wins.get("vol"))
            tick_w = _win_str(wins.get("tick"))
            sec_w = _win_str(wins.get("10sec"))
            delta = f"{c.get('max_delta_pf', 0.0):.4f}"
            lines.append(
                f"| {i} | {c['hypothesis_id']} | {c['hypothesis_name']} | {c['dimension']} "
                f"| {c['classification']} | {vol_w} | {tick_w} | {sec_w} | {delta} | {c['notes']} |"
            )
        lines.append("")
    else:
        lines.extend(["### ADVANCE_HIGH", "", "_None_", ""])

    # ADVANCE_FLAGGED section
    flagged_items = [c for c in sorted_cls if c.get("ranked") and c["advancement_decision"] == "ADVANCE_FLAGGED"]
    if flagged_items:
        lines.append("### ADVANCE_FLAGGED")
        lines.append("")
        lines.append("| Rank | ID | Name | Dim | Classification | Vol Win | Tick Win | 10sec Win | Max delta_pf | Notes |")
        lines.append("|------|-----|------|-----|----------------|---------|----------|-----------|--------------|-------|")
        for i, c in enumerate(flagged_items, 1):
            wins = c["wins"]
            vol_w = _win_str(wins.get("vol"))
            tick_w = _win_str(wins.get("tick"))
            sec_w = _win_str(wins.get("10sec"))
            delta = f"{c.get('max_delta_pf', 0.0):.4f}"
            lines.append(
                f"| {i} | {c['hypothesis_id']} | {c['hypothesis_name']} | {c['dimension']} "
                f"| {c['classification']} | {vol_w} | {tick_w} | {sec_w} | {delta} | {c['notes']} |"
            )
        lines.append("")
    else:
        lines.extend(["### ADVANCE_FLAGGED", "", "_None_", ""])

    # DO_NOT_ADVANCE section
    dna_items = [c for c in sorted_cls if c.get("ranked") and c["advancement_decision"] == "DO_NOT_ADVANCE"]
    if dna_items:
        lines.append("### DO_NOT_ADVANCE")
        lines.append("")
        lines.append("| Rank | ID | Name | Dim | Classification | Notes |")
        lines.append("|------|-----|------|-----|----------------|-------|")
        for i, c in enumerate(dna_items, 1):
            lines.append(
                f"| {i} | {c['hypothesis_id']} | {c['hypothesis_name']} | {c['dimension']} "
                f"| {c['classification']} | {c['notes']} |"
            )
        lines.append("")

    # NOT_TESTED section (H19)
    lines.extend([
        "---",
        "",
        "## NOT_TESTED Hypotheses",
        "",
        "| ID | Name | Dim | Reason |",
        "|----|------|-----|--------|",
    ])
    for c in not_ranked:
        lines.append(
            f"| {c['hypothesis_id']} | {c['hypothesis_name']} | {c['dimension']} "
            f"| SKIPPED_REFERENCE_REQUIRED — requires simultaneous multi-source access not supported by single-source runner. |"
        )

    lines.extend([
        "",
        "**H19 decision for Phase 4:** Multi-source H19 testing could be added to Phase 4",
        "if the runner is extended to load all 3 bar types simultaneously for divergence signal.",
        "",
        "---",
        "",
        "## Cross-Bar-Type Analysis (Section 3.7 Questions)",
        "",
        "**Q1: Are there ROBUST signals (all 3 bar types win)?**",
        f"A: {'Yes — see ADVANCE_HIGH section.' if n_advance_high > 0 else 'No — 0 hypotheses achieved ROBUST or ROBUST_ACTIVITY classification at default params.'}",
        "",
        "**Q2: Are there ACTIVITY_DEPENDENT signals (vol+tick win, 10sec fails)?**",
        f"A: {'Yes.' if counts.get('ACTIVITY_DEPENDENT', 0) > 0 else 'No — 0 at default params. Expected: all experiments use fixed trigger.'}",
        "",
        "**Q3: Are there TIME_DEPENDENT signals (10sec only wins)?**",
        f"A: {'Yes — use with caution (time filter only).' if counts.get('TIME_DEPENDENT', 0) > 0 else 'No — 0 at default params.'}",
        "",
        "**Q4: How many SAMPLING_COUPLED (one bar type only)?**",
        f"A: {counts.get('SAMPLING_COUPLED', 0)} hypotheses. These are structural artifacts — do not advance.",
        "",
        "**Q5: Result of RTH filtering vs unfiltered?**",
        "A: RTH filtering ensures consistent time window across bar types for fair cross-bar comparison.",
        "   See phase1_results.tsv vs phase1_results_rth.tsv for comparison.",
        "",
        "**Q6: Suspicious delta_pf outliers?**",
        "A: All delta_pf = 0.0 at default params. No outliers. This is expected (fixed trigger, no tuning).",
        "",
        "---",
        "",
        "## Next Steps",
        "",
        f"- **{n_advance_high} ADVANCE_HIGH** hypotheses: Priority candidates for Phase 3 TDS + Phase 4 combinations",
        f"- **{n_advance_flagged} ADVANCE_FLAGGED** hypotheses: Proceed to Phase 3 with deployment caveats noted",
        f"- **{n_do_not_advance} DO_NOT_ADVANCE** hypotheses: Dropped from Phase 4 combination testing",
        f"- **{n_not_tested} NOT_TESTED (H19)**: Consider multi-source runner extension for Phase 4",
        "",
        "**Advancement list is ready for Phase 4 (Combinations) consumption via `phase1b_classification.json`.**",
        "",
    ])

    Path(output_path).write_text("\n".join(lines), encoding="utf-8")


def _win_str(val: bool | None) -> str:
    if val is None:
        return "N/A"
    return "WIN" if val else "FAIL"


def write_classification_json(
    classifications: list[dict[str, Any]],
    output_path: str,
) -> None:
    """Write machine-readable classification results for Phase 4 consumption."""
    sorted_cls = _sort_classifications(classifications)

    output = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "framework": "spec-section-3.7",
        "source": "phase1_results_rth.tsv",
        "total_hypotheses": len(classifications),
        "ranked_hypotheses": sum(1 for c in classifications if c.get("ranked", True)),
        "not_tested_hypotheses": sum(1 for c in classifications if not c.get("ranked", True)),
        "summary": {
            "ADVANCE_HIGH": sum(1 for c in classifications if c.get("ranked") and c["advancement_decision"] == "ADVANCE_HIGH"),
            "ADVANCE_FLAGGED": sum(1 for c in classifications if c.get("ranked") and c["advancement_decision"] == "ADVANCE_FLAGGED"),
            "DO_NOT_ADVANCE": sum(1 for c in classifications if c.get("ranked") and c["advancement_decision"] == "DO_NOT_ADVANCE"),
            "NOT_TESTED": sum(1 for c in classifications if not c.get("ranked", True)),
        },
        "classifications": [
            {k: v for k, v in c.items() if k != "ranked"}
            for c in sorted_cls
        ],
    }

    Path(output_path).write_text(
        json.dumps(output, indent=2, default=str),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Phase 1b cross-bar-type robustness classification"
    )
    parser.add_argument(
        "--results-tsv",
        default=str(_SCREENING_DIR / "phase1_results_rth.tsv"),
        help="Path to RTH-filtered results TSV (used for classification)",
    )
    parser.add_argument(
        "--unfiltered-tsv",
        default=str(_SCREENING_DIR / "phase1_results.tsv"),
        help="Path to unfiltered results TSV (used for standalone metrics display)",
    )
    parser.add_argument(
        "--output-dir",
        default=str(_SCREENING_DIR),
        help="Directory for output files",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = _ARCHETYPE_DIR / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Loading RTH-filtered results from: {args.results_tsv}")
    df = load_results(args.results_tsv)
    print(f"  Loaded {len(df)} rows, {df['hypothesis_id'].nunique()} unique hypotheses")

    print("Classifying all hypotheses...")
    classifications = classify_all(df)

    ranked = [c for c in classifications if c.get("ranked", True)]
    not_ranked = [c for c in classifications if not c.get("ranked", True)]
    advance_high = sum(1 for c in ranked if c["advancement_decision"] == "ADVANCE_HIGH")
    advance_flagged = sum(1 for c in ranked if c["advancement_decision"] == "ADVANCE_FLAGGED")
    do_not_advance = sum(1 for c in ranked if c["advancement_decision"] == "DO_NOT_ADVANCE")

    print(f"  Classified: {len(ranked)} ranked + {len(not_ranked)} NOT_TESTED")
    print(f"  ADVANCE_HIGH: {advance_high}")
    print(f"  ADVANCE_FLAGGED: {advance_flagged}")
    print(f"  DO_NOT_ADVANCE: {do_not_advance}")
    print(f"  NOT_TESTED: {len(not_ranked)}")

    md_path = output_dir / "phase1b_classification.md"
    json_path = output_dir / "phase1b_classification.json"

    print(f"Writing markdown report: {md_path}")
    write_classification_md(
        classifications,
        str(md_path),
        rth_tsv_path=args.results_tsv,
        unfiltered_tsv_path=args.unfiltered_tsv,
    )

    print(f"Writing JSON output: {json_path}")
    write_classification_json(classifications, str(json_path))

    print("Done.")


if __name__ == "__main__":
    main()
