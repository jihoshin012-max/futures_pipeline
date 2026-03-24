"""Tests for stages/04-backtest/autoresearch/driver.py

Tests use tmp_path for all file I/O. Engine subprocess is mocked.
"""
import json
import shutil
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add autoresearch dir to path so driver can be imported directly
_AUTORESEARCH = Path(__file__).resolve().parents[1] / "stages/04-backtest/autoresearch"
if str(_AUTORESEARCH) not in sys.path:
    sys.path.insert(0, str(_AUTORESEARCH))

import driver  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SEEDED_CONFIG = {
    "version": "v1",
    "instrument": "NQ",
    "touches_csv": "stages/01-data/data/touches/NQ_ZTE_raw_P1.csv",
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
        "stop_ticks": 135,
        "leg_targets": [50, 120, 240],
        "trail_steps": [
            {"trigger_ticks": 30, "new_stop_ticks": 0},
            {"trigger_ticks": 60, "new_stop_ticks": 20},
            {"trigger_ticks": 120, "new_stop_ticks": 50},
            {"trigger_ticks": 200, "new_stop_ticks": 100},
        ],
        "time_cap_bars": 80,
    },
}

TSV_HEADER = (
    "run_id\tstage\ttimestamp\thypothesis_name\tarchetype\tversion\tfeatures"
    "\tpf_p1\tpf_p2\ttrades_p1\ttrades_p2\tmwu_p\tperm_p\tpctile\tn_prior_tests"
    "\tverdict\tsharpe_p1\tmax_dd_ticks\tavg_winner_ticks\tdd_multiple\twin_rate"
    "\tregime_breakdown\tapi_cost_usd\tnotes"
)


def _make_autoresearch_dir(tmp_path: Path) -> tuple[Path, Path]:
    """Return (autoresearch_dir, repo_root) with baseline files in place."""
    auto_dir = tmp_path / "autoresearch"
    auto_dir.mkdir()
    (auto_dir / "current_best").mkdir()
    # audit dir relative to repo_root
    repo_root = tmp_path
    audit_dir = repo_root / "audit"
    audit_dir.mkdir()
    (audit_dir / "audit_log.md").write_text("# Audit Log\n", encoding="utf-8")

    # Seed current_best/exit_params.json
    exit_params = auto_dir / "current_best" / "exit_params.json"
    exit_params.write_text(json.dumps(SEEDED_CONFIG, indent=2), encoding="utf-8")

    # Seed results.tsv with header + seeded row
    tsv = auto_dir / "results.tsv"
    seeded_row = (
        "abc1234\t04-backtest\t2026-01-01T00:00:00\t\tzone_touch\tv1\t"
        "\t1.2\t\t50\t\t\t\t\t0\tseeded\t\t500.0\t\t\t0.55\t\t\t"
    )
    tsv.write_text(TSV_HEADER + "\n" + seeded_row + "\n", encoding="utf-8")

    return auto_dir, repo_root


def _good_result_json(tmp_path: Path, pf: float = 1.5, n_trades: int = 60) -> Path:
    result = tmp_path / "result.json"
    result.write_text(
        json.dumps(
            {
                "pf": pf,
                "n_trades": n_trades,
                "win_rate": 0.55,
                "total_pnl_ticks": 500.0,
                "max_drawdown_ticks": 200.0,
                "per_mode": {"M1": {"pf": pf, "n_trades": n_trades, "win_rate": 0.55}},
            }
        ),
        encoding="utf-8",
    )
    return result


def _write_program_md(auto_dir: Path, metric="pf", keep_rule=0.05, budget=3) -> Path:
    program = auto_dir / "program.md"
    program.write_text(
        f"# Stage 04 Parameter Optimization\n"
        f"EDIT: exit_params.json only. DO NOT touch backtest_engine.py.\n"
        f"METRIC: {metric}\n"
        f"KEEP RULE: {keep_rule}\n"
        f"BUDGET: {budget}\n"
        f"\n## Current search direction\nRandom perturbation.\n",
        encoding="utf-8",
    )
    return program


# ---------------------------------------------------------------------------
# Unit tests for parse_program_md
# ---------------------------------------------------------------------------

