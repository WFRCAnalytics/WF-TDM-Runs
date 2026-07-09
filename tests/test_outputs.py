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
        assert "sha256" not in e  # inventory() is stat-only; hashing happens at copy time


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


def test_copy_selected_flattens_to_dest_dir(tmp_path):
    folder = _make_scenario_folder(tmp_path)
    entries = out.inventory(folder)
    selected = out.select(entries, ["reports/*.csv"])
    dest = tmp_path / "curated"
    curated = out.copy_selected(folder, selected, dest, max_file_size_mb=1)
    assert (dest / "a.csv").is_file()
    assert not (dest / "reports").exists()
    assert curated[0]["repo_path"] == (dest / "a.csv").as_posix()
    assert len(curated[0]["sha256"]) == 64


def test_copy_selected_raises_on_filename_collision(tmp_path):
    folder = tmp_path / "scenario"
    (folder / "reports").mkdir(parents=True)
    (folder / "skims").mkdir()
    (folder / "reports" / "a.csv").write_text("x,y\n1,2\n")
    (folder / "skims" / "a.csv").write_text("x,y\n3,4\n")
    entries = out.inventory(folder)
    selected = out.select(entries, ["*/a.csv"])
    assert len(selected) == 2
    with pytest.raises(OutputCollectionError):
        out.copy_selected(folder, selected, tmp_path / "curated", max_file_size_mb=1)


# ---------------------------------------------------------------------------
# column-filtered outputs.include entries ({"pattern": ..., "columns": [...]})
# ---------------------------------------------------------------------------


def _make_wide_csv(folder, rel_path, rows=3):
    path = folder / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["TAZID,Metric,Purpose,Total,DriveAlone,SharedRide"]
    for i in range(rows):
        lines.append(f"{i},PMT,HBW,{i * 10},{i},{i}")
    path.write_text("\n".join(lines) + "\n")
    return path


def test_select_attaches_columns_from_pattern_mapping():
    entries = [{"relative_path": "5_AssignHwy/4_Summaries/TAZ-Based Metrics.csv", "size_bytes": 1}]
    include = [{"pattern": "5_AssignHwy/4_Summaries/*.csv", "columns": ["TAZID", "Total"]}]
    selected = out.select(entries, include)
    assert selected[0]["columns"] == ["TAZID", "Total"]


def test_select_plain_string_pattern_has_no_columns():
    entries = [{"relative_path": "reports/a.csv", "size_bytes": 1}]
    selected = out.select(entries, ["reports/*.csv"])
    assert selected[0]["columns"] is None


def test_copy_selected_writes_column_filtered_csv(tmp_path):
    folder = tmp_path / "scenario"
    _make_wide_csv(folder, "5_AssignHwy/4_Summaries/TAZ-Based Metrics.csv")
    entries = out.inventory(folder)
    selected = out.select(
        entries,
        [{"pattern": "5_AssignHwy/4_Summaries/*.csv", "columns": ["TAZID", "Total"]}],
    )
    dest = tmp_path / "curated"
    curated = out.copy_selected(folder, selected, dest, max_file_size_mb=1)

    out_path = dest / "TAZ-Based Metrics_filtered.csv"
    assert out_path.is_file()
    assert out_path.read_text().splitlines()[0] == "TAZID,Total"
    assert curated[0]["repo_path"] == out_path.as_posix()
    assert curated[0]["size_bytes"] == out_path.stat().st_size


def test_validate_size_limit_skips_filtered_entries():
    # Raw size is huge, but this entry is destined to be filtered -- its raw
    # size says nothing about what actually gets committed, so the pre-copy
    # check must not reject it here (copy_selected checks the real bytes).
    entries = [
        {
            "relative_path": "5_AssignHwy/4_Summaries/TAZ-Based Metrics.csv",
            "size_bytes": 200 * 1024 * 1024,
            "columns": ["TAZID", "Total"],
        }
    ]
    out.validate_size_limit(entries, max_file_size_mb=1)  # should not raise


