import pytest

from tdmruns import metadata as md
from tdmruns import scenario_seed as seed
from tdmruns.exceptions import ScenarioSeedError


def _write_run(repo_root, run_set_id, scenario_id, run_id, status, scenario_folder):
    run_dir = repo_root / "runs" / run_set_id / scenario_id / run_id
    metadata = md.build(
        schema_version=1,
        run_set_id=run_set_id,
        scenario_id=scenario_id,
        run_id=run_id,
        status=status,
        started_at="2026-01-01T00:00:00+00:00",
        framework_commit_sha="deadbeef",
        tdm_state={},
        baseline_file="BY.block",
        run_set_overrides={},
        scenario_overrides={},
        scenario_folder=str(scenario_folder),
    )
    md.write(run_dir, metadata)


# ---------------------------------------------------------------------------
# metadata.latest_successful_run
# ---------------------------------------------------------------------------


def test_latest_successful_run_skips_newer_failure(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    _write_run(tmp_path, "rs", "Close00", "20260101-000000-aaaa", "success", source)
    _write_run(tmp_path, "rs", "Close00", "20260102-000000-bbbb", "failed", source)

    result = md.latest_successful_run(tmp_path, "rs", "Close00")
    assert result["run_id"] == "20260101-000000-aaaa"


def test_latest_successful_run_none_when_no_success(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    _write_run(tmp_path, "rs", "Close00", "20260101-000000-aaaa", "failed", source)

    assert md.latest_successful_run(tmp_path, "rs", "Close00") is None


# ---------------------------------------------------------------------------
# scenario_seed.seed
# ---------------------------------------------------------------------------


def test_seed_noop_when_not_declared(tmp_path):
    dest = tmp_path / "dest"
    dest.mkdir()
    assert seed.seed(tmp_path, "rs", {}, dest) is None


def test_seed_copies_from_latest_successful_run_despite_newer_failure(tmp_path):
    source = tmp_path / "source"
    (source / "sub").mkdir(parents=True)
    (source / "sub" / "file.txt").write_text("payload")

    _write_run(tmp_path, "rs", "Close00", "20260101-000000-aaaa", "success", source)
    _write_run(tmp_path, "rs", "Close00", "20260102-000000-bbbb", "failed", source)

    dest = tmp_path / "dest"
    dest.mkdir()
    result = seed.seed(tmp_path, "rs", {"start_from_copy": "Close00"}, dest)

    assert result == {"scenario_id": "Close00", "run_id": "20260101-000000-aaaa"}
    assert (dest / "sub" / "file.txt").read_text() == "payload"


def test_seed_raises_when_no_successful_run(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    _write_run(tmp_path, "rs", "Close00", "20260101-000000-aaaa", "failed", source)

    dest = tmp_path / "dest"
    dest.mkdir()
    with pytest.raises(ScenarioSeedError, match="no successful recorded run"):
        seed.seed(tmp_path, "rs", {"start_from_copy": "Close00"}, dest)


def test_seed_raises_when_no_recorded_run_at_all(tmp_path):
    dest = tmp_path / "dest"
    dest.mkdir()
    with pytest.raises(ScenarioSeedError, match="no successful recorded run"):
        seed.seed(tmp_path, "rs", {"start_from_copy": "Close00"}, dest)


def test_seed_raises_when_source_folder_missing(tmp_path):
    missing_source = tmp_path / "gone"
    _write_run(tmp_path, "rs", "Close00", "20260101-000000-aaaa", "success", missing_source)

    dest = tmp_path / "dest"
    dest.mkdir()
    with pytest.raises(ScenarioSeedError, match="no longer exists on disk"):
        seed.seed(tmp_path, "rs", {"start_from_copy": "Close00"}, dest)


def test_lock_down_copy_suppresses_copy(tmp_path):
    source = tmp_path / "source"
    (source / "sub").mkdir(parents=True)
    (source / "sub" / "file.txt").write_text("payload")
    _write_run(tmp_path, "rs", "Close00", "20260101-000000-aaaa", "success", source)

    dest = tmp_path / "dest"
    dest.mkdir()
    (dest / "existing.txt").write_text("keep me")

    result = seed.seed(
        tmp_path, "rs", {"start_from_copy": "Close00", "lock_down_copy": True}, dest
    )

    assert result is None
    assert not (dest / "sub").exists()
    assert (dest / "existing.txt").read_text() == "keep me"


def test_lock_down_copy_alone_without_start_from_copy_is_noop(tmp_path):
    dest = tmp_path / "dest"
    dest.mkdir()
    assert seed.seed(tmp_path, "rs", {"lock_down_copy": True}, dest) is None
