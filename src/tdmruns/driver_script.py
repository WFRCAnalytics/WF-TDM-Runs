r"""Staging of the driver script (_HailMary.s variant) for a run.

The TDM's Scenarios/_default/ library ships _HailMary_1Subfolder.s, the
driver script variant designed to run one directory level deeper than
Scenarios/_default/ itself -- exactly the depth of the per-run scenario
folder this framework creates (Scenarios/{version}/{scenario_id}__{run_id}/,
see config/framework.yaml's scenario_folder_template). Every run stages a
copy of it into that scenario folder before execution, alongside the
rendered _ControlCenter.yaml.

A run_set or scenario may declare driver_script (scenario overrides run_set)
to stage its own copy instead -- e.g. to add, remove, or replace a step. The
custom file lives in the run_set's own folder (e.g.
run_sets/<id>/hail-mary/_HailMary_1Subfolder_closer.s) and is staged keeping
its own on-disk filename, not renamed to match the default's.

Either way, only the one driver script file itself is staged. Companion or
modified step scripts referenced by a custom driver script are NOT staged --
they stay wherever the run_set keeps them and must be referenced from the
staged file by a relative path computed back to that location, the same way
the default file's own '..\..\..\2_ModelScripts\...' references are relative
to wherever it ends up running from.

A scenario's raw scenario_folder is reused across every run attempt for a
given scenario_id (no run_id component in scenario_folder_template -- see
ADR 0008), so a driver script staged by an earlier attempt (the default,
or a different custom one) can still be sitting there from before.
bin/RunModel.bat locates the driver script by globbing scenario_folder for
*.s, so more than one present is ambiguous. stage() therefore deletes any
*.s files already in scenario_folder before copying the resolved one in,
keeping the invariant that exactly one is ever present.

This is a distinct mechanism from Control Center overrides (controlcenter.py):
it substitutes which code runs, not a parameter value, so it never touches
the overrides dict or its baseline-key validation.
"""

import shutil
from pathlib import Path

from tdmruns import config as cfg
from tdmruns.exceptions import DriverScriptError


def stage(
    run_set_dir: Path,
    tdm_path: Path,
    defaults_dir: str,
    default_filename: str,
    run_set: dict,
    scenario: dict,
    scenario_folder: Path,
) -> str:
    """Copies the resolved driver script into scenario_folder, keeping its
    own filename. Uses the scenario/run_set's declared driver_script if any,
    otherwise the TDM's own default_filename under defaults_dir. Always
    stages something. Returns the source path for the metadata record --
    run_set-relative for a custom script, tdm-relative for the default."""
    declared = cfg.resolved_driver_script(run_set, scenario)
    if declared:
        script_path = run_set_dir / declared
        source_label = declared
    else:
        script_path = tdm_path / defaults_dir / default_filename
        source_label = f"{defaults_dir}/{default_filename}"

    if not script_path.is_file():
        raise DriverScriptError(f"driver_script not found: {script_path}")

    for stale in scenario_folder.glob("*.s"):
        stale.unlink()

    shutil.copy2(script_path, scenario_folder / script_path.name)

    return source_label
