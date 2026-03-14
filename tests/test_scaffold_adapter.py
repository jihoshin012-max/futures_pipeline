"""Integration tests for scaffold_adapter.py — covers all SCAF-27 behaviors.

Tests use tempfile fixtures and monkeypatch module-level constants so no live
repo files (audit_log.md, scoring_adapter.py) are ever mutated.

Run: python -m pytest tests/test_scaffold_adapter.py -v
"""

import sys
import textwrap
from pathlib import Path

import pytest

# Add shared/scoring_models/ to path so we can import scaffold_adapter directly
_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "shared" / "scoring_models"))

import scaffold_adapter as sa  # noqa: E402

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

ARCHETYPE_FIXTURE_CONTENT = textwrap.dedent(
    """\
    # Strategy Archetypes

    ## zone_touch
    - Description: Signal-touch zone strategy for NQ
    - Scoring adapter: ZoneTouchScoringAdapter
    - Current status: hypothesis stage

    ## Simulator Interface Contract
    """
)

ADAPTER_SEED_CONTENT = "import pandas as pd\n"
AUDIT_SEED_CONTENT = "# Audit Log\n"


@pytest.fixture()
def tmp_env(tmp_path, monkeypatch):
    """Create a synthetic repo tree in a temp dir and monkeypatch module constants."""
    # Archetype file
    arch_file = tmp_path / "strategy_archetypes.md"
    arch_file.write_text(ARCHETYPE_FIXTURE_CONTENT, encoding="utf-8")

    # Adapter stub target
    adapter_file = tmp_path / "scoring_adapter.py"
    adapter_file.write_text(ADAPTER_SEED_CONTENT, encoding="utf-8")

    # Audit log
    audit_file = tmp_path / "audit_log.md"
    audit_file.write_text(AUDIT_SEED_CONTENT, encoding="utf-8")

    # Monkeypatch module-level constants
    monkeypatch.setattr(sa, "ARCHETYPES_MD", arch_file)
    monkeypatch.setattr(sa, "ADAPTER_PY", adapter_file)
    monkeypatch.setattr(sa, "AUDIT_LOG", audit_file)
    monkeypatch.setattr(sa, "REPO_ROOT", tmp_path)

    return {
        "tmp_path": tmp_path,
        "arch_file": arch_file,
        "adapter_file": adapter_file,
        "audit_file": audit_file,
    }


# ---------------------------------------------------------------------------
# Test 1: parse_archetypes detects unregistered adapter
# ---------------------------------------------------------------------------


def test_parse_archetypes_detects_unregistered(tmp_env):
    """parse_archetypes returns archetype with correct name/adapter, needs_scaffold=True."""
    arch_file = tmp_env["arch_file"]
    result = sa.parse_archetypes(arch_file)

    assert len(result) == 1
    arch = result[0]
    assert arch["name"] == "zone_touch"
    assert arch["fields"]["scoring_adapter"] == "ZoneTouchScoringAdapter"
    assert sa.needs_scaffold(arch) is True


# ---------------------------------------------------------------------------
# Test 2: stub generation produces syntactically valid class
# ---------------------------------------------------------------------------


def test_stub_generation_produces_valid_class(tmp_env):
    """adapter_stub() produces a class with required structure."""
    arch_file = tmp_env["arch_file"]
    archetypes = sa.parse_archetypes(arch_file)
    stub = sa.adapter_stub(archetypes[0])

    assert "class ZoneTouchScoringAdapter" in stub
    assert "raise NotImplementedError" in stub
    assert "def score(self, df: pd.DataFrame)" in stub


# ---------------------------------------------------------------------------
# Test 3: main() creates adapter_test.py in expected location
# ---------------------------------------------------------------------------


def test_main_creates_adapter_test_file(tmp_env):
    """main() returns 0 and creates adapter_test.py at the expected temp path."""
    tmp_path = tmp_env["tmp_path"]

    rc = sa.main()

    assert rc == 0
    test_file = tmp_path / "shared" / "archetypes" / "zone_touch" / "adapter_test.py"
    assert test_file.exists(), f"Expected adapter_test.py at {test_file}"
    content = test_file.read_text(encoding="utf-8")
    assert "from scoring_models.scoring_adapter import ZoneTouchScoringAdapter" in content


# ---------------------------------------------------------------------------
# Test 4: main() appends MANUAL_NOTE to audit log
# ---------------------------------------------------------------------------


def test_main_appends_audit_entry(tmp_env):
    """main() writes a MANUAL_NOTE entry referencing zone_touch and scaffold_adapter.py."""
    audit_file = tmp_env["audit_file"]

    sa.main()

    content = audit_file.read_text(encoding="utf-8")
    assert "MANUAL_NOTE" in content
    assert "zone_touch" in content
    assert "scaffold_adapter.py" in content


# ---------------------------------------------------------------------------
# Test 5: idempotency — running main() twice does not duplicate the class
# ---------------------------------------------------------------------------


def test_idempotency_skips_existing_class(tmp_env):
    """Running main() twice produces exactly one class definition, not two."""
    adapter_file = tmp_env["adapter_file"]

    sa.main()  # first run — generates stub
    sa.main()  # second run — should skip

    adapter_text = adapter_file.read_text(encoding="utf-8")
    count = adapter_text.count("class ZoneTouchScoringAdapter")
    assert count == 1, f"Expected 1 class definition, found {count}"


# ---------------------------------------------------------------------------
# Test 6: rotation keyword triggers WARNING comment in stub
# ---------------------------------------------------------------------------


def test_rotation_keyword_warning(tmp_env):
    """adapter_stub() includes a rotation WARNING when description contains rotation keyword."""
    arch = {
        "name": "cross_rank",
        "description": "Cross-instrument rotation strategy",
        "fields": {"scoring_adapter": "CrossRankScoringAdapter"},
    }
    stub = sa.adapter_stub(arch)

    assert "WARNING: This archetype appears to be rotation-based" in stub
