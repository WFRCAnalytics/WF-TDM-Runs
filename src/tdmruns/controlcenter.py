"""Control Center rendering.

The TDM's Scenarios/_defaults/ library holds known-good, fully-populated
Control Center templates (one per scenario group/year) that an analyst would
normally copy and hand-edit. This module automates exactly that step: load
the chosen default, layer run set and scenario overrides on top, force in the
orchestrator-computed identity/path fields, layer in machine-local values,
and write the result out as the live _ControlCenter.yaml the TDM batch entry
point expects.

Input file selection (e.g. WFRC_SEFile) and sensitivity knobs (e.g.
HOT_Toll_Min) are not treated as separate concerns -- they are both just keys
in this same file, so there is exactly one override mechanism.
"""

from pathlib import Path

import yaml

from tdmruns.exceptions import ControlCenterError


def load_baseline(tdm_path: Path, defaults_dir: str, filename: str) -> dict:
    path = tdm_path / defaults_dir / filename
    if not path.is_file():
        raise ControlCenterError(
            f"Baseline Control Center '{filename}' not found at {path}. "
            f"Check the filename against what actually exists in {tdm_path / defaults_dir}."
        )
    with open(path) as f:
        try:
            data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise ControlCenterError(f"Could not parse {path} as YAML: {e}")
    if not isinstance(data, dict):
        raise ControlCenterError(f"{path} did not parse to a mapping of key/value pairs.")
    return data


def validate_overrides(baseline: dict, overrides: dict, source_label: str):
    unknown = sorted(k for k in overrides if k not in baseline)
    if unknown:
        raise ControlCenterError(
            f"{source_label} sets unknown Control Center key(s) not present in the "
            f"baseline file: {', '.join(unknown)}. This usually means a typo, or the "
            "baseline was changed by the TDM team and this override needs updating."
        )


def render(
    baseline: dict,
    run_set_overrides: dict,
    scenario_overrides: dict,
    local_layer: dict,
    identity_fields: dict,
) -> dict:
    """Layer order, each layer winning over the last: baseline -> run set
    overrides -> scenario overrides -> local/machine values -> orchestrator-
    computed identity fields (which always win, to guarantee folder/path
    consistency regardless of what any override layer set)."""
    merged = dict(baseline)
    merged.update(run_set_overrides)
    merged.update(scenario_overrides)
    merged.update(local_layer)
    merged.update(identity_fields)
    return merged


def write_block_file(rendered: dict, output_path: Path):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        yaml.safe_dump(rendered, f, default_flow_style=False, sort_keys=False, width=4096)
