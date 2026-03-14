"""Tests for assess.py --feedback-output extension.

Covers:
- TestFeedbackOutput: feedback file written with correct sections when flag provided
- TestFeedbackOutput: no feedback file written when flag omitted (backward compat)
- TestFeedbackWiring: feedback copied to stage03_ref_path; dir created if missing
- TestExistingBehavior: verdict_report.md output identical to pre-extension behavior
"""

import json
import sys
from pathlib import Path

import pytest

# Ensure repo root is on sys.path so assess.py imports shared modules
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------

MINIMAL_RESULT = {
    "n_trades": 55,
    "win_rate": 0.58,
    "total_pnl_ticks": 120.0,
    "max_drawdown_ticks": 30.0,
    "pf": 1.8,
    "per_mode": {
        "trend_up": {"pf": 2.1, "n_trades": 30, "win_rate": 0.60},
        "trend_down": {"pf": 0.7, "n_trades": 25, "win_rate": 0.52},
    },
}

RESULT_LOW_TRADES = {
    "n_trades": 10,
    "win_rate": 0.50,
    "total_pnl_ticks": -5.0,
    "max_drawdown_ticks": 15.0,
    "pf": 0.8,
    "per_mode": {},
}


def write_result_json(tmp_path: Path, data: dict) -> Path:
    result_file = tmp_path / "result.json"
    result_file.write_text(json.dumps(data), encoding="utf-8")
    return result_file


# -------------------------------------------------------------------
# Monkeypatch helper: disable instrument config lookup in assess.py
# -------------------------------------------------------------------

def patch_assess_cost(monkeypatch):
    """Patch _repo_root resolution so parse_instruments_md is skipped cleanly."""
    import stages.assessment_05 as _pkg  # not actually used; we patch via sys
    # Patch parse_instruments_md in the loaded module to return a stub
    try:
        from shared import data_loader
        monkeypatch.setattr(
            data_loader,
            "parse_instruments_md",
            lambda *a, **kw: {"cost_ticks": "2.0"},
        )
    except Exception:
        pass  # If import fails, assess.py's try/except handles it gracefully


# -------------------------------------------------------------------
# Import assess.main after repo root is on path
# -------------------------------------------------------------------