def test_parse_program_md(tmp_path):
    program = tmp_path / "program.md"
    program.write_text(
        "# Stage 04\nMETRIC: pf\nKEEP RULE: 0.05\nBUDGET: 500\n",
        encoding="utf-8",
    )
    result = driver.parse_program_md(program)
    assert result["metric"] == "pf"
    assert result["keep_rule"] == 0.05
    assert result["budget"] == 500


# ---------------------------------------------------------------------------
# Unit tests for validate_trail_steps
# ---------------------------------------------------------------------------

def test_validate_trail_steps_valid():
    steps = [
        {"trigger_ticks": 30, "new_stop_ticks": 0},
        {"trigger_ticks": 60, "new_stop_ticks": 20},
    ]
    assert driver.validate_trail_steps(steps) is True


def test_validate_trail_steps_empty():
    assert driver.validate_trail_steps([]) is True


def test_validate_trail_steps_too_many():
    steps = [{"trigger_ticks": i * 10, "new_stop_ticks": 0} for i in range(1, 8)]
    assert driver.validate_trail_steps(steps) is False


def test_validate_trail_steps_non_monotonic_triggers():
    steps = [
        {"trigger_ticks": 60, "new_stop_ticks": 0},
        {"trigger_ticks": 30, "new_stop_ticks": 0},
    ]
    assert driver.validate_trail_steps(steps) is False


def test_validate_trail_steps_stop_ge_trigger():
    steps = [{"trigger_ticks": 30, "new_stop_ticks": 30}]
    assert driver.validate_trail_steps(steps) is False


def test_validate_trail_steps_decreasing_stops():
    steps = [
        {"trigger_ticks": 30, "new_stop_ticks": 20},
        {"trigger_ticks": 60, "new_stop_ticks": 10},
    ]
    assert driver.validate_trail_steps(steps) is False


def test_validate_trail_steps_negative_first_stop():
    steps = [{"trigger_ticks": 30, "new_stop_ticks": -1}]
    assert driver.validate_trail_steps(steps) is False


# ---------------------------------------------------------------------------
# Unit tests for propose_next_params
# ---------------------------------------------------------------------------

def test_propose_next_params_returns_valid_config(tmp_path):
    auto_dir, _ = _make_autoresearch_dir(tmp_path)
    tsv = auto_dir / "results.tsv"
    proposed = driver.propose_next_params(SEEDED_CONFIG, tsv)
    # FIXED fields must be unchanged
    assert proposed["version"] == SEEDED_CONFIG["version"]
    assert proposed["instrument"] == SEEDED_CONFIG["instrument"]
    assert proposed["archetype"] == SEEDED_CONFIG["archetype"]
    assert proposed["active_modes"] == SEEDED_CONFIG["active_modes"]
    assert proposed["routing"] == SEEDED_CONFIG["routing"]
    # CANDIDATE fields must exist
    assert "M1" in proposed
    assert "stop_ticks" in proposed["M1"]
    assert "leg_targets" in proposed["M1"]
    assert "trail_steps" in proposed["M1"]
    assert "time_cap_bars" in proposed["M1"]
    # trail_steps must be valid
    assert driver.validate_trail_steps(proposed["M1"]["trail_steps"]) is True


# ---------------------------------------------------------------------------
# Integration tests for run_loop
# ---------------------------------------------------------------------------

def _mock_run_success(result_json_path: Path, pf=1.5, n_trades=60):
    """Return a mock subprocess.run that writes result.json and returns rc=0."""
    def _mock(*args, **kwargs):
        _good_result_json(result_json_path.parent, pf=pf, n_trades=n_trades)
        m = MagicMock()
        m.returncode = 0
        m.stderr = ""
        return m
    return _mock


def test_budget_enforcement(tmp_path):
    """Driver stops when n_prior_tests reaches budget.

    Seeded row = 1 prior test. Budget=3 means stop when tsv has 3 data rows.
    That means exactly 2 new experiments run (seeded=1, exp1=2, exp2=3 >= budget).
    Total: header + seeded + 2 experiments = 4 rows.
    """
    auto_dir, repo_root = _make_autoresearch_dir(tmp_path)
    _write_program_md(auto_dir, budget=3)
    result_path = auto_dir / "result.json"

    mock_run = _mock_run_success(result_path, pf=2.0, n_trades=60)

    with patch("driver.subprocess") as mock_subproc:
        mock_subproc.run.side_effect = mock_run
        driver.run_loop(auto_dir, repo_root, max_iterations=100)

    rows = auto_dir / "results.tsv"
    lines = [l for l in rows.read_text(encoding="utf-8").splitlines() if l.strip()]
    # 1 header + 1 seeded + 2 experiments (seeded counts as 1, budget=3 → 2 new runs)
    assert len(lines) == 4, f"Expected 4 lines (header+seeded+2 exps), got {len(lines)}"
    # Verify exactly 2 new experiment rows (excluding header and seeded)
    data_rows = lines[1:]  # skip header
    exp_rows = [r for r in data_rows if "seeded" not in r]
    assert len(exp_rows) == 2, f"Expected 2 experiment rows, got {len(exp_rows)}"


