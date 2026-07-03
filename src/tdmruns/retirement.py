"""Retiring a run set: freezing a small permanent snapshot of whatever its
reports need, then purging the (often large) curated output files under
runs/ now that the snapshot covers what reporting actually reads.

Two-step by design: snapshot_run_set() is safe and repeatable (no deletion),
so it can be run and its output reviewed via a report re-render before ever
calling purge_outputs(), which is the one irreversible-ish step here. Purge
never deletes run_metadata.json itself -- only the outputs/ files it
describes -- so every run's provenance (TDM ref, overrides, checksums)
survives as a permanent, tiny record even after the bytes are gone.
"""

import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from tdmruns import metadata as md
from tdmruns.exceptions import RetirementError


def snapshot_dir_path(repo_root: Path, run_set_id: str) -> Path:
    return repo_root / "run_sets" / run_set_id / "snapshot"


def _snapshot_is_populated(snapshot_dir: Path) -> bool:
    return snapshot_dir.is_dir() and any(p.is_file() for p in snapshot_dir.iterdir())


def snapshot_run_set(repo_root: Path, run_set: dict, run_set_id: str) -> list:
    """Invokes the run set's declared report_snapshot_script -- a subprocess,
    not an import, exactly like prep_script -- to (re)write
    run_sets/<id>/snapshot/. Returns the list of files present in the
    snapshot directory afterward. Raises RetirementError if no script is
    declared, the script is missing, or it exits non-zero."""
    script_rel = run_set.get("report_snapshot_script")
    if not script_rel:
        raise RetirementError(
            f"run set '{run_set_id}' has no report_snapshot_script declared in run_set.yaml -- "
            "nothing to snapshot. Add one before retiring this run set."
        )
    run_set_dir = repo_root / "run_sets" / run_set_id
    script_path = run_set_dir / script_rel
    if not script_path.is_file():
        raise RetirementError(f"report_snapshot_script not found: {script_path}")

    snap_dir = snapshot_dir_path(repo_root, run_set_id)
    snap_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable, str(script_path),
        "--run-set-dir", str(run_set_dir),
        "--snapshot-dir", str(snap_dir),
    ]
    result = subprocess.run(cmd)
    if result.returncode != 0:
        raise RetirementError(
            f"report_snapshot_script '{script_rel}' exited with code {result.returncode}."
        )
    if not _snapshot_is_populated(snap_dir):
        raise RetirementError(
            f"report_snapshot_script '{script_rel}' ran but left {snap_dir} empty."
        )
    return sorted(p for p in snap_dir.iterdir() if p.is_file())


def purge_outputs(repo_root: Path, run_set_id: str) -> dict:
    """Deletes every curated output file under runs/<run_set_id>/**/outputs/
    and marks each run's metadata as retired. Refuses unless a populated
    snapshot already exists, since that snapshot becomes the only surviving
    copy of what those reports read. Returns a summary dict (runs_purged,
    files_removed, bytes_freed)."""
    snap_dir = snapshot_dir_path(repo_root, run_set_id)
    if not _snapshot_is_populated(snap_dir):
        raise RetirementError(
            f"No populated snapshot at {snap_dir} -- run `tdmruns snapshot-run-set "
            f"--run-set {run_set_id}` first."
        )

    runs_root = repo_root / "runs" / run_set_id
    metadata_paths = sorted(runs_root.glob("*/*/run_metadata.json"))
    if not metadata_paths:
        raise RetirementError(f"No runs found under {runs_root}.")

    runs_purged = 0
    files_removed = 0
    bytes_freed = 0
    retired_at = datetime.now(timezone.utc).isoformat()

    for meta_path in metadata_paths:
        run_dir = meta_path.parent
        data = md.read(run_dir)
        if data.get("outputs", {}).get("retired"):
            continue

        outputs_dir = run_dir / "outputs"
        if outputs_dir.is_dir():
            for f in outputs_dir.iterdir():
                if f.is_file():
                    files_removed += 1
                    bytes_freed += f.stat().st_size
            shutil.rmtree(outputs_dir)

        data["outputs"]["retired"] = True
        data["outputs"]["retired_at"] = retired_at
        md.write(run_dir, data)
        runs_purged += 1

    return {
        "runs_purged": runs_purged,
        "files_removed": files_removed,
        "bytes_freed": bytes_freed,
    }
