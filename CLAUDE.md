# CLAUDE.md — TDM Run Management Framework project context

This file gives a future Claude session (or a returning one) full context on
what this project is, what has been built, what decisions were made and why,
and exactly where to pick up work. Read this before touching anything.

---

## What this project is

A two-part body of work for WFRC/MAG:

**Part 1 — The framework itself** (this repo, `m:\GitHub\WF-TDM-Runs`): a working
Python-based GitHub repository that manages Travel Demand Model (TDM) run sets —
sensitivity tests, project alternatives, validation runs, forecasting scenarios —
against a Cube Voyager TDM connected as a git submodule. Built and documented;
`tdm/` now points at the real TDM (see "What's currently mocked vs. real"),
which surfaced a real-vs-mock incompatibility the test suite doesn't cover yet.

**Part 2 — A presentation** (`_dev/tdm-run-management-framework-proposal.qmd` +
`_dev/styles.css`): a Quarto RevealJS slide deck proposing the framework to
WFRC/MAG's analytics group, targeting pilot approval. 15 slides, WFRC brand
colors, designed for a mixed audience of analysts, developers, and leadership.

---

## Background and motivation

The immediate trigger was a 14-scenario non-motorized sensitivity study that
took over a month — manually configuring each Control Center file, coordinating
SE data inputs, tracking which model version ran which scenario, and reassembling
scattered outputs for reporting. The framework was designed so that study could
be repeated in a fraction of the time with a complete, publishable record.

---

## The framework (Part 1)

### What it does

Sits around the existing TDM (never modifies it). For each scenario run:

1. Validates all config and override keys before touching anything
2. Resolves and checks out the requested TDM git tag in the submodule — refuses
   on a dirty working tree
3. Loads a baseline Control Center file from the TDM's `Scenarios/_default/`
   library, layers run_set overrides then scenario overrides on top (resolving
   any `input_files` relative paths to absolute), fills in orchestrator-computed
   identity/path fields, writes `_ControlCenter.yaml` into a fresh run folder
4. Invokes the TDM's fixed batch entry point with the control file path and
   scenario folder path as arguments
5. Inventories all outputs, copies only the glob-selected subset (hard 100
   MB/file ceiling) into the repo
6. Writes `run_metadata.json` — the source of truth for reporting

### What it doesn't touch

The TDM codebase, the `_default/` library, how Cube Voyager runs internally,
or the `Scenarios/` gitignored working folder convention.

### Key real-world constraints that shaped the design

- The TDM is **Cube Voyager**, run via one fixed batch entry point per version,
  taking exactly two arguments: a Control Center file path and a scenario folder
  path. That calling convention is captured in `config/framework.yaml`
  `execution:` — not hardcoded.
