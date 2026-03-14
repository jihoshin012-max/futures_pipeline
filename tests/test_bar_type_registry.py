"""Smoke tests for Phase 01.2 — bar type registry and subfolder structure.

Verifies:
- Physical subfolder layout matches architecture spec
- data_registry.md uses typed source_ids (bar_data_volume, not bar_data)
- Schema file naming convention satisfied
"""
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = REPO_ROOT / "stages/01-data/data/bar_data"
REGISTRY = REPO_ROOT / "_config/data_registry.md"
REFERENCES = REPO_ROOT / "stages/01-data/references"


def test_volume_subfolder_exists():
    assert (DATA_ROOT / "volume").is_dir()


def test_time_subfolder_exists():
    assert (DATA_ROOT / "time").is_dir()


def test_tick_subfolder_exists():
    assert (DATA_ROOT / "tick").is_dir()


def test_p1_bar_file_in_volume_subfolder():
    files = list((DATA_ROOT / "volume").glob("*_P1.txt"))
    assert len(files) >= 1, "No P1 bar file found in bar_data/volume/"


def test_p2_bar_file_in_volume_subfolder():
    files = list((DATA_ROOT / "volume").glob("*_P2.txt"))
    assert len(files) >= 1, "No P2 bar file found in bar_data/volume/"


def test_no_bar_files_in_root_bar_data():
    root_txt_files = list(DATA_ROOT.glob("*.txt"))
    assert len(root_txt_files) == 0, f"Bar files found in flat bar_data/: {root_txt_files}"


def test_registry_contains_bar_data_volume():
    text = REGISTRY.read_text(encoding="utf-8")
    assert "bar_data_volume" in text


def test_registry_does_not_contain_bare_bar_data_source_id():
    text = REGISTRY.read_text(encoding="utf-8")
    # Bare "| bar_data |" row must not exist — only typed variants
    import re
    bare_row = re.search(r"\|\s*bar_data\s*\|", text)
    assert bare_row is None, "Bare 'bar_data' source_id row still in data_registry.md"


def test_bar_data_volume_schema_exists():
    assert (REFERENCES / "bar_data_volume_schema.md").exists()


def test_old_bar_data_schema_renamed():
    # bar_data_schema.md should no longer exist (renamed to bar_data_volume_schema.md)
    assert not (REFERENCES / "bar_data_schema.md").exists(), (
        "bar_data_schema.md should be renamed to bar_data_volume_schema.md"
    )