def test_revert_restores_prior(tmp_path):
    """When metric does NOT improve, exit_params.json is restored to current_best."""
    auto_dir, repo_root = _make_autoresearch_dir(tmp_path)
    # budget=2: seeded row = n_prior_tests=1, so 1 experiment runs before budget hit
    _write_program_md(auto_dir, budget=2, keep_rule=0.05)
    result_path = auto_dir / "result.json"

    # Prior best has pf=1.2 (from seeded row), candidate returns pf=1.0 (worse)
    mock_run = _mock_run_success(result_path, pf=1.0, n_trades=60)

    # Record current_best content before run
    best_before = json.loads(
        (auto_dir / "current_best" / "exit_params.json").read_text(encoding="utf-8")
    )

    with patch("driver.subprocess") as mock_subproc:
        mock_subproc.run.side_effect = mock_run
        driver.run_loop(auto_dir, repo_root, max_iterations=1)

    # exit_params.json should match current_best (byte-identical after revert)
    exit_params = json.loads((auto_dir / "exit_params.json").read_text(encoding="utf-8"))
    assert exit_params == best_before, "Reverted config should match current_best"


def test_keep_updates_best(tmp_path):
    """When metric improves, current_best/exit_params.json is updated."""
    auto_dir, repo_root = _make_autoresearch_dir(tmp_path)
    # budget=2: seeded row = n_prior_tests=1, so 1 experiment runs before budget hit
    _write_program_md(auto_dir, budget=2, keep_rule=0.05)
    result_path = auto_dir / "result.json"

    # Returns pf=3.0, well above seeded 1.2 + threshold 0.05
    mock_run = _mock_run_success(result_path, pf=3.0, n_trades=60)

    with patch("driver.subprocess") as mock_subproc:
        mock_subproc.run.side_effect = mock_run
        driver.run_loop(auto_dir, repo_root, max_iterations=1)

    # current_best should now have the kept params (exit_params.json == current_best)
    exit_params = json.loads((auto_dir / "exit_params.json").read_text(encoding="utf-8"))
    kept = json.loads(
        (auto_dir / "current_best" / "exit_params.json").read_text(encoding="utf-8")
    )
    assert exit_params == kept, "Kept config should be written to current_best"

    # Verify TSV row says "kept"
    lines = (auto_dir / "results.tsv").read_text(encoding="utf-8").splitlines()
    last_row = lines[-1]
    cols = last_row.split("\t")
    assert cols[15] == "kept", f"Expected verdict 'kept', got {cols[15]}"


def test_experiment_anomaly(tmp_path):
    """Non-zero engine exit code logs EXPERIMENT_ANOMALY and loop continues."""
    auto_dir, repo_root = _make_autoresearch_dir(tmp_path)
    _write_program_md(auto_dir, budget=2)

    call_count = [0]
    result_path = auto_dir / "result.json"

    def _mock_mixed(*args, **kwargs):
        call_count[0] += 1
        m = MagicMock()
        if call_count[0] == 1:
            # First call: fail
            m.returncode = 1
            m.stderr = "Engine crashed\nFatal error"
        else:
            # Second call: succeed
            _good_result_json(result_path.parent, pf=1.5, n_trades=60)
            m.returncode = 0
            m.stderr = ""
        return m

    with patch("driver.subprocess") as mock_subproc:
        mock_subproc.run.side_effect = _mock_mixed
        driver.run_loop(auto_dir, repo_root, max_iterations=10)

    audit_log = (repo_root / "audit" / "audit_log.md").read_text(encoding="utf-8")
    assert "EXPERIMENT_ANOMALY" in audit_log, "EXPERIMENT_ANOMALY should be in audit_log.md"

    # Loop should continue: engine called at least twice (1 fail + budget experiments)
    assert call_count[0] >= 2, "Loop should continue after anomaly"


