import pytest

from tdmruns import outputs as out
from tdmruns.exceptions import OutputCollectionError


def _make_scenario_folder(tmp_path):
    folder = tmp_path / "scenario"
    (folder / "reports").mkdir(parents=True)
    (folder / "skims").mkdir()
    (folder / "reports" / "a.csv").write_text("x,y\n1,2\n")
    (folder / "skims" / "big.mtx").write_bytes(b"0" * (2 * 1024 * 1024))
    return folder


def test_inventory_lists_every_file(tmp_path):
    folder = _make_scenario_folder(tmp_path)
    entries = out.inventory(folder)
    paths = {e["relative_path"] for e in entries}
    assert paths == {"reports/a.csv", "skims/big.mtx"}
    for e in entries:
        assert e["size_bytes"] > 0
        assert len(e["sha256"]) == 64


def test_select_matches_glob_only():
    entries = [
        {"relative_path": "reports/a.csv", "size_bytes": 1},
        {"relative_path": "skims/big.mtx", "size_bytes": 1},
    ]
    selected = out.select(entries, ["reports/*.csv"])
    assert [e["relative_path"] for e in selected] == ["reports/a.csv"]


def test_select_with_no_patterns_selects_nothing():
    entries = [{"relative_path": "reports/a.csv", "size_bytes": 1}]
    assert out.select(entries, []) == []


def test_validate_size_limit_raises_for_oversized_file():
    entries = [{"relative_path": "skims/big.mtx", "size_bytes": 2 * 1024 * 1024}]
    with pytest.raises(OutputCollectionError):
        out.validate_size_limit(entries, max_file_size_mb=1)


def test_validate_size_limit_passes_when_under_limit():
    entries = [{"relative_path": "reports/a.csv", "size_bytes": 1024}]
    out.validate_size_limit(entries, max_file_size_mb=1)  # should not raise


def test_copy_selected_preserves_relative_structure(tmp_path):
    folder = _make_scenario_folder(tmp_path)
    entries = out.inventory(folder)
    selected = out.select(entries, ["reports/*.csv"])
    dest = tmp_path / "curated"
    curated = out.copy_selected(folder, selected, dest)
    assert (dest / "reports" / "a.csv").is_file()
    assert curated[0]["repo_path"] == (dest / "reports" / "a.csv").as_posix()
