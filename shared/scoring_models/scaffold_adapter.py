#!/usr/bin/env python3
# archetype: shared
"""Scaffold generator for scoring adapters.

Run manually after registering a new archetype in strategy_archetypes.md
with a scoring_adapter value that is not one of the three built-in adapters.

Usage:
    python shared/scoring_models/scaffold_adapter.py
"""

import os
import re
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ARCHETYPES_MD = REPO_ROOT / "stages/03-hypothesis/references/strategy_archetypes.md"
ADAPTER_PY = REPO_ROOT / "shared/scoring_models/scoring_adapter.py"
AUDIT_LOG = REPO_ROOT / "audit/audit_log.md"

REGISTERED_ADAPTERS = {"BinnedScoringAdapter", "SklearnScoringAdapter", "ONNXScoringAdapter"}

ROTATION_KEYWORDS = re.compile(
    r"\b(rotat|rank|cross[- ]?instrument|relative[- ]?strength|sector[- ]?momentum)\b",
    re.IGNORECASE,
)


def parse_archetypes(path: Path) -> list[dict]:
    """Parse strategy_archetypes.md and return archetype entries."""
    text = path.read_text(encoding="utf-8")
    archetypes = []
    current: dict | None = None

    for line in text.splitlines():
        # Section header = archetype name (skip template and contract sections)
        if line.startswith("## ") and not line.startswith("## ["):
            if "Simulator Interface Contract" in line:
                break
            if current:
                archetypes.append(current)
            name = line.removeprefix("## ").strip()
            current = {"name": name, "fields": {}, "description": ""}
        elif current and line.startswith("- "):
            match = re.match(r"^- ([^:]+):\s*(.+)$", line)
            if match:
                key = match.group(1).strip().lower().replace(" ", "_")
                val = match.group(2).strip()
                current["fields"][key] = val
                if key == "description":
                    current["description"] = val

    if current:
        archetypes.append(current)
    return archetypes


def needs_scaffold(archetype: dict) -> bool:
    """True if archetype has a scoring_adapter not in the registered set."""
    adapter = archetype["fields"].get("scoring_adapter", "")
    return adapter != "" and adapter not in REGISTERED_ADAPTERS


def make_class_name(archetype_name: str) -> str:
    """Convert archetype name to PascalCase + ScoringAdapter suffix."""
    parts = re.split(r"[\s_-]+", archetype_name)
    pascal = "".join(p.capitalize() for p in parts if p)
    return f"{pascal}ScoringAdapter"


def adapter_stub(archetype: dict) -> str:
    """Generate a stub class for the archetype."""
    cls_name = make_class_name(archetype["name"])
    arch_name = archetype["name"]
    description = archetype.get("description", arch_name)

    rotation_warning = ""
    if ROTATION_KEYWORDS.search(description):
        rotation_warning = (
            "    # WARNING: This archetype appears to be rotation-based.\n"
            "    # A RankingAdapter ranks across instruments rather than scoring\n"
            "    # individual signal rows. This also requires a new simulator and\n"
            "    # a new dispatch path in backtest_engine.py, not just this adapter.\n"
        )

    return (
        f"\n\nclass {cls_name}:\n"
        f'    """Scoring adapter for archetype: {arch_name}.\n'
        f"\n"
        f"    {description}\n"
        f'    """\n'
        f"\n"
        f"{rotation_warning}"
        f"    def __init__(self, model_path: str) -> None:\n"
        f"        self.model_path = model_path\n"
        f"\n"
        f'    def score(self, df: pd.DataFrame) -> "pd.Series[float]":\n'
        f"        # TODO: Implement scoring logic for {arch_name}\n"
        f'        raise NotImplementedError(\n'
        f'            "Implement score() for {arch_name} before Stage 04"\n'
        f"        )\n"
    )


def class_exists(adapter_text: str, cls_name: str) -> bool:
    """Check if a class is already defined in the adapter file."""
    return f"class {cls_name}" in adapter_text


