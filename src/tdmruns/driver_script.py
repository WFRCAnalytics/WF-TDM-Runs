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

When a run declares a non-empty general_parameter_overrides, stage() also
inserts an extra `READ FILE = '{general_parameters.OVERRIDE_FILENAME}'` line
right after the driver script's own GeneralParameters.block READ -- see
general_parameters.py for why this, not a per-run copy of
GeneralParameters.block itself, is how those overrides are applied. The
source driver script file itself is never modified; only the staged copy is.
"""

import re
import shutil
from pathlib import Path

from tdmruns import config as cfg
from tdmruns import general_parameters as gp
from tdmruns.exceptions import DriverScriptError

# Matches the driver script's own `READ FILE = '...GeneralParameters.block'`
# line (see general_parameters.py) so an extra READ FILE for this run's
# override file can be inserted right after it, keeping the same
# indentation. Path prefix is left open (`[^']*`) since it's a relative path
# that depends on the working-folder depth convention -- only the filename
# itself is fixed.
_GENERAL_PARAMETERS_READ_RE = re.compile(
    r"^([ \t]*)READ FILE[ \t]*=[ \t]*'[^']*GeneralParameters\.block'[ \t]*$", re.MULTILINE
)


def _insert_general_parameters_override_read(text: str, script_path: Path) -> str:
    """Inserts an extra `READ FILE = '{gp.OVERRIDE_FILENAME}'` line right
    after the driver script's own GeneralParameters.block READ, matching
    that line's indentation."""

    def _insert(m: re.Match) -> str:
        indent = m.group(1)
        return f"{m.group(0)}\n{indent}READ FILE = '{gp.OVERRIDE_FILENAME}'"

    new_text, n = _GENERAL_PARAMETERS_READ_RE.subn(_insert, text, count=1)
    if n == 0:
        raise DriverScriptError(
            f"general_parameter_overrides is set but {script_path} has no "
            "\"READ FILE = '...GeneralParameters.block'\" line to insert the override "
            "READ FILE after -- it isn't a recognized driver script variant."
        )
    return new_text


def stage(
    run_set_dir: Path,
    tdm_path: Path,
    defaults_dir: str,
    default_filename: str,
    run_set: dict,
    scenario: dict,
    scenario_folder: Path,
    general_parameter_overrides: dict = None,
) -> str:
    """Copies the resolved driver script into scenario_folder, keeping its
    own filename. Uses the scenario/run_set's declared driver_script if any,
    otherwise the TDM's own default_filename under defaults_dir. Always
    stages something. Returns the source path for the metadata record --
    run_set-relative for a custom script, tdm-relative for the default.

    When general_parameter_overrides is non-empty, the staged copy's text is
    rewritten to insert an extra READ FILE line for the override file (see
    _insert_general_parameters_override_read) instead of a plain byte-for-
    byte copy -- the source script itself is never modified."""
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

    dest_path = scenario_folder / script_path.name
    if general_parameter_overrides:
        text = _insert_general_parameters_override_read(script_path.read_text(), script_path)
        dest_path.write_text(text)
    else:
        shutil.copy2(script_path, dest_path)

    return source_label
