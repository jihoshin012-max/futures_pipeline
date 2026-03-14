# tests/test_backtest_engine.py
"""Integration and unit tests for backtest_engine.py.

Tests cover:
- Holdout guard: blocks P2 paths when flag exists; allows P1 paths
- Config validation: trail step rules enforced at load time
- Adapter validation: stub adapters (NotImplementedError) cause SystemExit naming the adapter (ENGINE-09)
- Unknown simulator module: SystemExit naming the module
- Output schema: result.json has all required keys
- Determinism: two runs with same config produce identical result.json
- Documentation tests: backtest_engine_qa.md, simulation_rules.md, config_schema.md coverage
"""

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

# Add repo root so engine imports resolve
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

# Path constants
HOLDOUT_FLAG_PATH = REPO_ROOT / "stages/04-backtest/p2_holdout/holdout_locked_P2.flag"
ENGINE_PATH = REPO_ROOT / "stages/04-backtest/autoresearch/backtest_engine.py"
P1_TOUCHES = str(REPO_ROOT / "stages/01-data/data/touches/ZRA_Hist_P1.csv")
P1_BARS = str(REPO_ROOT / "stages/01-data/data/bar_data/volume/NQ_BarData_250vol_P1.txt")
P2_TOUCHES = str(REPO_ROOT / "stages/01-data/data/touches/ZRA_Hist_P2.csv")
P2_BARS = str(REPO_ROOT / "stages/01-data/data/bar_data/volume/NQ_BarData_250vol_P2.txt")
SCORING_MODEL = str(REPO_ROOT / "shared/scoring_models/zone_touch_v1.json")
QA_DOC = REPO_ROOT / "stages/04-backtest/references/backtest_engine_qa.md"
SIM_RULES_DOC = REPO_ROOT / "shared/archetypes/zone_touch/simulation_rules.md"
CONFIG_SCHEMA_MD = REPO_ROOT / "stages/04-backtest/references/config_schema.md"
CONFIG_SCHEMA_JSON = REPO_ROOT / "stages/04-backtest/references/config_schema.json"


def make_valid_config(touches_csv=None, bar_data=None, scoring_model=None,
                      simulator_module="zone_touch_simulator",
                      scoring_adapter="BinnedScoringAdapter",
                      active_modes=None, trail_steps=None):
    """Build a minimal valid config dict."""
    if touches_csv is None:
        touches_csv = P1_TOUCHES
    if bar_data is None:
        bar_data = P1_BARS
    if scoring_model is None:
        scoring_model = SCORING_MODEL
    if active_modes is None:
        active_modes = ["M1"]
    if trail_steps is None:
        trail_steps = [
            {"trigger_ticks": 30, "new_stop_ticks": 0},
        ]
    return {
        "version": "v1",
        "instrument": "NQ",
        "touches_csv": touches_csv,
        "bar_data": bar_data,
        "scoring_model_path": scoring_model,
        "archetype": {
            "name": "zone_touch",
            "simulator_module": simulator_module,
            "scoring_adapter": scoring_adapter,
        },
        "active_modes": active_modes,
        "routing": {"score_threshold": 0, "seq_limit": 999},
        "M1": {
            "stop_ticks": 135,
            "leg_targets": [50],
            "trail_steps": trail_steps,
            "time_cap_bars": 80,
        },
    }


def write_config(config_dict, tmp_dir):
    """Write config dict to a temp JSON file and return its path."""
    path = os.path.join(tmp_dir, "config.json")
    with open(path, "w") as f:
        json.dump(config_dict, f)
    return path


def run_engine(config_path, output_path):
    """Import and call main() from backtest_engine.py."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("backtest_engine", ENGINE_PATH)
    mod = importlib.util.load_from_spec_and_exec(spec)
    mod.main(config_path, output_path)


def call_engine_main(config_path, output_path):
    """Call the engine main() function directly via importlib."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("backtest_engine", str(ENGINE_PATH))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.main(config_path, output_path)


# ---------------------------------------------------------------------------
# Holdout Guard Tests
# ---------------------------------------------------------------------------