def test_program_md_format():
    """program.md exists, is <=30 lines, and contains parseable METRIC/KEEP RULE/BUDGET."""
    program_path = _AUTORESEARCH / "program.md"
    assert program_path.exists(), "program.md must exist"
    lines = program_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) <= 30, f"program.md must be <=30 lines, got {len(lines)}"
    content = program_path.read_text(encoding="utf-8")
    assert "METRIC:" in content
    assert "KEEP RULE:" in content
    assert "BUDGET:" in content
    parsed = driver.parse_program_md(program_path)
    assert isinstance(parsed["metric"], str)
    assert isinstance(parsed["keep_rule"], float)
    assert isinstance(parsed["budget"], int)


def test_program_md_reread(tmp_path):
    """Driver picks up new BUDGET from program.md mid-run (re-reads every iteration)."""
    auto_dir, repo_root = _make_autoresearch_dir(tmp_path)
    result_path = auto_dir / "result.json"

    # Initial budget = 5
    _write_program_md(auto_dir, budget=5)

    engine_call_count = [0]

    def _mock_run_and_update(args, **kwargs):
        m = MagicMock()
        if args[0] == "git":
            m.returncode = 0
            m.stdout = ""
            m.stderr = ""
            return m
        # Engine call
        engine_call_count[0] += 1
        if engine_call_count[0] == 2:
            # After 2nd experiment, lower budget to 2 — driver should stop after this
            _write_program_md(auto_dir, budget=2)
        _good_result_json(result_path.parent, pf=1.5, n_trades=60)
        m.returncode = 0
        m.stderr = ""
        return m

    with patch("driver.subprocess") as mock_subproc:
        mock_subproc.run.side_effect = _mock_run_and_update
        driver.run_loop(auto_dir, repo_root, max_iterations=100)

    # Should have run exactly 2 experiments (budget reduced to 2 after 2nd)
    # seeded row counts as 1 prior test, so n_prior_tests=1 at start of exp 1
    # After exp 1: 2 rows => n_prior_tests=2 at start of exp 2
    # During exp 2: budget reduced to 2, so after exp 2: n_prior_tests=3 >= 2 => stop
    assert engine_call_count[0] == 2, f"Expected 2 engine calls, got {engine_call_count[0]}"


def test_trail_step_validation(tmp_path):
    """Driver rejects invalid trail steps before running engine."""
    # Verify propose_next_params always returns valid trail steps
    for _ in range(50):
        proposed = driver.propose_next_params(SEEDED_CONFIG, tmp_path / "results.tsv")
        assert driver.validate_trail_steps(proposed["M1"]["trail_steps"]) is True, \
            f"Invalid trail steps: {proposed['M1']['trail_steps']}"


def test_results_tsv_columns(tmp_path):
    """results.tsv row has all 24 columns matching dashboard/results_master.tsv header."""
    auto_dir, repo_root = _make_autoresearch_dir(tmp_path)
    # budget=2: seeded row = n_prior_tests=1, so 1 experiment runs before budget hit
    _write_program_md(auto_dir, budget=2)
    result_path = auto_dir / "result.json"

    mock_run = _mock_run_success(result_path, pf=1.5, n_trades=60)

    with patch("driver.subprocess") as mock_subproc:
        mock_subproc.run.side_effect = mock_run
        driver.run_loop(auto_dir, repo_root, max_iterations=1)

    rows_text = (auto_dir / "results.tsv").read_text(encoding="utf-8")
    lines = [l for l in rows_text.splitlines() if l.strip()]
    # header + seeded + 1 experiment
    assert len(lines) >= 3
    header_cols = lines[0].split("\t")
    exp_row_cols = lines[-1].split("\t")
    assert len(header_cols) == 24, f"Header should have 24 cols, got {len(header_cols)}"
    assert len(exp_row_cols) == 24, f"Row should have 24 cols, got {len(exp_row_cols)}"

    # Note: test_results_tsv_columns also verifies that git calls don't break the 24-col assertion


# ---------------------------------------------------------------------------
# New tests for event-driven git commits, unique run_id, hypothesis_name,
# and lockfile coordination (Task 1 of plan 05-04)
# ---------------------------------------------------------------------------

