"""Tests for stages/02-features/autoresearch/driver.py

Tests use tmp_path for all file I/O. evaluate_features.py subprocess is mocked.
Tests verify: budget enforcement, keep/revert file operations, entry-time violation
detection, program.md parsing, and TSV row structure.
"""
import json
import shutil
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add repo root so stage02 driver can be imported
_REPO_ROOT = Path(__file__).resolve().parents[1]
_AUTORESEARCH_02 = _REPO_ROOT / "stages/02-features/autoresearch"
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Import the driver under test using importlib to avoid module name collision with
# stages/04-backtest/autoresearch/driver.py (both are named "driver")
import importlib.util

_DRIVER_PATH = _AUTORESEARCH_02 / "driver.py"


def _load_driver():
    """Load stages/02-features/autoresearch/driver.py as 'stage02_driver' module."""
    spec = importlib.util.spec_from_file_location("stage02_driver", str(_DRIVER_PATH))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# Shared fixture helpers
# ---------------------------------------------------------------------------

TSV_HEADER = (
    "run_id\tstage\ttimestamp\thypothesis_name\tarchetype\tversion\tfeatures"
    "\tpf_p1\tpf_p2\ttrades_p1\ttrades_p2\tmwu_p\tperm_p\tpctile\tn_prior_tests"
    "\tverdict\tsharpe_p1\tmax_dd_ticks\tavg_winner_ticks\tdd_multiple\twin_rate"
    "\tregime_breakdown\tapi_cost_usd\tnotes"
)

FEATURE_ENGINE_CONTENT = """# archetype: zone_touch
def compute_features(bar_df, touch_row) -> dict:
    zone_width = (touch_row['ZoneTop'] - touch_row['ZoneBot']) / 0.25
    return {'zone_width': float(zone_width)}
"""

FEATURE_ENGINE_CURRENT_BEST_CONTENT = """# archetype: zone_touch
# current_best version
def compute_features(bar_df, touch_row) -> dict:
    return {'zone_width': 2.5}
"""


def _make_autoresearch_dir(tmp_path: Path, n_tsv_rows: int = 1) -> tuple[Path, Path, Path]:
    """Return (autoresearch_dir, repo_root, feature_engine_path) with baseline files.

    Sets up:
      - autoresearch/ with current_best/ subdirectory
      - shared/archetypes/zone_touch/feature_engine.py (the working copy)
      - current_best/feature_engine.py (the baseline copy)
      - results.tsv with n_tsv_rows data rows (plus header)
      - audit/audit_log.md
    """
    auto_dir = tmp_path / "autoresearch"
    auto_dir.mkdir()
    (auto_dir / "current_best").mkdir()

    repo_root = tmp_path

    # audit log
    audit_dir = repo_root / "audit"
    audit_dir.mkdir()
    (audit_dir / "audit_log.md").write_text("# Audit Log\n", encoding="utf-8")

    # feature_engine.py in shared/archetypes/zone_touch/
    archetype_dir = tmp_path / "shared" / "archetypes" / "zone_touch"
    archetype_dir.mkdir(parents=True)
    feature_engine_path = archetype_dir / "feature_engine.py"
    feature_engine_path.write_text(FEATURE_ENGINE_CONTENT, encoding="utf-8")

    # current_best/feature_engine.py (baseline)
    current_best_fe = auto_dir / "current_best" / "feature_engine.py"
    current_best_fe.write_text(FEATURE_ENGINE_CURRENT_BEST_CONTENT, encoding="utf-8")

    # results.tsv
    tsv = auto_dir / "results.tsv"
    rows = [TSV_HEADER]
    for i in range(n_tsv_rows):
        row = (
            f"abc{i:04d}\t02-features\t2026-01-01T00:0{i}:00\t\tzone_touch\t\t"
            f"zone_width\t0.5\t\t100\t100\t0.05\t\t\t{i}\tseeded\t\t\t\t\t\t\t\t"
        )
        rows.append(row)
    tsv.write_text("\n".join(rows) + "\n", encoding="utf-8")

    return auto_dir, repo_root, feature_engine_path