def create_adapter_test(archetype_name: str, cls_name: str) -> Path:
    """Create a minimal test for the adapter stub."""
    slug = re.sub(r"[\s-]+", "_", archetype_name).lower()
    test_dir = REPO_ROOT / f"shared/archetypes/{slug}"
    test_dir.mkdir(parents=True, exist_ok=True)
    test_path = test_dir / "adapter_test.py"

    test_code = (
        f'"""Adapter test for {archetype_name}.\n'
        f"\n"
        f"Stage 04 driver refuses to run until this test passes.\n"
        f'Run: python -m pytest {test_path.relative_to(REPO_ROOT)}\n'
        f'"""\n'
        f"\n"
        f"import pandas as pd\n"
        f"import pytest\n"
        f"import sys\n"
        f"from pathlib import Path\n"
        f"\n"
        f"sys.path.insert(0, str(Path(__file__).resolve().parents[2]))\n"
        f"from scoring_models.scoring_adapter import {cls_name}\n"
        f"\n"
        f"\n"
        f"def test_score_returns_series_of_correct_length():\n"
        f'    adapter = {cls_name}(model_path="dummy.json")\n'
        f"    df = pd.DataFrame({{\n"
        f'        "feature_a": [0.1, 0.2, 0.3, 0.4, 0.5],\n'
        f'        "feature_b": [1.0, 2.0, 3.0, 4.0, 5.0],\n'
        f"    }})\n"
        f"    result = adapter.score(df)\n"
        f"    assert isinstance(result, pd.Series)\n"
        f"    assert len(result) == len(df)\n"
        f"    assert result.dtype == float\n"
        f"\n"
        f"\n"
        f"def test_score_raises_not_implemented_before_phase4():\n"
        f'    adapter = {cls_name}(model_path="dummy.json")\n'
        f"    df = pd.DataFrame({{\n"
        f'        "feature_a": [0.1, 0.2, 0.3, 0.4, 0.5],\n'
        f"    }})\n"
        f"    with pytest.raises(NotImplementedError):\n"
        f"        adapter.score(df)\n"
    )
    test_path.write_text(test_code, encoding="utf-8")
    return test_path


def append_audit_entry(archetype_name: str) -> None:
    """Append a MANUAL_NOTE to audit_log.md."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = (
        f"\n## {timestamp} | MANUAL_NOTE\n"
        f"- subject: Adapter stub generated for {archetype_name}\n"
        f"- detail: Adapter stub generated for {archetype_name} — "
        f"implement score() before Stage 04\n"
        f"- human: scaffold_adapter.py\n"
    )
    with open(AUDIT_LOG, "a", encoding="utf-8") as f:
        f.write(entry)


def main() -> int:
    if not ARCHETYPES_MD.exists():
        print(f"ERROR: {ARCHETYPES_MD} not found", file=sys.stderr)
        return 1
    if not ADAPTER_PY.exists():
        print(f"ERROR: {ADAPTER_PY} not found", file=sys.stderr)
        return 1

    archetypes = parse_archetypes(ARCHETYPES_MD)
    to_scaffold = [a for a in archetypes if needs_scaffold(a)]

    if not to_scaffold:
        print("No unregistered adapters found in strategy_archetypes.md")
        return 0

    adapter_text = ADAPTER_PY.read_text(encoding="utf-8")
    generated = 0

    for arch in to_scaffold:
        cls_name = make_class_name(arch["name"])

        if class_exists(adapter_text, cls_name):
            print(f"SKIP: {cls_name} already exists in scoring_adapter.py")
            continue

        # Append stub to scoring_adapter.py
        stub = adapter_stub(arch)
        adapter_text += stub
        print(f"ADDED: {cls_name} to scoring_adapter.py")

        # Create test file
        test_path = create_adapter_test(arch["name"], cls_name)
        print(f"CREATED: {test_path.relative_to(REPO_ROOT)}")

        # Audit entry
        append_audit_entry(arch["name"])
        print(f"AUDIT: entry written for {arch['name']}")

        generated += 1

    if generated > 0:
        ADAPTER_PY.write_text(adapter_text, encoding="utf-8")
        print(f"\nDone: {generated} adapter stub(s) generated")

    return 0


if __name__ == "__main__":
    sys.exit(main())
