# TDM Run Management Framework

Experiment management, execution, reproducibility, and reporting for Travel
Demand Model (TDM) run sets — sensitivity tests, project alternatives,
validation runs, and forecasting scenarios. The TDM itself (Cube
Voyager-based) lives in a separate repository and is connected here as a git
submodule; this repo never modifies the TDM's own model code, Control Center
defaults library, or scenario-folder conventions. It only resolves and
validates TDM versions, renders per-run Control Center overrides, invokes the
TDM's fixed batch entry point, curates a size-bounded subset of outputs,
records structured run metadata, and publishes results via Quarto and GitHub
Pages.

## How it fits together

A run set is a named collection of related runs, each containing one or more
**scenarios** (one complete TDM experiment each). Running a scenario:

1. Resolves and checks out the requested TDM version in the `tdm/` submodule,
   recording the actual commit/tag/branch/dirty state regardless of what was
   requested.
2. Loads the run set's baseline Control Center file from the TDM's
   `Scenarios/_default/` library, layers the run set's shared overrides and
   then the scenario's own overrides on top, validates every override key
   actually exists in that baseline, and renders the result as
   `_ControlCenter.yaml` into a fresh, run-specific folder under
   `Scenarios/{version}/{scenario_id}__{run_id}/`.
3. Invokes the TDM's batch entry point with the rendered control file and
   scenario folder, exactly as a human would run it manually.
4. Inventories every file the model produced, copies only the files matching
   the declared output selection into this repo (rejecting anything over the
   configured size ceiling before it happens), and writes a structured
   `run_metadata.json` — the source of truth for everything downstream.

A new run set or scenario is two or three lines of YAML; no one edits a
Control Center file by hand or navigates into the TDM's model folders.

## Repository layout

```
tdm/                               git submodule -> the TDM repository
config/
  framework.yaml                   global settings (paths, invocation, size limits)
  local.example.yaml               copy to config/local.yaml (gitignored) per machine
  schemas/                         JSON Schema for run_set/scenario/run-metadata config
run_sets/<run_set_id>/
  run_set.yaml                     shared baseline, tdm_ref, overrides, output selection
  scenarios/<scenario_id>.yaml     sparse overrides specific to one scenario
  inputs/                          prepped input files (e.g. SE CSVs)
  prep/                            input preparation notebooks
runs/<run_set_id>/<scenario_id>/<run_id>/
  run_metadata.json                structured record -- the source of truth
  outputs/                         curated, size-bounded copies of selected outputs
src/tdmruns/                       the orchestrator (installable as the `tdmruns` CLI)
reports/                           Quarto project, data-driven from runs/
scripts/                           CI helper scripts (size ceiling, metadata validation)
.github/workflows/                 config validation, run-metadata validation, report publish
docs/architecture/                 ADRs recording why key decisions were made
tests/                             pytest suite, runs entirely against a throwaway mock TDM
```

## Getting started

```bash
git clone <this-repo-url>
cd WF-TDM-Runs
git submodule update --init --recursive

pip install -e .
cp config/local.example.yaml config/local.yaml   # fill in machine-specific values

tdmruns validate-config
tdmruns run-set --run-set non-motorized-2026
tdmruns status
```

`config/local.yaml` is gitignored — it holds machine-specific values
(`Voyager_EXE` path, `UserName`, etc.) that never belong in a scenario
definition.

### CLI reference

```bash
# Validate config (all run sets, or one)
tdmruns validate-config
tdmruns validate-config --run-set <run_set_id>

# Run all scenarios in a run set
tdmruns run-set --run-set <run_set_id>

# Run a single scenario
tdmruns run-scenario --run-set <run_set_id> --scenario <scenario_id>

# Re-run even if the scenario already completed successfully
tdmruns run-scenario --run-set <run_set_id> --scenario <scenario_id> --force

# Show latest result per scenario across all run sets
tdmruns status
```

Each run is assigned a unique `run_id`, so re-running a scenario creates a new
folder under `runs/<run_set_id>/<scenario_id>/` rather than overwriting the
previous result. The full run history is preserved; `tdmruns status` and the
reporting site show the most recent run per scenario.

### Adding a new run set

Create `run_sets/<run_set_id>/run_set.yaml` declaring `tdm_ref`,
`baseline_control_center` (a filename from the TDM's `Scenarios/_default/`
library), any shared `overrides`, and an output selection spec. Add one
`run_sets/<run_set_id>/scenarios/<scenario_id>.yaml` per run, each declaring
only the override keys that differ from the run set. Run
`tdmruns validate-config` before committing — it checks schema validity and
that every override key actually exists in the chosen baseline.

### Running the test suite

```bash
pip install -e ".[dev]"
pytest tests/
```

Every test builds its own throwaway TDM repo and framework repo under
`tmp_path`; nothing touches the example run sets or `tdm/` submodule checked
into this repo.

### Building the report locally

```bash
quarto preview reports
```

Requires the [Quarto CLI](https://quarto.org) plus `pandas` and `jupyter`
installed locally. The published version is built and deployed automatically
by `.github/workflows/publish-report.yml` on every push to `main`.

## Design decisions

The reasoning behind the major choices — in-place sequential submodule
checkout rather than worktrees, the single override mechanism for both input
files and model parameters, output curation with a hard size ceiling rather
than external storage, flat JSON metadata as the source of truth rather than a
database, and GitHub Actions scoped to validation/reporting rather than model
execution — is recorded in `docs/architecture/` as it was decided, with the
reasoning that was specific to this TDM and this team's existing workflow.
Read those before changing any of them.

## What's deliberately out of scope for v1

Parallel or distributed execution, scheduled/automated reruns, cross-version
comparison reporting, and long-term archival of full (uncurated) raw model
outputs are all real future needs the architecture leaves room for, but none
are built in v1. See `docs/architecture/0006-future-scalability.md` for what
would need to change and what wouldn't.