def _write_program_md(
    auto_dir: Path,
    metric: str = "spread",
    keep_rule: float = 0.15,
    budget: int = 5,
    new_feature: str = "zone_width",
) -> Path:
    program = auto_dir / "program.md"
    program.write_text(
        f"# Stage 02 Feature Autoresearch\n"
        f"EDIT: shared/archetypes/zone_touch/feature_engine.py only.\n"
        f"METRIC: {metric}\n"
        f"KEEP RULE: {keep_rule}\n"
        f"BUDGET: {budget}\n"
        f"NEW_FEATURE: {new_feature}\n"
        f"\n## Current search direction\nTest zone_width feature.\n",
        encoding="utf-8",
    )
    return program


def _make_feature_evaluation_json(
    auto_dir: Path,
    feature_name: str = "zone_width",
    spread: float = 0.5,
    mwu_p: float = 0.05,
    kept: bool = True,
    entry_time_violation: bool = False,
) -> Path:
    """Write a feature_evaluation.json simulating dispatcher output."""
    output = {
        "timestamp": "2026-01-01T00:00:00Z",
        "features_evaluated": [
            {
                "name": feature_name,
                "spread": spread,
                "mwu_p": mwu_p,
                "kept": kept,
                "entry_time_violation": entry_time_violation,
            }
        ],
    }
    path = auto_dir / "feature_evaluation.json"
    path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    return path


def _mock_subprocess_success(auto_dir: Path, spread=0.5, mwu_p=0.05, entry_time_violation=False):
    """Return a mock subprocess.run that writes feature_evaluation.json on engine calls."""
    def _mock(args, **kwargs):
        m = MagicMock()
        if args[0] == "git":
            m.returncode = 0
            m.stdout = ""
            m.stderr = ""
        else:
            # evaluate_features.py call — determine output path from args
            output_path = auto_dir / "feature_evaluation.json"
            for i, arg in enumerate(args):
                if arg == "--output" and i + 1 < len(args):
                    output_path = Path(args[i + 1])
                    break
            feature_name = "zone_width"
            for i, arg in enumerate(args):
                if arg == "--archetype" and i + 1 < len(args):
                    pass  # archetype known, not needed for mock
            _make_feature_evaluation_json(
                output_path.parent,
                feature_name=feature_name,
                spread=spread,
                mwu_p=mwu_p,
                kept=(spread > 0.15 and mwu_p < 0.10 and not entry_time_violation),
                entry_time_violation=entry_time_violation,
            )
            # Ensure file is at exact output_path location
            correct_path = output_path
            tmp_path = output_path.parent / "feature_evaluation.json"
            if correct_path != tmp_path and tmp_path.exists():
                shutil.copy2(str(tmp_path), str(correct_path))
            m.returncode = 0
            m.stderr = ""
        return m
    return _mock


# ---------------------------------------------------------------------------
# TestBudgetEnforcement
# ---------------------------------------------------------------------------