def get_main():
    import importlib
    spec = importlib.util.spec_from_file_location(
        "assess",
        str(REPO_ROOT / "stages/05-assessment/assess.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.main


# -------------------------------------------------------------------
# TestFeedbackOutput
# -------------------------------------------------------------------

class TestFeedbackOutput:
    def test_feedback_file_written_when_flag_provided(self, tmp_path, monkeypatch):
        """assess.py with --feedback-output writes feedback_to_hypothesis.md."""
        try:
            from shared import data_loader
            monkeypatch.setattr(
                data_loader,
                "parse_instruments_md",
                lambda *a, **kw: {"cost_ticks": "2.0"},
            )
        except Exception:
            pass

        result_file = write_result_json(tmp_path, MINIMAL_RESULT)
        verdict_file = tmp_path / "verdict_report.md"
        feedback_file = tmp_path / "feedback_to_hypothesis.md"

        main = get_main()
        main(
            input_path=str(result_file),
            output_path=str(verdict_file),
            feedback_output_path=str(feedback_file),
        )

        assert feedback_file.exists(), "feedback_to_hypothesis.md must be written"

    def test_feedback_file_contains_required_sections(self, tmp_path, monkeypatch):
        """Feedback file contains all required headers."""
        try:
            from shared import data_loader
            monkeypatch.setattr(
                data_loader,
                "parse_instruments_md",
                lambda *a, **kw: {"cost_ticks": "2.0"},
            )
        except Exception:
            pass

        result_file = write_result_json(tmp_path, MINIMAL_RESULT)
        verdict_file = tmp_path / "verdict_report.md"
        feedback_file = tmp_path / "feedback_to_hypothesis.md"

        main = get_main()
        main(
            input_path=str(result_file),
            output_path=str(verdict_file),
            feedback_output_path=str(feedback_file),
        )

        content = feedback_file.read_text(encoding="utf-8")
        assert "# Feedback to Hypothesis Generator" in content
        assert "## Verdict:" in content
        assert "## Key Metrics" in content
        assert "## What Worked" in content
        assert "## What to Avoid" in content

    def test_no_feedback_file_without_flag(self, tmp_path, monkeypatch):
        """assess.py without --feedback-output does NOT write feedback file (backward compat)."""
        try:
            from shared import data_loader
            monkeypatch.setattr(
                data_loader,
                "parse_instruments_md",
                lambda *a, **kw: {"cost_ticks": "2.0"},
            )
        except Exception:
            pass

        result_file = write_result_json(tmp_path, MINIMAL_RESULT)
        verdict_file = tmp_path / "verdict_report.md"

        main = get_main()
        main(
            input_path=str(result_file),
            output_path=str(verdict_file),
        )

        # No feedback file should exist anywhere in tmp_path except verdict
        feedback_candidates = list(tmp_path.glob("*feedback*"))
        assert len(feedback_candidates) == 0, (
            f"Unexpected feedback files written: {feedback_candidates}"
        )

    def test_feedback_contains_pf_and_trades(self, tmp_path, monkeypatch):
        """Feedback file contains key metric values from result."""
        try:
            from shared import data_loader
            monkeypatch.setattr(
                data_loader,
                "parse_instruments_md",
                lambda *a, **kw: {"cost_ticks": "2.0"},
            )
        except Exception:
            pass

        result_file = write_result_json(tmp_path, MINIMAL_RESULT)
        verdict_file = tmp_path / "verdict_report.md"
        feedback_file = tmp_path / "feedback.md"

        main = get_main()
        main(
            input_path=str(result_file),
            output_path=str(verdict_file),
            feedback_output_path=str(feedback_file),
        )

        content = feedback_file.read_text(encoding="utf-8")
        # Key metric values should appear
        assert "1.800" in content or "1.8" in content, "PF not found in feedback"
        assert "55" in content, "n_trades not found in feedback"


# -------------------------------------------------------------------
# TestFeedbackWiring
# -------------------------------------------------------------------

class TestFeedbackWiring:
    def test_feedback_copied_to_stage03_ref_path(self, tmp_path, monkeypatch):
        """assess.py with stage03_ref_path writes prior_results.md there."""
        try:
            from shared import data_loader
            monkeypatch.setattr(
                data_loader,
                "parse_instruments_md",
                lambda *a, **kw: {"cost_ticks": "2.0"},
            )
        except Exception:
            pass

        result_file = write_result_json(tmp_path, MINIMAL_RESULT)
        verdict_file = tmp_path / "verdict_report.md"
        feedback_file = tmp_path / "feedback_to_hypothesis.md"
        stage03_ref = tmp_path / "stage03" / "references" / "prior_results.md"

        main = get_main()
        main(
            input_path=str(result_file),
            output_path=str(verdict_file),
            feedback_output_path=str(feedback_file),
            stage03_ref_path=str(stage03_ref),
        )

        assert stage03_ref.exists(), "prior_results.md must be written to stage03_ref_path"

    def test_feedback_content_matches_stage03_ref(self, tmp_path, monkeypatch):
        """Content of feedback file matches what was copied to stage03_ref_path."""
        try:
            from shared import data_loader
            monkeypatch.setattr(
                data_loader,
                "parse_instruments_md",
                lambda *a, **kw: {"cost_ticks": "2.0"},
            )
        except Exception:
            pass

        result_file = write_result_json(tmp_path, MINIMAL_RESULT)
        verdict_file = tmp_path / "verdict_report.md"
        feedback_file = tmp_path / "feedback_to_hypothesis.md"
        stage03_ref = tmp_path / "stage03" / "references" / "prior_results.md"

        main = get_main()
        main(
            input_path=str(result_file),
            output_path=str(verdict_file),
            feedback_output_path=str(feedback_file),
            stage03_ref_path=str(stage03_ref),
        )

        feedback_content = feedback_file.read_text(encoding="utf-8")
        ref_content = stage03_ref.read_text(encoding="utf-8")
        assert feedback_content == ref_content, (
            "stage03 prior_results.md must be identical to feedback file"
        )

    def test_stage03_ref_dir_created_if_missing(self, tmp_path, monkeypatch):
        """If stage03_ref_path parent dirs don't exist, they are created."""
        try:
            from shared import data_loader
            monkeypatch.setattr(
                data_loader,
                "parse_instruments_md",
                lambda *a, **kw: {"cost_ticks": "2.0"},
            )
        except Exception:
            pass

        result_file = write_result_json(tmp_path, MINIMAL_RESULT)
        verdict_file = tmp_path / "verdict_report.md"
        feedback_file = tmp_path / "feedback.md"
        # Deep path that does not exist
        stage03_ref = tmp_path / "deep" / "nested" / "path" / "prior_results.md"
        assert not stage03_ref.parent.exists()

        main = get_main()
        main(
            input_path=str(result_file),
            output_path=str(verdict_file),
            feedback_output_path=str(feedback_file),
            stage03_ref_path=str(stage03_ref),
        )

        assert stage03_ref.exists(), "prior_results.md created even when parent dirs missing"


# -------------------------------------------------------------------
# TestExistingBehavior
# -------------------------------------------------------------------

class TestExistingBehavior:
    def test_verdict_report_written_without_feedback_flag(self, tmp_path, monkeypatch):
        """Existing --input/--output behavior: verdict_report.md still written correctly."""
        try:
            from shared import data_loader
            monkeypatch.setattr(
                data_loader,
                "parse_instruments_md",
                lambda *a, **kw: {"cost_ticks": "2.0"},
            )
        except Exception:
            pass

        result_file = write_result_json(tmp_path, MINIMAL_RESULT)
        verdict_file = tmp_path / "verdict_report.md"

        main = get_main()
        main(input_path=str(result_file), output_path=str(verdict_file))

        assert verdict_file.exists()
        content = verdict_file.read_text(encoding="utf-8")
        assert "# Verdict Report" in content
        assert "CANDIDATE_CONDITIONAL" in content or "CANDIDATE_YES" in content

    def test_verdict_report_contains_key_sections(self, tmp_path, monkeypatch):
        """Existing verdict_report.md has Summary, Cost Impact, Per-Mode, Verdict sections."""
        try:
            from shared import data_loader
            monkeypatch.setattr(
                data_loader,
                "parse_instruments_md",
                lambda *a, **kw: {"cost_ticks": "2.0"},
            )
        except Exception:
            pass

        result_file = write_result_json(tmp_path, MINIMAL_RESULT)
        verdict_file = tmp_path / "verdict.md"

        main = get_main()
        main(input_path=str(result_file), output_path=str(verdict_file))

        content = verdict_file.read_text(encoding="utf-8")
        assert "## Summary" in content
        assert "## Cost Impact" in content
        assert "## Per-Mode Breakdown" in content
        assert "## Verdict:" in content

    def test_insufficient_data_for_low_trades(self, tmp_path, monkeypatch):
        """Verdict is INSUFFICIENT_DATA when n_trades < 30."""
        try:
            from shared import data_loader
            monkeypatch.setattr(
                data_loader,
                "parse_instruments_md",
                lambda *a, **kw: {"cost_ticks": "2.0"},
            )
        except Exception:
            pass

        result_file = write_result_json(tmp_path, RESULT_LOW_TRADES)
        verdict_file = tmp_path / "verdict.md"

        main = get_main()
        main(input_path=str(result_file), output_path=str(verdict_file))

        content = verdict_file.read_text(encoding="utf-8")
        assert "INSUFFICIENT_DATA" in content
