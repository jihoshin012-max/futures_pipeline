"""Tests for stages/03-hypothesis/autoresearch/driver.py

Tests use tmp_path for all file I/O. Subprocess is mocked.
"""
import json
import shutil
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add autoresearch dir to path so driver can be imported directly
_AUTORESEARCH03 = Path(__file__).resolve().parents[1] / "stages/03-hypothesis/autoresearch"
if str(_AUTORESEARCH03) not in sys.path:
    sys.path.insert(0, str(_AUTORESEARCH03))

# Need to import with alias to avoid collision with Stage 04 driver in test_driver.py
import importlib.util
_spec = importlib.util.spec_from_file_location(
    "stage03_driver",
    str(_AUTORESEARCH03 / "driver.py"),
)
stage03_driver = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(stage03_driver)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SEEDED_CONFIG = {
    "version": "v1",
    "instrument": "NQ",
    "touches_csv": "stages/01-data/data/touches/ZRA_Hist_P1.csv",
    "bar_data": "stages/01-data/data/bar_data/volume/NQ_BarData_250vol_P1.txt",
    "scoring_model_path": "shared/scoring_models/zone_touch_v1.json",
    "archetype": {
        "name": "zone_touch",
        "simulator_module": "zone_touch_simulator",
        "scoring_adapter": "BinnedScoringAdapter",
    },
    "active_modes": ["M1"],
    "routing": {"score_threshold": 0, "seq_limit": 3},
    "M1": {
        "stop_ticks": 174,
        "leg_targets": [60, 81, 249],
        "trail_steps": [
            {"trigger_ticks": 76, "new_stop_ticks": 37},
            {"trigger_ticks": 91, "new_stop_ticks": 47},
            {"trigger_ticks": 109, "new_stop_ticks": 47},
            {"trigger_ticks": 220, "new_stop_ticks": 94},
        ],
        "time_cap_bars": 85,
    },
}

PROGRAM_MD_CONTENT = (
    "# Stage 03 Hypothesis Generation — Program\n"
    "METRIC: pf\n"
    "KEEP RULE: 0.1\n"
    "BUDGET: 200\n"
)

