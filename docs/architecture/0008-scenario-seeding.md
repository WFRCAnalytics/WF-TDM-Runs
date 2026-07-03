# 0008: `start_from_copy` -- seed a scenario's raw folder from a prior run

## Context

Some scenario modifications only take effect late in the model pipeline --
e.g. a change applied at mode choice. Rerunning every upstream step (input
processing, HH disaggregation, trip generation, distribution) from scratch
for those scenarios wastes most of a run's time reproducing output that
would be identical to an already-completed scenario's. Analysts want a way
to start a scenario from a copy of another scenario's already-run raw
folder instead of an empty one.

This is a distinct concern from `driver_script` (ADR 0007). That mechanism
decides *which code runs*; this one decides *what state the scenario folder
starts with* before that code runs. A scenario using `start_from_copy` will
typically also declare a `driver_script` whose custom logic skips the steps
whose output was already copied in -- but writing that skip logic is the
analyst's job inside the `.s` script itself. This framework mechanism only
ever copies files; it never inspects or modifies what Cube Voyager does
with them.

## Decision

A scenario may declare `start_from_copy: <scenario_id>`, naming another
scenario in the same run set. When declared, `run_scenario()` copies that
scenario's entire raw scenario folder into this scenario's freshly created
folder, before the Control Center is rendered or a driver script is staged
-- so this run's own files land on top of (and overwrite) whatever stale
copies came along in the copy, not the other way around.

The source folder is resolved via `metadata.latest_run(repo_root,
run_set_id, source_scenario_id)`'s recorded `scenario_folder` -- not the
source scenario's declared `manual_scenario_folder`. This works uniformly
whether the source scenario was executed through the CLI or imported from a
manual run (`import_manual_run()` records `scenario_folder` too), and reuses
the existing "most recent run" lookup rather than re-deriving one. It also
means `start_from_copy` has a real precondition: the source scenario must
already have a successful recorded run, checked explicitly
(`scenario_seed.seed()` raises `ScenarioSeedError` otherwise, along with a
missing-on-disk check for the recorded folder -- retirement only purges
curated `runs/**/outputs/` copies, never the raw TDM working folder, but
nothing guarantees it wasn't cleaned up by hand).

`start_from_copy` is scenario-only, not available at the run_set level --
it names a specific sibling scenario, which is never a run_set-wide default
the way `tdm_ref` or `driver_script` can be. It is scoped to scenarios
within the same run set; cross-run_set copying isn't supported (no known
need for it yet).

This wires into `run-scenario`/`run-set`'s existing pipeline only. There is
no standalone CLI command for it, unlike `prep-scenario`. It therefore
depends on the same `RunModel.bat` blocker as everything else in that
pipeline -- see CLAUDE.md pending work #1.

`run_metadata.json`'s `seeded_from` (`{scenario_id, run_id}`) always records
which prior run a scenario was seeded from, when one was used -- the same
"record everything that was actually used" property established for
overrides (ADR 0002) and driver scripts (ADR 0007).

## Consequences

A run_set can express "this scenario only changes something downstream of
step N" directly in its scenario YAML, and get the time savings without any
manual folder wrangling, once CLI-driven execution works. The copy itself
can be large (full scenario folders run tens of GB), so this trades disk
I/O time for recompute time -- a reasonable trade when upstream steps are
the expensive ones.

The cost: this can't be exercised yet for any real run_set. It requires (a)
`RunModel.bat` to exist so `run-scenario` can execute at all, and (b) the
source scenario to already have a successful recorded run -- for
`bring-work-trips-closer-to-home`, that means `Close00` needs a run_metadata
record before `Close01`'s `start_from_copy: Close00` can resolve to
anything. Until both are true, this mechanism is dormant but ready.
