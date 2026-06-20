# 0006: What v1 leaves out, and why it should still be addable later

## Context

The brief explicitly does not require v1 to support parallel/distributed
execution, scheduled/automated reruns, cross-version comparison reporting,
or dashboards, but does require the architecture not need major
restructuring to add them later.

## What's deferred, and the seam it would attach to

**Parallel/distributed execution.** Currently sequential, in-place submodule
checkout (ADR 0001). Adding this means giving each concurrent run its own
TDM checkout (`git worktree` or a separate clone), validated against
whatever path/catalog assumptions Cube actually has. Nothing about run
folders, Control Center rendering, metadata, or output curation needs to
change -- `run_scenario()` is already a self-contained unit of work that
doesn't share mutable state with any other run except the TDM checkout
itself.

**Scheduled/automated reruns.** `tdmruns run-set` is already a single
idempotent command (skips successful runs, re-runs failures) safe to invoke
repeatedly. A scheduler just needs somewhere to invoke it from with TDM
access -- which is also the blocker for running it in hosted CI (ADR 0005).

**Cross-version comparison reporting.** Run metadata already records the
exact resolved TDM version per run. A comparison view is a new Quarto page
querying `report_data.py` data across scenarios/run sets by TDM version
rather than by run set -- no change to how metadata is produced.

**Long-term archive of full raw outputs.** Deliberately out of scope (ADR
0003). Adding it later means writing the full inventory (already recorded)
to wherever the archive lives, keyed by the same run_id this repo already
uses -- not a change to anything currently built.

**Dashboards / advanced visualization.** Same data source
(`runs/**/run_metadata.json`) as the Quarto reports; an additional
consumer, not a replacement.
