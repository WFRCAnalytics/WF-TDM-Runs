# Report structure: `bring-work-trips-closer-to-home`

## Context

WFRC Analytics has an approved scoping memo for a sketch-level TDM test: shift
5/10/25% of home-based-work (HBW) trips that currently leave a "target area"
back into it, using the existing internal destination pattern, holding
everything else constant. Three geography types (City Area, Medium District,
Workshop Area) × three shift levels = 9 scenarios, plus a Closer00 baseline —
all 10 are already fully configured in `run_sets/bring-work-trips-closer-to-home/`,
and the redistribution mechanism itself is really implemented (not a stub) in
`scripts/redistribute_hbw_trips.py`. What doesn't exist yet is the reporting
layer that turns curated model outputs into the memo's promised deliverable
(§6: corridor volumes, transit ridership, VMT/VHD by county and facility
type, VHT/household, HBW trip length, plain-language summary + caveats),
with City Area as the lead geography and VHD as the lead metric (§7).

This plan is **documentation only** — no code or config changes have been
made yet. It gives a future session everything needed to execute without
re-deriving it: the data landed, the gaps found, the file layout, and the
section-by-section outline tied line-for-line to the memo.

## Current state (verified 2026-07-09)

- **Scenario config is complete.** `run_sets/bring-work-trips-closer-to-home/run_set.yaml`
  + `scenarios/Closer00.yaml`–`Closer09.yaml`: Closer00 = baseline; Closer01/04/07 =
  City Area (`CITY_UGRC`) at 10/5/25%; Closer02/05/08 = Medium District
  (`DISTMED`) at 10/5/25%; Closer03/06/09 = Workshop Area (`CITYGRP`) at
  10/5/25%. All non-baseline scenarios use `start_from_copy: Closer00`.
  (Note: `run_set.yaml`'s `description:` field is stale — it says "10%...
  three scenarios total, one per geography type," left over from an earlier
  draft of the design. Worth a one-line fix whenever this file is next
  touched, but not blocking.)
- **Data readiness is not complete.** Only Closer00 has a trustworthy
  successful run (`runs/bring-work-trips-closer-to-home/Closer00/20260709-131353-5a00/`).
  Closer01's one recorded attempt is `status: "failed"` (Voyager exit code 2)
  and its curated output checksums match Closer00's — stale carry-over, not
  real Closer01 data. Closer02–Closer09 have never executed.
- **No report scaffold exists** for this run set under `reports/run_sets/`
  (only `non-motorized-2023/` exists there today). `reports/index.qmd`'s
  generic branch (`report_data.has_custom_report_pages()`, `report_data.py:20-26`)
  auto-detects any run set with a `reports/run_sets/<id>/` directory and
  links to it with a generic blurb — **no index.qmd edit is required** to
  get a working link once the folder exists. An explicit named branch (like
  the hardcoded `non-motorized-2023` block at `index.qmd:36-47`, giving
  direct `slides.html`/`summary.html` links) is a nice-to-have, not a
  prerequisite.