def _make_mock_subprocess_tracking():
    """Return a mock subprocess that tracks git vs engine calls separately."""
    git_calls = []
    engine_results = []

    class MockSubproc:
        @staticmethod
        def run(args, **kwargs):
            m = MagicMock()
            if args[0] == "git":
                git_calls.append(args)
                m.returncode = 0
                m.stdout = ""
                m.stderr = ""
            else:
                # Engine call — pop from engine_results queue
                if engine_results:
                    return engine_results.pop(0)
                m.returncode = 0
                m.stderr = ""
            return m

    return MockSubproc, git_calls, engine_results


def _make_engine_mock_success(result_json_path, pf=1.5, n_trades=60):
    """Build an engine mock result that writes result.json."""
    def _write_and_return(*args, **kwargs):
        _good_result_json(result_json_path.parent, pf=pf, n_trades=n_trades)
        m = MagicMock()
        m.returncode = 0
        m.stderr = ""
        return m
    return _write_and_return


def test_git_commit_on_kept(tmp_path):
    """git add + git commit called with correct message when experiment is kept."""
    auto_dir, repo_root = _make_autoresearch_dir(tmp_path)
    _write_program_md(auto_dir, budget=2, keep_rule=0.05)
    result_path = auto_dir / "result.json"

    git_calls = []

    def _mock_run(args, **kwargs):
        m = MagicMock()
        if args[0] == "git":
            git_calls.append(list(args))
            m.returncode = 0
            m.stdout = ""
            m.stderr = ""
        else:
            # Engine call
            _good_result_json(result_path.parent, pf=3.0, n_trades=60)
            m.returncode = 0
            m.stderr = ""
        return m

    with patch("driver.subprocess") as mock_subproc:
        mock_subproc.run.side_effect = _mock_run
        driver.run_loop(auto_dir, repo_root, max_iterations=1)

    # Find git commit calls
    commit_calls = [c for c in git_calls if len(c) >= 3 and c[1] == "commit"]
    assert len(commit_calls) >= 1, f"Expected at least 1 git commit call, got: {commit_calls}"
    # Verify the kept commit message format
    kept_commit = None
    for c in commit_calls:
        msg = " ".join(c)
        if "kept experiment" in msg and "stage=04" in msg:
            kept_commit = c
            break
    assert kept_commit is not None, (
        f"Expected kept commit message format 'auto: kept experiment N | pf=X.XXX | archetype | stage=04', "
        f"got commits: {commit_calls}"
    )
    # Verify git add was also called
    add_calls = [c for c in git_calls if len(c) >= 2 and c[1] == "add"]
    assert len(add_calls) >= 1, "Expected at least 1 git add call for kept experiment"


def test_git_commit_on_budget_exhausted(tmp_path):
    """git commit called with budget-exhausted message after loop ends."""
    auto_dir, repo_root = _make_autoresearch_dir(tmp_path)
    # budget=2: 1 seeded row, 1 experiment runs, then budget exhausted
    _write_program_md(auto_dir, budget=2, keep_rule=0.05)
    result_path = auto_dir / "result.json"

    git_calls = []

    def _mock_run(args, **kwargs):
        m = MagicMock()
        if args[0] == "git":
            git_calls.append(list(args))
            m.returncode = 0
            m.stdout = ""
            m.stderr = ""
        else:
            # Engine call — pf below threshold so reverted, no kept commit
            _good_result_json(result_path.parent, pf=1.0, n_trades=60)
            m.returncode = 0
            m.stderr = ""
        return m

    with patch("driver.subprocess") as mock_subproc:
        mock_subproc.run.side_effect = _mock_run
        driver.run_loop(auto_dir, repo_root, max_iterations=100)

    commit_calls = [c for c in git_calls if len(c) >= 3 and c[1] == "commit"]
    exhausted_commit = None
    for c in commit_calls:
        msg = " ".join(c)
        if "budget exhausted" in msg and "stage-04" in msg:
            exhausted_commit = c
            break
    assert exhausted_commit is not None, (
        f"Expected budget-exhausted commit message, got commits: {commit_calls}"
    )