class TestBudgetEnforcement:

    def test_stops_at_budget(self, tmp_path):
        """With budget=3 and 3 existing TSV rows, driver runs no new experiments."""
        driver = _load_driver()
        auto_dir, repo_root, _ = _make_autoresearch_dir(tmp_path, n_tsv_rows=3)
        _write_program_md(auto_dir, budget=3)

        engine_call_count = [0]

        def _mock(args, **kwargs):
            m = MagicMock()
            if args[0] == "git":
                m.returncode = 0
                m.stdout = ""
                m.stderr = ""
            else:
                engine_call_count[0] += 1
                _make_feature_evaluation_json(auto_dir)
                m.returncode = 0
                m.stderr = ""
            return m

        with patch.object(driver, "subprocess") as mock_subproc:
            mock_subproc.run.side_effect = _mock
            driver.run_loop(auto_dir, repo_root, archetype="zone_touch", max_iterations=100)

        assert engine_call_count[0] == 0, (
            f"Expected 0 engine calls (budget exhausted), got {engine_call_count[0]}"
        )

    def test_runs_under_budget(self, tmp_path):
        """With budget=5 and 2 existing TSV rows, driver runs experiments."""
        driver = _load_driver()
        auto_dir, repo_root, _ = _make_autoresearch_dir(tmp_path, n_tsv_rows=2)
        _write_program_md(auto_dir, budget=5)

        engine_call_count = [0]

        def _mock(args, **kwargs):
            m = MagicMock()
            if args[0] == "git":
                m.returncode = 0
                m.stdout = ""
                m.stderr = ""
            else:
                engine_call_count[0] += 1
                output_path = auto_dir / "feature_evaluation.json"
                for i, arg in enumerate(args):
                    if arg == "--output" and i + 1 < len(args):
                        output_path = Path(args[i + 1])
                        break
                _make_feature_evaluation_json(output_path.parent)
                if output_path != output_path.parent / "feature_evaluation.json":
                    src = output_path.parent / "feature_evaluation.json"
                    if src.exists() and src != output_path:
                        shutil.copy2(str(src), str(output_path))
                m.returncode = 0
                m.stderr = ""
            return m

        with patch.object(driver, "subprocess") as mock_subproc:
            mock_subproc.run.side_effect = _mock
            driver.run_loop(auto_dir, repo_root, archetype="zone_touch", max_iterations=2)

        assert engine_call_count[0] > 0, "Expected engine calls when under budget"

    def test_budget_read_from_program_md(self, tmp_path):
        """Driver re-reads program.md each iteration — lowering budget mid-run stops it."""
        driver = _load_driver()
        auto_dir, repo_root, _ = _make_autoresearch_dir(tmp_path, n_tsv_rows=1)
        _write_program_md(auto_dir, budget=10)

        engine_call_count = [0]

        def _mock(args, **kwargs):
            m = MagicMock()
            if args[0] == "git":
                m.returncode = 0
                m.stdout = ""
                m.stderr = ""
            else:
                engine_call_count[0] += 1
                if engine_call_count[0] == 2:
                    # After 2nd experiment, lower budget — should stop
                    _write_program_md(auto_dir, budget=2)
                output_path = auto_dir / "feature_evaluation.json"
                for i, arg in enumerate(args):
                    if arg == "--output" and i + 1 < len(args):
                        output_path = Path(args[i + 1])
                        break
                _make_feature_evaluation_json(output_path.parent)
                if output_path != output_path.parent / "feature_evaluation.json":
                    src = output_path.parent / "feature_evaluation.json"
                    if src.exists() and src != output_path:
                        shutil.copy2(str(src), str(output_path))
                m.returncode = 0
                m.stderr = ""
            return m

        with patch.object(driver, "subprocess") as mock_subproc:
            mock_subproc.run.side_effect = _mock
            driver.run_loop(auto_dir, repo_root, archetype="zone_touch", max_iterations=100)

        # Should have run exactly 2 experiments before budget reduction took effect
        assert engine_call_count[0] == 2, (
            f"Expected 2 engine calls (budget reduced to 2 after 2nd), got {engine_call_count[0]}"
        )


# ---------------------------------------------------------------------------
# TestKeepRevert
# ---------------------------------------------------------------------------

