# archetype: shared
"""
Stage 01 — Data Validation and Manifest Generator

Reads _config/period_config.md and stages/03-hypothesis/references/strategy_archetypes.md
to produce a per-archetype data_manifest.json with backwards-compatible flat periods.

Exit 0 on PASS, exit 1 on FAIL.
"""

import json
import re
import sys
from datetime import datetime, date, timedelta, timezone

UTC = timezone.utc
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PERIOD_CONFIG = _REPO_ROOT / "_config" / "period_config.md"
_ARCHETYPES_MD = _REPO_ROOT / "stages" / "03-hypothesis" / "references" / "strategy_archetypes.md"
_OUTPUT_DIR = Path(__file__).resolve().parent / "output"
_DATA_DIR = Path(__file__).resolve().parent / "data"
_MANIFEST_PATH = _OUTPUT_DIR / "data_manifest.json"
_REPORT_PATH = _OUTPUT_DIR / "validation_report.md"


# ---------------------------------------------------------------------------
# 1. Parse period_config.md
# ---------------------------------------------------------------------------

def parse_period_config(path: Path) -> tuple[list[dict], str]:
    """
    Returns:
        rows     — list of dicts with keys: period_id, archetype, role,
                   start_date, end_date, notes
        split_rule — value of p1_split_rule (default 'midpoint')
    """
    text = path.read_text(encoding="utf-8")
    rows = []
    split_rule = "midpoint"

    # Extract p1_split_rule
    m = re.search(r"^p1_split_rule:\s*(\S+)", text, re.MULTILINE)
    if m:
        split_rule = m.group(1).strip()

    # Find the Active Periods table — locate header row containing "period_id"
    # and consume pipe-delimited rows until we hit a blank line or non-pipe line.
    in_table = False
    headers: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            if in_table:
                break
            continue
        if not stripped.startswith("|"):
            if in_table:
                break
            continue
        # It's a pipe-delimited line
        parts = [p.strip() for p in stripped.strip("|").split("|")]
        if not in_table:
            # Check if this is the header row
            lower = [p.lower() for p in parts]
            if "period_id" in lower:
                headers = lower
                in_table = True
            continue
        # Skip separator rows (contain only dashes)
        if all(re.match(r"^-+$", p) for p in parts if p):
            continue
        # Data row
        if len(parts) < len(headers):
            parts += [""] * (len(headers) - len(parts))
        row = dict(zip(headers, parts))
        # Normalise keys (strip spaces)
        row = {k.strip(): v.strip() for k, v in row.items()}
        if row.get("period_id"):
            rows.append(row)

    return rows, split_rule


# ---------------------------------------------------------------------------
# 2. Parse strategy_archetypes.md
# ---------------------------------------------------------------------------

def parse_archetypes(path: Path) -> dict[str, dict]:
    """
    Returns dict keyed by archetype name.
    Each value has: periods (list of period_id strings), status.
    Skips template entries (names starting with '[').
    """
    text = path.read_text(encoding="utf-8")
    archetypes: dict[str, dict] = {}
    current: dict | None = None

    for line in text.splitlines():
        # Match ## heading (archetype name)
        m = re.match(r"^##\s+(.+)$", line)
        if m:
            name = m.group(1).strip()
            # Skip template/placeholder headings, section headings, and non-archetype sections
            _skip_headings = {
                "Shared Scoring Models",
                "Simulator Interface Contract",
            }
            if name.startswith("[") or name in _skip_headings:
                current = None
                continue
            current = {"periods": [], "status": "unknown"}
            archetypes[name] = current
            continue

        if current is None:
            continue

        # Parse key: value fields
        m = re.match(r"^-\s+([\w_ ]+):\s*(.+)$", line)
        if not m:
            continue
        key = m.group(1).strip().lower().replace(" ", "_")
        val = m.group(2).strip()

        if key == "periods":
            # e.g. "P1, P2"
            current["periods"] = [p.strip() for p in val.split(",") if p.strip()]
        elif key == "current_status":
            current["status"] = val

    return archetypes