def test_git_commit_on_anomaly(tmp_path):
    """git commit called with ANOMALY message when engine returns non-zero."""
    auto_dir, repo_root = _make_autoresearch_dir(tmp_path)
    _write_program_md(auto_dir, budget=2)
    result_path = auto_dir / "result.json"

    git_calls = []
    call_count = [0]

    def _mock_run(args, **kwargs):
        m = MagicMock()
        if args[0] == "git":
            git_calls.append(list(args))
            m.returncode = 0
            m.stdout = ""
            m.stderr = ""
        else:
            call_count[0] += 1
            if call_count[0] == 1:
                # First engine call: anomaly
                m.returncode = 1
                m.stderr = "Engine crashed"
            else:
                _good_result_json(result_path.parent, pf=1.0, n_trades=60)
                m.returncode = 0
                m.stderr = ""
        return m

    with patch("driver.subprocess") as mock_subproc:
        mock_subproc.run.side_effect = _mock_run
        driver.run_loop(auto_dir, repo_root, max_iterations=10)

    commit_calls = [c for c in git_calls if len(c) >= 3 and c[1] == "commit"]
    anomaly_commit = None
    for c in commit_calls:
        msg = " ".join(c)
        if "ANOMALY" in msg and "stage-04" in msg:
            anomaly_commit = c
            break
    assert anomaly_commit is not None, (
        f"Expected ANOMALY commit message, got commits: {commit_calls}"
    )


def test_no_git_commit_on_reverted(tmp_path):
    """NO git commit called when experiment is reverted (metric did not improve)."""
    auto_dir, repo_root = _make_autoresearch_dir(tmp_path)
    # budget=2: exactly 1 experiment runs (seeded counts as 1, budget=2 → 1 new run)
    _write_program_md(auto_dir, budget=2, keep_rule=0.05)
    result_path = auto_dir / "result.json"

    git_calls = []

    def _mock_run(args, **kwargs):
        m = MagicMock()
        if args[0] == "git":
            git_calls.append(list(args))
            m.returncode = 0
            m.stdout = ""
            m.stderr = ""
        else:
            # pf=1.0 is below seeded 1.2 — reverted
            _good_result_json(result_path.parent, pf=1.0, n_trades=60)
            m.returncode = 0
            m.stderr = ""
        return m

    with patch("driver.subprocess") as mock_subproc:
        mock_subproc.run.side_effect = _mock_run
        driver.run_loop(auto_dir, repo_root, max_iterations=1)

    commit_calls = [c for c in git_calls if len(c) >= 3 and c[1] == "commit"]
    # There should be NO kept-experiment commit
    kept_commits = [c for c in commit_calls if "kept experiment" in " ".join(c)]
    assert len(kept_commits) == 0, (
        f"Expected no kept-experiment commits on revert, got: {kept_commits}"
    )


def test_unique_run_id(tmp_path):
    """run_id is unique per experiment (hash-based, not git HEAD)."""
    auto_dir, repo_root = _make_autoresearch_dir(tmp_path)
    _write_program_md(auto_dir, budget=4, keep_rule=0.0)
    result_path = auto_dir / "result.json"

    def _mock_run(args, **kwargs):
        m = MagicMock()
        if args[0] == "git":
            m.returncode = 0
            m.stdout = ""
            m.stderr = ""
        else:
            _good_result_json(result_path.parent, pf=1.5, n_trades=60)
            m.returncode = 0
            m.stderr = ""
        return m

    with patch("driver.subprocess") as mock_subproc:
        mock_subproc.run.side_effect = _mock_run
        driver.run_loop(auto_dir, repo_root, max_iterations=3)

    lines = [l for l in (auto_dir / "results.tsv").read_text(encoding="utf-8").splitlines() if l.strip()]
    # Skip header and seeded row
    data_rows = lines[2:]
    run_ids = [row.split("\t")[0] for row in data_rows]
    assert len(run_ids) == len(set(run_ids)), f"Duplicate run_ids found: {run_ids}"
    # run_ids should be 7-char hex strings (SHA-1 prefix, matches git short hash format)
    for rid in run_ids:
        assert len(rid) == 7, f"Expected 7-char run_id, got: {rid!r}"
        assert all(c in "0123456789abcdef" for c in rid), f"run_id not hex: {rid!r}"