class TestHoldoutGuard:

    def test_holdout_guard_blocks_p2(self, tmp_path):
        """Holdout flag + P2 path in config → SystemExit with HOLDOUT GUARD."""
        flag = HOLDOUT_FLAG_PATH
        flag.touch()
        try:
            config = make_valid_config(touches_csv=P2_TOUCHES, bar_data=P1_BARS)
            config_path = str(tmp_path / "config.json")
            output_path = str(tmp_path / "result.json")
            with open(config_path, "w") as f:
                json.dump(config, f)

            with pytest.raises(SystemExit) as exc_info:
                call_engine_main(config_path, output_path)

            assert "HOLDOUT GUARD" in str(exc_info.value)
        finally:
            if flag.exists():
                flag.unlink()

    def test_holdout_guard_blocks_p2_bar_data(self, tmp_path):
        """Holdout flag + P2 bar_data path → SystemExit with HOLDOUT GUARD."""
        flag = HOLDOUT_FLAG_PATH
        flag.touch()
        try:
            config = make_valid_config(touches_csv=P1_TOUCHES, bar_data=P2_BARS)
            config_path = str(tmp_path / "config.json")
            output_path = str(tmp_path / "result.json")
            with open(config_path, "w") as f:
                json.dump(config, f)

            with pytest.raises(SystemExit) as exc_info:
                call_engine_main(config_path, output_path)

            assert "HOLDOUT GUARD" in str(exc_info.value)
        finally:
            if flag.exists():
                flag.unlink()

    def test_holdout_guard_allows_p1(self, tmp_path):
        """Holdout flag + P1 paths only → runs normally (no SystemExit from holdout)."""
        flag = HOLDOUT_FLAG_PATH
        flag.touch()
        try:
            config = make_valid_config(touches_csv=P1_TOUCHES, bar_data=P1_BARS)
            config_path = str(tmp_path / "config.json")
            output_path = str(tmp_path / "result.json")
            with open(config_path, "w") as f:
                json.dump(config, f)

            # Should not raise SystemExit from holdout guard
            # (may raise other errors from missing files etc — but not holdout)
            try:
                call_engine_main(config_path, output_path)
            except SystemExit as e:
                assert "HOLDOUT GUARD" not in str(e), f"Holdout guard incorrectly blocked P1: {e}"
        finally:
            if flag.exists():
                flag.unlink()


# ---------------------------------------------------------------------------
# Config Validation Tests
# ---------------------------------------------------------------------------

class TestConfigValidation:

    def test_bad_trail_steps_not_monotonic(self, tmp_path):
        """trail_steps with non-monotonic trigger_ticks → SystemExit."""
        bad_trail = [
            {"trigger_ticks": 60, "new_stop_ticks": 0},
            {"trigger_ticks": 30, "new_stop_ticks": 20},  # 30 < 60 — not increasing
        ]
        config = make_valid_config(trail_steps=bad_trail)
        config_path = str(tmp_path / "config.json")
        output_path = str(tmp_path / "result.json")
        with open(config_path, "w") as f:
            json.dump(config, f)

        with pytest.raises(SystemExit) as exc_info:
            call_engine_main(config_path, output_path)

        assert "trigger_ticks" in str(exc_info.value).lower() or \
               "monoton" in str(exc_info.value).lower() or \
               "trail" in str(exc_info.value).lower()

    def test_new_stop_gte_trigger(self, tmp_path):
        """new_stop_ticks >= trigger_ticks → SystemExit."""
        bad_trail = [
            {"trigger_ticks": 30, "new_stop_ticks": 30},  # new_stop must be < trigger
        ]
        config = make_valid_config(trail_steps=bad_trail)
        config_path = str(tmp_path / "config.json")
        output_path = str(tmp_path / "result.json")
        with open(config_path, "w") as f:
            json.dump(config, f)

        with pytest.raises(SystemExit) as exc_info:
            call_engine_main(config_path, output_path)

        assert "new_stop_ticks" in str(exc_info.value).lower() or \
               "trail" in str(exc_info.value).lower()

    def test_new_stop_negative(self, tmp_path):
        """new_stop_ticks[0] < 0 → SystemExit."""
        bad_trail = [
            {"trigger_ticks": 30, "new_stop_ticks": -5},  # negative not allowed
        ]
        config = make_valid_config(trail_steps=bad_trail)
        config_path = str(tmp_path / "config.json")
        output_path = str(tmp_path / "result.json")
        with open(config_path, "w") as f:
            json.dump(config, f)

        with pytest.raises(SystemExit) as exc_info:
            call_engine_main(config_path, output_path)

        # Should abort with a message about non-negative stop
        assert exc_info.value.code != 0 or "trail" in str(exc_info.value).lower()

    def test_empty_trail_steps_allowed(self, tmp_path):
        """Empty trail_steps is valid (no-trail mode)."""
        config = make_valid_config(trail_steps=[])
        config_path = str(tmp_path / "config.json")
        output_path = str(tmp_path / "result.json")
        with open(config_path, "w") as f:
            json.dump(config, f)

        # Should not raise SystemExit from validation
        try:
            call_engine_main(config_path, output_path)
        except SystemExit as e:
            assert "trail" not in str(e).lower(), f"Empty trail_steps incorrectly rejected: {e}"


# ---------------------------------------------------------------------------
# Adapter Validation Tests (ENGINE-09)
# ---------------------------------------------------------------------------

