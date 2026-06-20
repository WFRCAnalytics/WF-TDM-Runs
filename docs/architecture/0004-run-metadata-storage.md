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
