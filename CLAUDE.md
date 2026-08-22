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
   identity/path fields, writes `_ControlCenter.block` into a fresh run folder
4. Invokes the TDM's fixed batch entry point with the control file path and
   scenario folder path as arguments
5. Inventories all outputs, copies only the glob-selected subset (over the
   configured size ceiling stays local, uncommitted, gitignored — see
   "Curated outputs..." below) into the repo, replacing whatever the
   scenario's previous attempt left there
6. Writes a permanent per-attempt metadata record — the source of truth for
   reporting

### What it doesn't touch

The TDM codebase, the `_default/` library, how Cube Voyager runs internally,
or the `Scenarios/` gitignored working folder convention.

### Key real-world constraints that shaped the design

- The TDM is **Cube Voyager**, run via one fixed batch entry point per version,
  taking exactly two arguments: a Control Center file path and a scenario folder
  path. That calling convention is captured in `config/framework.yaml`
  `execution:` — not hardcoded.
- The baseline `.block` files the orchestrator **reads** from the defaults
  library were originally assumed to be plain YAML with a `.block`
  extension — confirmed true for the early mock TDM, but **not true for the
  real TDM**: the real `1ControlCenter - BY_2019.block` is Cube Voyager's
  native indented `KEY = value` block format with `;` comments, not YAML.
  This was a real blocker for a while (`controlcenter.py`'s `load_baseline()`
  originally called `yaml.safe_load()` on it directly and failed) — resolved
  in commit `bc56130`; `controlcenter.py` now parses and writes the real
  block format on both sides (`_ControlCenter.block`, not `.yaml` — see
  "What's currently mocked vs. real" below for the confirmed-working
  end-to-end evidence).
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
│   └── <run_set_id>/<scenario_id>/
│       ├── run_info/             ← one <run_id>.json per attempt, forever, never
│       │                            deleted -- execution_mode: "cli" or "manual"
│       └── outputs/              ← only the LATEST attempt's curated files, flat;
│                                    wiped and replaced on every attempt
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
tdmruns run-set --run-set <id>                      # run all scenarios (concurrently within
                                                     # a shared tdm_ref, per max_parallel_runs)
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
(Cube Voyager invoked directly, outside `run-scenario`) when a real CLI-driven
run isn't possible yet (see the `.block`-format blocker below) or isn't
desired. It applies the scenario's `outputs.include` selection and size
ceiling exactly like a real run would, replacing whatever was in
`runs/<run_set>/<scenario>/outputs/`, and records the attempt permanently at
`runs/<run_set>/<scenario>/run_info/<run_id>.json` with `execution_mode:
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

Since curated outputs are always latest-attempt-only now (see "Curated
outputs..." below), `runs/` no longer accumulates a full copy per retry —
but a scenario's outputs still change if it's ever re-run *after* a run set
is considered "done," which would silently change a report's numbers with
no record of what it used to say. That's what retirement guards against now
— freezing report data, not primarily reclaiming disk space (though
`purge-run-set-outputs` still does that too, for whatever the run set's
scenarios currently hold). "If we need the data, we run the models again"
is the accepted tradeoff — `purge-run-set-outputs` deletes real,
currently-committed files.

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
   `runs/<id>/*/outputs/` directory's contents and marks each scenario's
   **latest** attempt (`runs/<id>/<scenario>/run_info/<latest_run_id>.json`)
   with `outputs.retired: true` / `outputs.retired_at`. Older, already-
   superseded attempts under `run_info/` never get this flag — their
   `curated[]` paths were already gone before retirement touched anything
   (see "Curated outputs..." below), so there's nothing for retirement to
   mark there. No metadata document is ever deleted — every attempt's record
   (TDM ref, overrides, checksums) stays forever as the permanent, tiny
   audit trail of what once existed, even after the bytes are gone.
   `scripts/validate_run_metadata.py` only ever checksums a scenario's
   latest `run_info/` record in the first place, and skips even that one
   when it's marked retired.

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
  **Confirmed end-to-end** — see the next bullet.
- `control_center_defaults_dir` in `config/framework.yaml` is `Scenarios/_default`
  (**singular**, not `_defaults` as earlier drafts of this doc said) — verified
  against the real submodule, which has `tdm/Scenarios/_default/`.
- **Resolved: Control Center block-format parsing/writing.** `controlcenter.py`
  reads and writes Cube Voyager's real native `KEY = value` / `;`-comment
  block format (not YAML) — `write_block_file()` writes `_ControlCenter.block`
  by substituting overridden lines into a full copy of the baseline template,
  preserving everything else byte-for-byte (see "Config layer order" above).
  This was fixed in commit `bc56130` ("Write real Cube .block Control Center
  files instead of YAML") — an earlier draft of this doc described this as a
  live, unfixed blocker for some time after that; it wasn't. Real proof it
  works end-to-end: `bring-work-trips-closer-to-home`'s recorded run history
  (`runs/bring-work-trips-closer-to-home/*/run_info/`) shows one real
  `execution_mode: "cli"` attempt per scenario that rendered a real
  `_ControlCenter.block`, invoked `bin/RunModel.bat`, ran Cube Voyager for
  hours, and produced a full 1000+-file inventory with curated outputs.
  Those specific attempts are recorded `status: "failed"` — not because
  anything about Control Center rendering or execution failed, but because
  they predate the "decide status from the model's own log, not the exit
  code alone" fix (see that architecture decision below) and got
  misclassified by Voyager's own unreliable exit code. Rather than re-running
  through the CLI once that fix landed, the already-completed raw folders
  were curated via `import-manual-run` instead (a pragmatic call, not a
  structural need) — which is why every *subsequent* attempt for these
  scenarios shows `execution_mode: "manual"`. `non-motorized-2023` predates
  this fix entirely and was always run manually by design (see below); that
  one's `manual_scenario_folder` convention has no bearing on whether CLI
  execution itself works.
- The test suite's fixtures still assume the old mock TDM layout (they try to
  copy a `RunModel_stub.py` that no longer exists in the now-real submodule),
  so `pytest tests/` currently shows ~19 errors in `test_config.py` /
  `test_integration.py` / `test_prep.py` — pre-existing, unrelated to Control
  Center rendering, and not something recent work introduced.
- Quarto reporting (`reports/`) renders successfully locally (`quarto render
  reports` / `quarto preview reports`) as of this session. GitHub Actions
  (`publish-report.yml`) installs `geopandas`/`plotly` and registers a
  `july2025` Jupyter kernel to match what the report `.qmd` files expect —
  not yet confirmed against a real GitHub Pages deploy.

### Architecture decisions (summary — full detail in `docs/architecture/`)

- **In-place submodule checkout, not git worktrees — but same-ref scenarios
  now run concurrently within that one checkout.** Cube runs in place inside
  the submodule's own checkout; worktree isolation (one checkout per
  concurrent scenario) is still deferred as unneeded complexity, per the
  user's own confirmation that running two Cube Voyager instances
  simultaneously on one machine already works fine and their license is
  per-machine, not per-seat. `execution.run_scenarios()` (invoked by
  `run-set`) groups a run set's scenarios by resolved `tdm_ref` first —
  the shared working tree can only be checked out to one ref at a time — and
  checks out each distinct ref exactly once (never once per scenario, never
  concurrently: `submodule.resolve_version()` does a real `git fetch`+
  `checkout`, and racing that across threads risks corrupting the checkout).
  Only *after* a group's single checkout completes does it dispatch that
  group's own scenarios through a `ThreadPoolExecutor` bounded by
  `run_set.yaml`'s `max_parallel_runs` (an integer, defaults to 1 — today's
  fully sequential behavior — if omitted); `run_scenario()` accepts an
  optional pre-resolved `version_state` so a worker never calls
  `resolve_version()` itself. Ref groups themselves always run one after
  another regardless of `max_parallel_runs`, since a later group's checkout
  would disrupt an earlier group's still-running scenarios reading from that
  same shared tree — this is the one case still effectively sequential, and
  would need actual worktree isolation to parallelize; a run set where every
  scenario shares one `tdm_ref` (the common case) gets full concurrency in a
  single group. A group whose own checkout fails records every scenario in
  that group as failed with that error, since none of them could have run.
  Covered by `tests/test_execution.py` (grouping/ordering/concurrency-cap/
  cross-group-isolation/failure-isolation, all fully mocked — no real
  submodule or Cube Voyager involved) — not yet exercised end-to-end against
  a real concurrent multi-scenario `run-set` invocation.
- **One override mechanism** — `_ControlCenter.block` keys are all just keys,
  whether they select input files or tune model parameters. `input_files` in
  scenario YAML is syntactic sugar for file-path overrides with automatic path
  resolution; it merges into the same single override dict.
- **`general_parameter_overrides` is a second, separate override mechanism,
  for a file Control Center overrides can't reach** — ported from
  `WF-TDM-Calibration`'s `tdmcalib`. `tdm/1_Inputs/0_GlobalData/
  GeneralParameters.block` (`config/framework.yaml`'s
  `general_parameters_path`) is a single file shared by *every* scenario's
  working folder — unlike the Control Center, which is templated fresh per
  run, there's no per-scenario copy of it to substitute lines into, and
  copying the whole ~1200-line file would mean either editing inside `tdm/`
  (forbidden) or a per-scenario copy that's immediately stale the moment the
  TDM team updates the shared original. `run_set.yaml`/`scenario.yaml` may
  declare `general_parameter_overrides` (scenario overrides run_set, same
  precedence as `overrides`, merged via
  `config.resolved_general_parameter_overrides()` — recorded as one merged
  dict in metadata, not layer-by-layer like Control Center's
  `run_set_overrides`/`scenario_overrides` split, since there's no per-layer
  file to attribute a key to). Validated the same way as Control Center keys
  (`cc.validate_overrides()` against `general_parameters.load_baseline()`'s
  real parse of the shared file — an unknown key is a hard failure before
  execution). If non-empty, `execution.py` writes only the overridden key/
  value pairs to a small per-run file
  (`general_parameters.OVERRIDE_FILENAME`,
  `_GeneralParametersOverrides.block`, in the scenario folder — never a copy
  of the real file), and `driver_script.stage()` inserts one extra
  `READ FILE = '_GeneralParametersOverrides.block'` line into the *staged
  copy* of the driver script, immediately after its own
  `READ FILE = '...GeneralParameters.block'` line — Cube Voyager's own
  last-assignment-wins semantics then apply the override with the real file
  never touched or copied. No run_set currently declares this (added ahead
  of need, not because one does yet) — not yet exercised end-to-end against
  real Cube Voyager, only via `tests/test_general_parameters.py`/
  `tests/test_driver_script.py`'s unit coverage of each piece.
- **Driver script is staged every run, default or custom — a third, narrow
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
  scenario folder it's given (see "What's currently mocked vs. real" above)
  — confirmed end-to-end via `bring-work-trips-closer-to-home`'s recorded
  run history.
- **`start_from_copy` seeds a scenario's raw folder from a prior scenario's
  run — a fourth, narrow mechanism, orthogonal to overrides and driver
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
  `run-scenario`/`run-set` only (no standalone command); the source scenario
  needs a successful run on record first. Because the raw
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
- **Curated outputs with a size ceiling that degrades gracefully, not a hard
  failure** — raw outputs stay gitignored. Only a declared, glob-selected
  subset gets copied into `runs/<run_set>/<scenario>/outputs/` (only the
  latest attempt's files — see the "Only the latest attempt's curated
  outputs..." bullet below), and every copied file gets a checksum (at copy
  time) — the full inventory (for
  the aggregate count/byte-total in metadata) is stat()-only, since scenario
  folders routinely hold thousands of files and tens of GB and nothing ever
  read the per-file checksum for anything not selected (see
  `docs/architecture/0003-output-management.md`'s update note). Ported from
  `WF-TDM-Calibration`'s `tdmcalib`: a selected file that turns out to exceed
  `outputs.max_file_size_mb` once actually written no longer fails curation
  (and with it, marks an otherwise-successful model run `"failed"` in
  `run_metadata.json`) — it's kept on disk with `"committed": false` in its
  manifest entry, and `outputs/.gitignore` is regenerated on every curation
  run to list exactly the currently-oversized files (see
  `src/tdmruns/outputs.py`'s `_write_outputs_gitignore()`). The file is still
  usable locally (e.g. rendering a report on the machine that curated it);
  it's just never committed. `scripts/validate_run_metadata.py` skips the
  on-disk checksum check for `"committed": false` entries the same way it
  already does for retired runs, since a fresh checkout won't have the file.
- **Success/failure is decided from the model's own completion log, never
  from Voyager's process exit code alone** — reverses an earlier deliberate
  choice. `src/tdmruns/model_log.py` parses
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
  `decide_status()` prefers the log when a recognizable "TOTAL MODEL RUN
  TIME" entry is found for the current attempt (the file is `APPEND=T` and
  reused across every CLI-driven retry of a given `scenario_id`, so only the
  text up to and including the *last* such entry is read as this attempt's),
  and now (ported from `tdmcalib`) treats a missing or *unresolved* log
  result as `"failed"` rather than falling back to a clean exit code — a run
  is never called `"success"` without the model's own confirmation.
  `model_log.py`'s `read_model_log()` also gained a correctness fix ported
  from `tdmcalib`: since the driver script never calls `Exit` after
  `:ONERROR`, a caught crash can log a crash+total block and keep running
  into a *later* step, which can crash again and append another block — so
  the last "TOTAL MODEL RUN TIME" entry isn't reliably a once-per-run final
  marker. `read_model_log()` now returns `None` (unresolved, so
  `decide_status()` records the run as failed pending confirmation) whenever
  anything is logged *after* that last block, rather than trusting a
  possibly-superseded checkpoint. It also prefers a trailing `"MODEL RUN
  SUCCESSFUL"` line (written only via `:ENDMODEL`, on newer TDM pins) as
  conclusive proof of a real finish when present, regardless of how many
  earlier crash+retry checkpoints preceded it. `run_metadata.json`'s
  `execution.status_source` records which signal won
  (`"model_log"`/`"exit_code"`), and `execution.model_log` carries the parsed
  outcome, crashed step (if any), and the model's own Beg/End/Run-Time
  strings — also the source for run-duration/crash-point detail in reports.
  `execution.model_log.exit_code_mismatch` is `true` whenever the two
  signals disagreed, so a run can still be audited even though the log won.
  On a failed run, `src/tdmruns/prn_log.py` (also ported from `tdmcalib`)
  folds Voyager's own `F(NNN): <description>` fatal-error lines from the
  most recently written `*.PRN` file in the scenario folder into the error
  message, alongside `model_log.py`'s crashed step name — see
  `execution.py`'s `_append_prn_errors()`.
