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
`tdm/` now points at the real TDM (see "What's currently mocked vs. real").
The real-vs-mock Control Center format incompatibility that surfaced has
since been fixed in `controlcenter.py`, though the test suite's own fixtures
(separately) still assume the old mock layout — see that section for detail.

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
3. Loads a baseline Control Center `.block` file from the TDM's
   `Scenarios/_default/` library, layers run_set overrides then scenario
   overrides on top (resolving any `input_files` relative paths to absolute),
   fills in orchestrator-computed identity/path fields, writes
   `_ControlCenter.block` (real Cube block syntax, not YAML) into a fresh run
   folder
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
- The real TDM's baseline `.block` files (e.g. `1ControlCenter - BY_2019.block`)
  are Cube Voyager's native indented `KEY = value` block format with `;`
  comments, not YAML — an early assumption that they were plain YAML with a
  `.block` extension (true only for the now-retired mock TDM) was wrong.
  `controlcenter.py` was rewritten (commit `bc56130`) to parse and write that
  native format directly: `load_baseline()` reads real `KEY = value`
  assignments, and `write_block_file()` writes a real `_ControlCenter.block`,
  preserving every comment/blank line/control-flow statement from the
  template verbatim and substituting only overridden lines. This was the top
  blocker for CLI-driven runs against the real TDM; it's resolved, and real
  runs now succeed through it (see "What's currently mocked vs. real" below).
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
│       ├── input_prep.ipynb      ← input preparation notebook (committed; optional)
│       ├── <scripts folder>/     ← optional custom driver script (declared via driver_script
│       │                            in run_set.yaml/scenario.yaml, e.g. hail-mary/), staged
│       │                            (that one file, own filename kept) into the per-run
│       │                            scenario folder every run -- falling back to the TDM's
│       │                            own default driver script when not declared; any
│       │                            companion/modified step scripts stay here and are
│       │                            referenced from it by relative path (see ADR 0007)
│       ├── report_snapshot_script (declared in run_set.yaml, optional) ← freezes
│       │                            this run set's report data before retirement
│       └── snapshot/             ← generated by `tdmruns snapshot-run-set`; small,
│                                    committed CSVs a retired run set's reports read
│                                    once runs/ curated outputs are purged
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
│   ├── chart_utils.py            ← shared Plotly chart styling (see below)
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
│   ├── metadata.py
│   └── retirement.py             ← snapshot-run-set / purge-run-set-outputs logic
├── bin/
│   └── RunModel.bat               ← fixed batch entry point (config/framework.yaml
│                                     execution.entry_point); TDM-version-independent,
│                                     deliberately lives here and not in tdm/ (see
│                                     "What's currently mocked vs. real")
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

### Slide-deck chart legends

Every `reports/run_sets/<id>/slides.qmd` should call
`chart_utils.use_slide_chart_defaults()` once, in its setup cell (see
`bring-work-trips-closer-to-home/slides.qmd` or `non-motorized-2023/slides.qmd`
for the exact pattern: `sys.path.insert(0, os.path.join('..', '..'))` then
`from chart_utils import use_slide_chart_defaults; use_slide_chart_defaults()`).
This registers a Plotly template moving the legend to a horizontal band at
the top-left by default — Plotly Express's own default (top-right, outside
the plot) collides with Plotly's modebar icons (also top-right) on a
RevealJS deck's narrow, fixed-size canvas. This collision was independently
hand-fixed per-chart twice (non-motorized-2023, then
bring-work-trips-closer-to-home) before being centralized here — any new
slides.qmd should call this instead of re-discovering the same fix. A chart
needing a different offset (e.g. a taller multi-line title) can still pass
its own `legend=dict(y=...)` on top of the template's default; an explicit
per-chart value always wins over the template. `summary.qmd` pages (full-width
HTML, not a fixed slide canvas) don't have this collision and don't need it.

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
                                                     # set (see below for folder resolution)