def test_copy_selected_raises_and_cleans_up_when_filtered_output_still_too_big(tmp_path):
    folder = tmp_path / "scenario"
    _make_wide_csv(folder, "5_AssignHwy/4_Summaries/TAZ-Based Metrics.csv", rows=1000)
    entries = out.inventory(folder)
    selected = out.select(
        entries,
        [{"pattern": "5_AssignHwy/4_Summaries/*.csv", "columns": ["TAZID", "Total"]}],
    )
    dest = tmp_path / "curated"
    with pytest.raises(OutputCollectionError):
        out.copy_selected(folder, selected, dest, max_file_size_mb=0.0001)
    assert not (dest / "TAZ-Based Metrics_filtered.csv").exists()


def test_copy_selected_raises_when_declared_column_missing(tmp_path):
    folder = tmp_path / "scenario"
    _make_wide_csv(folder, "5_AssignHwy/4_Summaries/TAZ-Based Metrics.csv")
    entries = out.inventory(folder)
    selected = out.select(
        entries,
        [{"pattern": "5_AssignHwy/4_Summaries/*.csv", "columns": ["TAZID", "NoSuchColumn"]}],
    )
    dest = tmp_path / "curated"
    with pytest.raises(OutputCollectionError, match="NoSuchColumn"):
        out.copy_selected(folder, selected, dest, max_file_size_mb=1)


# ---------------------------------------------------------------------------
# curate() -- shared status/error/curated resolution for run_scenario() and
# import_manual_run()
# ---------------------------------------------------------------------------


def test_curate_stays_success_when_something_matches(tmp_path):
    folder = _make_scenario_folder(tmp_path)
    inventory = out.inventory(folder)
    output_spec = {"include": ["reports/*.csv"], "max_file_size_mb": 1}
    run_dir = tmp_path / "run"

    status, error, curated = out.curate(folder, inventory, output_spec, run_dir, "success", None)

    assert status == "success"
    assert error is None
    assert len(curated) == 1


def test_curate_stays_success_when_no_outputs_declared(tmp_path):
    # A run set legitimately declaring no outputs.include shouldn't be
    # penalized for curating nothing -- only a declared-but-unmatched
    # pattern is a red flag.
    folder = _make_scenario_folder(tmp_path)
    inventory = out.inventory(folder)
    output_spec = {"include": [], "max_file_size_mb": 1}
    run_dir = tmp_path / "run"

    status, error, curated = out.curate(folder, inventory, output_spec, run_dir, "success", None)

    assert status == "success"
    assert error is None
    assert curated == []


def test_curate_fails_when_declared_patterns_match_nothing(tmp_path):
    # Regression test: Close00's exit code was 0 but outputs.include's
    # patterns matched nothing (the model hadn't reached that step yet) --
    # this used to be silently recorded as "success" with curated: [].
    folder = _make_scenario_folder(tmp_path)
    inventory = out.inventory(folder)
    output_spec = {"include": ["nonexistent/*.csv"], "max_file_size_mb": 1}
    run_dir = tmp_path / "run"

    status, error, curated = out.curate(folder, inventory, output_spec, run_dir, "success", None)

    assert status == "failed"
    assert "nonexistent/*.csv" in error
    assert curated == []


def test_curate_preserves_and_appends_to_existing_error_on_no_match(tmp_path):
    folder = _make_scenario_folder(tmp_path)
    inventory = out.inventory(folder)
    output_spec = {"include": ["nonexistent/*.csv"], "max_file_size_mb": 1}
    run_dir = tmp_path / "run"

    status, error, curated = out.curate(
        folder, inventory, output_spec, run_dir, "failed", "model exited with code 2."
    )

    assert status == "failed"
    assert error.startswith("model exited with code 2.")
    assert "nonexistent/*.csv" in error
    assert curated == []


def test_curate_fails_when_curation_itself_raises(tmp_path):
    folder = _make_scenario_folder(tmp_path)
    inventory = out.inventory(folder)
    output_spec = {"include": ["skims/*.mtx"], "max_file_size_mb": 1}  # big.mtx is 2 MB
    run_dir = tmp_path / "run"

    status, error, curated = out.curate(folder, inventory, output_spec, run_dir, "success", None)

    assert status == "failed"
    assert "exceed the 1 MB limit" in error
    assert curated == []
