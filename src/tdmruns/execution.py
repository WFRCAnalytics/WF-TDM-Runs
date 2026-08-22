"""
Execution orchestration: run-folder creation, command building, invoking
the TDM's fixed batch entry point, and the top-level run_scenario() that ties
config, version resolution, Control Center rendering, execution, output
curation, and metadata together into one auditable attempt.
"""

import os
import platform
import secrets
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from tdmruns import config as cfg
from tdmruns import controlcenter as cc
from tdmruns import driver_script as ds
from tdmruns import general_parameters as gp
from tdmruns import metadata as md
from tdmruns import model_log as mlog
from tdmruns import outputs as out
from tdmruns import prep
from tdmruns import prn_log
from tdmruns import scenario_seed as seed
from tdmruns import submodule as sub
from tdmruns.exceptions import ExecutionError


def generate_run_id() -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    suffix = secrets.token_hex(2)
    return f"{ts}-{suffix}"


def scenario_folder_path(
    repo_root: Path,
    tdm_path: Path,
    framework: dict,
    resolved_version_label: str,
    run_set_id: str,
    scenario_id: str,
    run_id: str,
) -> Path:
    rel = framework["scenario_folder_template"].format(
        resolved_version=resolved_version_label,
        run_set_id=run_set_id,
        scenario_id=scenario_id,
        run_id=run_id,
    )
    return tdm_path / rel


def _windows_style(path_str: str, trailing_sep: bool = True) -> str:
    s = path_str.replace("/", "\\")
    if trailing_sep and not s.endswith("\\"):
        s += "\\"
    return s


