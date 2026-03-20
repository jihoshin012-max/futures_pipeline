"""Tests for stages/03-hypothesis/autoresearch/hypothesis_generator.py

Tests use tmp_path for all file I/O. Engine subprocess is mocked.
"""
import csv
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add autoresearch dir to path so hypothesis_generator can be imported directly
_AUTORESEARCH = Path(__file__).resolve().parents[1] / "stages/03-hypothesis/autoresearch"
if str(_AUTORESEARCH) not in sys.path:
    sys.path.insert(0, str(_AUTORESEARCH))

import hypothesis_generator  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_touches_csv(path: Path, rows: list) -> None:
    """Write a minimal touches CSV with DateTime column and given rows."""
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["DateTime", "Price", "OtherCol"])
        for row in rows:
            writer.writerow(row)


P1A_DATE = "10/15/2025 10:00"   # P1a (before P1b start)
P1B_DATE = "11/15/2025 10:00"   # P1b (within 2025-11-01 to 2025-12-14)
P1B_DATE2 = "12/10/2025 10:00"  # also P1b
LATE_DATE = "12/20/2025 10:00"  # after P1b end — outside range


# ---------------------------------------------------------------------------
# TestP1bFilter
# ---------------------------------------------------------------------------

class TestP1bFilter:
    def test_filters_to_p1b_rows(self, tmp_path):
        """write_p1b_filtered_csv returns only rows in [2025-11-01, 2025-12-14]."""
        csv_path = tmp_path / "touches.csv"
        _write_touches_csv(csv_path, [
            [P1A_DATE, 100, "a"],
            [P1B_DATE, 101, "b"],
            [P1B_DATE2, 102, "c"],
            [LATE_DATE, 103, "d"],
        ])
        out_path = hypothesis_generator.write_p1b_filtered_csv(str(csv_path))
        try:
            with open(out_path, encoding="utf-8", newline="") as f:
                reader = csv.reader(f)
                rows = list(reader)
            # Header + 2 P1b rows
            assert len(rows) == 3, f"Expected 3 rows (header + 2 P1b), got {len(rows)}: {rows}"
            dates = [r[0] for r in rows[1:]]
            assert P1B_DATE in dates
            assert P1B_DATE2 in dates
            assert P1A_DATE not in dates
            assert LATE_DATE not in dates
        finally:
            Path(out_path).unlink(missing_ok=True)

    def test_empty_p1b_raises_value_error(self, tmp_path):
        """write_p1b_filtered_csv raises ValueError when no P1b rows found."""
        csv_path = tmp_path / "touches.csv"
        _write_touches_csv(csv_path, [
            [P1A_DATE, 100, "a"],
        ])
        with pytest.raises(ValueError, match="(?i)p1b|empty|no.*rows|filtered"):
            hypothesis_generator.write_p1b_filtered_csv(str(csv_path))

    def test_only_p1b_rows_passes(self, tmp_path):
        """write_p1b_filtered_csv succeeds when all rows are in P1b range."""
        csv_path = tmp_path / "touches.csv"
        _write_touches_csv(csv_path, [
            [P1B_DATE, 101, "b"],
            [P1B_DATE2, 102, "c"],
        ])
        out_path = hypothesis_generator.write_p1b_filtered_csv(str(csv_path))
        try:
            with open(out_path, encoding="utf-8", newline="") as f:
                reader = csv.reader(f)
                rows = list(reader)
            assert len(rows) == 3  # header + 2 rows
        finally:
            Path(out_path).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# TestRunnerOutputs
# ---------------------------------------------------------------------------

SEEDED_CONFIG = {
    "version": "v1",
    "instrument": "NQ",
    "touches_csv": "stages/01-data/data/touches/NQ_ZRA_Hist_P1.csv",
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
        ],
        "time_cap_bars": 85,
    },
}

GOOD_RESULT = {"pf": 1.5, "n_trades": 50, "win_rate": 0.55}
GOOD_RESULT_P1B = {"pf": 1.3, "n_trades": 25, "win_rate": 0.52}


def _make_mock_subprocess_run(config_path, result_path, result_p1b_path):
    """Return a mock subprocess.run that writes fake result.json files on success."""
    call_count = [0]

    def _mock_run(args, **kwargs):
        m = MagicMock()
        call_count[0] += 1
        if "--output-p1b" in args or str(result_p1b_path) in args:
            # P1b run
            Path(result_p1b_path).write_text(json.dumps(GOOD_RESULT_P1B), encoding="utf-8")
        else:
            # P1 run
            Path(result_path).write_text(json.dumps(GOOD_RESULT), encoding="utf-8")
        m.returncode = 0
        m.stderr = ""
        m.stdout = ""
        return m

    return _mock_run, call_count


