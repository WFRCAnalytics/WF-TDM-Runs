# TDM sensitivity testing framework

Experiment management, execution, reproducibility, and reporting for Travel
Demand Model (TDM) sensitivity testing. The TDM itself (Cube Voyager-based)
lives in a separate repository and is connected here as a git submodule;
this repo never modifies the TDM's own model code, Control Center defaults
library, or scenario-folder conventions. It only resolves and validates TDM
versions, renders per-run Control Center overrides, invokes the TDM's fixed
batch entry point, curates a size-bounded subset of outputs, records
structured run metadata, and publishes results via Quarto and GitHub Pages.

## How it fits together

A sensitivity test is organized as a **battery** (a named collection of
related runs) containing one or more **scenarios** (one complete TDM
experiment each). Running a scenario:

1. Resolves and checks out the requested TDM version in the `tdm/` submodule, recording the actual commit/tag/branch/dirty state regardless of what was requested.
2. Loads the battery's baseline Control Center file from the TDM's `Scenarios/_defaults/` library, layers the battery's shared overrides and then the scenario's own overrides on top, validates every override key actually exists in that baseline, and renders the result as `_ControlCenter.yaml` into a fresh, run-specific folder under `Scenarios/{version}/{scenario_id}__{run_id}/`.
3. Invokes the TDM's batch entry point with the rendered control file and scenario folder, exactly as a human would run it manually.
4. Inventories every file the model produced, copies only the files matching the declared output selection into this repo (rejecting anything over the configured size ceiling before it happens), and writes a structured `run_metadata.json` -- the source of truth for everything downstream.

A new battery or scenario is two or three lines of YAML; no one edits a
Control Center file by hand or navigates into the TDM's model folders.

## Repository layout

```
tdm/                          git submodule -> the TDM repository
config/
  framework.yaml               global settings (paths, invocation, size limits)
  local.example.yaml           copy to config/local.yaml (gitignored) per machine
  schemas/                     JSON Schema for battery/scenario/run-metadata config
batteries/<battery_id>/
  battery.yaml                 shared baseline, tdm_ref, overrides, output selection
  scenarios/<scenario_id>.yaml sparse overrides specific to one scenario
runs/<battery_id>/<scenario_id>/<run_id>/
  run_metadata.json             structured record -- the source of truth
  outputs/                      curated, size-bounded copies of selected outputs
src/tdmsens/                   the orchestrator (installable as the `tdmsens` CLI)
reports/                       Quarto project, data-driven from runs/
scripts/                       CI helper scripts (size ceiling, metadata validation)
.github/workflows/             config validation, run-metadata validation, report publish
docs/architecture/             ADRs recording why key decisions were made
tests/                         pytest suite, runs entirely against a throwaway mock TDM
```

## Getting started

```bash
git clone <this-repo-url>
cd tdm-sensitivity-framework
git submodule update --init --recursive

pip install -e .
cp config/local.example.yaml config/local.yaml   # fill in Voyager_EXE etc. for this machine

tdmsens validate-config
tdmsens run-battery --battery toll-sensitivity-2026
tdmsens status
```

`config/local.yaml` is gitignored -- it holds machine-specific values
(`Voyager_EXE` path, `UserName`, etc.) that never belong in a scenario
definition.

### Connecting the real TDM repository

`.gitmodules` in this repo points `tdm/` at a placeholder/local path used
for testing. Point it at the real TDM repository before real use:

```bash
git submodule set-url tdm <real-tdm-repo-url>
git submodule sync
git submodule update --init --recursive
```

If the TDM repository is private, CI workflows that check it out (currently
`validate-config.yml`) will need a deploy key or PAT configured as a repo
secret -- see `docs/architecture/0005-ci-scope.md`.

### Adding a new battery

Create `batteries/<battery_id>/battery.yaml` declaring `tdm_ref`,
`baseline_control_center` (a filename from the TDM's `Scenarios/_defaults/`
library), any shared `overrides`, and an output selection spec. Add one
`batteries/<battery_id>/scenarios/<scenario_id>.yaml` per sensitivity test,
each declaring only the override keys that differ from the battery. Run
`tdmsens validate-config` before committing -- it checks schema validity and
that every override key actually exists in the chosen baseline.

### Running the test suite

```bash
pip install -e ".[dev]"
pytest tests/
```

Every test builds its own throwaway TDM repo and framework repo under
`tmp_path`; nothing touches the example battery or `tdm/` submodule checked
into this repo.

### Building the report locally

```bash
quarto preview reports
```

Requires the [Quarto CLI](https://quarto.org) plus `pandas` and `jupyter`
installed locally. The published version is built and deployed automatically
by `.github/workflows/publish-report.yml` on every push to `main`.

## Design decisions

The reasoning behind the major choices -- in-place sequential submodule
checkout rather than worktrees, the two-tier battery/scenario override
model, output curation with a hard size ceiling rather than external
storage, flat JSON metadata as the source of truth rather than a database,
and GitHub Actions scoped to validation/reporting rather than model
execution -- is recorded in `docs/architecture/` as it was decided, with the
reasoning that was specific to this TDM and this team's existing workflow.
Read those before changing any of them.

## What's deliberately out of scope for v1

Parallel or distributed execution, scheduled/automated reruns, cross-version
comparison reporting, and long-term archival of full (uncurated) raw model
outputs are all real future needs the architecture leaves room for, but none
are built in v1. See `docs/architecture/0006-future-scalability.md` for what
would need to change and what wouldn't.
