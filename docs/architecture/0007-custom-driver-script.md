# 0007: Driver script staged every run, default or custom -- a second, narrow mechanism

## Context

`_HailMary.s`-family scripts, in the TDM's `Scenarios/_default/` library,
are the driver: they `READ FILE` the Control Center block, then sequentially
`READ FILE` every model-step `.s` script under `2_ModelScripts/`. A run_set
may need to add, remove, or replace a step -- something no Control Center
key can express, since ADR 0002's override mechanism only ever substitutes
*values* for keys already present in the baseline, not which code executes.

`_default/` actually holds two variants: `_HailMary.s` and
`_HailMary_1Subfolder.s`. The `1Subfolder` variant's `READ FILE` lines are
already written one level deeper (`..\..\..\2_ModelScripts\...`, three
levels up) than `_HailMary.s`'s (`..\..\2_ModelScripts\...`, two levels up)
-- confirmed by reading the file directly. That depth matches exactly where
the per-run scenario folder this framework creates
(`Scenarios/{version}/{scenario_id}__{run_id}/`, from
`config/framework.yaml`'s `scenario_folder_template`) sits: one directory
level deeper below the TDM root than `Scenarios/_default/` itself. So
`_HailMary_1Subfolder.s` is already the right variant to run from that
folder, unmodified.

## Decision

Every run stages a driver script into its scenario folder before execution
-- there is no "do nothing" case:

- **Default**: the framework copies `Scenarios/_default/<default_driver_script>`
  (`config/framework.yaml`'s `default_driver_script`, currently
  `_HailMary_1Subfolder.s`) into the scenario folder, keeping that filename.
- **Custom**: a run_set (or scenario, overriding the run_set's default) may
  declare `driver_script`, a path relative to the run_set directory (e.g.
  `run_sets/<id>/hail-mary/_HailMary_1Subfolder_closer.s`). When declared,
  the framework stages that file instead, into the same destination,
  **keeping its own on-disk filename** -- it is not renamed to match the
  default's.

Either way, staging happens right after the Control Center is written and
before the model is invoked (`driver_script.py`'s `stage()`, called from
`execution.py`'s `run_scenario()`).

**Only the one driver script file is staged, never its companions.** Any
new or modified step scripts a custom driver script needs stay wherever the
run_set keeps them (e.g. alongside it in `run_sets/<id>/hail-mary/`) and are
referenced from the staged file by a relative path computed back to that
location -- the same way the default file's own
`..\..\..\2_ModelScripts\...` references are relative to wherever it ends
up running from. The framework does not resolve or rewrite these paths; the
author of a custom driver script is responsible for getting them right, the
same as any other `READ FILE` path in a `.s` script.

This is deliberately **not** folded into the `overrides` mechanism from ADR
0002. Overrides are validated as a closed whitelist against baseline keys
(`controlcenter.validate_overrides()`) because they only ever change a
parameter's value within a known schema. Swapping the driver script changes
what code runs -- a different kind of change, with no baseline key to
validate against -- so it gets its own declared field and its own staging
step rather than being shoehorned into the overrides dict.

`run_metadata.json`'s `control_center.driver_script` always records which
driver script was actually staged for a run -- the default's TDM-relative
path, or the custom one's run_set-relative path -- keeping the same "record
everything that was actually used" property ADR 0002 established for
overrides.

## Consequences

A run_set that needs a structurally different model run (a new step, a
skipped step, a reordered sequence) gets there by committing a custom
driver script (and any companion `.s` files it references) under its own
folder, reviewable in a PR diff like everything else this framework
manages -- no hand-edit of the TDM's shared `_default/` library, and no risk
to any other run_set or scenario. Because staging always happens, the
framework is self-contained for driver-script provisioning regardless of
what the TDM's own batch entry point does on its own.

The cost is that authoring a correct custom driver script requires getting
two different relative-path depths right by hand (one for default step
scripts, one for companion scripts back in the run_set's own folder), and
there is no validation of either -- an incorrect path is a Cube Voyager
error, discoverable only by actually running the model.

There is also one open dependency this repo doesn't control: `RunModel.bat`
(the TDM's fixed batch entry point) does not exist yet in the current
checkout (a separate, pre-existing blocker). This design assumes the entry
point runs whichever driver script it finds staged in the scenario folder
it's given, under whatever filename that file happens to have (default and
custom scripts are staged under different names -- `_HailMary_1Subfolder.s`
vs. e.g. `_HailMary_1Subfolder_closer.s`). That needs confirming once the
entry point exists.
