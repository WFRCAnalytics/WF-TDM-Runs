"""Command-line interface. Run `tdmruns --help` from anywhere inside the repo."""

import sys
from pathlib import Path

import click

from tdmruns import config as cfg
from tdmruns import execution as ex
from tdmruns import metadata as md
from tdmruns import prep
from tdmruns import submodule as sub
from tdmruns.exceptions import tdmrunsError
from tdmruns.paths import find_repo_root


@click.group()
@click.pass_context
def main(ctx):
    """TDM run management framework."""
    try:
        ctx.obj = {"repo_root": find_repo_root()}
    except tdmrunsError as e:
        click.echo(str(e), err=True)
        sys.exit(2)


@main.command("validate-config")
@click.option("--run-set", "run_set_id", default=None, help="Validate only this run set.")
@click.pass_context
def validate_config(ctx, run_set_id):
    """Validate run set and scenario configs against schema, and check every
    declared override key exists in its baseline Control Center file."""
    repo_root = ctx.obj["repo_root"]
    run_set_ids = [run_set_id] if run_set_id else _all_run_set_ids(repo_root)
    if not run_set_ids:
        click.echo("No run sets found under run_sets/.")
        return
    framework = cfg.load_framework_config(repo_root)
    tdm_path = repo_root / framework["tdm_submodule_path"]
    had_error = False
    for rsid in run_set_ids:
        try:
            run_set = cfg.load_run_set(repo_root, rsid)
        except tdmrunsError as e:
            click.echo(f"[FAIL] run set '{rsid}': {e}", err=True)
            had_error = True
            continue
        scenario_ids = cfg.list_scenario_ids(repo_root, rsid)
        if not scenario_ids:
            click.echo(f"[WARN] run set '{rsid}' has no scenarios.")
        for sid in scenario_ids:
            try:
                scenario = cfg.load_scenario(repo_root, rsid, sid)
                from tdmruns import controlcenter as cc

                baseline_filename = cfg.resolved_baseline_filename(run_set, scenario)
                baseline = cc.load_baseline(
                    tdm_path, framework["control_center_defaults_dir"], baseline_filename
                )
                rs_dir = repo_root / "run_sets" / rsid
                run_set_overrides, scenario_overrides = cfg.merged_control_center_overrides(
                    run_set, scenario, rs_dir
                )
                cc.validate_overrides(baseline, run_set_overrides, f"run set '{rsid}'.overrides")
                cc.validate_overrides(baseline, scenario_overrides, f"scenario '{sid}'.overrides")
                cfg.resolved_output_spec(framework, run_set, scenario)
                click.echo(f"[OK]   {rsid}/{sid}")
            except tdmrunsError as e:
                click.echo(f"[FAIL] {rsid}/{sid}: {e}", err=True)
                had_error = True
    sys.exit(1 if had_error else 0)


@main.command("sync-tdm")
@click.option("--run-set", "run_set_id", required=True)
@click.option(
    "--scenario", "scenario_id", default=None,
    help="Use this scenario's tdm_ref override instead of the run set's.",
)
def sync_tdm_cmd(run_set_id, scenario_id):
    """Make the TDM submodule match the tag/branch/commit declared in the
    run set's (or scenario's) tdm_ref -- a git checkout under the hood, so
    it mutates the submodule's working tree. Refuses on a dirty tree before
    and after checkout, same as a real scenario run, but does not render a
    Control Center or execute the model."""
    repo_root = find_repo_root()
    label = f"{run_set_id}/{scenario_id}" if scenario_id else run_set_id
    try:
        framework = cfg.load_framework_config(repo_root)
        run_set = cfg.load_run_set(repo_root, run_set_id)
        ref = run_set["tdm_ref"]
        if scenario_id:
            scenario = cfg.load_scenario(repo_root, run_set_id, scenario_id)
            ref = cfg.resolved_tdm_ref(run_set, scenario)
        tdm_path = repo_root / framework["tdm_submodule_path"]
        state = sub.resolve_version(repo_root, tdm_path, ref)
    except tdmrunsError as e:
        click.echo(f"[FAIL] {label}: {e}", err=True)
        sys.exit(1)
    click.echo(f"[OK] {label}: TDM synced to '{ref}'")
    for k, v in state.as_dict().items():
        click.echo(f"  {k}: {v}")


@main.command("run-scenario")
@click.option("--run-set", "run_set_id", required=True)
@click.option("--scenario", "scenario_id", required=True)
@click.option("--force", is_flag=True, help="Run even if a successful run already exists.")
def run_scenario_cmd(run_set_id, scenario_id, force):
    """Run a single scenario end to end."""
    repo_root = find_repo_root()
    try:
        result = ex.run_scenario(repo_root, run_set_id, scenario_id, force=force)
    except tdmrunsError as e:
        click.echo(f"[FAIL] {run_set_id}/{scenario_id}: {e}", err=True)
        sys.exit(1)
    click.echo(f"[{result['status'].upper()}] {run_set_id}/{scenario_id} run {result['run_id']}")
    if result["status"] != "success":
        click.echo(f"  {result.get('error')}", err=True)
        sys.exit(1)