- **Manual execution is a first-class path, not just a workaround** —
  `import-manual-run(-set)` curates outputs for a scenario run outside the
  CLI the same way `run-scenario` does after a real execution (same
  select/size-check/copy sequence), flattening curated files into
  `outputs/` (no preserved subfolder structure) and tagging that attempt's
  `run_info/<run_id>.json` with `execution_mode: "manual"`. It never
  touches the TDM submodule. It always creates a new attempt rather than
  trying to detect whether the raw folder changed since the last import
  (an mtime-based staleness check was tried and deliberately removed as
  unneeded complexity — every invocation is already a deliberate human
  action).
- **Only the latest attempt's curated outputs are ever kept on disk per
  scenario — permanent per-attempt metadata is a separate, unbounded
  history** — ported from `WF-TDM-Calibration`'s `tdmcalib`. Before this,
  every attempt (including every failed retry) kept its own full
  `runs/<run_set>/<scenario>/<run_id>/outputs/` copy forever, so a scenario
  under active iteration accumulated one copy per retry — real, not
  theoretical: `bring-work-trips-closer-to-home` alone reached 3.7 GB across
  2–5 attempts per scenario before this change, most of it superseded
  output nobody was reading. `execution.py`'s `run_scenario()` and
  `import_manual_run()` now call `_reset_run_outputs()` immediately before
  curating — wiping everything under `runs/<run_set>/<scenario>/` except
  `run_info/` — so `outputs/` always holds exactly the current attempt's
  files, win or lose. `run_info/<run_id>.json`, by contrast, is never
  touched by this reset: `metadata.write()` adds one file there per attempt
  and nothing ever deletes them, so the full history (every override set,
  every TDM ref, every checksum manifest — even for output files long since
  overwritten) survives regardless of how many times a scenario is re-run.
  `metadata.list_runs()` surfaces only each scenario's latest attempt (what
  reports and `tdmruns status` want); `metadata.list_attempts()` surfaces
  the full newest-first history for one scenario (what
  `latest_successful_run()` — used by `start_from_copy` seeding — and
  `reports/report_data.py`'s run-history table want). This narrows what the
  snapshot/purge retirement mechanism above is *for* — it no longer exists
  primarily to reclaim disk space (there's much less to reclaim now, by
  construction) but still matters to freeze report numbers before a
  "finished" run set's scenarios might ever be re-run again.
- **Flat JSON metadata as source of truth** — one metadata document per
  attempt (`runs/<run_set>/<scenario>/run_info/<run_id>.json`), committed,
  schema-versioned. No database. Quarto reads these directly.
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
  `input_prep.ipynb` at the run_set root). Each scenario's `overrides:` points
  `WFRC_SEFile`/`MAG_SEFile` straight at its file with a plain relative path —
  e.g. `WFRC_SEFile: '..\..\..\run_sets\non-motorized-2023\inputs\SE_S01.csv'`
  — rather than the `input_files:` block (framework-resolved to an absolute
  path) these scenarios used until this session. The relative path works
  because the TDM's own model scripts read `WFRC_SEFile`/`MAG_SEFile` as a
  suffix appended to a fixed prefix (`@ModelDir@\1_Inputs\2_SEData\`, see
  `tdm/2_ModelScripts/0_InputProcessing/b_SEProcessing/1_DemographicsAnalysis.s`),
  so three `..\` climb back out of `1_Inputs\2_SEData\` to the repo root, the
  same relative-navigation trick `_HailMary_1Subfolder.s` already uses to
  reach `2_ModelScripts\` from the scenario folder. Note this is a plain
  single-quoted YAML scalar, not double-quoted — double quotes would treat
  `\r` (from `..\run_sets\...`) as a carriage-return escape and corrupt the
  path. `input_files:` itself is untouched as a mechanism (schema + `config.py`
  still support it) for any run set that wants the absolute-path version; only
  non-motorized-2023 has stopped using it, for now.
- **Not run through `run-scenario`/`run-set`.** This run set predates the
  Control Center block-format fix (see "What's currently mocked vs. real"
  above), so these scenarios were run manually (Cube Voyager invoked
  directly, outside the framework) — not a limitation that still applies to
  new run sets today, just how this one was actually done. Each scenario
  YAML declares a
  `manual_scenario_folder` (e.g. `Scenarios/non-motorized-2023/
  BY_2019_SensitivityTest_01`, relative to the TDM submodule root) pointing
  at that raw, gitignored output. `run_set.yaml` and `S10.yaml`/`S11.yaml`'s
  `outputs.include` glob patterns are the real selection patterns — used both
  as documentation of what a CLI-driven run would curate, and as what
  `import-manual-run(-set)` actually applies today.
- **Outputs gathered via `tdmruns import-manual-run-set --run-set
  non-motorized-2023`**, which curates each scenario's raw, unfiltered
  `outputs.include`-matched files into `runs/non-motorized-2023/S01`–`S13/
  outputs/` and writes a permanent per-attempt record to `run_info/` with
  `execution_mode: "manual"`. This run set is already retired (see
  "Retiring a run set"), so its `outputs/` is empty now regardless — its
  numbers live in `run_sets/non-motorized-2023/snapshot/` instead. There
  used to be a separate, pre-filtered backfill under
  `run_sets/non-motorized-2023/data/outputs/` (and a one-off script to
  produce it) — both were deleted once the reports were pointed at `runs/`
  directly; `runs/` is now the only copy of curated output for this run set.
- **Reporting pages** (custom, not the generic `runs/`-metadata-driven
  pattern): `reports/run_sets/non-motorized-2023/slides.qmd` (RevealJS deck)
  and `summary.qmd` (detailed HTML writeup), both linked directly from
  `reports/index.qmd`. Both import `run_sets/non-motorized-2023/report_loader.py`
  (previously this data-loading/aggregation logic was duplicated verbatim
  between the two `.qmd` files; it's now factored into one shared module).
  `report_loader.py` calls `report_data.py`'s `latest_run_per_scenario`/
  `curated_output_paths`/`is_retired` to resolve each scenario's most
  recently imported files (or, once this run set is retired, the frozen
  `run_sets/non-motorized-2023/snapshot/` CSVs instead — see "Retiring a run
  set" above; this run set is the reference implementation for that
  mechanism, and `report_snapshot.py` is its declared
  `report_snapshot_script`, though it hasn't actually been retired/purged
  yet). The BY_2019 baseline (test_id 0) and the static TAZ/District
  shapefiles (`tdm/1_Inputs/1_TAZ/...`) are still read straight from the
  gitignored `tdm/` working tree either way, since neither is scoped to a
  single scenario/run and isn't part of what retirement freezes (see the
  known limitation noted under "Retiring a run set").

SE files are referenced in scenario YAMLs directly under `overrides:`
(`WFRC_SEFile`/`MAG_SEFile`, relative paths like
`'..\..\..\run_sets\non-motorized-2023\inputs\SE_S01.csv'`) — see the SE prep
bullet above for why, not via `input_files`.

### `toll-sensitivity-2026`

Example run set for toll sensitivity testing. Scenarios defined, no runs executed.

---

## Pending work / what to do next

In rough priority order:

**1. Fix the test suite's fixtures.**
`tests/` fixtures still assume the old mock TDM layout (copying a
`RunModel_stub.py` that no longer exists now that `tdm/` points at the real
repo) — ~19 errors in `test_config.py` / `test_integration.py` / `test_prep.py`.
Pre-existing, not caused by recent work, but blocks using `pytest` as a
signal until updated.

**2. Run `tdmruns validate-config --run-set non-motorized-2023`**
against the real submodule to confirm S01–S13's override keys are valid, then
consider re-running the scenarios through `run-scenario`/`run-set` so this run
set no longer depends on `manual_scenario_folder`/`import-manual-run-set` —
though that path is now solid enough (flattened, checksummed, schema-validated)
that switching isn't urgent on its own.

**3. Verify GitHub Actions actually deploys.**
`publish-report.yml` was updated this session to install `geopandas`/`plotly`
and register a `july2025` Jupyter kernel matching what the report `.qmd` files
declare — confirmed to render locally via `quarto render reports`, but not yet
confirmed against a real GitHub Pages deploy. Watch the first push's Actions
run for kernel/package issues that don't show up locally.

**4. `validate-config.yml` / `validate-run-metadata.yml` workflows** are
written but still unconfirmed against the real (possibly private) TDM repo —
if private, they'll need a deploy key or PAT to check out the submodule.

**5. `bin/RunModel.bat` end-to-end is confirmed working** (see "What's
currently mocked vs. real" above) — `bring-work-trips-closer-to-home`'s
recorded history shows it locating and running the staged driver script,
Cube Voyager executing for hours, and `VOYAGER_EXE` resolving correctly on a
real workstation. What's *not* yet confirmed: a CLI-driven run that also
comes back `status: "success"` end-to-end on the first try — every recorded
`execution_mode: "cli"` attempt so far predates the "decide status from the
model's own log" fix and got misclassified as failed by Voyager's exit code
alone (see above). Worth a fresh `run-scenario` invocation against an
already-seeded scenario to confirm the fix actually produces a clean
`"success"` now, rather than inferring it from older records.

**6. `start_from_copy` is now exercisable for `bring-work-trips-closer-to-home`.**
`Closer00` (`Closer01`/`Closer02`/`Closer03` all declare `start_from_copy:
Closer00`) has recorded successful runs now that `RunModel.bat` works
end-to-end, so the copy source resolves. Fixed a real bug in
`scenario_seed.seed()` this session: it used to require the single most
recent recorded run to have `status: "success"`, so Closer00's frequent
unrelated re-run failures (block-format/exit-code issues while iterating,
output curation tripping the 45 MB ceiling) would wrongly block Closer01/02/03
from copying, even with an earlier Closer00 success on record. It now calls
the new `metadata.latest_successful_run()`, which skips past newer failures
to find the most recent success. Also added `lock_down_copy: true` (scenario
YAML), since the raw scenario folder is reused across every retry of a given
scenario_id — without it, every Closer01 retry would re-`shutil.copytree()`
Closer00's entire raw folder (currently ~34 GB) again. Declare it on
Closer01/02/03 once each has been seeded once and doesn't need Closer00's
folder re-copied on further retries. Covered by new unit tests in
`tests/test_scenario_seed.py`; still not exercised end-to-end via a live
`run-scenario` invocation against the real TDM.

**7. Concurrent `run-set` execution (`max_parallel_runs`) is wired up but
not yet exercised end-to-end.** See the "In-place submodule checkout... but
same-ref scenarios now run concurrently" architecture decision above for the
full mechanism (`execution.run_scenarios()` groups by resolved `tdm_ref`,
checks out each group's ref exactly once, dispatches that group's scenarios
through a `ThreadPoolExecutor` bounded by `run_set.yaml`'s
`max_parallel_runs`). Fully covered by mocked unit tests in
`tests/test_execution.py` (no real submodule or Cube Voyager touched), but
no run set has actually declared `max_parallel_runs > 1` and been run for
real yet — worth a small, cheap real trial (e.g. 2 already-seeded scenarios
in one run set, `max_parallel_runs: 2`) before trusting it on a large batch,
to confirm Cube Voyager's own concurrent-instance behavior on the actual
workstation matches what was manually verified outside the framework.
