"""Loading, schema validation, and layered merging of framework/run_set/scenario
config. This is the only place that knows how the four config layers (local
machine, TDM-version baseline, run_set defaults, scenario overrides) combine."""

import json
from pathlib import Path

import yaml
import jsonschema

from tdmruns.exceptions import ConfigValidationError

SCHEMA_DIR_NAME = "schemas"


def load_yaml(path: Path) -> dict:
    if not path.is_file():
        raise ConfigValidationError(f"Config file not found: {path}")
    with open(path, encoding="utf-8-sig") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ConfigValidationError(f"{path} must contain a YAML mapping at the top level.")
    return data


def _load_schema(repo_root: Path, name: str) -> dict:
    schema_path = repo_root / "config" / SCHEMA_DIR_NAME / name
    with open(schema_path) as f:
        return json.load(f)


def _validate(data: dict, schema: dict, context: str):
    validator = jsonschema.Draft7Validator(schema)
    errors = sorted(validator.iter_errors(data), key=lambda e: list(e.path))
    if errors:
        lines = [f"{context} failed schema validation:"]
        for e in errors:
            loc = "/".join(str(p) for p in e.path) or "(root)"
            lines.append(f"  - {loc}: {e.message}")
        raise ConfigValidationError("\n".join(lines))


def load_framework_config(repo_root: Path) -> dict:
    """Loads config/framework.yaml, then layers config/local.yaml on top if
    present (it is gitignored and machine-specific, so it may not exist)."""
    framework = load_yaml(repo_root / "config" / "framework.yaml")
    local_path = repo_root / "config" / "local.yaml"
    local = load_yaml(local_path) if local_path.is_file() else {}
    framework["_local"] = local
    return framework


def load_run_set(repo_root: Path, run_set_id: str) -> dict:
    from tdmruns.paths import run_set_file

    path = run_set_file(repo_root, run_set_id)
    if not path.is_file():
        raise ConfigValidationError(f"No such run set '{run_set_id}' (expected {path}).")
    data = load_yaml(path)
    schema = _load_schema(repo_root, "run_set.schema.json")
    _validate(data, schema, f"run set '{run_set_id}'")
    if data["run_set_id"] != run_set_id:
        raise ConfigValidationError(
            f"run_set.yaml at {path} declares run_set_id "
            f"'{data['run_set_id']}' but lives under run_sets/{run_set_id}/."
        )
    return data


def load_scenario(repo_root: Path, run_set_id: str, scenario_id: str) -> dict:
    from tdmruns.paths import scenario_file

    path = scenario_file(repo_root, run_set_id, scenario_id)
    if not path.is_file():
        raise ConfigValidationError(
            f"No such scenario '{scenario_id}' in run set '{run_set_id}' (expected {path})."
        )
    data = load_yaml(path)
    schema = _load_schema(repo_root, "scenario.schema.json")
    _validate(data, schema, f"scenario '{run_set_id}/{scenario_id}'")
    if data["scenario_id"] != scenario_id:
        raise ConfigValidationError(
            f"scenario file at {path} declares scenario_id "
            f"'{data['scenario_id']}' but is named {scenario_id}.yaml."
        )
    return data


def list_scenario_ids(repo_root: Path, run_set_id: str) -> list:
    from tdmruns.paths import scenarios_dir

    d = scenarios_dir(repo_root, run_set_id)
    if not d.is_dir():
        return []
    return sorted(p.stem for p in d.glob("*.yaml"))


def resolved_tdm_ref(run_set: dict, scenario: dict) -> str:
    return scenario.get("tdm_ref") or run_set["tdm_ref"]


def resolved_baseline_filename(run_set: dict, scenario: dict) -> str:
    return scenario.get("baseline_control_center") or run_set["baseline_control_center"]


def resolved_start_at_label(scenario: dict) -> str | None:
    """STEPn/STEPn_nn label to resume this scenario's driver script from, or
    None for a normal full run -- see driver_script.py. Scenario-only (no
    run_set-level fallback, unlike driver_script/voyager_exe): which step a
    crashed attempt should resume from is inherently specific to that one
    scenario's own run history, not something a whole run_set would
    meaningfully share."""
    return scenario.get("start_at_label")


