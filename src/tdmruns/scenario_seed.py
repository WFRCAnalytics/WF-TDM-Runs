"""Seeding a scenario's raw folder from a prior scenario's run.

Some scenario modifications only take effect late in the model pipeline
(e.g. a change applied at mode choice). Rerunning every upstream step from
scratch for those wastes time reproducing output identical to an
already-completed scenario. A scenario may declare start_from_copy: <scenario_id>
to have its raw scenario folder seeded with a full copy of that other
scenario's most recent successful run, before this run's own Control Center
and driver script are written into it.

The source is resolved via that scenario's run_metadata.json (metadata.py),
not a declared manual_scenario_folder -- this works uniformly whether the
source scenario was run through the CLI or imported from a manual run
(import_manual_run() records scenario_folder too). It uses
metadata.latest_successful_run(), which skips past newer failed attempts,
rather than requiring the single most recent run (of any status) to have
succeeded -- a scenario re-run for an unrelated reason (e.g. output curation
tripping the size limit) shouldn't block copying from an earlier success.

Because the raw scenario folder is reused across every run attempt for a
given scenario_id (scenario_folder_template has no run_id component), a
scenario declaring start_from_copy re-copies the source's entire folder on
every one of its own retries too -- which can be tens of GB. A scenario may
additionally declare lock_down_copy: true once its folder already holds the
seeded state it needs, to skip the copy on subsequent runs without removing
the start_from_copy declaration (kept for the record of where it came from).

This mechanism only decides what state a scenario folder starts with. It
does not make Cube Voyager skip any steps -- that logic, if wanted, belongs
in a custom driver_script (see driver_script.py, ADR 0007) the analyst
writes to check for and skip past already-completed steps.
"""

import shutil
from pathlib import Path

from tdmruns import metadata as md
from tdmruns.exceptions import ScenarioSeedError


def seed(repo_root: Path, run_set_id: str, scenario: dict, scenario_folder: Path) -> dict | None:
    """
    Copy a prior scenario's raw folder into scenario_folder, if declared.

    If start_from_copy is declared and lock_down_copy is not set, copies the
    entire raw scenario folder from the source scenario's most recent
    successful run into scenario_folder. Returns {"scenario_id", "run_id"}
    identifying the source for the metadata record, or None if not declared
    or if lock_down_copy suppressed the copy.
    """
    source_scenario_id = scenario.get("start_from_copy")
    if not source_scenario_id:
        return None
    if scenario.get("lock_down_copy"):
        return None

    source_run = md.latest_successful_run(repo_root, run_set_id, source_scenario_id)
    if source_run is None:
        raise ScenarioSeedError(
            f"start_from_copy: '{source_scenario_id}' has no successful recorded run in "
            f"run set '{run_set_id}' -- run or import it successfully before scenarios "
            "can copy from it."
        )

    source_folder = Path(source_run["scenario_folder"])
    if not source_folder.is_dir():
        raise ScenarioSeedError(
            f"start_from_copy: '{source_scenario_id}''s recorded scenario_folder "
            f"{source_folder} no longer exists on disk."
        )

    shutil.copytree(source_folder, scenario_folder, dirs_exist_ok=True)

    return {"scenario_id": source_scenario_id, "run_id": source_run["run_id"]}