class TestAdapterValidation:

    def test_adapter_validation_aborts_on_stub(self, tmp_path):
        """Config pointing to SklearnScoringAdapter → SystemExit naming the adapter."""
        config = make_valid_config(scoring_adapter="SklearnScoringAdapter")
        config_path = str(tmp_path / "config.json")
        output_path = str(tmp_path / "result.json")
        with open(config_path, "w") as f:
            json.dump(config, f)

        with pytest.raises(SystemExit) as exc_info:
            call_engine_main(config_path, output_path)

        error_msg = str(exc_info.value)
        assert "SklearnScoringAdapter" in error_msg or "stub" in error_msg.lower()

    def test_adapter_validation_aborts_on_onnx_stub(self, tmp_path):
        """Config pointing to ONNXScoringAdapter → SystemExit naming the adapter."""
        config = make_valid_config(scoring_adapter="ONNXScoringAdapter")
        config_path = str(tmp_path / "config.json")
        output_path = str(tmp_path / "result.json")
        with open(config_path, "w") as f:
            json.dump(config, f)

        with pytest.raises(SystemExit) as exc_info:
            call_engine_main(config_path, output_path)

        error_msg = str(exc_info.value)
        assert "ONNXScoringAdapter" in error_msg or "stub" in error_msg.lower()


# ---------------------------------------------------------------------------
# Unknown Simulator Module Test
# ---------------------------------------------------------------------------

class TestSimulatorLoading:

    def test_unknown_simulator_aborts(self, tmp_path):
        """Config with nonexistent simulator_module → SystemExit naming the module."""
        config = make_valid_config(simulator_module="nonexistent_simulator_xyz")
        config_path = str(tmp_path / "config.json")
        output_path = str(tmp_path / "result.json")
        with open(config_path, "w") as f:
            json.dump(config, f)

        with pytest.raises(SystemExit) as exc_info:
            call_engine_main(config_path, output_path)

        error_msg = str(exc_info.value)
        assert "nonexistent_simulator_xyz" in error_msg or "simulator" in error_msg.lower()


# ---------------------------------------------------------------------------
# Engine Output Tests
# ---------------------------------------------------------------------------

class TestEngineOutput:

    def test_engine_produces_output(self, tmp_path):
        """Valid config → result.json exists with all required keys."""
        config = make_valid_config()
        config_path = str(tmp_path / "config.json")
        output_path = str(tmp_path / "result.json")
        with open(config_path, "w") as f:
            json.dump(config, f)

        call_engine_main(config_path, output_path)

        assert Path(output_path).exists(), "result.json not created"
        with open(output_path) as f:
            result = json.load(f)

        # Required top-level keys (Q6 schema)
        required_keys = {"pf", "n_trades", "win_rate", "total_pnl_ticks",
                         "max_drawdown_ticks", "per_mode"}
        assert required_keys.issubset(set(result.keys())), \
            f"Missing keys: {required_keys - set(result.keys())}"

        # per_mode must have an entry for each active mode
        assert "M1" in result["per_mode"], "per_mode missing M1 key"
        per_mode_m1 = result["per_mode"]["M1"]
        assert "pf" in per_mode_m1
        assert "n_trades" in per_mode_m1
        assert "win_rate" in per_mode_m1

    def test_engine_determinism(self, tmp_path):
        """Two runs with same config produce identical result.json content."""
        config = make_valid_config()
        config_path = str(tmp_path / "config.json")
        output1 = str(tmp_path / "result1.json")
        output2 = str(tmp_path / "result2.json")
        with open(config_path, "w") as f:
            json.dump(config, f)

        call_engine_main(config_path, output1)
        call_engine_main(config_path, output2)

        with open(output1) as f:
            r1 = json.load(f)
        with open(output2) as f:
            r2 = json.load(f)

        assert r1 == r2, f"Results differ between runs:\nRun1: {r1}\nRun2: {r2}"


# ---------------------------------------------------------------------------
# Documentation Tests
# ---------------------------------------------------------------------------

class TestDocumentation:

    def test_qa_doc_complete(self):
        """backtest_engine_qa.md must have Q1 through Q6 sections."""
        assert QA_DOC.exists(), f"QA doc not found at {QA_DOC}"
        content = QA_DOC.read_text(encoding="utf-8")
        for i in range(1, 7):
            assert f"## Q{i}" in content, f"QA doc missing ## Q{i} section"

    def test_simulation_rules_doc(self):
        """simulation_rules.md must exist and have required sections."""
        assert SIM_RULES_DOC.exists(), f"simulation_rules.md not found at {SIM_RULES_DOC}"
        content = SIM_RULES_DOC.read_text(encoding="utf-8")
        required_sections = ["Entry Mechanics", "Exit Mechanics", "Trail Mechanics",
                              "Time Cap", "SimResult Contract"]
        for section in required_sections:
            assert section in content, \
                f"simulation_rules.md missing section: {section}"

    def test_schema_doc_coverage(self):
        """config_schema.md must document all top-level keys from config_schema.json."""
        assert CONFIG_SCHEMA_MD.exists(), f"config_schema.md not found at {CONFIG_SCHEMA_MD}"
        assert CONFIG_SCHEMA_JSON.exists(), f"config_schema.json not found at {CONFIG_SCHEMA_JSON}"

        with open(CONFIG_SCHEMA_JSON) as f:
            schema = json.load(f)
        doc_content = CONFIG_SCHEMA_MD.read_text(encoding="utf-8")

        # Check each top-level key from schema.json is mentioned in schema.md
        for key in schema.keys():
            assert key in doc_content, \
                f"config_schema.md missing documentation for key: '{key}'"