SEEDED_TSV_ROW = (
    "abc1234\t03-hypothesis\t2026-01-01T00:00:00\tzone_touch\tzone_touch\tv1\t"
    "\t1.2\t\t50\t\t\t\t\t0\tseeded\t\t500.0\t\t\t0.55\t\t\t\t"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_autoresearch_dir(tmp_path: Path) -> tuple:
    """Return (autoresearch_dir, repo_root) with baseline files in place."""
    auto_dir = tmp_path / "autoresearch"
    auto_dir.mkdir()
    (auto_dir / "current_best").mkdir()

    repo_root = tmp_path
    audit_dir = repo_root / "audit"
    audit_dir.mkdir()
    (audit_dir / "audit_log.md").write_text("# Audit Log\n", encoding="utf-8")

    # Seed current_best/hypothesis_config.json
    config_path = auto_dir / "current_best" / "hypothesis_config.json"
    config_path.write_text(json.dumps(SEEDED_CONFIG, indent=2), encoding="utf-8")

    # Write program.md
    (auto_dir / "program.md").write_text(PROGRAM_MD_CONTENT, encoding="utf-8")

    # Seed results.tsv with header + seeded row
    tsv = auto_dir / "results.tsv"
    tsv.write_text(stage03_driver.TSV_HEADER + "\n" + SEEDED_TSV_ROW + "\n", encoding="utf-8")

    # Write period_config.md with replication_gate
    config_dir = repo_root / "_config"
    config_dir.mkdir()
    (config_dir / "period_config.md").write_text(
        "# Period Configuration\n"
        "replication_gate: flag_and_review\n"
        "# P1a = 2025-09-16 to 2025-10-31 | P1b = 2025-11-01 to 2025-12-14\n",
        encoding="utf-8",
    )

    return auto_dir, repo_root


def _write_program_md(auto_dir: Path, metric="pf", keep_rule=0.1, budget=200) -> Path:
    """Write program.md with given fields."""
    program = auto_dir / "program.md"
    program.write_text(
        f"# Stage 03 Hypothesis Generation\n"
        f"METRIC: {metric}\n"
        f"KEEP RULE: {keep_rule}\n"
        f"BUDGET: {budget}\n",
        encoding="utf-8",
    )
    return program


def _make_result_json(path: Path, pf: float = 1.5, n_trades: int = 50) -> None:
    """Write a result.json to the given path."""
    path.write_text(
        json.dumps({
            "pf": pf,
            "n_trades": n_trades,
            "win_rate": 0.55,
            "total_pnl_ticks": 400.0,
            "max_drawdown_ticks": 200.0,
        }),
        encoding="utf-8",
    )


def _make_mock_subprocess(
    auto_dir: Path,
    p1_pf: float = 1.5, p1_trades: int = 50,
    p1b_pf: float = 1.2, p1b_trades: int = 20,
    fail_on_call: int = None,
):
    """Build a mock subprocess.run that writes result.json and result_p1b.json."""
    result_json = auto_dir / "result.json"
    result_p1b_json = auto_dir / "result_p1b.json"
    call_count = [0]

    def _mock_run(args, **kwargs):
        call_count[0] += 1
        m = MagicMock()
        if args and args[0] == "git":
            m.returncode = 0
            m.stdout = ""
            m.stderr = ""
            return m
        # Engine call (hypothesis_generator.py subprocess)
        if fail_on_call is not None and call_count[0] == fail_on_call:
            m.returncode = 1
            m.stderr = "Simulated engine failure"
            return m
        _make_result_json(result_json, pf=p1_pf, n_trades=p1_trades)
        _make_result_json(result_p1b_json, pf=p1b_pf, n_trades=p1b_trades)
        m.returncode = 0
        m.stderr = ""
        return m

    return _mock_run, call_count


# ---------------------------------------------------------------------------
# test_parse_program_md
# ---------------------------------------------------------------------------

def test_parse_program_md(tmp_path):
    """parse_program_md returns correct metric, keep_rule, budget for Stage 03 program.md."""
    auto_dir = tmp_path / "autoresearch"
    auto_dir.mkdir()
    program = _write_program_md(auto_dir, metric="pf", keep_rule=0.1, budget=200)
    result = stage03_driver.parse_program_md(program)
    assert result["metric"] == "pf", f"Expected metric='pf', got {result['metric']!r}"
    assert result["keep_rule"] == 0.1, f"Expected keep_rule=0.1, got {result['keep_rule']}"
    assert result["budget"] == 200, f"Expected budget=200, got {result['budget']}"


# ---------------------------------------------------------------------------
# TestBudgetEnforcement
# ---------------------------------------------------------------------------

class TestBudgetEnforcement:
    def test_stops_when_budget_reached(self, tmp_path):
        """Driver stops immediately when n_prior_tests >= budget.

        Pre-populate 3 rows with budget=3 -> loop exits without running any experiments.
        """
        auto_dir, repo_root = _make_autoresearch_dir(tmp_path)
        # budget=3, add 2 more rows so total = 3 (seeded + 2 = 3)
        extra_row = SEEDED_TSV_ROW.replace("0\tseeded", "1\tkept")
        extra_row2 = SEEDED_TSV_ROW.replace("0\tseeded", "2\tkept")
        tsv = auto_dir / "results.tsv"
        tsv.write_text(
            stage03_driver.TSV_HEADER + "\n" + SEEDED_TSV_ROW + "\n"
            + extra_row + "\n" + extra_row2 + "\n",
            encoding="utf-8",
        )
        _write_program_md(auto_dir, budget=3)

        mock_run, call_count = _make_mock_subprocess(auto_dir)

        with patch.object(stage03_driver, "subprocess") as mock_subproc:
            mock_subproc.run.side_effect = mock_run
            stage03_driver.run_loop(auto_dir, repo_root, max_iterations=100)

        # Engine should NOT have been called (loop exited immediately)
        engine_calls = [
            c for c in mock_subproc.run.call_args_list
            if c[0][0] and c[0][0][0] != "git"
        ]
        assert len(engine_calls) == 0, (
            f"Expected 0 engine calls when budget already reached, got {len(engine_calls)}"
        )

    def test_runs_exactly_budget_experiments_from_zero(self, tmp_path):
        """Driver runs exactly budget experiments when starting from seeded row.

        seeded row counts as 1. budget=3 -> 2 new experiments run (total 3 rows).
        """
        auto_dir, repo_root = _make_autoresearch_dir(tmp_path)
        _write_program_md(auto_dir, budget=3)

        mock_run, call_count = _make_mock_subprocess(auto_dir, p1_pf=1.0, p1b_pf=1.1, p1b_trades=10)

        with patch.object(stage03_driver, "subprocess") as mock_subproc:
            mock_subproc.run.side_effect = mock_run
            stage03_driver.run_loop(auto_dir, repo_root, max_iterations=100)

        tsv_lines = [
            l for l in (auto_dir / "results.tsv").read_text(encoding="utf-8").splitlines()
            if l.strip()
        ]
        # header + seeded + 2 experiments = 4 lines
        assert len(tsv_lines) == 4, (
            f"Expected 4 lines (header+seeded+2 exps), got {len(tsv_lines)}"
        )


# ---------------------------------------------------------------------------
# TestReplicationEnforcement
# ---------------------------------------------------------------------------

class TestReplicationEnforcement:
    def test_p1b_fail_reverts(self, tmp_path):
        """P1 passes (PF > baseline + keep_rule) but P1b PF < 1.0 -> reverted with
        verdict='p1b_replication_fail' when replication_gate='hard_block'."""
        auto_dir, repo_root = _make_autoresearch_dir(tmp_path)
        # Override replication_gate to hard_block
        (repo_root / "_config" / "period_config.md").write_text(
            "replication_gate: hard_block\n"
            "# P1a = 2025-09-16 to 2025-10-31 | P1b = 2025-11-01 to 2025-12-14\n",
            encoding="utf-8",
        )
        _write_program_md(auto_dir, budget=2, keep_rule=0.1)

        # P1 passes: pf=1.5 > 1.2 + 0.1. P1b fails: pf=0.8 < 1.0
        mock_run, _ = _make_mock_subprocess(
            auto_dir, p1_pf=1.5, p1_trades=50, p1b_pf=0.8, p1b_trades=15
        )

        with patch.object(stage03_driver, "subprocess") as mock_subproc:
            mock_subproc.run.side_effect = mock_run
            stage03_driver.run_loop(auto_dir, repo_root, max_iterations=1)

        tsv_lines = [
            l for l in (auto_dir / "results.tsv").read_text(encoding="utf-8").splitlines()
            if l.strip()
        ]
        # Get last experiment row
        last_row = tsv_lines[-1].split("\t")
        header = stage03_driver.TSV_HEADER.split("\t")
        verdict_idx = header.index("verdict")
        verdict = last_row[verdict_idx]
        assert verdict == "p1b_replication_fail", (
            f"Expected verdict='p1b_replication_fail', got {verdict!r}"
        )

        # current_best should NOT have been updated (reverted)
        current_best = json.loads(
            (auto_dir / "current_best" / "hypothesis_config.json").read_text(encoding="utf-8")
        )
        assert current_best == SEEDED_CONFIG, "current_best should be unchanged after p1b fail"

    def test_p1b_pass_keeps(self, tmp_path):
        """P1 passes and P1b PF > 1.0 with n_trades >= 10 -> kept with replication_pass=True."""
        auto_dir, repo_root = _make_autoresearch_dir(tmp_path)
        _write_program_md(auto_dir, budget=2, keep_rule=0.1)

        # P1 passes: pf=1.5. P1b passes: pf=1.2 > 1.0, n_trades=15 >= 10
        mock_run, _ = _make_mock_subprocess(
            auto_dir, p1_pf=1.5, p1_trades=50, p1b_pf=1.2, p1b_trades=15
        )

        with patch.object(stage03_driver, "subprocess") as mock_subproc:
            mock_subproc.run.side_effect = mock_run
            stage03_driver.run_loop(auto_dir, repo_root, max_iterations=1)

        tsv_lines = [
            l for l in (auto_dir / "results.tsv").read_text(encoding="utf-8").splitlines()
            if l.strip()
        ]
        last_row = tsv_lines[-1].split("\t")
        header = stage03_driver.TSV_HEADER.split("\t")
        verdict_idx = header.index("verdict")
        replication_pass_idx = header.index("replication_pass")

        verdict = last_row[verdict_idx]
        replication_pass = last_row[replication_pass_idx]

        assert verdict == "kept", f"Expected verdict='kept', got {verdict!r}"
        assert replication_pass == "True", (
            f"Expected replication_pass='True', got {replication_pass!r}"
        )

    def test_weak_replication_flagged(self, tmp_path):
        """P1 passes, P1b fails, replication_gate='flag_and_review' ->
        verdict='kept_weak_replication', replication_pass=False in TSV."""
        auto_dir, repo_root = _make_autoresearch_dir(tmp_path)
        # flag_and_review is the default in _make_autoresearch_dir
        _write_program_md(auto_dir, budget=2, keep_rule=0.1)

        # P1 passes: pf=1.5. P1b fails: pf=0.8 < 1.0
        mock_run, _ = _make_mock_subprocess(
            auto_dir, p1_pf=1.5, p1_trades=50, p1b_pf=0.8, p1b_trades=15
        )

        with patch.object(stage03_driver, "subprocess") as mock_subproc:
            mock_subproc.run.side_effect = mock_run
            stage03_driver.run_loop(auto_dir, repo_root, max_iterations=1)

        tsv_lines = [
            l for l in (auto_dir / "results.tsv").read_text(encoding="utf-8").splitlines()
            if l.strip()
        ]
        last_row = tsv_lines[-1].split("\t")
        header = stage03_driver.TSV_HEADER.split("\t")
        verdict_idx = header.index("verdict")
        replication_pass_idx = header.index("replication_pass")

        verdict = last_row[verdict_idx]
        replication_pass = last_row[replication_pass_idx]

        assert verdict == "kept_weak_replication", (
            f"Expected verdict='kept_weak_replication', got {verdict!r}"
        )
        assert replication_pass == "False", (
            f"Expected replication_pass='False', got {replication_pass!r}"
        )

    def test_p1_fail_skips_p1b(self, tmp_path):
        """P1 fails keep rule -> reverted immediately, replication_pass='' (not checked)."""
        auto_dir, repo_root = _make_autoresearch_dir(tmp_path)
        _write_program_md(auto_dir, budget=2, keep_rule=0.1)

        # P1 fails: pf=1.0 < 1.2 + 0.1 = 1.3
        mock_run, call_count = _make_mock_subprocess(
            auto_dir, p1_pf=1.0, p1_trades=50, p1b_pf=1.5, p1b_trades=20
        )

        with patch.object(stage03_driver, "subprocess") as mock_subproc:
            mock_subproc.run.side_effect = mock_run
            stage03_driver.run_loop(auto_dir, repo_root, max_iterations=1)

        tsv_lines = [
            l for l in (auto_dir / "results.tsv").read_text(encoding="utf-8").splitlines()
            if l.strip()
        ]
        last_row = tsv_lines[-1].split("\t")
        header = stage03_driver.TSV_HEADER.split("\t")
        verdict_idx = header.index("verdict")
        replication_pass_idx = header.index("replication_pass")

        verdict = last_row[verdict_idx]
        replication_pass = last_row[replication_pass_idx]

        assert verdict == "reverted", f"Expected verdict='reverted', got {verdict!r}"
        assert replication_pass == "", (
            f"Expected replication_pass='' (not checked), got {replication_pass!r}"
        )


# ---------------------------------------------------------------------------
# TestTsvLayout
# ---------------------------------------------------------------------------

class TestTsvLayout:
    def test_25_columns_with_replication_pass(self, tmp_path):
        """results.tsv has 25 columns with replication_pass as column 25 (index 24)."""
        auto_dir, repo_root = _make_autoresearch_dir(tmp_path)
        _write_program_md(auto_dir, budget=2, keep_rule=0.1)

        # P1 passes, P1b passes
        mock_run, _ = _make_mock_subprocess(
            auto_dir, p1_pf=1.5, p1_trades=50, p1b_pf=1.2, p1b_trades=15
        )

        with patch.object(stage03_driver, "subprocess") as mock_subproc:
            mock_subproc.run.side_effect = mock_run
            stage03_driver.run_loop(auto_dir, repo_root, max_iterations=1)

        tsv_text = (auto_dir / "results.tsv").read_text(encoding="utf-8")
        lines = [l for l in tsv_text.splitlines() if l.strip()]
        assert len(lines) >= 3, "Expected at least header + seeded + 1 experiment row"

        header_cols = lines[0].split("\t")
        exp_row_cols = lines[-1].split("\t")

        assert len(header_cols) == 25, (
            f"Header should have 25 cols, got {len(header_cols)}: {header_cols}"
        )
        assert len(exp_row_cols) == 25, (
            f"Experiment row should have 25 cols, got {len(exp_row_cols)}: {exp_row_cols}"
        )
        assert header_cols[24] == "replication_pass", (
            f"Column 25 (index 24) should be 'replication_pass', got {header_cols[24]!r}"
        )
        assert header_cols.index("replication_pass") == 24, (
            "replication_pass should be the last (25th) column"
        )
