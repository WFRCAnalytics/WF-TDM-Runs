import json
import sys

import pytest

from tdmruns import metadata as md
from tdmruns import retirement as ret
from tdmruns.exceptions import RetirementError


def _write_script(path, body):
    path.write_text(f"import sys\nfrom pathlib import Path\n{body}\n")


def _run_set(script_rel=None):
    run_set = {"run_set_id": "rs"}
    if script_rel is not None:
        run_set["report_snapshot_script"] = script_rel
    return run_set


def test_snapshot_run_set_requires_declared_script(tmp_path):
    (tmp_path / "run_sets" / "rs").mkdir(parents=True)
    with pytest.raises(RetirementError, match="no report_snapshot_script"):
        ret.snapshot_run_set(tmp_path, _run_set(), "rs")


def test_snapshot_run_set_missing_script_file(tmp_path):
    (tmp_path / "run_sets" / "rs").mkdir(parents=True)
    with pytest.raises(RetirementError, match="not found"):
        ret.snapshot_run_set(tmp_path, _run_set("snap.py"), "rs")


def test_snapshot_run_set_writes_files(tmp_path):
    rs_dir = tmp_path / "run_sets" / "rs"
    rs_dir.mkdir(parents=True)
    script = rs_dir / "snap.py"
    _write_script(script, """
import argparse
p = argparse.ArgumentParser()
p.add_argument('--run-set-dir', required=True)
p.add_argument('--snapshot-dir', required=True)
args = p.parse_args()
(Path(args.snapshot_dir) / 'data.csv').write_text('a,b\\n1,2\\n')
""")
    files = ret.snapshot_run_set(tmp_path, _run_set("snap.py"), "rs")
    assert [f.name for f in files] == ["data.csv"]
    assert (tmp_path / "run_sets" / "rs" / "snapshot" / "data.csv").is_file()


def test_snapshot_run_set_raises_on_nonzero_exit(tmp_path):
    rs_dir = tmp_path / "run_sets" / "rs"
    rs_dir.mkdir(parents=True)
    script = rs_dir / "snap.py"
    _write_script(script, "sys.exit(1)")
    with pytest.raises(RetirementError, match="exited with code 1"):
        ret.snapshot_run_set(tmp_path, _run_set("snap.py"), "rs")


def test_snapshot_run_set_raises_when_script_leaves_dir_empty(tmp_path):
    rs_dir = tmp_path / "run_sets" / "rs"
    rs_dir.mkdir(parents=True)
    script = rs_dir / "snap.py"
    _write_script(script, "pass")
    with pytest.raises(RetirementError, match="empty"):
        ret.snapshot_run_set(tmp_path, _run_set("snap.py"), "rs")


def _write_run(repo_root, run_set_id, scenario_id, run_id, with_outputs=True, retired=False):
    run_dir = repo_root / "runs" / run_set_id / scenario_id / run_id
    outputs_dir = run_dir / "outputs"
    outputs_dir.mkdir(parents=True)
    files = []
    if with_outputs:
        for name, content in [("a.csv", "x" * 100), ("b.csv", "y" * 50)]:
            f = outputs_dir / name
            f.write_text(content)
            files.append({"relative_path": name, "size_bytes": len(content), "sha256": "abc", "repo_path": str(f)})
    metadata = {
        "schema_version": 1,
        "run_set_id": run_set_id,
        "scenario_id": scenario_id,
        "run_id": run_id,
        "status": "success",
        "outputs": {"inventory_count": len(files), "inventory_total_bytes": 150, "curated": files},
    }
    if retired:
        metadata["outputs"]["retired"] = True
        metadata["outputs"]["retired_at"] = "2020-01-01T00:00:00+00:00"
    md.write(run_dir, metadata)
    return run_dir


def _populate_snapshot(repo_root, run_set_id):
    snap_dir = ret.snapshot_dir_path(repo_root, run_set_id)
    snap_dir.mkdir(parents=True)
    (snap_dir / "data.csv").write_text("a,b\n1,2\n")


def test_purge_outputs_requires_populated_snapshot(tmp_path):
    _write_run(tmp_path, "rs", "S01", "20260101-000000-aaaa")
    with pytest.raises(RetirementError, match="snapshot-run-set"):
        ret.purge_outputs(tmp_path, "rs")


def test_purge_outputs_raises_when_no_runs(tmp_path):
    _populate_snapshot(tmp_path, "rs")
    (tmp_path / "runs" / "rs").mkdir(parents=True)
    with pytest.raises(RetirementError, match="No runs found"):
        ret.purge_outputs(tmp_path, "rs")


def test_purge_outputs_deletes_files_and_marks_retired(tmp_path):
    run_dir = _write_run(tmp_path, "rs", "S01", "20260101-000000-aaaa")
    _populate_snapshot(tmp_path, "rs")

    summary = ret.purge_outputs(tmp_path, "rs")

    assert summary == {"runs_purged": 1, "files_removed": 2, "bytes_freed": 150}
    assert not (run_dir / "outputs").exists()

    data = json.loads((run_dir / "run_metadata.json").read_text())
    assert data["outputs"]["retired"] is True
    assert data["outputs"]["retired_at"]
    assert data["outputs"]["curated"][0]["relative_path"] == "a.csv"  # manifest survives


def test_purge_outputs_skips_already_retired_runs(tmp_path):
    run_dir = _write_run(tmp_path, "rs", "S01", "20260101-000000-aaaa", with_outputs=False, retired=True)
    _populate_snapshot(tmp_path, "rs")

    summary = ret.purge_outputs(tmp_path, "rs")

    assert summary == {"runs_purged": 0, "files_removed": 0, "bytes_freed": 0}
