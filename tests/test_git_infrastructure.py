"""Subprocess-based tests for git infrastructure: pre-commit hook, post-commit hook.

Tests create a fresh temp git repo via tmp_path, install the real hooks from
.git/hooks/, and exercise them via subprocess git commands. Hooks don't exist
yet at time of writing — these tests fail RED until Task 2 creates them.

Run: python -m pytest tests/test_git_infrastructure.py -x -q
"""

import json
import subprocess
import os
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_HOOKS_DIR = _REPO_ROOT / ".git" / "hooks"
_PRE_COMMIT_HOOK = _HOOKS_DIR / "pre-commit"
_POST_COMMIT_HOOK = _HOOKS_DIR / "post-commit"

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def git_repo(tmp_path):
    """
    Create a fresh temp git repo with both hooks installed.

    - git init
    - configure user.email and user.name
    - copy pre-commit and post-commit hooks from the real repo
    - chmod +x both hooks
    - create an initial commit so HEAD exists (needed for diff-tree in post-commit)
    """
    repo = tmp_path / "repo"
    repo.mkdir()

    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    # Install hooks from real repo (will fail RED if hooks don't exist)
    hooks_dir = repo / ".git" / "hooks"
    for hook_name, src_path in [
        ("pre-commit", _PRE_COMMIT_HOOK),
        ("post-commit", _POST_COMMIT_HOOK),
    ]:
        dst = hooks_dir / hook_name
        dst.write_bytes(src_path.read_bytes())  # raises FileNotFoundError if not found
        dst.chmod(0o755)

    # Initial commit so HEAD exists (post-commit can call git diff-tree HEAD)
    seed = repo / "README.md"
    seed.write_text("# test repo\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init: initial commit"],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    return repo


@pytest.fixture()
def git_repo_with_audit(git_repo):
    """
    Extends git_repo with a committed audit/audit_log.md so the append-only
    check has something to diff against.
    """
    audit_dir = git_repo / "audit"
    audit_dir.mkdir(parents=True)
    audit_log = audit_dir / "audit_log.md"
    audit_log.write_text(
        "# Futures Pipeline Audit Log\n\n## 2026-01-01 | MANUAL_NOTE\n- subject: seed\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "audit/audit_log.md"], cwd=git_repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "manual: add audit log seed"],
        cwd=git_repo,
        check=True,
        capture_output=True,
    )
    return git_repo


# ---------------------------------------------------------------------------
# GIT-01: autocommit watcher — manual smoke test only
# ---------------------------------------------------------------------------


@pytest.mark.skip(reason="requires background process — manual verification")
def test_autocommit_smoke():
    """autocommit.sh polls every 30s and commits changes. Verified manually."""
    pass


# ---------------------------------------------------------------------------
# GIT-02: pre-commit — holdout guard
# ---------------------------------------------------------------------------