tdmruns snapshot-run-set --run-set <id>             # freeze a report snapshot (see below)
tdmruns purge-run-set-outputs --run-set <id>        # delete curated outputs once retired
tdmruns status                                      # show latest result per scenario
```

`sync-tdm` actually mutates the submodule (git fetch + checkout) to match
whatever `tdm_ref` is declared in config — it's not a dry-run preview. It
refuses on a dirty submodule tree, same guard `run-scenario` uses internally
before rendering anything.

`import-manual-run(-set)` exists because a scenario can be run manually
(Cube Voyager invoked directly, outside `run-scenario`) when that's simply
preferred, or for run sets (like `non-motorized-2023`) run before CLI-driven
execution against the real TDM was working. It applies the scenario's `outputs.include` selection and size
ceiling exactly like a real run would, curates into `runs/<run_set>/<scenario>/
<run_id>/outputs/`, and records `run_metadata.json` with `execution_mode:
"manual"`. `--scenario-folder` defaults to the scenario's declared
`manual_scenario_folder` (relative to the TDM submodule root) when omitted,
falling back further to the `scenario_folder_template` convention
(`Scenarios/<run_set_id>/<scenario_id>`) already used for CLI-driven runs if
the scenario doesn't declare one at all — a scenario whose raw folder happens
to follow that naming (e.g. `bring-work-trips-closer-to-home`'s Closer00–Closer09)
doesn't need `manual_scenario_folder` declared; one is still required when the
raw folder's name departs from it (e.g. non-motorized-2023's
`BY_2019_SensitivityTest_NN` naming — see below).
It does not check out, fetch, or otherwise touch the TDM submodule — only
its current state is read for the record. There is no skip-if-unchanged
logic and no `--force`: every invocation creates a fresh timestamped run,
since running the command at all is already the deliberate signal to
(re-)gather outputs — the alternative (guessing staleness from the raw
folder's mtime) was tried and dropped as unnecessary complexity.

### Retiring a run set

`runs/` bloats as run_sets accumulate curated outputs — non-motorized-2023
alone was 491 MB across 13 scenarios, almost all of it in per-scenario
`*_ZoneSummary_TripsByMode.csv` files (~39 MB each) that the reports filter
down to a handful of columns/rows at render time. Once a run_set is done and
won't be re-run, most of that is redundant with what its reports actually
display. "If we need the data, we run the models again" is the accepted
tradeoff — `purge-run-set-outputs` deletes real, currently-committed files.

Two steps, deliberately separate (the first is safe and repeatable; the
second is the irreversible-ish one):

1. **`tdmruns snapshot-run-set --run-set <id>`** — invokes the run set's
   declared `report_snapshot_script` (a plain Python script, subprocess-invoked
   exactly like `prep_script`, with `--run-set-dir` and `--snapshot-dir`
   arguments), which reads whatever that run set's reports need from `runs/`
   and writes small CSVs into `run_sets/<id>/snapshot/`. Safe to re-run;
   overwrites any existing snapshot; deletes nothing. Re-render the reports
   afterward (they automatically prefer the snapshot once one exists — see
   below) to confirm they still match before ever purging.
2. **`tdmruns purge-run-set-outputs --run-set <id>`** — refuses unless
   `run_sets/<id>/snapshot/` already exists and is populated. Deletes every
   `runs/<id>/**/outputs/` directory's contents and marks each run's
   `run_metadata.json` with `outputs.retired: true` / `outputs.retired_at`.
   The metadata JSON itself (TDM ref, overrides, checksums) is never deleted
   — it's the permanent, tiny audit trail of what once existed, even after
   the bytes are gone. `scripts/validate_run_metadata.py` skips the on-disk
   checksum check for runs marked retired.

Reports don't get an "if retired" branch of their own — that's centralized
once in each run_set's own loader module, which checks
`report_data.is_retired(run_set_id)` (true once `snapshot/` is populated) and
reads the frozen CSVs instead of live `runs/` output when so. See
`run_sets/non-motorized-2023/report_loader.py` /
`report_snapshot.py` for the reference implementation: `report_loader.py`
factors out logic that used to be duplicated verbatim between
`summary.qmd` and `slides.qmd`, and its two leaf I/O functions
(`load_scenario`/`load_se`) are the only retirement-aware part — everything
else (aggregation, deltas, chart-ready tables) is unchanged and shared.

**Known limitation:** this mechanism only freezes what a run set's reports
read from `runs/`. Static reference data reports read directly from the
(gitignored) `tdm/` working tree — non-motorized-2023's base-year (test_id 0)
CSV and the TAZ/district shapefiles — is always read live, never frozen. That
isn't `runs/` bloat, so it's out of scope here, but it means a retired
report's base-year numbers and geography could in principle drift if the
`tdm/` submodule later moves to a different ref for unrelated work. A future
extension could have `report_snapshot_script` freeze those pieces too if full
permanence is ever needed.

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
  local mock.
- `bin/RunModel.bat` — the fixed batch entry point `config/framework.yaml`
  `execution.entry_point` points at — now exists, and deliberately lives in
  **this framework repo**, not the `tdm/` submodule: it's a thin, TDM-version-
  independent wrapper that locates whatever driver script the orchestrator
  already staged into the scenario folder (glob on `*.s`, not a hardcoded
  `_HailMary` name, matching the ADR 0007 assumption) and runs it through
  Cube Voyager, `pushd`-ing into the scenario folder first so the driver
  script's relative `READ FILE = '..\..\..\2_ModelScripts\...'` paths
  resolve correctly, then propagates Voyager's exit code back out. Voyager's
  install location is machine-local, not hardcoded in the bat file — it's
  read from `config/local.yaml`'s existing `Voyager_EXE` key and passed
  through by `execution.invoke()` as the `VOYAGER_EXE` environment variable;
  the bat file fails loudly if that's unset or points at a nonexistent path.
  Because of this, `build_command()` (`src/tdmruns/execution.py`) now
  resolves `execution.entry_point` against `repo_root`, not `tdm_path`.
  **Confirmed working at least once end-to-end** against real Cube Voyager —
  at least one recorded `execution_mode: "cli"`, `status: "success"` run
  (`exit_code: 0`) exists in `runs/`, proving the plumbing (block-format
  Control Center, driver-script staging, `RunModel.bat`, `VOYAGER_EXE`)
  genuinely works together. Other recorded `execution_mode: "cli"` attempts
  have failed with `exit_code: 1`, mostly predating the "decide status from
  the model's own log" fix below — at least some of these are likely the same
  false-negative the architecture note about that fix describes (Cube
  completed cleanly but the pre-fix exit-code-only logic recorded it as
  failed), not necessarily genuine crashes, though they weren't retroactively
  re-evaluated. CLI-driven runs are proven possible but not yet reliable in
  practice — treat individual `status: "failed"` records with some
  skepticism until re-run under the current model-log-aware status logic.
  The driver script's `READ FILE =
  '..\..\..\1_Inputs\0_GlobalData\GeneralParameters.block'` turned out to be a
  fixed path into the TDM tree, not something per-run staging was ever needed
  for — an earlier assumption in this doc that a `0GeneralParameters.block`
  needed staging into the scenario folder was wrong.
- `control_center_defaults_dir` in `config/framework.yaml` is `Scenarios/_default`
  (**singular**, not `_defaults` as earlier drafts of this doc said) — verified
  against the real submodule, which has `tdm/Scenarios/_default/`.
- **Control Center `.block`-format blocker: resolved.** `controlcenter.py`
  (`load_baseline()` / `write_block_file()`) now reads and writes Cube's
  native `.block` format directly instead of YAML (commit `bc56130`, see the
  constraints note above) — `tdmruns validate-config` and real CLI-driven
  runs both work against the real TDM now. Run sets executed manually before
  this fix landed haven't been auto-migrated to `run-scenario`/`run-set` —
  that's a per-run-set decision to make going forward, not a remaining
  capability gap. `import-manual-run(-set)` remains a first-class, supported
  path regardless (e.g. for cases where manual execution is simply
  preferred), not just a stand-in for a broken CLI path.
- The test suite has two separate, unrelated gaps: (1) fixtures still assume
  the old mock TDM layout (they try to copy a `RunModel_stub.py` that no
  longer exists in the now-real submodule) — ~19 errors in `test_config.py` /
  `test_integration.py` / `test_prep.py`, pre-existing and not caused by
  recent work; (2) `test_controlcenter.py` has 3 failures because
  `write_block_file()`'s signature changed to
  `(baseline_path, overrides, output_path)` when it was rewritten for the
  real `.block` format, but the tests still call the old 2-arg form — a
  regression from that rewrite that hasn't been fixed yet.
- Quarto reporting (`reports/`) renders successfully locally (`quarto render
  reports` / `quarto preview reports`) as of this session. GitHub Actions
  (`publish-report.yml`) installs `geopandas`/`plotly` and registers a
  `july2025` Jupyter kernel to match what the report `.qmd` files expect —
  not yet confirmed against a real GitHub Pages deploy.

### Architecture decisions (summary — full detail in `docs/architecture/`)

- **In-place sequential submodule checkout, not git worktrees** — Cube runs
  in place inside its own checkout. Worktree isolation adds complexity for no
  immediate benefit. Deferred to a future PR if parallel execution is needed.
- **One override mechanism** — `_ControlCenter.block` keys are all just keys,
  whether they select input files or tune model parameters. `input_files` in
  scenario YAML is syntactic sugar for file-path overrides with automatic path
  resolution; it merges into the same single override dict.
- **Driver script is staged every run, default or custom — a second, narrow
  mechanism deliberately separate from overrides** — every run stages a
  driver script into its scenario folder: the TDM's own default
  (`config/framework.yaml`'s `default_driver_script`, currently
  `_HailMary_1Subfolder.s`, from `Scenarios/_default/`) unless a run_set or
  scenario declares `driver_script` (path to a custom copy, e.g.
  `run_sets/<id>/hail-mary/_HailMary_1Subfolder_closer.s`), staged keeping
  its own on-disk filename either way. The per-run scenario folder sits
  **one directory level deeper** below the TDM root than `Scenarios/_default/`
  does (`Scenarios/<version>/<scenario_id>__<run_id>/` vs.
  `Scenarios/_default/`) — exactly the depth `_HailMary_1Subfolder.s` is
  already written for (`..\..\..\2_ModelScripts\...`, three levels up, vs.
  plain `_HailMary.s`'s two). Companion or modified step scripts are **not**
  auto-staged — they stay wherever the run_set keeps them and must be
  referenced from the custom driver script by a relative path computed back
  to that location. This swaps which code runs, not a parameter value, so
  it's not folded into `overrides`/`validate_overrides()` — see
  `docs/architecture/0007-custom-driver-script.md`. `bin/RunModel.bat` now
  exists and does glob for whatever driver script it finds staged in the
  scenario folder it's given (see "What's currently mocked vs. real" above);
  confirmed capable of a real end-to-end success at least once, though CLI
  runs aren't yet reliable in practice — see the nuance in "What's currently
  mocked vs. real" above.
- **`start_from_copy` seeds a scenario's raw folder from a prior scenario's
  run — a third, narrow mechanism, orthogonal to overrides and driver
  scripts** — a scenario may declare `start_from_copy: <scenario_id>`
  (naming a sibling scenario in the same run set) to have its entire raw
  scenario folder copied from that scenario's most recent *successful*
  recorded run before this run's own Control Center/driver script are
  written — useful when a scenario's modification only affects a model step
  late in the pipeline, so upstream steps don't need to be recomputed. The
  source folder is resolved via `metadata.latest_successful_run()`'s
  recorded `scenario_folder` (works whether the source was run via the CLI
  or imported from a manual run), not a declared `manual_scenario_folder` —
  see `docs/architecture/0008-scenario-seeding.md`. `latest_successful_run()`
  skips past any newer failed attempts to find the most recent success — an
  earlier version called plain `latest_run()` and required *that* one to
  have succeeded, which wrongly blocked copying whenever a scenario's latest
  attempt failed for a reason unrelated to seeding (e.g. output curation
  tripping the size limit) even though an earlier attempt had succeeded.
  This mechanism only copies files; it never makes Cube Voyager skip a step
  — that's the analyst's own `driver_script` logic to write. Wired into
  `run-scenario`/`run-set` only (no standalone command), so it depends on
  the same block-format blocker as everything else routed through Cube, plus
  the source scenario needing a successful run first. Because the raw
  scenario folder is reused across every run attempt for a given
  `scenario_id` (`scenario_folder_template` has no `run_id` component), a
  scenario declaring `start_from_copy` re-copies the source's entire folder
  — potentially tens of GB — on every one of its own retries too. A
  scenario may additionally declare `lock_down_copy: true` once its folder
  already holds the seeded state it needs, to suppress that repeated copy
  without discarding the `start_from_copy` declaration (kept as the record
  of where it was seeded from); it has no effect unless `start_from_copy` is
  also declared.
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
- **Success/failure is decided from the model's own completion log, not
  Voyager's process exit code, when that log is available** — reverses an
  earlier deliberate choice. `src/tdmruns/model_log.py` parses
  `<scenario_folder>\_Log\_RunTime.txt`, written by the model scripts
  themselves via `_TimeStamp_ModelSuccess.block` / `_TimeStamp_ModelCrashed.block`
  at `:ENDMODEL` / `:ONERROR` in the Hail Mary driver script. Real recorded
  runs of `bring-work-trips-closer-to-home` showed this was necessary, not
  theoretical: Closer01's log shows two full, clean "TOTAL MODEL RUN TIME"
  completions with no crash marker, yet one of those attempts was recorded
  as `status: "failed", exit_code: 1` — Voyager's exit code disagreed with
  what the model itself reported it did. (The driver script also never calls
  `Exit` after `:ONERROR`, so the reverse — a crash that still exits 0 — is
  equally possible, not just the direction seen so far.) `execution.py`'s
  `decide_status()` now prefers the log when a recognizable
  "TOTAL MODEL RUN TIME" entry is found for the current attempt (the file is
  `APPEND=T` and reused across every CLI-driven retry of a given
  `scenario_id`, so only the text since the *previous* such entry — or file
  start — is read as this attempt's), and falls back to the exit code alone
  when no entry exists yet (e.g. Cube never started). `run_metadata.json`'s
  `execution.status_source` records which signal won
  (`"model_log"`/`"exit_code"`), and `execution.model_log` carries the parsed
  outcome, crashed step (if any), and the model's own Beg/End/Run-Time
  strings — also the source for run-duration/crash-point detail in reports.
  `execution.model_log.exit_code_mismatch` is `true` whenever the two
  signals disagreed, so a run can still be audited even though the log won.
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

## Pending work / what to do next

In rough priority order:

**1. Fix `test_controlcenter.py`'s 3 failures.**
`write_block_file()`'s signature changed to
`(baseline_path, overrides, output_path)` when `controlcenter.py` was
rewritten for the real `.block` format (commit `bc56130`), but
`test_controlcenter.py` still calls it with the old 2-arg form —
`test_render_precedence`, `test_render_identity_wins_over_scenario_override`,
and `test_write_and_reload_block_file_roundtrip` all fail with
`TypeError: write_block_file() missing 1 required positional argument`. A
straightforward regression from that rewrite; update the tests to the new
signature.

**2. Fix the test suite's other fixtures.**
`tests/` fixtures still assume the old mock TDM layout (copying a
`RunModel_stub.py` that no longer exists now that `tdm/` points at the real
repo) — ~19 errors in `test_config.py` / `test_integration.py` / `test_prep.py`.
Pre-existing, not caused by recent work, but blocks using `pytest` as a
signal until updated.

**3. Consider migrating run sets still using `manual_scenario_folder` /
`import-manual-run(-set)` to `run-scenario`/`run-set`** now that the Control
Center blocker that used to prevent this is fixed (see "What's currently
mocked vs. real" above) — a per-run-set decision, not urgent on its own,
since the manual+import path is solid enough (flattened, checksummed,
schema-validated) to keep using where preferred.

**4. Verify GitHub Actions actually deploys.**
`publish-report.yml` was updated this session to install `geopandas`/`plotly`
and register a `july2025` Jupyter kernel matching what the report `.qmd` files
declare — confirmed to render locally via `quarto render reports`, but not yet
confirmed against a real GitHub Pages deploy. Watch the first push's Actions
run for kernel/package issues that don't show up locally.

**5. `validate-config.yml` / `validate-run-metadata.yml` workflows** are
written but still unconfirmed against the real (possibly private) TDM repo —
if private, they'll need a deploy key or PAT to check out the submodule.

**6. `bin/RunModel.bat` has one confirmed real success; drive down the CLI
failure rate.**
`bin/RunModel.bat` (lives in the framework repo, not `tdm/` — see "What's
currently mocked vs. real" above) globs the scenario folder for whatever
driver script `src/tdmruns/driver_script.py` staged there (default
`_HailMary_1Subfolder.s` or a run_set's custom one, see ADR 0007), `pushd`s
into the scenario folder so the driver script's relative
`..\..\..\2_ModelScripts\...` paths resolve, and invokes Cube Voyager via
the `VOYAGER_EXE` env var (sourced from `config/local.yaml`'s `Voyager_EXE`
by `execution.invoke()`). One real, uncontested success is on record
(`exit_code: 0`), proving the plumbing works, but other recorded
`execution_mode: "cli"` attempts show `status: "failed"` — most predate the
model-log status fix and may be the same false-negative it was built to
catch (see below), but that hasn't been confirmed per-attempt. Worth
re-running a scenario or two through `run-scenario` now that the model-log
fix exists, to get a clean, currently-fresh confirmation that CLI status
reporting is accurate end-to-end. Success/failure prefers the model's own
`_Log\_RunTime.txt` completion report over Voyager's process exit code
(`%ERRORLEVEL%` right after `start /w`, propagated by `RunModel.bat` and
read by `execution.invoke()`) — see the "Success/failure is decided from the
model's own completion log" architecture decision above. Falls back to the
exit code alone when no recognizable log entry exists yet.

**7. `start_from_copy` has been exercised end-to-end via live
`run-scenario` invocations against the real TDM**, not just unit tests —
confirming the `metadata.latest_successful_run()` fix (see the architecture
decision above) actually resolves a seed source correctly in practice.
Covered by unit tests in `tests/test_scenario_seed.py`.
