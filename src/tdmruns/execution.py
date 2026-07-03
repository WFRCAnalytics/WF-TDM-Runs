"""Execution orchestration: run-folder creation, command building, invoking
the TDM's fixed batch entry point, and the top-level run_scenario() that ties
config, version resolution, Control Center rendering, execution, output
curation, and metadata together into one auditable attempt."""

import platform
import secrets
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from tdmruns import config as cfg
from tdmruns import controlcenter as cc
from tdmruns import driver_script as ds
from tdmruns import metadata as md
from tdmruns import outputs as out
from tdmruns import prep
from tdmruns import scenario_seed as seed
from tdmruns import submodule as sub
from tdmruns.exceptions import ConfigValidationError, ExecutionError


def generate_run_id() -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    suffix = secrets.token_hex(2)
    return f"{ts}-{suffix}"


def scenario_folder_path(
    repo_root: Path,
    tdm_path: Path,
    framework: dict,
    resolved_version_label: str,
    scenario_id: str,
    run_id: str,
) -> Path:
    rel = framework["scenario_folder_template"].format(
        resolved_version=resolved_version_label, scenario_id=scenario_id, run_id=run_id
    )
    return tdm_path / rel


def _windows_style(path_str: str, trailing_sep: bool = True) -> str:
    s = path_str.replace("/", "\\")
    if trailing_sep and not s.endswith("\\"):
        s += "\\"
    return s


def build_command(
    framework: dict, tdm_path: Path, control_center_path: Path, scenario_folder: Path
) -> list:
    execution_cfg = framework["execution"]
    entry_point_abs = (tdm_path / execution_cfg["entry_point"]).resolve()
    if not entry_point_abs.is_file():
        raise ExecutionError(
            f"TDM batch entry point not found at {entry_point_abs} "
            f"(config/framework.yaml execution.entry_point = '{execution_cfg['entry_point']}')."
        )
    args = [
        a.format(control_center_path=str(control_center_path), scenario_folder=str(scenario_folder))
        for a in execution_cfg["args"]
    ]
    if entry_point_abs.suffix.lower() in (".bat", ".cmd") and platform.system() == "Windows":
        return ["cmd.exe", "/c", str(entry_point_abs), *args]
    if entry_point_abs.suffix.lower() == ".py":
        return [sys.executable, str(entry_point_abs), *args]
    return [str(entry_point_abs), *args]


def invoke(command: list, cwd: Path, log_path: Path, timeout_seconds: int) -> int:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "w") as log:
        log.write(f"command: {command}\ncwd: {cwd}\n\n")
        log.flush()
        try:
            result = subprocess.run(
                command, cwd=str(cwd), stdout=log, stderr=subprocess.STDOUT, timeout=timeout_seconds
            )
            return result.returncode
        except subprocess.TimeoutExpired:
            log.write(f"\n\nTIMED OUT after {timeout_seconds}s\n")
            return -1


