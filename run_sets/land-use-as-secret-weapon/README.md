# land-use-as-secret-weapon

Run from the repo root (`M:\GitHub\WF-TDM-Runs`), with `pip install -e .` /
`uv run` set up.

## Prep inputs (once, or whenever the source data changes)

```
uv run python run_sets/land-use-as-secret-weapon/inputs/_input-prep/prepare-se-2040-base.py
```

Writes `inputs/SE_2040_Base.csv` (WFRC 2040 data for TAZID 1-2216, MAG data
interpolated to 2040 for TAZID 2217-3562).

## Validate config

```
uv run tdmruns validate-config --run-set land-use-as-secret-weapon
```

Checks every scenario's override keys against the baseline before anything
is run. Run this after editing `run_set.yaml` or any scenario YAML.

## Sync the TDM submodule

```
uv run tdmruns sync-tdm --run-set land-use-as-secret-weapon
```

Checks out the submodule to this run_set's `tdm_ref`. Refuses on a dirty
submodule tree. `run-scenario`/`run-set` do this automatically, but useful
to run standalone first if you just want to confirm the ref resolves.

## Run one scenario

```
uv run tdmruns run-scenario --run-set land-use-as-secret-weapon --scenario lusw00
```

Add `--force` to re-run a scenario that already has a successful recorded run.

## Run every scenario in the run set

```
uv run tdmruns run-set --run-set land-use-as-secret-weapon
```

## Check status

```
uv run tdmruns status
```

Shows the latest result per scenario across all run sets.

## Copy outputs only, without running the model

Not applicable here — this run set executes through the CLI
(`run-scenario`/`run-set`), which curates outputs automatically as part of
the run. `import-manual-run` / `import-manual-run-set` only apply to
scenarios run manually outside the CLI (see the framework's top-level
`CLAUDE.md`); use them only if a scenario here ever needs to be run that way
instead.

## Retiring this run set (once it's done and won't be re-run)

```
uv run tdmruns snapshot-run-set --run-set land-use-as-secret-weapon
uv run tdmruns purge-run-set-outputs --run-set land-use-as-secret-weapon
```

Only relevant once reports exist that read from `runs/` and the curated
outputs need to be trimmed down. See "Retiring a run set" in the top-level
`CLAUDE.md` before using this.