class TestRunnerOutputs:
    def _make_config(self, tmp_path: Path, touches_csv_path: str = None) -> Path:
        """Create a config JSON in tmp_path, optionally override touches_csv."""
        cfg = dict(SEEDED_CONFIG)
        if touches_csv_path:
            cfg = {**SEEDED_CONFIG, "touches_csv": touches_csv_path}
        config_path = tmp_path / "hypothesis_config.json"
        config_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
        return config_path

    def _make_touches_csv(self, tmp_path: Path) -> Path:
        """Create a minimal touches CSV with P1b rows."""
        csv_path = tmp_path / "touches_p1.csv"
        _write_touches_csv(csv_path, [
            [P1A_DATE, 100, "a"],
            [P1B_DATE, 101, "b"],
            [P1B_DATE2, 102, "c"],
        ])
        return csv_path

    def test_run_produces_both_output_files(self, tmp_path):
        """run() produces both result.json and result_p1b.json."""
        touches_csv = self._make_touches_csv(tmp_path)
        config_path = self._make_config(tmp_path, str(touches_csv))
        result_path = tmp_path / "result.json"
        result_p1b_path = tmp_path / "result_p1b.json"
        engine_path = tmp_path / "fake_engine.py"
        engine_path.write_text("pass", encoding="utf-8")

        def _mock_run(args, **kwargs):
            m = MagicMock()
            # Determine which output file to write based on --output flag
            if "--output-p1b" in args:
                idx = args.index("--output-p1b")
                Path(args[idx + 1]).write_text(json.dumps(GOOD_RESULT_P1B), encoding="utf-8")
            elif "--output" in args:
                idx = args.index("--output")
                Path(args[idx + 1]).write_text(json.dumps(GOOD_RESULT), encoding="utf-8")
            m.returncode = 0
            m.stderr = ""
            return m

        with patch("hypothesis_generator.subprocess") as mock_subproc:
            mock_subproc.run.side_effect = _mock_run
            hypothesis_generator.run(
                config_path=str(config_path),
                result_path=str(result_path),
                result_p1b_path=str(result_p1b_path),
                engine_path=str(engine_path),
                repo_root=str(tmp_path),
            )

        assert result_path.exists(), "result.json should be created by run()"
        assert result_p1b_path.exists(), "result_p1b.json should be created by run()"

    def test_p1b_config_uses_filtered_touches(self, tmp_path):
        """P1b engine call receives a temp config with a different (filtered) touches path."""
        touches_csv = self._make_touches_csv(tmp_path)
        config_path = self._make_config(tmp_path, str(touches_csv))
        result_path = tmp_path / "result.json"
        result_p1b_path = tmp_path / "result_p1b.json"
        engine_path = tmp_path / "fake_engine.py"
        engine_path.write_text("pass", encoding="utf-8")

        p1b_config_touches = []

        def _mock_run(args, **kwargs):
            m = MagicMock()
            # Determine which is the P1b call by inspecting the --config argument
            if "--config" in args:
                cfg_idx = args.index("--config")
                cfg_path = args[cfg_idx + 1]
                # The second call (P1b) will have a temp config path
                if "--output-p1b" in args or (
                    result_p1b_path and str(result_p1b_path) in args
                ):
                    # Read the temp config to check touches_csv
                    cfg_data = json.loads(Path(cfg_path).read_text(encoding="utf-8"))
                    p1b_config_touches.append(cfg_data.get("touches_csv", ""))
                    Path(str(result_p1b_path)).write_text(
                        json.dumps(GOOD_RESULT_P1B), encoding="utf-8"
                    )
                else:
                    Path(str(result_path)).write_text(
                        json.dumps(GOOD_RESULT), encoding="utf-8"
                    )
            m.returncode = 0
            m.stderr = ""
            return m

        with patch("hypothesis_generator.subprocess") as mock_subproc:
            mock_subproc.run.side_effect = _mock_run
            hypothesis_generator.run(
                config_path=str(config_path),
                result_path=str(result_path),
                result_p1b_path=str(result_p1b_path),
                engine_path=str(engine_path),
                repo_root=str(tmp_path),
            )

        # P1b config must have used a different (temp) touches path, not original
        assert len(p1b_config_touches) >= 1, "P1b engine call should have been made"
        assert p1b_config_touches[0] != str(touches_csv), (
            f"P1b config should use filtered temp touches, not original: {p1b_config_touches[0]}"
        )

    def test_temp_files_cleaned_up_on_success(self, tmp_path):
        """Temp files (filtered CSV and temp config) are cleaned up after successful run()."""
        touches_csv = self._make_touches_csv(tmp_path)
        config_path = self._make_config(tmp_path, str(touches_csv))
        result_path = tmp_path / "result.json"
        result_p1b_path = tmp_path / "result_p1b.json"
        engine_path = tmp_path / "fake_engine.py"
        engine_path.write_text("pass", encoding="utf-8")

        temp_paths_seen = []

        def _mock_run(args, **kwargs):
            m = MagicMock()
            if "--output-p1b" in args:
                # Capture temp config path if any
                if "--config" in args:
                    cfg_idx = args.index("--config")
                    temp_paths_seen.append(args[cfg_idx + 1])
                Path(str(result_p1b_path)).write_text(
                    json.dumps(GOOD_RESULT_P1B), encoding="utf-8"
                )
            else:
                Path(str(result_path)).write_text(
                    json.dumps(GOOD_RESULT), encoding="utf-8"
                )
            m.returncode = 0
            m.stderr = ""
            return m

        with patch("hypothesis_generator.subprocess") as mock_subproc:
            mock_subproc.run.side_effect = _mock_run
            hypothesis_generator.run(
                config_path=str(config_path),
                result_path=str(result_path),
                result_p1b_path=str(result_p1b_path),
                engine_path=str(engine_path),
                repo_root=str(tmp_path),
            )

        # Check that temp config and temp CSV are cleaned up
        for temp_path in temp_paths_seen:
            assert not Path(temp_path).exists(), (
                f"Temp file should be cleaned up after success: {temp_path}"
            )

    def test_temp_files_cleaned_up_on_failure(self, tmp_path):
        """Temp files are cleaned up even when engine raises CalledProcessError."""
        import subprocess as real_subprocess

        touches_csv = self._make_touches_csv(tmp_path)
        config_path = self._make_config(tmp_path, str(touches_csv))
        result_path = tmp_path / "result.json"
        result_p1b_path = tmp_path / "result_p1b.json"
        engine_path = tmp_path / "fake_engine.py"
        engine_path.write_text("pass", encoding="utf-8")

        temp_paths_seen = []

        def _mock_run(args, **kwargs):
            # On P1b call, raise CalledProcessError
            if "--output-p1b" in args:
                if "--config" in args:
                    cfg_idx = args.index("--config")
                    temp_paths_seen.append(args[cfg_idx + 1])
                raise real_subprocess.CalledProcessError(1, args)
            else:
                Path(str(result_path)).write_text(
                    json.dumps(GOOD_RESULT), encoding="utf-8"
                )
                m = MagicMock()
                m.returncode = 0
                m.stderr = ""
                return m

        with patch("hypothesis_generator.subprocess") as mock_subproc:
            mock_subproc.run.side_effect = _mock_run
            mock_subproc.CalledProcessError = real_subprocess.CalledProcessError
            with pytest.raises(real_subprocess.CalledProcessError):
                hypothesis_generator.run(
                    config_path=str(config_path),
                    result_path=str(result_path),
                    result_p1b_path=str(result_p1b_path),
                    engine_path=str(engine_path),
                    repo_root=str(tmp_path),
                )

        # Temp files should be cleaned up even on failure
        for temp_path in temp_paths_seen:
            assert not Path(temp_path).exists(), (
                f"Temp file should be cleaned up on failure: {temp_path}"
            )

    def test_engine_failure_propagates(self, tmp_path):
        """Non-zero engine exit raises subprocess.CalledProcessError."""
        import subprocess as real_subprocess

        touches_csv = self._make_touches_csv(tmp_path)
        config_path = self._make_config(tmp_path, str(touches_csv))
        result_path = tmp_path / "result.json"
        result_p1b_path = tmp_path / "result_p1b.json"
        engine_path = tmp_path / "fake_engine.py"
        engine_path.write_text("pass", encoding="utf-8")

        def _mock_run(args, **kwargs):
            # Use check=True simulation: raise if returncode != 0
            raise real_subprocess.CalledProcessError(1, args)

        with patch("hypothesis_generator.subprocess") as mock_subproc:
            mock_subproc.run.side_effect = _mock_run
            mock_subproc.CalledProcessError = real_subprocess.CalledProcessError
            with pytest.raises(real_subprocess.CalledProcessError):
                hypothesis_generator.run(
                    config_path=str(config_path),
                    result_path=str(result_path),
                    result_p1b_path=str(result_p1b_path),
                    engine_path=str(engine_path),
                    repo_root=str(tmp_path),
                )