- **Curated outputs are missing 3 things the report needs** (confirmed
  against `tdm/Scenarios/.../Closer00/` raw output tree — the underlying files
  already exist on disk, they're just not in `outputs.include` yet):
  1. `CO_FIPS` column on `Summary_SEGID.csv` (needed for county rollups) —
     add to the existing `columns:` list in `run_set.yaml`.
  2. `4_ModeChoice/3_TransitAssign/_transit_brding_summary_route.csv`
     (`Name`/`Period`/`Boardings`/`Alightings` — `Name` values `Blue`/`Green`/`Red`
     = TRAX, `RCRT_OGPN` = FrontRunner) — not curated at all today; add as a
     new `outputs.include` entry (~23 KB, trivial against the 95 MB cap).
  3. `0_InputProcessing/SE_File.dbf` (has `Z`/`TOTHH`/`CO_FIPS`/`CO_NAME`) for
     per-household normalization (VHT/HH) — add as a new entry. Since land
     use is identical across all 10 scenarios per the memo's own design, this
     only needs to be captured for Closer00 and reused everywhere.
  - Fix these in `run_set.yaml` and re-run
    `tdmruns import-manual-run --run-set bring-work-trips-closer-to-home
    --scenario Closer00` to re-curate once these are added — do this **before**
    building the loader, since the loader depends on all three.
- **No corridor→SEGID crosswalk exists.** Checked two candidate sources:
  `tdm/1_Inputs/6_Segment/Master_Segs_withFactors_20251229_Direction.dbf`
  (good for numbered routes — I-15/I-80/I-215/US-89/SR-201/SR-73 — but has
  no coverage of the named local arterials/parkways the memo lists) vs.
  `tdm/1_Inputs/3_Highway/GIS/WFv1000_MasterNet_20250821 - Link.dbf` (the
  network's actual link file — has `SEGID` + a `STREET` field covering the
  full memo list: Legacy, Bangerter, Redwood Rd, West Davis, State St, 5600
  South, 3300 South, 9000 South, 12300 South, Porter Rockwell (truncated
  `Porter Ro`), MVC/MVC-201, University Pkwy, plus the numbered routes).
  **`Link.dbf` is the right source.** Two names need fuzzy/manual matching
  (`MVC`/`MVC-201`, `Porter Ro`) — spot-check against a map before finalizing.
- **HBW trip length** is a straightforward join, not a gap: `PMT` from
  `TAZ-Based Metrics.csv` (`Metric=='PMT', Purpose=='HBW'`) divided by trip
  count (`All`, `Purpose=='HBW'`) from `_ZoneSummary_TripsByMode.csv`, both
  already curated, joined on `TAZID/Period/PA`.

## Recommended file layout

- `run_sets/bring-work-trips-closer-to-home/inputs/corridor_segid_crosswalk.csv`
  — one-time, committed artifact (`SEGID, corridor_label`) built from the
  live `Link.dbf` `STREET` field. Keeps `report_loader.py` a plain-CSV reader
  at render time (no geopandas/shapefile dependency baked into report code),
  and makes the crosswalk itself reviewable/versioned rather than re-derived
  silently on every render.
- `run_sets/bring-work-trips-closer-to-home/report_loader.py` — mirrors
  `run_sets/non-motorized-2023/report_loader.py`'s shape exactly (shared
  module imported by both `.qmd` files, single `load()` entrypoint,
  retirement-aware leaf loaders via `report_data.is_retired()` +
  `run_sets/.../snapshot/`). Contents:
  - `SCENARIO_META` — hand-encoded `scenario_id → geography_type, shift_pct`
    table for Closer00–Closer09 (same style as non-motorized-2023's hardcoded
    `SCENARIO_META`).
  - `COUNTY_FIPS_NAME` — small static dict, the 6 WFRC/MAG counties.
  - Leaf loaders (`*_from_runs()` + retirement-aware wrapper, one pair per
    curated file): `load_trips`, `load_shares`, `load_segid` (joins in the
    corridor crosswalk + county names), `load_taz_metrics`,
    `load_transit_route` (new), `load_hh` (new, Closer00-only — land use is
    constant across scenarios by design).
  - Aggregation/delta functions, each parameterized by `geography_type` /
    `shift_pct` so charts can facet City Area vs. Medium District vs.
    Workshop Area: `build_corridor_volumes`, `build_vmt_vhd_by_county_facility`,
    `build_transit_ridership`, `build_vht_per_household`,
    `build_hbw_trip_length`, `build_mode_share` (supporting only).
- `reports/run_sets/bring-work-trips-closer-to-home/summary.qmd` and
  `slides.qmd` — same two-document pattern as non-motorized-2023.
- Optional, not required: a ~10-line addition to `reports/index.qmd`
  alongside the existing `non-motorized-2023` special case, for direct
  `slides.html`/`summary.html` links instead of the generic fallback blurb.
- `run_sets/bring-work-trips-closer-to-home/report_snapshot.py` — **defer**.
  The `report_snapshot_script: report_snapshot.py` reference in `run_set.yaml`
  is already dangling and harmless; it only matters when
  `tdmruns snapshot-run-set` is actually invoked, which per this repo's
  retirement pattern (CLAUDE.md) happens only when the run set is done and
  about to be purged. Writing it now means rewriting it every time the
  loader's `*_from_runs()` functions change during initial development.

## `summary.qmd` section outline (mirrored, condensed, in `slides.qmd`)

Ordered and weighted to match the memo's §7 decisions (City Area leads the
narrative; VHD leads as the headline metric, VMT is explanatory):

1. **Header/scope recap** — 3-4 sentences: the question, 2027 basis /
   v10.0.0-beta.1, the mechanism — not a methodology deep-dive (that's
   pushed to the appendix).
2. **Plain-language takeaways** — headline City-Area number first, direction/
   magnitude for VHD and VMT, one caveat teaser line.
3. **Congestion (headline): VHD by county/region and facility type** — City
   Area's 3 shift levels as the primary chart; Medium District/Workshop Area
   shown directly beneath in a visually subordinate (smaller, muted) form —
   one chart function parameterized by `geography_type`, called once
   prominent + twice reduced.
4. **Why VHD moved: VMT by county/region and facility type** — explicitly
   framed as explanatory, same lead/secondary layout.
5. **Corridor detail** — named-corridor volume-change table (City Area
   first), with Medium District/Workshop Area as a compact comparison
   beneath.
6. **Transit ridership** — FrontRunner + TRAX boardings, same structure.
7. **Free time added back: peak VHT per household** — county + region, City
   Area primary. Deliberately VHT (free-flow + delay), not VHD, so it also
   captures the time saved from trips simply being shorter, not only from
   less congestion.
8. **HBW trip length** — county + region, City Area primary.
9. **Mode share** — supporting context, explicitly labeled supplemental (not
   a memo-mandated headline).
10. **Cross-scale comparison table** — all 3 geography types × 3 shift levels
    side by side, since §7 keeps this a first-class deliverable even though
    City Area leads the write-up.
11. **Caveats and interpretation** — restate the memo's 5 mandatory caveats
    near-verbatim (not a real forecast; no feasibility check; sketch/order-
    of-magnitude; HBW-only; no second-order effects; same mechanism at all 3
    shift levels).