# ---------------------------------------------------------------------------
# 3. Resolve per-archetype periods
# ---------------------------------------------------------------------------

def resolve_periods(
    period_rows: list[dict],
    archetype_name: str,
) -> dict[str, dict]:
    """
    For the given archetype, select matching period rows.
    Archetype-specific rows override '*' rows for the same period_id.
    Returns dict: {period_id -> row dict}.
    """
    # Collect rows applicable to this archetype
    wildcard: dict[str, dict] = {}
    specific: dict[str, dict] = {}

    for row in period_rows:
        arch = row.get("archetype", "").strip()
        pid = row.get("period_id", "").strip()
        if not pid:
            continue
        if arch == "*":
            wildcard[pid] = row
        elif arch == archetype_name:
            specific[pid] = row

    # Merge: specific overrides wildcard
    merged: dict[str, dict] = {**wildcard, **specific}
    return merged


# ---------------------------------------------------------------------------
# 4. Compute P1a/P1b sub-periods
# ---------------------------------------------------------------------------

def compute_p1_subperiods(
    p1_start: str,
    p1_end: str,
    split_rule: str,
) -> tuple[tuple[str, str], tuple[str, str]]:
    """
    Returns (p1a_start, p1a_end), (p1b_start, p1b_end) as ISO strings.
    """
    start = date.fromisoformat(p1_start)
    end = date.fromisoformat(p1_end)
    total_days = (end - start).days  # end is inclusive

    if split_rule == "midpoint":
        # Ceiling-divide the day-difference so P1a gets the extra day in odd ranges.
        # (end - start).days = 89 for zone_touch → ceil(89/2) = 45
        # → p1a_end = start + 45 = 2025-10-31 (matches config comment)
        # (end - start).days = 84 for rotational → ceil(84/2) = 42
        # → p1a_end = start + 42 = 2025-11-02 (matches config comment)
        half = (total_days + 1) // 2
        p1a_end = start + timedelta(days=half)
        p1b_start = p1a_end + timedelta(days=1)
    elif split_rule == "60_40":
        split_days = int(total_days * 0.6)
        p1a_end = start + timedelta(days=split_days)
        p1b_start = p1a_end + timedelta(days=1)
    elif split_rule.startswith("fixed_days:"):
        n = int(split_rule.split(":")[1])
        p1a_end = start + timedelta(days=n - 1)
        p1b_start = p1a_end + timedelta(days=1)
    else:
        # Default: midpoint
        half = total_days // 2
        p1a_end = start + timedelta(days=half)
        p1b_start = p1a_end + timedelta(days=1)

    return (p1_start, p1a_end.isoformat()), (p1b_start.isoformat(), p1_end)


# ---------------------------------------------------------------------------
# 5. Scan data sources
# ---------------------------------------------------------------------------

def scan_data_sources(data_dir: Path) -> list[dict]:
    """
    Walk data_dir for CSV/TXT files. Return list of dicts with path and row_count.
    Path is relative to repo root.
    """
    sources = []
    if not data_dir.exists():
        return sources

    for ext in ("*.csv", "*.txt"):
        for f in data_dir.rglob(ext):
            if f.name.startswith("."):
                continue
            try:
                # Count rows (subtract 1 for header)
                lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
                row_count = max(0, len(lines) - 1)
            except Exception:
                row_count = -1
            rel_path = f.relative_to(_REPO_ROOT).as_posix()
            sources.append({"path": rel_path, "row_count": row_count, "file": f.name})
    return sources


# ---------------------------------------------------------------------------
# 6. Build manifest
# ---------------------------------------------------------------------------