class TestKeepRevert:

    def test_keep_copies_to_current_best(self, tmp_path):
        """On keep (spread > keep_rule AND mwu_p < 0.10), feature_engine.py is copied to current_best/."""
        driver = _load_driver()
        auto_dir, repo_root, feature_engine_path = _make_autoresearch_dir(tmp_path, n_tsv_rows=1)
        _write_program_md(auto_dir, budget=2, keep_rule=0.15, new_feature="zone_width")

        # Write a distinct working feature_engine.py so we can verify copy
        feature_engine_path.write_text("# archetype: zone_touch\n# VERSION: working\n", encoding="utf-8")

        mock_run = _mock_subprocess_success(auto_dir, spread=0.5, mwu_p=0.05)

        with patch.object(driver, "subprocess") as mock_subproc:
            mock_subproc.run.side_effect = mock_run
            driver.run_loop(auto_dir, repo_root, archetype="zone_touch", max_iterations=1)

        current_best_fe = auto_dir / "current_best" / "feature_engine.py"
        assert current_best_fe.exists(), "current_best/feature_engine.py must exist after keep"
        content = current_best_fe.read_text(encoding="utf-8")
        assert "# VERSION: working" in content, (
            f"current_best/feature_engine.py should contain kept version, got: {content!r}"
        )

    def test_revert_restores_from_current_best(self, tmp_path):
        """On revert (spread <= keep_rule), feature_engine.py is restored from current_best/."""
        driver = _load_driver()
        auto_dir, repo_root, feature_engine_path = _make_autoresearch_dir(tmp_path, n_tsv_rows=1)
        _write_program_md(auto_dir, budget=2, keep_rule=0.15, new_feature="zone_width")

        # Distinct working version
        feature_engine_path.write_text("# archetype: zone_touch\n# VERSION: candidate\n", encoding="utf-8")
        # Current best has a known content
        current_best_fe = auto_dir / "current_best" / "feature_engine.py"
        current_best_fe.write_text("# archetype: zone_touch\n# VERSION: prior_best\n", encoding="utf-8")

        # spread too low → revert
        mock_run = _mock_subprocess_success(auto_dir, spread=0.05, mwu_p=0.05)

        with patch.object(driver, "subprocess") as mock_subproc:
            mock_subproc.run.side_effect = mock_run
            driver.run_loop(auto_dir, repo_root, archetype="zone_touch", max_iterations=1)

        content = feature_engine_path.read_text(encoding="utf-8")
        assert "# VERSION: prior_best" in content, (
            f"feature_engine.py should be restored to current_best version, got: {content!r}"
        )

    def test_keep_verdict_in_tsv(self, tmp_path):
        """Kept experiment has verdict='kept' in TSV row."""
        driver = _load_driver()
        auto_dir, repo_root, _ = _make_autoresearch_dir(tmp_path, n_tsv_rows=1)
        _write_program_md(auto_dir, budget=2, keep_rule=0.15, new_feature="zone_width")

        mock_run = _mock_subprocess_success(auto_dir, spread=0.5, mwu_p=0.05)

        with patch.object(driver, "subprocess") as mock_subproc:
            mock_subproc.run.side_effect = mock_run
            driver.run_loop(auto_dir, repo_root, archetype="zone_touch", max_iterations=1)

        lines = (auto_dir / "results.tsv").read_text(encoding="utf-8").splitlines()
        non_empty = [l for l in lines if l.strip()]
        last_row = non_empty[-1]
        cols = last_row.split("\t")
        # verdict is column index 15 (0-based)
        assert cols[15] == "kept", f"Expected verdict 'kept', got {cols[15]!r}"

    def test_revert_verdict_in_tsv(self, tmp_path):
        """Reverted experiment has verdict='reverted' in TSV row."""
        driver = _load_driver()
        auto_dir, repo_root, _ = _make_autoresearch_dir(tmp_path, n_tsv_rows=1)
        _write_program_md(auto_dir, budget=2, keep_rule=0.15, new_feature="zone_width")

        # spread too low → revert
        mock_run = _mock_subprocess_success(auto_dir, spread=0.05, mwu_p=0.05)

        with patch.object(driver, "subprocess") as mock_subproc:
            mock_subproc.run.side_effect = mock_run
            driver.run_loop(auto_dir, repo_root, archetype="zone_touch", max_iterations=1)

        lines = (auto_dir / "results.tsv").read_text(encoding="utf-8").splitlines()
        non_empty = [l for l in lines if l.strip()]
        last_row = non_empty[-1]
        cols = last_row.split("\t")
        assert cols[15] == "reverted", f"Expected verdict 'reverted', got {cols[15]!r}"


