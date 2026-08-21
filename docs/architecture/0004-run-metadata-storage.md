# 0004: Flat, schema-versioned JSON files as the source of truth, not a database

## Context

Run metadata needs to be the source of truth for reporting, and needs to
support "many independent runs over a long time, across many run sets."
A database would offer query convenience at scale, but adds an operational
dependency (something to host, back up, migrate) this framework doesn't
otherwise need.

## Decision

One `run_metadata.json` document per run, committed to the repo under
`runs/{run_set}/{scenario}/{run_id}/`, validated against
`config/schemas/run_metadata.schema.json` with an explicit
`schema_version` field. The Quarto reporting layer discovers and aggregates
across these files at build time; nothing else maintains a hand-written
index.

## Consequences

Metadata is git-diffable, human-readable without tooling, and requires no
server. Reporting is automatically data-driven -- a new run set shows up
the moment it has a committed run, with no reporting code change. Schema
evolution is handled by bumping `schema_version` and writing a short
migration note here rather than a database migration.

This will not scale gracefully to a very large number of runs (tens of
thousands) if reporting ever needs ad hoc cross-run-set querying beyond what
a directory scan can do efficiently. If that need arises, the metadata
files remain the source of truth and a database becomes a derived,
rebuildable index over them -- not a replacement.

## Update: one metadata file per attempt, permanently, at `run_info/{run_id}.json`

Originally each run's metadata document sat at
`runs/{run_set}/{scenario}/{run_id}/run_metadata.json`, a sibling of that
same directory's `outputs/` -- meaning every attempt, including every failed
retry, kept its own full curated-output copy forever. In practice this let
`runs/` bloat under active iteration, not just for finished run sets:
`bring-work-trips-closer-to-home` alone reached 3.7 GB across 2-5 attempts
per scenario, almost all of it superseded output nobody was reading.

Ported from the sibling `WF-TDM-Calibration` repo's `tdmcalib`: metadata
documents now live at `runs/{run_set}/{scenario}/run_info/{run_id}.json` --
one per attempt, permanent, never deleted -- while curated outputs move up
to `runs/{run_set}/{scenario}/outputs/` and are wiped and re-curated on
*every* attempt (`execution.py`'s `_reset_run_outputs()`), so only the
latest attempt's files are ever on disk. The metadata history is now
unbounded (nothing about it changed size-wise or scaling-wise); only the
disk-heavy curated-output side stopped accumulating. See
`src/tdmruns/metadata.py`'s module docstring and CLAUDE.md's "Only the
latest attempt's curated outputs are ever kept..." bullet for the full
mechanism, and "Retiring a run set" for how this narrows what
`snapshot-run-set`/`purge-run-set-outputs` are for.