def run_scenario(repo_root: Path, run_set_id: str, scenario_id: str, force: bool = False) -> dict:
    """Executes one full attempt of a scenario: resolve version, render
    Control Center, invoke the TDM, curate outputs, write metadata. Returns
    the run metadata dict. Raises on validation failures that should stop
    execution before anything happens (config errors, unknown override keys,
    unresolvable TDM ref); execution and output failures are instead recorded
    in a 'failed' run record so a run set can continue to the next scenario
    rather than aborting."""
    framework = cfg.load_framework_config(repo_root)
    run_set = cfg.load_run_set(repo_root, run_set_id)
    scenario = cfg.load_scenario(repo_root, run_set_id, scenario_id)

    if not force:
        existing = md.latest_run(repo_root, run_set_id, scenario_id)
        if existing and existing["status"] == "success":
            return existing

    tdm_path = repo_root / framework["tdm_submodule_path"]
    requested_ref = cfg.resolved_tdm_ref(run_set, scenario)
    baseline_filename = cfg.resolved_baseline_filename(run_set, scenario)
    rs_dir = repo_root / "run_sets" / run_set_id
    run_set_overrides, scenario_overrides = cfg.merged_control_center_overrides(run_set, scenario, rs_dir)
    output_spec = cfg.resolved_output_spec(framework, run_set, scenario)

    run_id = generate_run_id()
    started_at = md.utc_now_iso()
    fw_commit = md.framework_commit(repo_root)

    # --- version resolution (hard failure stops everything before execution) ---
    version_state = sub.resolve_version(repo_root, tdm_path, requested_ref)
    version_label = sub.short_version_label(version_state)

    # --- render Control Center (hard failure on unknown override keys) ---
    baseline = cc.load_baseline(
        tdm_path, framework["control_center_defaults_dir"], baseline_filename
    )
    cc.validate_overrides(baseline, run_set_overrides, f"run set '{run_set_id}'.overrides")
    cc.validate_overrides(baseline, scenario_overrides, f"scenario '{scenario_id}'.overrides")
    local_layer = framework.get("_local", {})
    cc.validate_overrides(baseline, local_layer, "config/local.yaml")

    # --- prep scripts (hard failure stops this scenario before execution) ---
    prep.run_prep_scripts(run_set, scenario, rs_dir, scenario_id)

    folder = scenario_folder_path(
        repo_root, tdm_path, framework, version_label, scenario_id, run_id
    )
    folder.mkdir(parents=True, exist_ok=True)

    # --- seed from a prior scenario's raw folder, if declared (before this
    # run's own Control Center/driver script are written, so they overwrite
    # any stale copies rather than the other way around) ---
    seeded_from = seed.seed(repo_root, run_set_id, scenario, folder)

    identity_fields = {
        "ScenarioName": scenario_id,
        "ScenarioDir": _windows_style(str(folder.relative_to(tdm_path))),
        "ParentDir": _windows_style(str(tdm_path.resolve())),
    }
    rendered = cc.render(
        baseline, run_set_overrides, scenario_overrides, local_layer, identity_fields
    )
    control_center_path = folder / "_ControlCenter.yaml"
    cc.write_block_file(rendered, control_center_path)

    # --- stage the driver script: declared custom one, or the TDM's default ---
    driver_script_path = ds.stage(
        rs_dir,
        tdm_path,
        framework["control_center_defaults_dir"],
        framework["default_driver_script"],
        run_set,
        scenario,
        folder,
    )

    # --- execute ---
    command = build_command(framework, tdm_path, control_center_path, folder)
    log_path = folder / "logs" / "orchestrator_invocation.log"
    exit_code = invoke(
        command,
        cwd=tdm_path,
        log_path=log_path,
        timeout_seconds=framework["execution"]["timeout_seconds"],
    )
    status = "success" if exit_code == 0 else "failed"
    error = (
        None
        if exit_code == 0
        else f"TDM batch entry point exited with code {exit_code}. See {log_path}."
    )

    # --- inventory + curate outputs (best effort even on failure) ---
    full_inventory = out.inventory(folder)
    selected = out.select(full_inventory, output_spec["include"])
    curated = []
    if selected:
        try:
            out.validate_size_limit(selected, output_spec["max_file_size_mb"])
            run_dir = repo_root / "runs" / run_set_id / scenario_id / run_id
            curated = out.copy_selected(folder, selected, run_dir / "outputs")
        except Exception as e:  # noqa: BLE001 -- recorded in metadata, not swallowed silently
            status = "failed"
            error = (error + " " if error else "") + f"Output curation failed: {e}"

    run_metadata = md.build(
        schema_version=framework["run_metadata_schema_version"],
        run_set_id=run_set_id,
        scenario_id=scenario_id,
        run_id=run_id,
        status=status,
        started_at=started_at,
        framework_commit_sha=fw_commit,
        tdm_state=version_state.as_dict(),
        baseline_file=baseline_filename,
        run_set_overrides=run_set_overrides,
        scenario_overrides=scenario_overrides,
        rendered_path=str(control_center_path),
        driver_script=driver_script_path,
        seeded_from=seeded_from,
        scenario_folder=str(folder),
        command=command,
        exit_code=exit_code,
        log_path=str(log_path),
        inventory_count=len(full_inventory),
        inventory_total_bytes=sum(e["size_bytes"] for e in full_inventory),
        curated=curated,
        finished_at=md.utc_now_iso(),
        error=error,
    )
    run_dir = repo_root / "runs" / run_set_id / scenario_id / run_id
    md.write(run_dir, run_metadata)
    return run_metadata