- The `_ControlCenter.yaml` the orchestrator **writes** is plain YAML. The
  baseline `.block` files it **reads** from the defaults library were assumed
  to also be plain YAML with a `.block` extension — confirmed true for the
  mock TDM, but **not true for the real TDM** (see "What's currently mocked
  vs. real" below): the real `1ControlCenter - BY_2019.block` is Cube
  Voyager's native indented `KEY = value` block format with `;` comments, not
  YAML. `controlcenter.py`'s `load_baseline()` calls `yaml.safe_load()` on it
  directly and fails. This is the current top blocker for running anything
  through the CLI against the real TDM.
- Input file selection (e.g. `WFRC_SEFile`) and sensitivity knobs (e.g.
  `HOT_Toll_Min`) are both just keys in the same flat YAML file. There is
  exactly one override mechanism, not two.
- Raw model outputs can be tens of gigabytes. They stay in the gitignored
  `Scenarios/` working folder. Only small, deliberately selected files (CSVs,
  logs) get curated into the framework repo.
- Cube Voyager is licensed per machine. Execution happens on a researcher's
  workstation or on-prem server. GitHub Actions is scoped to validation and
  reporting only — never model execution.

### Repository layout

```
wf-tdm-runs/
├── tdm/                          ← TDM git submodule (real TDM; see "What's currently mocked vs. real")
├── config/
│   ├── framework.yaml            ← global settings
│   ├── local.example.yaml        ← copy to local.yaml (gitignored) per machine
│   └── schemas/                  ← JSON Schema for run_set, scenario, run_metadata
├── run_sets/
│   └── <run_set_id>/
│       ├── run_set.yaml          ← config: shared tdm_ref/baseline/overrides
│       ├── scenarios/            ← config: one YAML file per scenario
│       │   └── <scenario_id>.yaml
│       ├── inputs/               ← prepped input files (e.g. SE CSVs); committed, not gitignored
│       └── input_prep.ipynb      ← input preparation notebook (committed; optional)
├── runs/                         ← committed metadata + curated outputs only, whether
│   │                                gathered by a CLI-driven run or import-manual-run(-set)
│   └── <run_set_id>/<scenario_id>/<run_id>/
│       ├── run_metadata.json     ← execution_mode: "cli" or "manual"
│       └── outputs/
├── reports/                      ← Quarto website
│   ├── _quarto.yml
│   ├── index.qmd                 ← auto-discovers CLI-run run sets from runs/;
│   │                                run sets with custom pages (e.g. non-motorized-2023)
│   │                                are linked in manually instead
│   ├── report_data.py            ← shared data helpers (reads runs/ metadata)
│   └── run_sets/
│       ├── <run_set_id>.qmd      ← generic per-run-set page, data-driven from runs/
│       └── <run_set_id>/         ← custom per-run-set pages (e.g. slides.qmd +
│                                    summary.qmd for non-motorized-2023), reading the
│                                    latest curated outputs via report_data.py and
│                                    applying any report-specific filtering at render
│                                    time rather than pre-filtering a committed copy
├── src/tdmruns/                  ← orchestrator CLI
│   ├── cli.py
│   ├── config.py
│   ├── controlcenter.py
│   ├── submodule.py
│   ├── execution.py
│   ├── outputs.py
│   └── metadata.py
├── scripts/
│   ├── check_file_sizes.py       ← CI backstop for 100 MB ceiling
│   └── validate_run_metadata.py  ← CI schema + checksum validation
├── .github/workflows/
│   ├── validate-config.yml
│   ├── validate-run-metadata.yml
│   └── publish-report.yml
├── _dev/                         ← presentation source (not part of the framework)
│   ├── tdm-run-management-framework-proposal.qmd
│   └── styles.css
├── tests/                        ← pytest suite; fixtures currently stale against
│                                    the real submodule, see "What's currently mocked vs. real"
├── docs/architecture/            ← 6 ADRs
└── pyproject.toml
```

### CLI commands

```bash
pip install -e .
tdmruns validate-config                              # validate all run_sets
tdmruns validate-config --run-set <id>              # validate one run_set
tdmruns sync-tdm --run-set <id>                     # sync the submodule to tdm_ref
tdmruns sync-tdm --run-set <id> --scenario <id>     # ...or a scenario's tdm_ref override
tdmruns prep-scenario --run-set <id> --scenario <id> # run prep_script only, no model execution
tdmruns run-set --run-set <id>                      # run all scenarios
tdmruns run-scenario --run-set <id> --scenario <id> # run one scenario
tdmruns run-scenario ... --force                    # re-run even if already successful
tdmruns import-manual-run --run-set <id> --scenario <id> [--scenario-folder <path>]
                                                     # curate outputs for a scenario run
                                                     # outside the CLI (see below)
tdmruns import-manual-run-set --run-set <id>        # same, for every scenario in a run
                                                     # set that declares manual_scenario_folder
tdmruns status                                      # show latest result per scenario
```

`sync-tdm` actually mutates the submodule (git fetch + checkout) to match
whatever `tdm_ref` is declared in config — it's not a dry-run preview. It
refuses on a dirty submodule tree, same guard `run-scenario` uses internally
before rendering anything.

`import-manual-run(-set)` exists because a scenario can be run manually
(Cube Voyager invoked directly, outside `run-scenario`) when a real CLI-driven
run isn't possible yet (see the `.block`-format blocker below) or isn't
desired. It applies the scenario's `outputs.include` selection and size
ceiling exactly like a real run would, curates into `runs/<run_set>/<scenario>/
<run_id>/outputs/`, and records `run_metadata.json` with `execution_mode:
"manual"`. `--scenario-folder` defaults to the scenario's declared
`manual_scenario_folder` (relative to the TDM submodule root) when omitted.
It does not check out, fetch, or otherwise touch the TDM submodule — only
its current state is read for the record. There is no skip-if-unchanged
logic and no `--force`: every invocation creates a fresh timestamped run,
since running the command at all is already the deliberate signal to
(re-)gather outputs — the alternative (guessing staleness from the raw
folder's mtime) was tried and dropped as unnecessary complexity.

### Config layer order (later layers win)

```
baseline .block file  →  run_set overrides + run_set input_files
  →  scenario overrides + scenario input_files
     →  local.yaml (machine values)  →  orchestrator identity fields
        (ScenarioName, ScenarioDir, ParentDir — always win, always computed)
```

`input_files` entries in run_set or scenario YAML are relative file paths
(e.g. `inputs/SE_S01.csv`) resolved to absolute paths against the run_set
directory at runtime. This keeps scenario YAMLs machine-independent.

Every override key (including resolved input_files) is validated against the
chosen baseline before execution. An unknown key is a hard failure before the
model is touched.

### What's currently mocked vs. real

- `tdm/` submodule is now connected to the **real TDM repo**
  (`https://github.com/WFRCAnalytics/WF-TDM-Development.git`) — no longer the
  local mock. `config/framework.yaml` `execution.entry_point` is already
  `RunModel.bat`; the mock's `RunModel_stub.py` no longer exists in the
  submodule.
- `control_center_defaults_dir` in `config/framework.yaml` is `Scenarios/_default`
  (**singular**, not `_defaults` as earlier drafts of this doc said) — verified
  against the real submodule, which has `tdm/Scenarios/_default/`.
- **Blocker (still open):** `tdmruns validate-config` fails against the real
  TDM — `1ControlCenter - BY_2019.block` in the real defaults library is Cube
  Voyager's native block format, not YAML (see the constraints note above).
  `cli.py`/`controlcenter.py` haven't been updated for this yet, so no real
  scenario has been run through `run-scenario`/`run-set`. Until it's fixed,
  new run sets are executed manually (Cube Voyager invoked directly) and their
  outputs gathered with `tdmruns import-manual-run(-set)` (see CLI commands
  above) — a first-class, supported path now, not a one-off workaround. See
  `non-motorized-2023` below for the current example.
- The test suite's fixtures still assume the old mock TDM layout (they try to
  copy a `RunModel_stub.py` that no longer exists in the now-real submodule),
  so `pytest tests/` currently shows ~19 errors in `test_config.py` /
  `test_integration.py` / `test_prep.py` — pre-existing, unrelated to the
  block-file blocker above, and not something recent work introduced.
- Quarto reporting (`reports/`) renders successfully locally (`quarto render
  reports` / `quarto preview reports`) as of this session. GitHub Actions
  (`publish-report.yml`) installs `geopandas`/`plotly` and registers a
  `july2025` Jupyter kernel to match what the report `.qmd` files expect —
  not yet confirmed against a real GitHub Pages deploy.

### Architecture decisions (summary — full detail in `docs/architecture/`)

- **In-place sequential submodule checkout, not git worktrees** — Cube runs
  in place inside its own checkout. Worktree isolation adds complexity for no
  immediate benefit. Deferred to a future PR if parallel execution is needed.
- **One override mechanism** — `_ControlCenter.yaml` keys are all just keys,
  whether they select input files or tune model parameters. `input_files` in
  scenario YAML is syntactic sugar for file-path overrides with automatic path
  resolution; it merges into the same single override dict.
- **Input prep is manual, not automated** — each run_set has an optional
  `input_prep.ipynb` notebook at its root that generates input files (e.g.
  SE CSVs) into its `inputs/` folder. The framework does not run prep;
  analysts run it once before executing the run_set.
- **Curated outputs with a hard size ceiling** — raw outputs stay gitignored.
  Only a declared, glob-selected, size-checked subset enters the repo.
  Checksums are computed only for that curated subset (at copy time), not for
  every file the model produced — the full inventory (for the aggregate
  count/byte-total in metadata) is stat()-only, since scenario folders
  routinely hold thousands of files and tens of GB and nothing ever read the
  per-file checksum for anything not selected (see `docs/architecture/0003-output-management.md`'s update note).
- **Manual execution is a first-class path, not just a workaround** —
  `import-manual-run(-set)` curates outputs for a scenario run outside the
  CLI the same way `run-scenario` does after a real execution (same
  select/size-check/copy sequence), flattening curated files into
  `outputs/` (no preserved subfolder structure) and tagging
  `run_metadata.json` with `execution_mode: "manual"`. It never touches the
  TDM submodule. It always creates a new run rather than trying to detect
  whether the raw folder changed since the last import (an mtime-based
  staleness check was tried and deliberately removed as unneeded complexity
  — every invocation is already a deliberate human action).
- **Flat JSON metadata as source of truth** — one `run_metadata.json` per run,
  committed, schema-versioned. No database. Quarto reads these directly.
- **CI scoped to validation and reporting** — never model execution.
- **Future capabilities** (parallel runs, scheduled reruns, cross-version
  comparison, dashboards) are all deferred but attach cleanly to existing
  seams without redesign.

---

## The presentation (Part 2)

**`_dev/` has been deleted from the repo.** The reason/outcome of the pilot
pitch isn't recorded here. The section below documents what the deck
contained for historical reference; none of these files exist anymore.

### Files

- `_dev/tdm-run-management-framework-proposal.qmd` — 15-slide Quarto RevealJS deck
- `_dev/styles.css` — WFRC brand colors, must sit in the same folder as the `.qmd`

### Render

```bash
quarto render _dev/tdm-run-management-framework-proposal.qmd
# or for live preview:
quarto preview _dev/tdm-run-management-framework-proposal.qmd
```

### Slide structure

1. Where we are today — non-motorized study anchor (14 scenarios, over a month)
2. This isn't a process problem — it's a tooling gap
3. The proposal — what the framework manages vs. what it doesn't touch
4. How the two repositories relate — GitHub-level diagram (developer slide)
5. Inside the framework repo — annotated folder tree (developer slide)
6. It was built for our TDM specifically — `_defaults/`, Control Center, batch entry point
7. What a run set looks like — example YAML configs (run_set.yaml + scenario.yaml)
8. What running it looks like — incremental pipeline walkthrough
9. What the record looks like — example `run_metadata.json`
10. What gets published — GitHub Pages site structure and auto-discovery
11. What changes for analysts — before/after comparison
12. What stays the same — direct answer to "we already have a workflow"
13. The pilot — scope, success criteria, what's required
14. What we're asking for today — approval checklist
15. Questions — anticipated objections with prepared answers

### WFRC brand colors used

| Name | Hex | Used for |
|---|---|---|
| Navy | `#1B3A5C` | Headings, body text, table headers, title |
| Teal | `#1A8FAA` | Bold text, code borders, subtitle, footer |
| Amber | `#F5A623` | H2 underlines, blockquote border, progress bar |
| Light teal | `#E8F4F8` | Code backgrounds, table striping, blockquote bg |

### Font sizing

- Base slide text: 80% of RevealJS default
- Bullet point text: 65% (of the already-scaled 80% base — effectively ~52%)
- Code blocks: 0.85em relative to base

### Audience and tone

Mixed: analysts/modelers + developers + some leadership. Two objections were
anticipated and addressed directly in the deck:
- *"We already have a workflow"* — slide 12 ("What stays the same")
- *"How do we know it works for our TDM?"* — slide 6 (it was designed against
  our specific conventions) + slide 13 (that's what the pilot is for)

The ask is deliberately narrow: pilot approval for one run set, one lead
analyst, 4–6 weeks, a review session at the end. Not a program commitment.

---

## Current run sets

### `non-motorized-2023`

13-scenario non-motorized sensitivity study — repeat of the study that
originally took over a month. **Renamed from `non-motorized-2026`** once the
actual model runs (base year 2019, results reported 2023) were completed and
folded into the repo; the old `non-motorized-2026` run_set/report were deleted.

- **TDM ref:** `archive/non-motorized-sensitivity-tests` (per `run_set.yaml`
  `tdm_ref` — not `v1000-E3`, which an earlier draft of this doc said).
- **Baseline:** `1ControlCenter - BY_2019.block`
- **Scenarios:** S01–S13 (HH/EMP multipliers at smldst/smldst+taz scope, plus
  full SE_2050 and SE_2050_transit_corridors substitutions)
- **SE prep:** done — `run_sets/non-motorized-2023/inputs/SE_S01.csv`
  through `SE_S13.csv` are already generated and committed (produced by
  `input_prep.ipynb` at the run_set root).
- **Not run through `run-scenario`/`run-set`.** The block-file-parsing
  blocker above means these scenarios were run manually (Cube Voyager
  invoked directly, outside the framework). Each scenario YAML declares a
  `manual_scenario_folder` (e.g. `Scenarios/non-motorized-2023/
  BY_2019_SensitivityTest_01`, relative to the TDM submodule root) pointing
  at that raw, gitignored output. `run_set.yaml` and `S10.yaml`/`S11.yaml`'s
  `outputs.include` glob patterns are the real selection patterns — used both
  as documentation of what a CLI-driven run would curate, and as what
  `import-manual-run(-set)` actually applies today.
- **Outputs gathered via `tdmruns import-manual-run-set --run-set
  non-motorized-2023`**, which curates each scenario's raw, unfiltered
  `outputs.include`-matched files into `runs/non-motorized-2023/S01`–`S13/
  <run_id>/outputs/` and writes `run_metadata.json` with `execution_mode:
  "manual"`. There used to be a separate, pre-filtered backfill under
  `run_sets/non-motorized-2023/data/outputs/` (and a one-off script to
  produce it) — both were deleted once the reports were pointed at `runs/`
  directly; `runs/` is now the only copy of curated output for this run set.
- **Reporting pages** (custom, not the generic `runs/`-metadata-driven
  pattern): `reports/run_sets/non-motorized-2023/slides.qmd` (RevealJS deck)
  and `summary.qmd` (detailed HTML writeup), both linked directly from
  `reports/index.qmd`. Both import `reports/report_data.py` (`sys.path.insert(0,
  '../..')` since they live two levels deeper) and call
  `latest_run_per_scenario`/`curated_output_paths` to resolve each scenario's
  most recently imported files, then apply the `Period=='Dy' & PA=='P'` +
  fixed-column filter themselves at render time (unified with the base-year
  branch, which always worked this way) rather than reading a pre-filtered
  copy. The BY_2019 baseline (test_id 0) and the static TAZ/District
  shapefiles (`tdm/1_Inputs/1_TAZ/...`) are still read straight from the
  gitignored `tdm/` working tree, since neither is scoped to a single
  scenario/run.

SE files are referenced in scenario YAMLs via `input_files` (relative paths
like `inputs/SE_S01.csv`), resolved to absolute at runtime.

### `toll-sensitivity-2026`

Example run set for toll sensitivity testing. Scenarios defined, no runs executed.

---

## Pending work / what to do next

In rough priority order:

**1. Fix `controlcenter.py`'s baseline parser for the real TDM's `.block` format.**
`load_baseline()` (`src/tdmruns/controlcenter.py:23`) calls `yaml.safe_load()`
directly on the baseline file, which works for the mock TDM but not the real
one — the real `1ControlCenter - BY_2019.block` is Cube Voyager's native
indented `KEY = value` / `;`-comment block format. This blocks
`tdmruns validate-config` and any real CLI-driven run. Until it's fixed, new
run sets have to be executed manually outside the framework and their outputs
gathered with `tdmruns import-manual-run(-set)`, the way `non-motorized-2023`
is (declaring `manual_scenario_folder` per scenario).

**2. Fix the test suite's fixtures.**
`tests/` fixtures still assume the old mock TDM layout (copying a
`RunModel_stub.py` that no longer exists now that `tdm/` points at the real
repo) — ~19 errors in `test_config.py` / `test_integration.py` / `test_prep.py`.
Pre-existing, not caused by recent work, but blocks using `pytest` as a
signal until updated.

**3. Once #1 is fixed, run `tdmruns validate-config --run-set non-motorized-2023`**
against the real submodule to confirm S01–S13's override keys are valid, then
consider re-running the scenarios through `run-scenario`/`run-set` so this run
set no longer depends on `manual_scenario_folder`/`import-manual-run-set` —
though that path is now solid enough (flattened, checksummed, schema-validated)
that switching isn't urgent on its own.

**4. Verify GitHub Actions actually deploys.**
`publish-report.yml` was updated this session to install `geopandas`/`plotly`
and register a `july2025` Jupyter kernel matching what the report `.qmd` files
declare — confirmed to render locally via `quarto render reports`, but not yet
confirmed against a real GitHub Pages deploy. Watch the first push's Actions
run for kernel/package issues that don't show up locally.

**5. `validate-config.yml` / `validate-run-metadata.yml` workflows** are
written but still unconfirmed against the real (possibly private) TDM repo —
if private, they'll need a deploy key or PAT to check out the submodule.