# ---------------------------------------------------------------------------
# TestEntryTimeViolation
# ---------------------------------------------------------------------------

class TestEntryTimeViolation:

    def test_violation_blocks_keep(self, tmp_path):
        """entry_time_violation=True in feature dict → verdict='entry_time_violation', no keep."""
        driver = _load_driver()
        auto_dir, repo_root, feature_engine_path = _make_autoresearch_dir(tmp_path, n_tsv_rows=1)
        _write_program_md(auto_dir, budget=2, keep_rule=0.15, new_feature="zone_width")

        # Mark current_best content so we can detect if it changed
        current_best_fe = auto_dir / "current_best" / "feature_engine.py"
        current_best_fe.write_text("# archetype: zone_touch\n# VERSION: prior_best\n", encoding="utf-8")

        # spread > 0.15 AND mwu_p < 0.10 (would keep), but entry_time_violation=True → must not keep
        mock_run = _mock_subprocess_success(
            auto_dir, spread=0.5, mwu_p=0.05, entry_time_violation=True
        )

        with patch.object(driver, "subprocess") as mock_subproc:
            mock_subproc.run.side_effect = mock_run
            driver.run_loop(auto_dir, repo_root, archetype="zone_touch", max_iterations=1)

        # TSV verdict must be 'entry_time_violation'
        lines = (auto_dir / "results.tsv").read_text(encoding="utf-8").splitlines()
        non_empty = [l for l in lines if l.strip()]
        last_row = non_empty[-1]
        cols = last_row.split("\t")
        assert cols[15] == "entry_time_violation", (
            f"Expected verdict 'entry_time_violation', got {cols[15]!r}"
        )

        # current_best must NOT have been updated (no keep should have occurred)
        content = current_best_fe.read_text(encoding="utf-8")
        assert "# VERSION: prior_best" in content, (
            f"current_best/feature_engine.py should NOT be updated on violation, got: {content!r}"
        )


# ---------------------------------------------------------------------------
# parse_program_md tests
# ---------------------------------------------------------------------------

def test_parse_program_md(tmp_path):
    """Parses METRIC, KEEP RULE, BUDGET, NEW_FEATURE from program.md format."""
    driver = _load_driver()
    program = tmp_path / "program.md"
    program.write_text(
        "# Stage 02 Feature Autoresearch\n"
        "METRIC: spread\n"
        "KEEP RULE: 0.15\n"
        "BUDGET: 300\n"
        "NEW_FEATURE: zone_width\n",
        encoding="utf-8",
    )
    result = driver.parse_program_md(program)
    assert result["metric"] == "spread"
    assert result["keep_rule"] == 0.15
    assert result["budget"] == 300
    assert result["new_feature"] == "zone_width"