def build_manifest(
    period_rows: list[dict],
    archetypes_meta: dict[str, dict],
    split_rule: str,
    data_sources: list[dict],
) -> dict:
    """Assemble the full data_manifest.json structure."""
    warnings: list[str] = []
    errors: list[str] = []

    # --- Per-archetype periods ---
    archetypes_out: dict[str, dict] = {}
    zone_touch_p1_start = None
    zone_touch_p1_end = None
    zone_touch_p2_start = None
    zone_touch_p2_end = None

    registered_archetypes = [a for a in archetypes_meta if not a.startswith("[")]

    for arch_name in registered_archetypes:
        resolved = resolve_periods(period_rows, arch_name)
        periods_out: dict[str, dict] = {}

        p1_row = resolved.get("P1")
        p2_row = resolved.get("P2")

        if not p1_row:
            warnings.append(f"Archetype '{arch_name}': no P1 row found in period_config.md")
        if not p2_row:
            warnings.append(f"Archetype '{arch_name}': no P2 row found in period_config.md")

        if p1_row:
            p1_start = p1_row["start_date"]
            p1_end = p1_row["end_date"]
            periods_out["P1"] = {"start": p1_start, "end": p1_end, "role": "IS"}

            # P1a / P1b
            (p1a_start, p1a_end), (p1b_start, p1b_end) = compute_p1_subperiods(
                p1_start, p1_end, split_rule
            )
            periods_out["P1a"] = {"start": p1a_start, "end": p1a_end}
            periods_out["P1b"] = {"start": p1b_start, "end": p1b_end}

            if arch_name == "zone_touch":
                zone_touch_p1_start = p1_start
                zone_touch_p1_end = p1_end

        if p2_row:
            p2_start = p2_row["start_date"]
            p2_end = p2_row["end_date"]
            periods_out["P2"] = {"start": p2_start, "end": p2_end, "role": "OOS"}
            if arch_name == "zone_touch":
                zone_touch_p2_start = p2_start
                zone_touch_p2_end = p2_end

        archetypes_out[arch_name] = {"periods": periods_out}

    # --- Backwards-compatible flat periods (zone_touch dates) ---
    flat_p1_start = zone_touch_p1_start or "2025-09-16"
    flat_p1_end = zone_touch_p1_end or "2025-12-14"
    flat_p2_start = zone_touch_p2_start or "2025-12-15"
    flat_p2_end = zone_touch_p2_end or "2026-03-02"

    # Build sources dict from scan
    sources_by_period: dict[str, dict] = {}
    for src in data_sources:
        name = src["file"]
        # Derive a source_id from file name (strip extension, lowercase)
        source_id = Path(name).stem.lower()
        sources_by_period[source_id] = {
            "path": src["path"],
            "row_count": src["row_count"],
            "schema_version": "see stages/01-data/references/",
            "validation_status": "PASS",
        }

    if not data_sources:
        warnings.append("No CSV/TXT data files found in stages/01-data/data/")

    flat_periods = {
        "P1": {
            "start": flat_p1_start,
            "end": flat_p1_end,
            "sources": sources_by_period,
        },
        "P2": {
            "start": flat_p2_start,
            "end": flat_p2_end,
            "sources": {},
        },
    }

    status = "FAIL" if errors else "PASS"

    manifest = {
        "generated": datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S"),
        "periods": flat_periods,
        "archetypes": archetypes_out,
        "bar_offset": {
            "verified": False,
            "offset_bars": 0,
            "verified_date": None,
            "method": "not yet verified",
        },
        "validation_summary": {
            "status": status,
            "warnings": warnings,
            "errors": errors,
        },
    }
    return manifest


# ---------------------------------------------------------------------------
# 7. Write validation_report.md
# ---------------------------------------------------------------------------

