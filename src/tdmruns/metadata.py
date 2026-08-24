"""Run metadata: the framework's source of truth. One JSON document per
attempt, schema-versioned, committed to the repo. Reporting reads only this
-- never the TDM submodule or the gitignored scenario working folders
directly.

Every attempt for a (run_set_id, scenario_id) pair keeps its own metadata
document, forever, at runs/{run_set_id}/{scenario_id}/run_info/{run_id}.json
-- a permanent audit trail of every run/import invocation, kept regardless
of outcome. This is the one part of runs/{run_set_id}/{scenario_id}/ that is
never wiped. Curated outputs (runs/{run_set_id}/{scenario_id}/outputs/*, a
sibling of run_info/) are a different story: only the latest attempt's
outputs are ever kept on disk (see execution.py, which wipes and re-curates
them on every attempt) -- so "latest attempt" still matters for outputs/
status purposes even though metadata history is now unbounded.
list_runs()/latest_run() resolve it by run_id, which sorts chronologically
since generate_run_id() (execution.py) prefixes it with a UTC timestamp."""
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def framework_commit(repo_root: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=str(repo_root), capture_output=True, text=True
    )
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def build(
    schema_version: int,
    run_set_id: str,
    scenario_id: str,
    run_id: str,
    status: str,
    started_at: str,
    framework_commit_sha: str,
    tdm_state: dict,
    baseline_file: str,
    run_set_overrides: dict,
    scenario_overrides: dict,
    general_parameter_overrides: dict = None,
    rendered_path: str = None,
    driver_script: str = None,
    start_at_label: str = None,
    start_at_override: bool = False,
    seeded_from: dict = None,
    scenario_folder: str = None,
    command: list = None,
    voyager_exe: str = None,
    exit_code: int = None,
    log_path: str = None,
    status_source: str = None,
    model_log: dict = None,
    inventory_count: int = None,
    inventory_total_bytes: int = None,
    curated: list = None,
    finished_at: str = None,
    error: str = None,
    execution_mode: str = "cli",
) -> dict:
    # rendered_path/command/driver_script are only meaningful when the
    # orchestrator itself rendered a Control Center, staged a driver script,
    # and invoked the model (execution_mode "cli") -- always set together in
    # that case, always absent for a manual import. Left out entirely rather
    # than set to null, since the schema types them as non-nullable.
    control_center = {
        "baseline_file": baseline_file,
        "run_set_overrides": run_set_overrides,
        "scenario_overrides": scenario_overrides,
    }
    if rendered_path is not None:
        control_center["rendered_path"] = rendered_path
    if driver_script is not None:
        control_center["driver_script"] = driver_script
    if start_at_label is not None:
        control_center["start_at_label"] = start_at_label
        control_center["start_at_override"] = start_at_override

    execution = {}
    if command is not None:
        execution["command"] = command
    if voyager_exe is not None:
        execution["voyager_exe"] = voyager_exe
    if exit_code is not None:
        execution["exit_code"] = exit_code
    if log_path is not None:
        execution["log_path"] = log_path
    if status_source is not None:
        execution["status_source"] = status_source
    if model_log is not None:
        execution["model_log"] = model_log

    result = {
        "schema_version": schema_version,
        "run_set_id": run_set_id,
        "scenario_id": scenario_id,
        "run_id": run_id,
        "status": status,
        "execution_mode": execution_mode,
        "started_at": started_at,
        "finished_at": finished_at,
        "framework_commit": framework_commit_sha,
        "tdm": tdm_state,
        "control_center": control_center,
        "scenario_folder": scenario_folder,
        "execution": execution,
        "outputs": {
            "inventory_count": inventory_count,
            "inventory_total_bytes": inventory_total_bytes,
            "curated": curated or [],
        },
        "error": error,
    }
    # seeded_from is only set when start_from_copy was declared for this
    # scenario -- absent otherwise, same "leave out entirely" convention.
    if seeded_from is not None:
        result["seeded_from"] = seeded_from
    # general_parameters is only set when this run actually declares
    # general_parameter_overrides (run_set and/or scenario level, merged) --
    # absent otherwise, same "leave out entirely" convention.
    if general_parameter_overrides:
        result["general_parameters"] = {"overrides": general_parameter_overrides}
    return result