@main.command("run-set")
@click.option("--run-set", "run_set_id", required=True)
@click.option("--only", "only", default=None, help="Comma-separated scenario IDs to run.")
@click.option(
    "--force", is_flag=True, help="Re-run scenarios even if a successful run already exists."
)
def run_set_cmd(run_set_id, only, force):
    """Run every scenario in a run set sequentially. A failed scenario does
    not stop the rest of the run set."""
    repo_root = find_repo_root()
    only_list = only.split(",") if only else None
    results = ex.run_scenarios(repo_root, run_set_id, only=only_list, force=force)
    n_ok = sum(1 for r in results if r["status"] == "success")
    n_fail = sum(1 for r in results if r["status"] != "success")
    for r in results:
        click.echo(
            f"[{r['status'].upper():7s}] {run_set_id}/{r['scenario_id']}  run={r.get('run_id')}"
        )
    click.echo(f"\n{n_ok} succeeded, {n_fail} failed.")
    sys.exit(1 if n_fail else 0)


@main.command("import-manual-run")
@click.option("--run-set", "run_set_id", required=True)
@click.option("--scenario", "scenario_id", required=True)
@click.option(
    "--scenario-folder", "scenario_folder",
    default=None,
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    help=(
        "Raw output folder from a scenario run outside the CLI (e.g. Cube Voyager invoked "
        "directly). Defaults to the scenario's manual_scenario_folder in its YAML."
    ),
)
@click.pass_context
def import_manual_run_cmd(ctx, run_set_id, scenario_id, scenario_folder):
    """Curate outputs for a scenario that was run manually, outside
    run-scenario/run-set. Applies the scenario's outputs.include glob
    selection and size ceiling exactly as a CLI-driven run would, copies the
    result into runs/<run-set>/<scenario>/<run-id>/outputs/, and records
    run_metadata.json with execution_mode "manual" so it's clear the model
    itself wasn't invoked by this framework. Does not touch the TDM
    submodule. Always creates a new timestamped run -- there's no
    skip-if-unchanged check, since running this command is itself the
    deliberate signal to (re-)gather outputs."""
    repo_root = ctx.obj["repo_root"]
    try:
        result = ex.import_manual_run(repo_root, run_set_id, scenario_id, scenario_folder)
    except tdmrunsError as e:
        click.echo(f"[FAIL] {run_set_id}/{scenario_id}: {e}", err=True)
        sys.exit(1)
    click.echo(
        f"[{result['status'].upper()}] {run_set_id}/{scenario_id} run {result['run_id']} (manual)"
    )
    n_curated = len(result["outputs"]["curated"])
    click.echo(f"  {n_curated} file(s) curated to runs/{run_set_id}/{scenario_id}/{result['run_id']}/outputs/")
    if result["status"] != "success":
        click.echo(f"  {result.get('error')}", err=True)
        sys.exit(1)


@main.command("import-manual-run-set")
@click.option("--run-set", "run_set_id", required=True)
@click.option("--only", "only", default=None, help="Comma-separated scenario IDs to import.")
def import_manual_run_set_cmd(run_set_id, only):
    """Curate outputs for every scenario in a run set that was run manually,
    using each scenario's declared manual_scenario_folder. A failed or
    undeclared scenario does not stop the rest of the run set. Always
    creates a new timestamped run per scenario -- see import-manual-run."""
    repo_root = find_repo_root()
    only_list = only.split(",") if only else None
    results = ex.import_manual_run_set(repo_root, run_set_id, only=only_list)
    n_ok = sum(1 for r in results if r["status"] == "success")
    n_fail = sum(1 for r in results if r["status"] != "success")
    for r in results:
        click.echo(
            f"[{r['status'].upper():7s}] {run_set_id}/{r['scenario_id']}  run={r.get('run_id')}"
        )
        if r["status"] != "success" and r.get("error"):
            click.echo(f"    {r['error']}", err=True)
    click.echo(f"\n{n_ok} succeeded, {n_fail} failed.")
    sys.exit(1 if n_fail else 0)


@main.command("prep-scenario")
@click.option("--run-set", "run_set_id", required=True)
@click.option("--scenario", "scenario_id", required=True)
@click.pass_context
def prep_scenario_cmd(ctx, run_set_id, scenario_id):
    """Run prep scripts for a single scenario without executing the model."""
    repo_root = ctx.obj["repo_root"]
    try:
        run_set = cfg.load_run_set(repo_root, run_set_id)
        scenario = cfg.load_scenario(repo_root, run_set_id, scenario_id)
        rs_dir = repo_root / "run_sets" / run_set_id
        prep.run_prep_scripts(run_set, scenario, rs_dir, scenario_id)
    except tdmrunsError as e:
        click.echo(f"[FAIL] {run_set_id}/{scenario_id}: {e}", err=True)
        sys.exit(1)
    click.echo(f"[OK]   {run_set_id}/{scenario_id} prep complete")


@main.command("status")
@click.option("--run-set", "run_set_id", default=None)
@click.option("--scenario", "scenario_id", default=None)
def status_cmd(run_set_id, scenario_id):
    """Show the latest known run status for each scenario."""
    repo_root = find_repo_root()
    runs = md.list_runs(repo_root, run_set_id, scenario_id)
    seen = set()
    for r in runs:
        key = (r["run_set_id"], r["scenario_id"])
        if key in seen:
            continue
        seen.add(key)
        click.echo(
            f"{r['run_set_id']}/{r['scenario_id']}: {r['status']} (run {r['run_id']}, {r['started_at']})"
        )
    if not runs:
        click.echo("No runs recorded yet.")


def _all_run_set_ids(repo_root: Path) -> list:
    run_sets_dir = repo_root / "run_sets"
    if not run_sets_dir.is_dir():
        return []
    return sorted(p.name for p in run_sets_dir.iterdir() if p.is_dir())


if __name__ == "__main__":
    main()