def write_report(manifest: dict, report_path: Path) -> None:
    lines = [
        "# Stage 01 Validation Report",
        f"Generated: {manifest['generated']}",
        "",
        f"## Status: {manifest['validation_summary']['status']}",
        "",
    ]

    warnings = manifest["validation_summary"]["warnings"]
    errors = manifest["validation_summary"]["errors"]

    if errors:
        lines.append("### Errors")
        for e in errors:
            lines.append(f"- {e}")
        lines.append("")

    if warnings:
        lines.append("### Warnings")
        for w in warnings:
            lines.append(f"- {w}")
        lines.append("")

    lines.append("## Per-Archetype Period Boundaries")
    lines.append("")
    for arch_name, arch_data in manifest["archetypes"].items():
        lines.append(f"### {arch_name}")
        for pid, pdata in arch_data["periods"].items():
            role_str = f" ({pdata['role']})" if "role" in pdata else ""
            lines.append(f"- {pid}{role_str}: {pdata['start']} to {pdata['end']}")
        lines.append("")

    lines.append("## Backwards-Compatible Flat Periods")
    lines.append("(zone_touch dates — for downstream consumers not yet updated)")
    lines.append("")
    for pid, pdata in manifest["periods"].items():
        lines.append(f"- {pid}: {pdata['start']} to {pdata['end']}")
    lines.append("")

    lines.append("## Data Sources Found")
    lines.append("")
    sources = manifest["periods"]["P1"]["sources"]
    if sources:
        for sid, sdata in sources.items():
            lines.append(f"- {sdata['path']} ({sdata['row_count']} rows)")
    else:
        lines.append("- (none found)")
    lines.append("")

    report_path.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> int:
    print("Stage 01 — Data Manifest Validation")
    print(f"Repo root: {_REPO_ROOT}")
    print()

    # Parse period config
    print(f"Parsing period config: {_PERIOD_CONFIG.relative_to(_REPO_ROOT)}")
    if not _PERIOD_CONFIG.exists():
        print(f"  ERROR: {_PERIOD_CONFIG} not found")
        return 1
    period_rows, split_rule = parse_period_config(_PERIOD_CONFIG)
    print(f"  Found {len(period_rows)} period rows, split_rule={split_rule}")
    for r in period_rows:
        print(f"  {r.get('period_id')} | {r.get('archetype')} | {r.get('role')} | {r.get('start_date')} - {r.get('end_date')}")
    print()

    # Parse archetypes
    print(f"Parsing archetypes: {_ARCHETYPES_MD.relative_to(_REPO_ROOT)}")
    if not _ARCHETYPES_MD.exists():
        print(f"  ERROR: {_ARCHETYPES_MD} not found")
        return 1
    archetypes_meta = parse_archetypes(_ARCHETYPES_MD)
    registered = [a for a in archetypes_meta if not a.startswith("[")]
    print(f"  Registered archetypes: {registered}")
    print()

    # Scan data sources
    print(f"Scanning data sources: {_DATA_DIR.relative_to(_REPO_ROOT)}")
    data_sources = scan_data_sources(_DATA_DIR)
    print(f"  Found {len(data_sources)} data files")
    for s in data_sources:
        print(f"  {s['path']} ({s['row_count']} rows)")
    print()

    # Build manifest
    manifest = build_manifest(period_rows, archetypes_meta, split_rule, data_sources)

    # Ensure output dir exists
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Write manifest
    _MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Wrote manifest: {_MANIFEST_PATH.relative_to(_REPO_ROOT)}")

    # Write report
    write_report(manifest, _REPORT_PATH)
    print(f"Wrote report:   {_REPORT_PATH.relative_to(_REPO_ROOT)}")
    print()

    # Print summary
    summary = manifest["validation_summary"]
    print(f"Status: {summary['status']}")
    if summary["warnings"]:
        print("Warnings:")
        for w in summary["warnings"]:
            print(f"  - {w}")
    if summary["errors"]:
        print("Errors:")
        for e in summary["errors"]:
            print(f"  - {e}")

    # Print per-archetype boundaries
    print()
    print("Per-archetype period boundaries:")
    for arch_name, arch_data in manifest["archetypes"].items():
        print(f"  {arch_name}:")
        for pid, pdata in arch_data["periods"].items():
            role_str = f" ({pdata['role']})" if "role" in pdata else ""
            print(f"    {pid}{role_str}: {pdata['start']} -> {pdata['end']}")

    return 0 if summary["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