def write(run_dir: Path, metadata: dict):
    run_info_dir = run_dir / "run_info"
    run_info_dir.mkdir(parents=True, exist_ok=True)
    with open(run_info_dir / f"{metadata['run_id']}.json", "w") as f:
        json.dump(metadata, f, indent=2)
        f.write("\n")


def _latest_run_id(run_dir: Path) -> str:
    """The most recent attempt's run_id under run_dir/run_info/, or None if
    none exist. run_id sorts chronologically (see module docstring), so the
    lexicographically-greatest filename stem is the latest attempt."""
    run_info_dir = run_dir / "run_info"
    if not run_info_dir.is_dir():
        return None
    candidates = sorted(run_info_dir.glob("*.json"))
    return candidates[-1].stem if candidates else None


def read(run_dir: Path, run_id: str = None) -> dict:
    """Reads one attempt's metadata document. run_id=None (the default)
    resolves to the latest attempt."""
    run_id = run_id or _latest_run_id(run_dir)
    with open(run_dir / "run_info" / f"{run_id}.json") as f:
        return json.load(f)


def _scenario_run_dir(repo_root: Path, run_set_id: str, scenario_id: str) -> Path:
    return repo_root / "runs" / run_set_id / scenario_id


def list_runs(repo_root: Path, run_set_id: str = None, scenario_id: str = None) -> list:
    """The latest attempt for each (run_set_id, scenario_id) under runs/,
    optionally filtered to one run set or one scenario -- sorted by
    (run_set_id, scenario_id) for a stable order. Full attempt history lives
    in each scenario's own run_info/ -- see list_attempts() -- but this,
    like the old single-file-per-run layout, only ever surfaces the latest
    one per scenario."""
    runs_root = repo_root / "runs"
    if not runs_root.is_dir():
        return []
    rs_ids = [run_set_id] if run_set_id else sorted(p.name for p in runs_root.iterdir() if p.is_dir())
    found = []
    for rs_id in rs_ids:
        rs_dir = runs_root / rs_id
        if not rs_dir.is_dir():
            continue
        scen_ids = (
            [scenario_id] if scenario_id
            else sorted(p.name for p in rs_dir.iterdir() if p.is_dir())
        )
        for scen_id in scen_ids:
            run = latest_run(repo_root, rs_id, scen_id)
            if run is not None:
                found.append(run)
    return found


def list_attempts(repo_root: Path, run_set_id: str, scenario_id: str) -> list:
    """Every attempt ever recorded for (run_set_id, scenario_id),
    newest-first -- the permanent audit trail run_info/ keeps regardless of
    outcome (see module docstring). Newest-first (unlike ported sibling
    tdmcalib's oldest-first list_attempts()) since both of this repo's own
    consumers -- latest_successful_run() below and reports/report_data.py's
    run-history table -- want to see the most recent attempt first."""
    run_dir = _scenario_run_dir(repo_root, run_set_id, scenario_id)
    run_info_dir = run_dir / "run_info"
    if not run_info_dir.is_dir():
        return []
    return [read(run_dir, run_id=p.stem) for p in sorted(run_info_dir.glob("*.json"), reverse=True)]


def latest_run(repo_root: Path, run_set_id: str, scenario_id: str) -> dict:
    run_dir = _scenario_run_dir(repo_root, run_set_id, scenario_id)
    run_id = _latest_run_id(run_dir)
    return read(run_dir, run_id=run_id) if run_id else None


def latest_successful_run(repo_root: Path, run_set_id: str, scenario_id: str) -> dict:
    """
    Like latest_run(), but skips past newer failed attempts.

    Returns the most recent run with status "success" -- a scenario re-run
    for an unrelated reason (e.g. a later attempt that failed) shouldn't
    shadow an earlier successful one.
    """
    for run in list_attempts(repo_root, run_set_id, scenario_id):
        if run["status"] == "success":
            return run
    return None