def test_parse_program_md_missing_field(tmp_path):
    """Raises ValueError when required field missing."""
    driver = _load_driver()
    program = tmp_path / "program.md"
    # Missing NEW_FEATURE
    program.write_text(
        "# Stage 02\nMETRIC: spread\nKEEP RULE: 0.15\nBUDGET: 300\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="new_feature"):
        driver.parse_program_md(program)


def test_parse_program_md_missing_budget(tmp_path):
    """Raises ValueError when BUDGET is missing."""
    driver = _load_driver()
    program = tmp_path / "program.md"
    program.write_text(
        "# Stage 02\nMETRIC: spread\nKEEP RULE: 0.15\nNEW_FEATURE: zone_width\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="budget"):
        driver.parse_program_md(program)


# ---------------------------------------------------------------------------
# TSV structure tests
# ---------------------------------------------------------------------------

def test_tsv_row_has_24_columns(tmp_path):
    """TSV data rows have 24 columns matching the standard header."""
    driver = _load_driver()
    auto_dir, repo_root, _ = _make_autoresearch_dir(tmp_path, n_tsv_rows=1)
    _write_program_md(auto_dir, budget=2)

    mock_run = _mock_subprocess_success(auto_dir, spread=0.5, mwu_p=0.05)

    with patch.object(driver, "subprocess") as mock_subproc:
        mock_subproc.run.side_effect = mock_run
        driver.run_loop(auto_dir, repo_root, archetype="zone_touch", max_iterations=1)

    rows_text = (auto_dir / "results.tsv").read_text(encoding="utf-8")
    lines = [l for l in rows_text.splitlines() if l.strip()]
    header_cols = lines[0].split("\t")
    last_row_cols = lines[-1].split("\t")
    assert len(header_cols) == 24, f"Header should have 24 cols, got {len(header_cols)}"
    assert len(last_row_cols) == 24, f"Row should have 24 cols, got {len(last_row_cols)}"


def test_tsv_stage_column_is_02_features(tmp_path):
    """stage column in TSV row is '02-features'."""
    driver = _load_driver()
    auto_dir, repo_root, _ = _make_autoresearch_dir(tmp_path, n_tsv_rows=1)
    _write_program_md(auto_dir, budget=2)

    mock_run = _mock_subprocess_success(auto_dir, spread=0.5, mwu_p=0.05)

    with patch.object(driver, "subprocess") as mock_subproc:
        mock_subproc.run.side_effect = mock_run
        driver.run_loop(auto_dir, repo_root, archetype="zone_touch", max_iterations=1)

    lines = (auto_dir / "results.tsv").read_text(encoding="utf-8").splitlines()
    non_empty = [l for l in lines if l.strip()]
    last_row = non_empty[-1]
    cols = last_row.split("\t")
    # stage is column index 1
    assert cols[1] == "02-features", f"Expected stage '02-features', got {cols[1]!r}"


def test_tsv_spread_in_pf_p1_column(tmp_path):
    """pf_p1 column (index 7) carries the spread value."""
    driver = _load_driver()
    auto_dir, repo_root, _ = _make_autoresearch_dir(tmp_path, n_tsv_rows=1)
    _write_program_md(auto_dir, budget=2)

    mock_run = _mock_subprocess_success(auto_dir, spread=0.42, mwu_p=0.05)

    with patch.object(driver, "subprocess") as mock_subproc:
        mock_subproc.run.side_effect = mock_run
        driver.run_loop(auto_dir, repo_root, archetype="zone_touch", max_iterations=1)

    lines = (auto_dir / "results.tsv").read_text(encoding="utf-8").splitlines()
    non_empty = [l for l in lines if l.strip()]
    last_row = non_empty[-1]
    cols = last_row.split("\t")
    # pf_p1 is column index 7 — carries spread
    assert float(cols[7]) == pytest.approx(0.42), (
        f"Expected pf_p1 (spread) = 0.42, got {cols[7]!r}"
    )


def test_tsv_mwu_p_column(tmp_path):
    """mwu_p column (index 11) carries the MWU p-value."""
    driver = _load_driver()
    auto_dir, repo_root, _ = _make_autoresearch_dir(tmp_path, n_tsv_rows=1)
    _write_program_md(auto_dir, budget=2)

    mock_run = _mock_subprocess_success(auto_dir, spread=0.5, mwu_p=0.037)

    with patch.object(driver, "subprocess") as mock_subproc:
        mock_subproc.run.side_effect = mock_run
        driver.run_loop(auto_dir, repo_root, archetype="zone_touch", max_iterations=1)

    lines = (auto_dir / "results.tsv").read_text(encoding="utf-8").splitlines()
    non_empty = [l for l in lines if l.strip()]
    last_row = non_empty[-1]
    cols = last_row.split("\t")
    assert float(cols[11]) == pytest.approx(0.037), (
        f"Expected mwu_p = 0.037, got {cols[11]!r}"
    )