def test_hypothesis_name_from_file(tmp_path):
    """hypothesis_name column populated from promoted_hypothesis.json when it exists."""
    auto_dir, repo_root = _make_autoresearch_dir(tmp_path)
    _write_program_md(auto_dir, budget=2, keep_rule=0.0)
    result_path = auto_dir / "result.json"

    # Write promoted_hypothesis.json
    (auto_dir / "promoted_hypothesis.json").write_text(
        json.dumps({"name": "mean_reversion_v2"}), encoding="utf-8"
    )

    def _mock_run(args, **kwargs):
        m = MagicMock()
        if args[0] == "git":
            m.returncode = 0
            m.stdout = ""
            m.stderr = ""
        else:
            _good_result_json(result_path.parent, pf=1.5, n_trades=60)
            m.returncode = 0
            m.stderr = ""
        return m

    with patch("driver.subprocess") as mock_subproc:
        mock_subproc.run.side_effect = _mock_run
        driver.run_loop(auto_dir, repo_root, max_iterations=1)

    lines = (auto_dir / "results.tsv").read_text(encoding="utf-8").splitlines()
    last_row = lines[-1]
    cols = last_row.split("\t")
    # hypothesis_name is column index 3
    assert cols[3] == "mean_reversion_v2", f"Expected 'mean_reversion_v2', got {cols[3]!r}"


def test_hypothesis_name_fallback(tmp_path):
    """hypothesis_name falls back to archetype name when promoted_hypothesis.json absent."""
    auto_dir, repo_root = _make_autoresearch_dir(tmp_path)
    _write_program_md(auto_dir, budget=2, keep_rule=0.0)
    result_path = auto_dir / "result.json"

    # No promoted_hypothesis.json

    def _mock_run(args, **kwargs):
        m = MagicMock()
        if args[0] == "git":
            m.returncode = 0
            m.stdout = ""
            m.stderr = ""
        else:
            _good_result_json(result_path.parent, pf=1.5, n_trades=60)
            m.returncode = 0
            m.stderr = ""
        return m

    with patch("driver.subprocess") as mock_subproc:
        mock_subproc.run.side_effect = _mock_run
        driver.run_loop(auto_dir, repo_root, max_iterations=1)

    lines = (auto_dir / "results.tsv").read_text(encoding="utf-8").splitlines()
    last_row = lines[-1]
    cols = last_row.split("\t")
    # hypothesis_name column (index 3) should be archetype name
    archetype_name = SEEDED_CONFIG["archetype"]["name"]
    assert cols[3] == archetype_name, (
        f"Expected archetype name '{archetype_name}' as fallback, got {cols[3]!r}"
    )


def test_lockfile_created_and_removed(tmp_path):
    """.autoresearch_running lockfile created at loop start and removed on completion."""
    auto_dir, repo_root = _make_autoresearch_dir(tmp_path)
    _write_program_md(auto_dir, budget=2, keep_rule=0.0)
    result_path = auto_dir / "result.json"
    lockfile = repo_root / ".autoresearch_running"

    lockfile_states = []

    def _mock_run(args, **kwargs):
        m = MagicMock()
        if args[0] == "git":
            m.returncode = 0
            m.stdout = ""
            m.stderr = ""
        else:
            # Check lockfile exists during engine call
            lockfile_states.append(lockfile.exists())
            _good_result_json(result_path.parent, pf=1.5, n_trades=60)
            m.returncode = 0
            m.stderr = ""
        return m

    with patch("driver.subprocess") as mock_subproc:
        mock_subproc.run.side_effect = _mock_run
        driver.run_loop(auto_dir, repo_root, max_iterations=1)

    # Lockfile should have existed during the run
    assert any(lockfile_states), "Lockfile should exist during engine execution"
    # Lockfile should be removed after completion
    assert not lockfile.exists(), "Lockfile should be removed after loop completes"


def test_lockfile_removed_on_error(tmp_path):
    """.autoresearch_running lockfile removed even when loop raises exception."""
    auto_dir, repo_root = _make_autoresearch_dir(tmp_path)
    _write_program_md(auto_dir, budget=2)
    lockfile = repo_root / ".autoresearch_running"

    def _mock_run(args, **kwargs):
        if args[0] != "git":
            raise RuntimeError("Unexpected engine crash")
        m = MagicMock()
        m.returncode = 0
        m.stdout = ""
        m.stderr = ""
        return m

    with patch("driver.subprocess") as mock_subproc:
        mock_subproc.run.side_effect = _mock_run
        try:
            driver.run_loop(auto_dir, repo_root, max_iterations=1)
        except Exception:
            pass  # Exception is expected — we only care about lockfile cleanup

    assert not lockfile.exists(), "Lockfile should be removed even after exception"
