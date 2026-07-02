"""Execution of optional input-preparation scripts declared in run_set.yaml
or scenario.yaml.

Scripts are plain Python files. The framework invokes them with two named
arguments so they can locate the run_set's data/inputs/ directory and know which
scenario they are prepping:

    python <script> --run-set-dir <abs-path> --scenario-id <id>

The run_set-level script (if declared) runs first; the scenario-level script
(if declared) runs second. Either or both may be absent -- that is not an
error. A non-zero exit code is a hard failure that stops execution before
the model is touched.
"""

import subprocess
import sys
from pathlib import Path

from tdmruns.exceptions import PrepScriptError


def _run_one(script_path: Path, run_set_dir: Path, scenario_id: str) -> None:
    """Execute a single prep script. Output streams to the caller's terminal."""
    if not script_path.is_file():
        raise PrepScriptError(f"Prep script not found: {script_path}")
    cmd = [
        sys.executable,
        str(script_path),
        "--run-set-dir", str(run_set_dir),
        "--scenario-id", scenario_id,
    ]
    result = subprocess.run(cmd)
    if result.returncode != 0:
        raise PrepScriptError(
            f"Prep script '{script_path.name}' exited with code {result.returncode}."
        )


def run_prep_scripts(run_set: dict, scenario: dict, run_set_dir: Path, scenario_id: str) -> None:
    """Run the run_set-level prep script (if any) then the scenario-level prep
    script (if any). Paths are resolved relative to run_set_dir."""
    rs_script = run_set.get("prep_script")
    sc_script = scenario.get("prep_script")
    if rs_script:
        _run_one(run_set_dir / rs_script, run_set_dir, scenario_id)
    if sc_script:
        _run_one(run_set_dir / sc_script, run_set_dir, scenario_id)