12. **Appendix** — mechanism detail, scenario-ID mapping table, model
    version/vintage, links to `run_set.yaml`/`redistribute_hbw_trips.py`, and
    (while the build is in flight) an explicit data-completeness note: "N of
    9 shift scenarios have verified runs as of this rendering."

## Build order (for a future implementation session)

1. Fix `run_set.yaml`'s 3 curation gaps; re-import Closer00.
2. Build and spot-check `corridor_segid_crosswalk.csv` against `Link.dbf`.
3. Build `report_loader.py` leaf loaders + aggregations, smoke-test against
   Closer00 alone (row counts, no-null joins, corridor coverage %).
4. Scaffold both `.qmd` files with the full section structure above,
   populated with Closer00 absolute numbers and explicit "pending" callouts
   wherever a section needs a second scenario for deltas. Render and review
   structure/layout before investing in more scenarios.
5. Get Closer01 to a real successful run (it's currently `failed` with
   stale/carried-over outputs) — first real before/after pair, validates the
   entire delta pipeline.
6. Prioritize remaining runs in lead-geography order: City Area's other two
   shift levels (Closer04, Closer07) next, then Medium District
   (Closer02/05/08), then Workshop Area (Closer03/06/09) last.
7. Extend `SCENARIO_META` as each batch lands; no loader redesign needed.

## Verification

- After step 1: confirm `tdmruns import-manual-run` picks up `CO_FIPS`, the
  transit boardings file, and `SE_File` in the re-curated
  `runs/bring-work-trips-closer-to-home/Closer00/<new-run-id>/outputs/`.
- After step 3: unit-test-style smoke checks on the loader (row counts
  match raw file counts, join keys don't drop rows unexpectedly, corridor
  crosswalk coverage is high for the named list).
- After step 4: `quarto render reports` (or `quarto preview reports`) and
  visually confirm both `.qmd` files render without errors and read
  sensibly with Closer00-only data before scaling to more scenarios.

## Addendum (2026-07-10): HBW trip length distribution via matrix curation

The average-only HBW trip length metric above was extended with a full
trip-volume-weighted length distribution, using a new framework-level
`outputs.include` entry type: `{"matrix": <glob>, "tabs": [...]}` (parallel
to `{"file": ..., "columns": [...]}`), added to `config/schemas/*.schema.json`,
`src/tdmruns/outputs.py`, and a new shared `src/tdmruns/matrix_utils.py`.
This is a real framework mechanism, not a one-off script — reusable by any
future run_set that needs a specific table extracted from a large
multi-table Cube Voyager `.mtx` (skims routinely run 300-400 MB; the whole
file is never curated).

**Key facts, verified this session:**
- Curation was previously 100% Voyager-free; a `matrix:` entry makes
  curation invoke CONVERTMAT for the first time, scoped only to run_sets
  that declare one (`execution.py` threads `config/local.yaml`'s
  `Voyager_EXE` into `out.curate()` for both `run_scenario()` and
  `import_manual_run()`).
- `GP_Dist` (the highway skim's distance table) is congestion-sensitive —
  the shortest path is chosen by time (`07_PerformFinalNetSkim.s`'s
  `PATHLOAD PATH=lw.AM_TotTime`), with distance traced along that path — so
  it must be extracted per scenario, not once and reused.
- `redistribute_hbw_trips.py` was **not** refactored to share
  `matrix_utils.py`'s CONVERTMAT helpers, despite the duplication, because
  it runs under a separate Python environment
  (`tdm/2_ModelScripts/_Python/py-tdm-env/`) that does not have `tdmruns`
  installed — confirmed via a direct import test. Refactoring it would have
  broken an already-working script.
- `HBW_trips_allsegs_pkok.mtx`'s tables (`motor`, `nonmotor`, plus 24
  per-mode detail tables) are stored at **100x scale** — confirmed
  empirically: `(motor + nonmotor) / 100` matches
  `_ZoneSummary_TripsByMode.csv`'s trusted HBW/Dy/P region total within
  0.001%. `report_loader.py`'s `HBW_MATRIX_SCALE = 100` applies this.
- The distribution is built region-wide only (not by county) from the raw
  `GP_Dist` skim × `(motor+nonmotor)/100` trip matrix, binned into
  `DISTANCE_BIN_EDGES`, excluding Cube's `NOACCESS` sentinel (9999) cells.
  Its weighted average (10.83 mi, Closer00) is a useful but *not identical*
  cross-check against the existing PMT/trips-based average (10.56 mi) —
  different methodologies, expected to be close, not equal.
- CONVERTMAT's own incidental script/log files must run in a scratch
  `tempfile.TemporaryDirectory()`, not next to the destination OMX — an
  early version left `.s`/`.bat`/`TPPL*.PRN` files sitting inside the
  committed `runs/.../outputs/` folder, caught and fixed before backfilling.
- Closer00–03 were backfilled via `tdmruns import-manual-run` (no Cube
  re-run needed — the source `.mtx` files already existed on disk from the
  earlier runs); Closer04–09 will pick up the new curated outputs
  automatically once they're first run or imported, no further code changes
  needed.