def resolved_voyager_exe(framework: dict, run_set: dict, scenario: dict) -> str | None:
    """Absolute path to the Cube Voyager executable to invoke for this
    scenario: scenario-level voyager_exe wins, then the run set's, then
    config/local.yaml's machine-wide Voyager_EXE default. A run set/scenario
    only needs to declare this when its TDM version requires a different
    Cube Voyager install than the machine default -- e.g. a network binary
    format the machine's default install can't read."""
    return (
        scenario.get("voyager_exe")
        or run_set.get("voyager_exe")
        or framework.get("_local", {}).get("Voyager_EXE")
    )


def resolved_driver_script(run_set: dict, scenario: dict) -> str | None:
    """Path (relative to the run_set directory) to a custom _HailMary.s
    driver script, or None if neither the scenario nor the run set declares
    one -- in which case the TDM's own default driver script is used
    unmodified."""
    return scenario.get("driver_script") or run_set.get("driver_script")


def resolved_output_spec(framework: dict, run_set: dict, scenario: dict) -> dict:
    """Scenario output spec overrides the run set's; run set's overrides the
    framework default. include patterns are NOT merged across levels --
    a scenario-level `outputs` block fully replaces the run set's, since a
    partial merge of glob lists would be ambiguous to reason about."""
    spec = run_set.get("outputs", {})
    if "outputs" in scenario:
        spec = scenario["outputs"]
    max_mb = spec.get("max_file_size_mb", framework["outputs"]["max_file_size_mb"])
    if max_mb > framework["outputs"]["max_file_size_mb"]:
        raise ConfigValidationError(
            f"max_file_size_mb ({max_mb}) exceeds the framework-wide ceiling "
            f"({framework['outputs']['max_file_size_mb']}) set in config/framework.yaml."
        )
    return {"include": spec.get("include", []), "max_file_size_mb": max_mb}


def resolved_manual_scenario_folder(
    tdm_path: Path,
    framework: dict,
    run_set_id: str,
    scenario_id: str,
    scenario: dict,
) -> Path:
    """Resolves the raw folder a manually-run scenario's outputs live in,
    relative to the TDM submodule root. Uses the scenario's declared
    manual_scenario_folder if present -- needed when the raw folder's name
    doesn't follow scenario_id (e.g. non-motorized-2023's
    BY_2019_SensitivityTest_NN naming). Otherwise falls back to the same
    scenario_folder_template convention already used for CLI-driven runs
    (Scenarios/<run_set_id>/<scenario_id>), since a manually-run scenario's
    raw folder is reused across every run attempt exactly like a CLI-driven
    one is -- so no per-scenario declaration is needed unless the naming
    departs from that convention."""
    rel = scenario.get("manual_scenario_folder") or framework["scenario_folder_template"].format(
        run_set_id=run_set_id,
        scenario_id=scenario_id,
    )
    return tdm_path / rel


def _resolve_input_files(run_set_dir: Path, input_files: dict) -> dict:
    """Resolve relative paths in an input_files block to absolute paths
    anchored at run_set_dir. Absolute paths are passed through unchanged."""
    resolved = {}
    for key, value in input_files.items():
        p = Path(value)
        resolved[key] = str((run_set_dir / p).resolve() if not p.is_absolute() else p)
    return resolved


def resolved_general_parameter_overrides(run_set: dict, scenario: dict) -> dict:
    """Merges run_set-level and scenario-level general_parameter_overrides
    into a single dict, scenario winning -- unlike Control Center overrides,
    these aren't recorded per-layer in metadata (see general_parameters.py),
    so there's no need to keep them separate the way
    merged_control_center_overrides() does. No input_files-style path
    resolution: GeneralParameters.block values are plain parameters, not
    file selections."""
    merged = dict(run_set.get("general_parameter_overrides", {}))
    merged.update(scenario.get("general_parameter_overrides", {}))
    return merged


def merged_control_center_overrides(run_set: dict, scenario: dict, run_set_dir: Path) -> tuple:
    """Returns (run_set_overrides, scenario_overrides) separately -- kept
    distinct rather than pre-merged so run metadata can show exactly which
    layer each applied key came from.

    Paths declared in input_files sections are resolved to absolute paths
    anchored at run_set_dir and merged into the appropriate override dict."""
    rs_overrides = dict(run_set.get("overrides", {}))
    sc_overrides = dict(scenario.get("overrides", {}))

    rs_input_files = run_set.get("input_files", {})
    if rs_input_files:
        rs_overrides.update(_resolve_input_files(run_set_dir, rs_input_files))

    sc_input_files = scenario.get("input_files", {})
    if sc_input_files:
        sc_overrides.update(_resolve_input_files(run_set_dir, sc_input_files))

    return rs_overrides, sc_overrides
