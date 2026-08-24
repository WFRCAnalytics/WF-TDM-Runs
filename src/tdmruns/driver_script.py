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

declared driver_script is resolved first against run_set_dir (a fully custom
file); if not found there, it's resolved as a bare filename against
defaults_dir instead -- lets a scenario select one of the TDM's own
Scenarios/_default/ variants by name (e.g. the resumable driver script
below) without needing a local copy in the run_set's own folder. Ported from
WF-TDM-Calibration's tdmcalib, whose driver_script.py already did this.

A scenario may also declare start_at_label (STEPn or STEPn_nn, matching a
label inside a *resumable* driver script variant -- e.g. the TDM's own
__HailMary_1Subfolder_resumable.s) to resume a crashed attempt instead of
re-running from the beginning. Absent or 'STEP0' means a normal full run; no
rewrite is performed against the staged driver script in that case, so this
is a no-op unless a resume is actually declared. Any other value rewrites
the staged copy's 'RESUME POINT' GOTO target to that label (the source file
itself, and tdm/, are never modified) -- raises DriverScriptError if the
resolved driver script has no such marker, since a silently-ignored
start_at_label would be worse than an explicit failure. Relies on the raw
scenario folder not being wiped between run attempts (see CLAUDE.md's
"Only the latest attempt's curated outputs..." decision -- run_info/ is what
gets wiped-and-recreated per attempt, never the raw scenario folder itself),
so whatever an earlier crashed attempt already wrote is still there for the
resumed steps to pick up. `tdmruns run-scenario --start-at <label>`
overrides a scenario's own declared start_at_label for one attempt only
(see execution.py's run_scenario()) -- the sanctioned way to do an ad hoc
resume; reserve the scenario YAML's own start_at_label for a run that's
deliberately partial by design (e.g. paired with start_from_copy).
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

# Matches the RESUME POINT marker comment in a resumable driver script
# template (e.g. the TDM's own Scenarios/_default/__HailMary_1Subfolder_
# resumable.s) through its GOTO line, keeping the line's own indentation but
# capturing the label so it can be swapped for start_at_label's value. Cube
# Voyager PILOT's GOTO takes a bare label (no ':' prefix -- that's only for
# the label's own definition).
_RESUME_POINT_RE = re.compile(r"(RESUME POINT:.*?\n[ \t]*GOTO )(:?)([A-Za-z0-9_]+)", re.DOTALL)

# start_at_label value (also the default label a resumable driver script's
# own RESUME POINT marker already points at) meaning "run from the
# beginning" -- no rewrite is performed for this value, same as when
# start_at_label isn't declared at all.
STEP0 = "STEP0"


def _rewrite_resume_point(text: str, label: str, script_path: Path) -> str:
    new_text, n = _RESUME_POINT_RE.subn(rf"\g<1>{label}", text, count=1)
    if n == 0:
        raise DriverScriptError(
            f"start_at_label is '{label}' but {script_path} has no 'RESUME POINT' "
            "GOTO marker to rewrite -- it isn't a resumable driver script variant."
        )
    return new_text


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
    start_at_label: str = None,
) -> str:
    """Copies the resolved driver script into scenario_folder, keeping its
    own filename. Uses the scenario/run_set's declared driver_script if any
    -- resolved first against run_set_dir (a fully custom file), falling
    back to a bare filename against defaults_dir (one of the TDM's own
    Scenarios/_default/ variants, e.g. a resumable one) if not found there
    -- otherwise the TDM's own default_filename under defaults_dir. Always
    stages something. Returns the source path for the metadata record --
    run_set-relative for a custom script, tdm-relative otherwise.

    When general_parameter_overrides is non-empty and/or start_at_label is
    anything other than None/'STEP0', the staged copy's text is rewritten
    (extra READ FILE line for the override file -- see
    _insert_general_parameters_override_read -- and/or the RESUME POINT
    GOTO target -- see _rewrite_resume_point) instead of a plain byte-for-
    byte copy. The source script itself is never modified either way."""
    declared = cfg.resolved_driver_script(run_set, scenario)
    if declared:
        custom_path = run_set_dir / declared
        if custom_path.is_file():
            script_path = custom_path
            source_label = declared
        else:
            script_path = tdm_path / defaults_dir / declared
            source_label = f"{defaults_dir}/{declared}"
    else:
        script_path = tdm_path / defaults_dir / default_filename
        source_label = f"{defaults_dir}/{default_filename}"

    if not script_path.is_file():
        raise DriverScriptError(f"driver_script not found: {script_path}")

    for stale in scenario_folder.glob("*.s"):
        stale.unlink()

    dest_path = scenario_folder / script_path.name
    needs_resume_rewrite = start_at_label not in (None, STEP0)
    if general_parameter_overrides or needs_resume_rewrite:
        text = script_path.read_text()
        if needs_resume_rewrite:
            text = _rewrite_resume_point(text, start_at_label, script_path)
        if general_parameter_overrides:
            text = _insert_general_parameters_override_read(text, script_path)
        dest_path.write_text(text)
    else:
        shutil.copy2(script_path, dest_path)

    return source_label