def import_manual_run(
    repo_root: Path,
    run_set_id: str,
    scenario_id: str,
    scenario_folder: Path = None,
) -> dict:
    """Curates outputs and records metadata for a scenario that was executed
    outside the CLI -- e.g. Cube Voyager invoked directly against a raw
    scenario_folder, because the TDM's real Control Center isn't renderable
    by this framework yet. Applies the same select/size-check/copy sequence
    run_scenario() uses after a real execution, so runs/ stays the one place
    curated outputs land regardless of how the model was actually invoked.
    Does not check out, fetch, or otherwise touch the TDM submodule -- only
    its current (read-only) state is recorded, since a checkout here would
    not reflect what was actually used for this manual run anyway.

    scenario_folder defaults to the scenario's declared manual_scenario_folder
    (relative to the TDM submodule root) when not passed explicitly -- lets
    import_manual_run_set() drive a whole run set without per-scenario paths.

    Unlike run_scenario(), there's no skip-if-already-successful check: this
    is only ever invoked deliberately (there's no automatic trigger for a
    manual run the way there is for CLI execution), so the invocation itself
    is the signal that outputs should be (re-)gathered -- every call creates
    a new timestamped run rather than guessing whether the raw folder
    changed since the last import."""
    framework = cfg.load_framework_config(repo_root)
    run_set = cfg.load_run_set(repo_root, run_set_id)
    scenario = cfg.load_scenario(repo_root, run_set_id, scenario_id)

    tdm_path = repo_root / framework["tdm_submodule_path"]
    if scenario_folder is None:
        scenario_folder = cfg.resolved_manual_scenario_folder(tdm_path, scenario)
        if scenario_folder is None:
            raise ConfigValidationError(
                f"scenario '{scenario_id}' has no --scenario-folder given and no "
                "manual_scenario_folder declared in its YAML -- nothing to import from."
            )

    requested_ref = cfg.resolved_tdm_ref(run_set, scenario)
    baseline_filename = cfg.resolved_baseline_filename(run_set, scenario)
    rs_dir = repo_root / "run_sets" / run_set_id
    run_set_overrides, scenario_overrides = cfg.merged_control_center_overrides(run_set, scenario, rs_dir)
    output_spec = cfg.resolved_output_spec(framework, run_set, scenario)

    run_id = generate_run_id()
    started_at = md.utc_now_iso()
    fw_commit = md.framework_commit(repo_root)
    version_state = sub.current_state(tdm_path, requested_ref)

    full_inventory = out.inventory(scenario_folder)
    selected = out.select(full_inventory, output_spec["include"])
    curated = []
    status, error = "success", None
    if selected:
        try:
            out.validate_size_limit(selected, output_spec["max_file_size_mb"])
            run_dir = repo_root / "runs" / run_set_id / scenario_id / run_id
            curated = out.copy_selected(scenario_folder, selected, run_dir / "outputs")
        except Exception as e:  # noqa: BLE001 -- recorded in metadata, not swallowed silently
            status, error = "failed", f"Output curation failed: {e}"
    else:
        status = "failed"
        error = (
            f"No files under {scenario_folder} matched outputs.include "
            f"{output_spec['include']!r}."
        )

    run_metadata = md.build(
        schema_version=framework["run_metadata_schema_version"],
        run_set_id=run_set_id,
        scenario_id=scenario_id,
        run_id=run_id,
        status=status,
        started_at=started_at,
        framework_commit_sha=fw_commit,
        tdm_state=version_state.as_dict(),
        baseline_file=baseline_filename,
        run_set_overrides=run_set_overrides,
        scenario_overrides=scenario_overrides,
        scenario_folder=str(scenario_folder),
        inventory_count=len(full_inventory),
        inventory_total_bytes=sum(e["size_bytes"] for e in full_inventory),
        curated=curated,
        finished_at=md.utc_now_iso(),
        error=error,
        execution_mode="manual",
    )
    run_dir = repo_root / "runs" / run_set_id / scenario_id / run_id
    md.write(run_dir, run_metadata)
    return run_metadata


def import_manual_run_set(repo_root: Path, run_set_id: str, only: list = None) -> list:
    """Runs import_manual_run() for every scenario in a run set that declares
    a manual_scenario_folder. A scenario missing that field is recorded as a
    skipped result rather than stopping the rest of the run set -- mirrors
    run_scenarios()'s per-scenario failure isolation."""
    scenario_ids = cfg.list_scenario_ids(repo_root, run_set_id)
    if only:
        scenario_ids = [s for s in scenario_ids if s in only]
    results = []
    for scenario_id in scenario_ids:
        try:
            results.append(import_manual_run(repo_root, run_set_id, scenario_id))
        except Exception as e:  # noqa: BLE001 -- one scenario's error shouldn't stop the set
            results.append(
                {
                    "run_set_id": run_set_id,
                    "scenario_id": scenario_id,
                    "run_id": None,
                    "status": "failed",
                    "error": str(e),
                }
            )
    return results


def run_scenarios(repo_root: Path, run_set_id: str, only: list = None, force: bool = False) -> list:
    """Runs every scenario in a run set sequentially. A failed scenario does
    not stop the run set -- successful runs already on disk are untouched,
    and the function returns metadata for every attempted scenario so the
    caller can report a clear success/failure summary."""
    scenario_ids = cfg.list_scenario_ids(repo_root, run_set_id)
    if only:
        scenario_ids = [s for s in scenario_ids if s in only]
    results = []
    for scenario_id in scenario_ids:
        try:
            results.append(run_scenario(repo_root, run_set_id, scenario_id, force=force))
        except Exception as e:  # noqa: BLE001 -- config/version errors stop this scenario, not the run set
            results.append(
                {
                    "run_set_id": run_set_id,
                    "scenario_id": scenario_id,
                    "run_id": None,
                    "status": "failed",
                    "error": str(e),
                }
            )
    return results
