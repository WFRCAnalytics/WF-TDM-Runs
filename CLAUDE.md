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
against a Cube Voyager TDM connected as a git submodule. Built, tested (34 pytest
tests passing), and documented.

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
3. Loads a baseline Control Center file from the TDM's `Scenarios/_defaults/`
   library, layers run_set overrides then scenario overrides on top (resolving
   any `input_files` relative paths to absolute), fills in orchestrator-computed
   identity/path fields, writes `_ControlCenter.yaml` into a fresh run folder
4. Invokes the TDM's fixed batch entry point with the control file path and
   scenario folder path as arguments
5. Inventories all outputs, copies only the glob-selected subset (hard 100
   MB/file ceiling) into the repo
6. Writes `run_metadata.json` — the source of truth for reporting

### What it doesn't touch

The TDM codebase, the `_defaults/` library, how Cube Voyager runs internally,
or the `Scenarios/` gitignored working folder convention.

### Key real-world constraints that shaped the design

- The TDM is **Cube Voyager**, run via one fixed batch entry point per version,
  taking exactly two arguments: a Control Center file path and a scenario folder
  path. That calling convention is captured in `config/framework.yaml`
  `execution:` — not hardcoded.
- The `_ControlCenter.yaml` is plain YAML. The defaults library has files like
  `1ControlCenter - BY_2023.block`, `1ControlCenter - RTP_2050.block`,
  `NB28_2042`, `Needs_2032`, `TIP_2028`, etc. — extension is `.block` but
  content is plain YAML throughout.
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
├── tdm/                          ← TDM git submodule (currently points at mock)
├── config/
│   ├── framework.yaml            ← global settings
│   ├── local.example.yaml        ← copy to local.yaml (gitignored) per machine
│   └── schemas/                  ← JSON Schema for run_set, scenario, run_metadata
├── run_sets/
│   └── <run_set_id>/
│       ├── run_set.yaml
│       ├── scenarios/
│       │   └── <scenario_id>.yaml
│       ├── inputs/               ← prepped input files (e.g. SE CSVs); gitignored until generated
│       └── prep/                 ← input preparation notebooks (committed)
├── runs/                         ← committed metadata + curated outputs only
│   └── <run_set_id>/<scenario_id>/<run_id>/
│       ├── run_metadata.json
│       └── outputs/
├── reports/                      ← Quarto website, data-driven from runs/
│   ├── _quarto.yml
│   ├── index.qmd                 ← auto-discovers all run sets, links to their pages
│   ├── report_data.py            ← shared data helpers (reads runs/ metadata)
│   └── run_sets/
│       └── <run_set_id>.qmd      ← per-run-set detail page
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
├── tests/                        ← 34 pytest tests, all passing
├── docs/architecture/            ← 6 ADRs
└── pyproject.toml
```

### CLI commands

```bash
pip install -e .
tdmruns validate-config                              # validate all run_sets
tdmruns validate-config --run-set <id>              # validate one run_set
tdmruns run-set --run-set <id>                      # run all scenarios
tdmruns run-scenario --run-set <id> --scenario <id> # run one scenario
tdmruns run-scenario ... --force                    # re-run even if already successful
tdmruns status                                      # show latest result per scenario
```

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

- `tdm/` submodule points at a **local mock TDM repo** (a `Scenarios/_defaults/`
  library with two templates and a `RunModel_stub.py` stand-in for `RunModel.bat`).
  To connect the real TDM: `git submodule set-url tdm <real-url>`, then
  `git submodule sync && git submodule update --init --recursive`.
- `config/framework.yaml` `execution.entry_point` is currently `RunModel_stub.py` —
  change to `RunModel.bat` once the real submodule is connected.
- The framework itself is real, working Python. Run `pytest tests/` to confirm.
- Quarto reporting (`reports/`) is structured and coded but has not been rendered —
  run `quarto preview reports` as the first check once Quarto CLI is available.
- GitHub Actions workflows are written but haven't run (no real GitHub repo yet).

### Architecture decisions (summary — full detail in `docs/architecture/`)

- **In-place sequential submodule checkout, not git worktrees** — Cube runs
  in place inside its own checkout. Worktree isolation adds complexity for no
  immediate benefit. Deferred to a future PR if parallel execution is needed.
- **One override mechanism** — `_ControlCenter.yaml` keys are all just keys,
  whether they select input files or tune model parameters. `input_files` in
  scenario YAML is syntactic sugar for file-path overrides with automatic path
  resolution; it merges into the same single override dict.
- **Input prep is manual, not automated** — each run_set has a `prep/` folder
  for notebooks that generate input files (e.g. SE CSVs). The framework does
  not run prep; analysts run it once before executing the run_set.
- **Curated outputs with a hard size ceiling** — raw outputs stay gitignored.
  Only a declared, glob-selected, size-checked subset enters the repo.
- **Flat JSON metadata as source of truth** — one `run_metadata.json` per run,
  committed, schema-versioned. No database. Quarto reads these directly.
- **CI scoped to validation and reporting** — never model execution.
- **Future capabilities** (parallel runs, scheduled reruns, cross-version
  comparison, dashboards) are all deferred but attach cleanly to existing
  seams without redesign.

---

## The presentation (Part 2)

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

### `non-motorized-2026`

13-scenario non-motorized sensitivity study. Repeat of the study that originally
took over a month — the intended pilot run set.

- **TDM ref:** `v920-E3`
- **Baseline:** `1ControlCenter - BY_2019.block`
- **Scenarios:** S01–S13 (HH/EMP multipliers at smldst/smldst+taz scope, plus
  full SE_2050 and SE_2050_transit_corridors substitutions)
- **SE prep:** `run_sets/non-motorized-2026/prep/1-non-motorized-sensitivity-test-setup.ipynb`
  — run once to generate `inputs/SE_S01.csv` through `inputs/SE_S13.csv`
- **Reporting page:** `reports/run_sets/non-motorized-2026.qmd`

SE files are referenced in scenario YAMLs via `input_files` (relative paths
like `inputs/SE_S01.csv`), resolved to absolute at runtime.

### `toll-sensitivity-2026`

Example run set for toll sensitivity testing. Scenarios defined, no runs executed.

---

## Pending work / what to do next

In rough priority order:

**1. Run the SE prep notebook.**
Open and execute `run_sets/non-motorized-2026/prep/1-non-motorized-sensitivity-test-setup.ipynb`
in the `july2025` conda env. Adjust the `tdm_dev_dir` path at the top if needed.
Outputs go to `run_sets/non-motorized-2026/inputs/SE_S01.csv` through `SE_S13.csv`.

**2. Connect the real TDM submodule.**
```bash
git submodule set-url tdm <real-tdm-repo-url>
git submodule sync
git submodule update --init --recursive
```
Then update `config/framework.yaml` `execution.entry_point` from
`RunModel_stub.py` to `RunModel.bat`.

**3. Verify `Scenarios/_defaults/` path.**
Confirm the real TDM repo's defaults library lives at `Scenarios/_defaults/`
and that `1ControlCenter - BY_2019.block` exists there. Update
`control_center_defaults_dir` in `config/framework.yaml` if the path differs.

**4. Run `tdmruns validate-config --run-set non-motorized-2026`** against the
real submodule to confirm all override keys in S01–S13 are valid for that baseline.

**5. Execute the pilot run set.**
```bash
tdmruns run-set --run-set non-motorized-2026
```

**6. Render and verify the Quarto reports.**
```bash
quarto preview reports
```

**7. Set up the real GitHub repo**, enable GitHub Pages, configure Actions.
If the TDM repo is private, add a deploy key or PAT for the `validate-config.yml`
workflow that checks out the submodule.

**8. Present and get pilot approval.**
Presentation deck has been removed from the repo (_dev/ deleted).