def test_holdout_guard(git_repo):
    """Staging any file under stages/04-backtest/p2_holdout/ must abort commit."""
    holdout_dir = git_repo / "stages" / "04-backtest" / "p2_holdout"
    holdout_dir.mkdir(parents=True)
    flag = holdout_dir / "holdout_locked_P2.flag"
    flag.write_text("locked\n", encoding="utf-8")

    subprocess.run(
        ["git", "add", "stages/04-backtest/p2_holdout/holdout_locked_P2.flag"],
        cwd=git_repo,
        check=True,
        capture_output=True,
    )
    result = subprocess.run(
        ["git", "commit", "-m", "test: should be blocked"],
        cwd=git_repo,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0, "Expected non-zero exit from pre-commit guard"
    combined = (result.stdout + result.stderr).lower()
    assert "holdout" in combined or "p2" in combined, (
        f"Expected 'holdout' or 'P2' in output, got:\nstdout={result.stdout}\nstderr={result.stderr}"
    )


def test_holdout_guard_allows_other_files(git_repo):
    """Staging a file NOT under p2_holdout/ must succeed."""
    safe_file = git_repo / "safe_file.txt"
    safe_file.write_text("safe content\n", encoding="utf-8")

    subprocess.run(["git", "add", "safe_file.txt"], cwd=git_repo, check=True, capture_output=True)
    result = subprocess.run(
        ["git", "commit", "-m", "test: safe commit"],
        cwd=git_repo,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, (
        f"Expected success for non-holdout file, got:\nstdout={result.stdout}\nstderr={result.stderr}"
    )


# ---------------------------------------------------------------------------
# GIT-02: pre-commit — audit append-only enforcement
# ---------------------------------------------------------------------------


def test_audit_append_only_blocks_deletion(git_repo_with_audit):
    """Staging audit_log.md with a line removed must abort commit."""
    repo = git_repo_with_audit
    audit_log = repo / "audit" / "audit_log.md"

    # Remove one line (delete the "- subject: seed" line)
    original = audit_log.read_text(encoding="utf-8")
    reduced = "\n".join(
        line for line in original.splitlines() if "- subject: seed" not in line
    ) + "\n"
    audit_log.write_text(reduced, encoding="utf-8")

    subprocess.run(["git", "add", "audit/audit_log.md"], cwd=repo, check=True, capture_output=True)
    result = subprocess.run(
        ["git", "commit", "-m", "test: deleting audit line (should fail)"],
        cwd=repo,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0, "Expected non-zero exit from audit append-only check"
    combined = (result.stdout + result.stderr).lower()
    assert "append" in combined or "append-only" in combined or "deletion" in combined, (
        f"Expected 'append' or 'deletion' in output, got:\nstdout={result.stdout}\nstderr={result.stderr}"
    )


def test_audit_append_only_allows_append(git_repo_with_audit):
    """Staging audit_log.md with lines appended (no deletions) must succeed."""
    repo = git_repo_with_audit
    audit_log = repo / "audit" / "audit_log.md"

    # Append a new entry — no lines removed
    with open(audit_log, "a", encoding="utf-8") as f:
        f.write("\n## 2026-01-02 | MANUAL_NOTE\n- subject: appended entry\n")

    subprocess.run(["git", "add", "audit/audit_log.md"], cwd=repo, check=True, capture_output=True)
    result = subprocess.run(
        ["git", "commit", "-m", "test: append-only audit entry (should succeed)"],
        cwd=repo,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, (
        f"Expected success for append-only audit change, got:\nstdout={result.stdout}\nstderr={result.stderr}"
    )


# ---------------------------------------------------------------------------
# GIT-03: post-commit — commit log
# ---------------------------------------------------------------------------


def test_commit_log_written(git_repo):
    """After a successful commit, .git/commit_log.txt must contain the commit hash."""
    new_file = git_repo / "feature.txt"
    new_file.write_text("feature content\n", encoding="utf-8")

    subprocess.run(["git", "add", "feature.txt"], cwd=git_repo, check=True, capture_output=True)
    result = subprocess.run(
        ["git", "commit", "-m", "test: commit log test"],
        cwd=git_repo,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, (
        f"Commit failed unexpectedly:\nstdout={result.stdout}\nstderr={result.stderr}"
    )

    commit_log = git_repo / ".git" / "commit_log.txt"
    assert commit_log.exists(), ".git/commit_log.txt was not created by post-commit hook"

    # Get the hash of the commit we just made
    hash_result = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=git_repo,
        capture_output=True,
        text=True,
    )
    commit_hash = hash_result.stdout.strip()
    log_content = commit_log.read_text(encoding="utf-8")
    assert commit_hash in log_content, (
        f"Expected commit hash '{commit_hash}' in commit_log.txt, got:\n{log_content}"
    )


# ---------------------------------------------------------------------------
# GIT-03: post-commit — OOS_RUN audit entry
# ---------------------------------------------------------------------------


def test_oos_run_entry(git_repo_with_audit):
    """
    After committing a file matching holdout_locked*.flag, audit_log.md must
    contain an OOS_RUN entry with period, pf, and n_trades fields.
    """
    repo = git_repo_with_audit

    # Create the verdict_report.json that the hook reads
    verdict_dir = repo / "stages" / "05-assessment" / "output"
    verdict_dir.mkdir(parents=True)
    verdict_file = verdict_dir / "verdict_report.json"
    verdict_file.write_text(
        json.dumps({"pf": "1.5", "n_trades": "42", "verdict": "PASS"}),
        encoding="utf-8",
    )

    # Create holdout flag file
    holdout_dir = repo / "stages" / "04-backtest" / "p2_holdout"
    holdout_dir.mkdir(parents=True)
    flag = holdout_dir / "holdout_locked_P2.flag"
    flag.write_text("locked\n", encoding="utf-8")

    # The pre-commit hook will BLOCK this commit because it touches p2_holdout/
    # So we must temporarily disable the pre-commit hook to test the post-commit behavior
    pre_commit_hook = repo / ".git" / "hooks" / "pre-commit"
    pre_commit_backup = repo / ".git" / "hooks" / "pre-commit.bak"
    pre_commit_hook.rename(pre_commit_backup)

    try:
        subprocess.run(
            ["git", "add", "stages/04-backtest/p2_holdout/holdout_locked_P2.flag",
             "stages/05-assessment/output/verdict_report.json"],
            cwd=repo,
            check=True,
            capture_output=True,
        )
        result = subprocess.run(
            ["git", "commit", "-m", "test: OOS run flag commit"],
            cwd=repo,
            capture_output=True,
            text=True,
        )
    finally:
        # Restore pre-commit hook
        pre_commit_backup.rename(pre_commit_hook)

    assert result.returncode == 0, (
        f"Commit failed:\nstdout={result.stdout}\nstderr={result.stderr}"
    )

    audit_log = repo / "audit" / "audit_log.md"
    content = audit_log.read_text(encoding="utf-8")
    assert "OOS_RUN" in content, f"Expected OOS_RUN entry in audit_log.md:\n{content}"
    assert "period:" in content, f"Expected 'period:' field in OOS_RUN entry:\n{content}"
    assert "pf:" in content, f"Expected 'pf:' field in OOS_RUN entry:\n{content}"
    assert "n_trades:" in content, f"Expected 'n_trades:' field in OOS_RUN entry:\n{content}"


# ---------------------------------------------------------------------------
# GIT-02 (pre-commit): HYPOTHESIS_PROMOTED auto-entry
# ---------------------------------------------------------------------------


def test_hypothesis_promoted_entry(git_repo_with_audit):
    """
    After committing a file under 03-hypothesis/output/promoted_hypotheses/,
    audit_log.md must contain a HYPOTHESIS_PROMOTED entry.
    """
    repo = git_repo_with_audit

    promo_dir = repo / "03-hypothesis" / "output" / "promoted_hypotheses"
    promo_dir.mkdir(parents=True)
    hyp_file = promo_dir / "zone_touch_m1a_v3.json"
    hyp_file.write_text(json.dumps({"hypothesis_id": "zone_touch_m1a_v3"}), encoding="utf-8")

    subprocess.run(
        ["git", "add", "03-hypothesis/output/promoted_hypotheses/zone_touch_m1a_v3.json"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    result = subprocess.run(
        ["git", "commit", "-m", "promote: zone_touch_m1a_v3"],
        cwd=repo,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, (
        f"Commit failed:\nstdout={result.stdout}\nstderr={result.stderr}"
    )

    audit_log = repo / "audit" / "audit_log.md"
    content = audit_log.read_text(encoding="utf-8")
    assert "HYPOTHESIS_PROMOTED" in content, (
        f"Expected HYPOTHESIS_PROMOTED entry in audit_log.md:\n{content}"
    )


# ---------------------------------------------------------------------------
# GIT-02 (pre-commit): PERIOD_CONFIG_CHANGED auto-entry
# ---------------------------------------------------------------------------


def test_period_config_changed_entry(git_repo_with_audit):
    """
    After committing a change to _config/period_config.md, audit_log.md must
    contain a PERIOD_CONFIG_CHANGED entry. The commit must NOT be blocked.
    """
    repo = git_repo_with_audit

    config_dir = repo / "_config"
    config_dir.mkdir(parents=True)
    period_config = config_dir / "period_config.md"

    # First commit: create the file so HEAD has a version of it
    period_config.write_text(
        "# Period Config\n\n| Period | Start | End |\n|--------|-------|-----|\n| P1 | 2025-09-16 | 2025-12-14 |\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "_config/period_config.md"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "manual: initial period config"],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    # Second commit: modify the file — triggers PERIOD_CONFIG_CHANGED
    period_config.write_text(
        "# Period Config\n\n| Period | Start | End |\n|--------|-------|-----|\n"
        "| P1 | 2025-09-16 | 2025-12-14 |\n"
        "| P2 | 2025-12-15 | 2026-03-02 |\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "_config/period_config.md"], cwd=repo, check=True, capture_output=True)
    result = subprocess.run(
        ["git", "commit", "-m", "manual: add P2 period boundary"],
        cwd=repo,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, (
        f"Commit was blocked unexpectedly (period_config change should warn, not block):\n"
        f"stdout={result.stdout}\nstderr={result.stderr}"
    )

    audit_log = repo / "audit" / "audit_log.md"
    content = audit_log.read_text(encoding="utf-8")
    assert "PERIOD_CONFIG_CHANGED" in content, (
        f"Expected PERIOD_CONFIG_CHANGED entry in audit_log.md:\n{content}"
    )
