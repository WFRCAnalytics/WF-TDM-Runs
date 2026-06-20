# 0002: Battery/scenario override layers, not manual Control Center editing

## Context

The TDM's Control Center file (`_ControlCenter.yaml`, distributed as
templates under `Scenarios/_defaults/`) is normally copied and hand-edited
by an analyst when setting up a new scenario. The framework's brief calls
for defining scenarios through configuration rather than manual modification
of model files, but the existing workflow is exactly that manual edit.

The brief also originally separated "input management" (selecting alternate
input files) from "Control Center overrides" (sensitivity knobs) as two
different objectives. Looking at a real Control Center file, both are just
keys in the same flat document -- `WFRC_SEFile` (an input selection) and
`HOT_Toll_Min` (a sensitivity knob) are equally just entries to override.

## Decision

There is exactly one override mechanism: a sparse `overrides` map in
`battery.yaml` (shared across every scenario in the battery) and another in
each `scenario.yaml` (specific to that one test). The orchestrator renders
the final `_ControlCenter.yaml` automatically: baseline default -> battery
overrides -> scenario overrides -> machine-local values -> orchestrator-
computed identity/path fields (which always win, regardless of what any
override layer set). Every override key is validated against the chosen
baseline before anything runs; an unknown key is a hard failure.

## Consequences

Adding a sensitivity test is two or three lines of YAML, reviewable in a PR
diff, with no trip into the TDM's model folders. "Record all applied
overrides" and "include overrides in reports" are satisfied directly --
the override set in run metadata is exactly what was declared, not
something diffed out after the fact.

The cost is that the framework now owns generating a file the TDM team may
also still hand-edit for non-sensitivity, ad hoc runs. The two workflows
don't conflict (the framework only ever writes into its own
`{scenario_id}__{run_id}` folders, never into a baseline default or an
analyst's manually-created folder), but it's worth the TDM team knowing both
paths to a working `_ControlCenter.yaml` exist.
