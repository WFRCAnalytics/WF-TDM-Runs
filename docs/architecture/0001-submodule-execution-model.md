# 0001: In-place sequential submodule checkout, not git worktrees

## Context

Early design considered giving every run an isolated `git worktree` of the
TDM submodule, so different scenarios could safely use different TDM
versions without one run's checkout affecting another's, and so the
architecture would be ready for parallel execution.

In practice, the TDM (Cube Voyager) executes in place inside its own
checkout, using its own `Scenarios/` folder as the run workspace. Cube
projects carry path and catalog assumptions tied to that location.

## Decision

v1 checks out the TDM submodule in place and runs scenarios sequentially.
Per-run isolation happens one level down, at the `Scenarios/{version}/{scenario_id}__{run_id}/`
folder, which is unique per attempt. Switching TDM versions between
scenarios means checking out a different ref in the same submodule location
before the next run, not maintaining multiple simultaneous checkouts.

## Consequences

Two scenarios in flight at once against different TDM versions is not
possible in v1 -- this matches how Cube Voyager is actually run today
(one license, one execution, in place) and removes a class of path/catalog
problems a worktree would have risked introducing for no immediate benefit.

If true parallel or distributed execution becomes a real requirement later,
the natural extension is `git worktree` per concurrent run (or separate
submodule clones), validated first against whatever Cube's path/catalog
assumptions turn out to require. Nothing about the run-folder, Control
Center rendering, or metadata design needs to change to support that --
only how the TDM submodule itself is checked out.