def build_command(
    framework: dict, repo_root: Path, control_center_path: Path, scenario_folder: Path
) -> list:
    execution_cfg = framework["execution"]
    entry_point_abs = (repo_root / execution_cfg["entry_point"]).resolve()
    if not entry_point_abs.is_file():
        raise ExecutionError(
            f"Batch entry point not found at {entry_point_abs} "
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


def invoke(command: list, cwd: Path, log_path: Path, timeout_seconds: int, env: dict = None) -> int:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    full_env = {**os.environ, **env} if env else None
    with open(log_path, "w") as log:
        log.write(f"command: {command}\ncwd: {cwd}\n\n")
        log.flush()
        try:
            result = subprocess.run(
                command,
                cwd=str(cwd),
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=timeout_seconds,
                env=full_env,
            )
            return result.returncode
        except subprocess.TimeoutExpired:
            log.write(f"\n\nTIMED OUT after {timeout_seconds}s\n")
            return -1


def decide_status(
    exit_code: int, model_log_result: dict | None, log_path: Path, scenario_folder: Path
) -> tuple:
    r"""Decides run status/error from the model's own _Log\_RunTime.txt
    completion report -- the only check trusted here. Voyager's own process
    exit code is not reliable on its own: real recorded runs have shown it
    can disagree with the exit code (a clean "TOTAL MODEL RUN TIME" entry
    with a non-zero exit code, and vice versa -- the driver script never
    calls Exit after :ONERROR). A missing or unresolved model-log result
    (see model_log.py -- e.g. Cube never started, was killed before writing
    anything, or its last logged entry was superseded by further step
    activity) is therefore treated as failed rather than falling back to the
    exit code: a run is never called "success" without the model's own
    confirmation. exit_code is still folded into the error text for
    diagnostics.

    Returns (status, error, status_source, model_log_result) -- the last one
    is the input dict with exit_code_mismatch filled in (or None, unchanged).
    """
    if model_log_result is None:
        status = "failed"
        error = (
            f"No resolved model completion report in "
            f"{scenario_folder / '_Log' / '_RunTime.txt'} (see {log_path}). "
            f"Voyager exit code: {exit_code}."
        )
        return status, error, "exit_code", None

    if model_log_result["outcome"] == "crashed":
        status = "failed"
        step = model_log_result["crashed_step"] or "an unrecognized step"
        error = (
            f"Model crashed during {step} (see "
            f"{scenario_folder / '_Log' / '_RunTime.txt'}). Voyager exit code: {exit_code}."
        )
    else:
        status = "success"
        error = None
    model_log_result["exit_code_mismatch"] = (status == "success") != (exit_code == 0)
    return status, error, "model_log", model_log_result


def _append_prn_errors(error: str, scenario_folder: Path) -> str:
    """Folds Voyager's own F(NNN): fatal-error lines from the most recent
    *.PRN file into a failed run's error message, alongside decide_status's
    step-level summary -- see prn_log.py for why that PRN is the right one
    and how a real Voyager error line is told apart from an F(x) function
    reference inside PILOT script code. No-ops (returns error unchanged) if
    there's no PRN file or none of its lines match, e.g. a hang/timeout that
    never got as far as Voyager reporting anything."""
    prn_path, fatal_lines = prn_log.latest_fatal_errors(scenario_folder)
    if not fatal_lines:
        return error
    return f"{error}\n\nVoyager errors ({prn_path.name}):\n" + "\n".join(fatal_lines)


def _reset_run_outputs(run_dir: Path):
    """Clears everything under run_dir except run_info/ (see metadata.py) --
    curated outputs are wiped and rebuilt fresh on every attempt (only the
    latest is ever kept on disk, so retry cruft doesn't accumulate in runs/
    the way per-run_id output copies used to), but run_info/'s per-attempt
    metadata history is permanent and must survive this reset."""
    if not run_dir.exists():
        return
    for child in run_dir.iterdir():
        if child.name == "run_info":
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def run_scenario(
    repo_root: Path,
    run_set_id: str,
    scenario_id: str,
    force: bool = False,
    version_state: "sub.TdmVersionState | None" = None,
) -> dict:
    """
    Executes one full attempt of a scenario: resolve version, render
    Control Center, invoke the TDM, curate outputs, write metadata. Returns
    the run metadata dict. Raises on validation failures that should stop
    execution before anything happens (config errors, unknown override keys,
    unresolvable TDM ref); execution and output failures are instead recorded
    in a 'failed' run record so a run set can continue to the next scenario
    rather than aborting.

    version_state, if given, is used as-is instead of calling
    sub.resolve_version() here -- run_scenarios() passes one in when it has
    already checked out this scenario's resolved tdm_ref once on behalf of a
    whole group of scenarios sharing that ref (see its own docstring for
    why a per-scenario checkout can't run concurrently). Must match this
    scenario's own resolved_tdm_ref(); passing a version_state for the wrong
    ref would silently run this scenario against the wrong TDM version, so
    that's checked explicitly rather than trusted.
    """
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
    run_set_overrides, scenario_overrides = cfg.merged_control_center_overrides(
        run_set, scenario, rs_dir
    )
    general_parameter_overrides = cfg.resolved_general_parameter_overrides(run_set, scenario)
    output_spec = cfg.resolved_output_spec(framework, run_set, scenario)

    run_id = generate_run_id()
    started_at = md.utc_now_iso()
    fw_commit = md.framework_commit(repo_root)

    # --- version resolution (hard failure stops everything before execution) ---
    if version_state is None:
        version_state = sub.resolve_version(repo_root, tdm_path, requested_ref)
    elif version_state.requested_ref != requested_ref:
        message = (
            f"Internal error: pre-resolved version_state is for ref "
            f"'{version_state.requested_ref}' but scenario '{scenario_id}' resolves to "
            f"'{requested_ref}'. Refusing to run against the wrong TDM version."
        )
        raise ExecutionError(message)
    version_label = sub.short_version_label(version_state)

    # --- render Control Center (hard failure on unknown override keys) ---
    baseline = cc.load_baseline(
        tdm_path, framework["control_center_defaults_dir"], baseline_filename
    )
    cc.validate_overrides(baseline, run_set_overrides, f"run set '{run_set_id}'.overrides")
    cc.validate_overrides(baseline, scenario_overrides, f"scenario '{scenario_id}'.overrides")
    local_layer = framework.get("_local", {})
    # Voyager_EXE is a framework-only value (used below for the VOYAGER_EXE
    # env var) -- it is not a real Control Center key, so it's excluded from
    # what gets validated/rendered into the block file.
    cc_local_layer = {k: v for k, v in local_layer.items() if k != "Voyager_EXE"}
    cc.validate_overrides(baseline, cc_local_layer, "config/local.yaml")

    # --- validate General Parameter overrides against the real, shared
    # GeneralParameters.block (hard failure on unknown keys, same as
    # Control Center overrides above) -- see general_parameters.py ---
    if general_parameter_overrides:
        gp_baseline = gp.load_baseline(tdm_path, framework["general_parameters_path"])
        cc.validate_overrides(
            gp_baseline, general_parameter_overrides,
            f"run set '{run_set_id}'/scenario '{scenario_id}'.general_parameter_overrides",
        )

    # --- prep scripts (hard failure stops this scenario before execution) ---
    prep.run_prep_scripts(run_set, scenario, rs_dir, scenario_id)

    folder = scenario_folder_path(
        repo_root, tdm_path, framework, version_label, run_set_id, scenario_id, run_id
    )
    folder.mkdir(parents=True, exist_ok=True)

    # --- seed from a prior scenario's raw folder, if declared (before this
    # run's own Control Center/driver script are written, so they overwrite
    # any stale copies rather than the other way around) ---
    seeded_from = seed.seed(repo_root, run_set_id, scenario, folder)

    identity_fields = {
        "ScenarioName": scenario_id,
        "ScenarioDir": _windows_style(str(folder.resolve()), trailing_sep=False),
        "ModelDir": _windows_style(str(tdm_path.resolve()), trailing_sep=False),
    }
    rendered = cc.render(run_set_overrides, scenario_overrides, cc_local_layer, identity_fields)
    baseline_path = tdm_path / framework["control_center_defaults_dir"] / baseline_filename
    control_center_path = folder / "_ControlCenter.block"
    cc.write_block_file(baseline_path, rendered, control_center_path)

    # --- write the General Parameter override file, if declared (see
    # general_parameters.py) -- driver_script.stage() below inserts the
    # extra READ FILE line that picks this up ---
    if general_parameter_overrides:
        gp.write_override_file(general_parameter_overrides, folder / gp.OVERRIDE_FILENAME)

    # --- stage the driver script: declared custom one, or the TDM's default ---
    driver_script_path = ds.stage(
        rs_dir,
        tdm_path,
        framework["control_center_defaults_dir"],
        framework["default_driver_script"],
        run_set,
        scenario,
        folder,
        general_parameter_overrides=general_parameter_overrides,
    )

    # --- execute ---
    command = build_command(framework, repo_root, control_center_path, folder)
    log_path = folder / "logs" / "orchestrator_invocation.log"
    exit_code = invoke(
        command,
        cwd=tdm_path,
        log_path=log_path,
        timeout_seconds=framework["execution"]["timeout_seconds"],
        env={"VOYAGER_EXE": local_layer.get("Voyager_EXE", "")},
    )
    model_log_result = mlog.read_model_log(folder)
    status, error, status_source, model_log_result = decide_status(
        exit_code, model_log_result, log_path, folder
    )
    if status == "failed":
        error = _append_prn_errors(error, folder)

    # --- inventory + curate outputs (best effort even on failure) ---
    full_inventory = out.inventory(folder)
    run_dir = repo_root / "runs" / run_set_id / scenario_id
    # Only the latest attempt's outputs are ever kept on disk for a
    # scenario -- wipe whatever a previous attempt left (everything but
    # run_info/'s permanent history) before this attempt's own curate()
    # recreates it, so a narrowed outputs.include or a failed re-run can't
    # leave stale files behind.
    _reset_run_outputs(run_dir)
    status, error, curated = out.curate(
        folder, full_inventory, output_spec, run_dir, status, error, repo_root,
        voyager_exe=local_layer.get("Voyager_EXE"),
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
        general_parameter_overrides=general_parameter_overrides,
        rendered_path=str(control_center_path),
        driver_script=driver_script_path,
        seeded_from=seeded_from,
        scenario_folder=str(folder),
        command=command,
        exit_code=exit_code,
        log_path=str(log_path),
        status_source=status_source,
        model_log=model_log_result,
        inventory_count=len(full_inventory),
        inventory_total_bytes=sum(e["size_bytes"] for e in full_inventory),
        curated=curated,
        finished_at=md.utc_now_iso(),
        error=error,
    )
    md.write(run_dir, run_metadata)
    return run_metadata


def import_manual_run(
    repo_root: Path, run_set_id: str, scenario_id: str, scenario_folder: Path = None
) -> dict:
    """
    Curates outputs and records metadata for a scenario that was executed
    outside the CLI -- e.g. Cube Voyager invoked directly against a raw
    scenario_folder, because the TDM's real Control Center isn't renderable
    by this framework yet. Applies the same select/size-check/copy sequence
    run_scenario() uses after a real execution, so runs/ stays the one place
    curated outputs land regardless of how the model was actually invoked.
    Does not check out, fetch, or otherwise touch the TDM submodule -- only
    its current (read-only) state is recorded, since a checkout here would
    not reflect what was actually used for this manual run anyway.

    scenario_folder defaults to the scenario's declared manual_scenario_folder
    (relative to the TDM submodule root) when not passed explicitly, falling
    back further to the scenario_folder_template convention
    (Scenarios/<run_set_id>/<scenario_id>) already used for CLI-driven runs
    when the scenario doesn't declare one at all -- lets import_manual_run_set()
    drive a whole run set without per-scenario paths, and lets a scenario
    whose raw folder happens to follow that naming convention (e.g. Closer00)
    skip declaring manual_scenario_folder entirely.

    Unlike run_scenario(), there's no skip-if-already-successful check: this
    is only ever invoked deliberately (there's no automatic trigger for a
    manual run the way there is for CLI execution), so the invocation itself
    is the signal that outputs should be (re-)gathered -- every call creates
    a new timestamped run rather than guessing whether the raw folder
    changed since the last import.
    """
    framework = cfg.load_framework_config(repo_root)
    run_set = cfg.load_run_set(repo_root, run_set_id)
    scenario = cfg.load_scenario(repo_root, run_set_id, scenario_id)

    tdm_path = repo_root / framework["tdm_submodule_path"]
    if scenario_folder is None:
        scenario_folder = cfg.resolved_manual_scenario_folder(
            tdm_path, framework, run_set_id, scenario_id, scenario
        )

    requested_ref = cfg.resolved_tdm_ref(run_set, scenario)
    baseline_filename = cfg.resolved_baseline_filename(run_set, scenario)
    rs_dir = repo_root / "run_sets" / run_set_id
    run_set_overrides, scenario_overrides = cfg.merged_control_center_overrides(
        run_set, scenario, rs_dir
    )
    general_parameter_overrides = cfg.resolved_general_parameter_overrides(run_set, scenario)
    output_spec = cfg.resolved_output_spec(framework, run_set, scenario)

    run_id = generate_run_id()
    started_at = md.utc_now_iso()
    fw_commit = md.framework_commit(repo_root)
    version_state = sub.current_state(tdm_path, requested_ref)

    local_layer = framework.get("_local", {})
    full_inventory = out.inventory(scenario_folder)
    run_dir = repo_root / "runs" / run_set_id / scenario_id
    # Same "latest attempt only" wipe as run_scenario() -- see its comment.
    _reset_run_outputs(run_dir)
    status, error, curated = out.curate(
        scenario_folder, full_inventory, output_spec, run_dir, "success", None, repo_root,
        voyager_exe=local_layer.get("Voyager_EXE"),
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
        general_parameter_overrides=general_parameter_overrides,
        scenario_folder=str(scenario_folder),
        inventory_count=len(full_inventory),
        inventory_total_bytes=sum(e["size_bytes"] for e in full_inventory),
        curated=curated,
        finished_at=md.utc_now_iso(),
        error=error,
        execution_mode="manual",
    )
    md.write(run_dir, run_metadata)
    return run_metadata


def import_manual_run_set(repo_root: Path, run_set_id: str, only: list = None) -> list:
    """
    Runs import_manual_run() for every scenario in the run set, resolving
    each one's raw folder via resolved_manual_scenario_folder() (declared
    manual_scenario_folder, or the scenario_folder_template convention if
    not declared). A scenario whose resolved folder doesn't actually hold
    the declared outputs.include patterns is recorded as a failed result
    rather than stopping the rest of the run set -- mirrors
    run_scenarios()'s per-scenario failure isolation.
    """
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
    """
    Runs every scenario in a run set. Scenarios are grouped by their
    resolved tdm_ref first -- the TDM submodule can only be checked out to
    one ref at a time, so each distinct ref is checked out exactly once
    (never concurrently, and never once per scenario) before that group's
    own scenarios run. Within a group, up to run_set.yaml's
    max_parallel_runs scenarios run concurrently (default 1, i.e. today's
    fully sequential behavior if the run set doesn't declare it). Groups
    themselves always run one after another, never overlapping -- a later
    group's checkout would otherwise disrupt an earlier group's still-
    running scenarios sharing the same submodule working tree. A run set
    where every scenario shares one tdm_ref (the common case) gets full
    concurrency up to the configured limit in a single group.

    A failed scenario does not stop the run set -- successful runs already
    on disk are untouched, and the function returns metadata for every
    attempted scenario, in original scenario order (regardless of which
    order concurrent scenarios actually finished in), so the caller can
    report a clear success/failure summary. A group whose own ref fails to
    resolve/check out records every scenario in that group as failed with
    that same error, since none of them could have run.
    """
    run_set = cfg.load_run_set(repo_root, run_set_id)
    framework = cfg.load_framework_config(repo_root)
    tdm_path = repo_root / framework["tdm_submodule_path"]
    max_parallel = run_set.get("max_parallel_runs", 1)

    scenario_ids = cfg.list_scenario_ids(repo_root, run_set_id)
    if only:
        scenario_ids = [s for s in scenario_ids if s in only]

    # Group by resolved tdm_ref, preserving each group's first-appearance
    # order so group processing order (and thus checkout order) is
    # deterministic across runs.
    groups = {}
    for scenario_id in scenario_ids:
        scenario = cfg.load_scenario(repo_root, run_set_id, scenario_id)
        ref = cfg.resolved_tdm_ref(run_set, scenario)
        groups.setdefault(ref, []).append(scenario_id)

    results_by_id = {}
    for ref, group_scenario_ids in groups.items():
        try:
            version_state = sub.resolve_version(repo_root, tdm_path, ref)
        except Exception as e:  # noqa: BLE001 -- one ref's checkout failure shouldn't stop other groups
            for scenario_id in group_scenario_ids:
                results_by_id[scenario_id] = {
                    "run_set_id": run_set_id,
                    "scenario_id": scenario_id,
                    "run_id": None,
                    "status": "failed",
                    "error": str(e),
                }
            continue

        workers = min(max_parallel, len(group_scenario_ids))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_to_id = {
                executor.submit(
                    run_scenario, repo_root, run_set_id, scenario_id,
                    force=force, version_state=version_state,
                ): scenario_id
                for scenario_id in group_scenario_ids
            }
            for future in as_completed(future_to_id):
                scenario_id = future_to_id[future]
                try:
                    results_by_id[scenario_id] = future.result()
                except Exception as e:  # noqa: BLE001 -- config/version errors stop this scenario, not the run set
                    results_by_id[scenario_id] = {
                        "run_set_id": run_set_id,
                        "scenario_id": scenario_id,
                        "run_id": None,
                        "status": "failed",
                        "error": str(e),
                    }

    return [results_by_id[scenario_id] for scenario_id in scenario_ids]
