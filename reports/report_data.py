"""Data discovery for the Quarto reporting site. Reads only committed
run_metadata.json files under runs/ -- never the TDM submodule, never the
gitignored scenario working folders. This is what makes the reporting layer
fully decoupled from execution: a new run set shows up here automatically
the moment it has at least one committed run, with no reporting code change."""
import json
from pathlib import Path

REPORTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = REPORTS_DIR.parent


def discover_run_set_ids() -> list:
    runs_dir = REPO_ROOT / "runs"
    if not runs_dir.is_dir():
        return []
    return sorted(p.name for p in runs_dir.iterdir() if p.is_dir())


def _load_run_set_yaml(run_set_id: str) -> dict:
    import yaml
    path = REPO_ROOT / "run_sets" / run_set_id / "run_set.yaml"
    if not path.is_file():
        return {}
    return yaml.safe_load(open(path, encoding="utf-8-sig")) or {}


def run_set_description(run_set_id: str) -> str:
    return (_load_run_set_yaml(run_set_id).get("description") or "").strip()


def run_set_author(run_set_id: str) -> str:
    return (_load_run_set_yaml(run_set_id).get("author") or "").strip()


def run_set_latest_run_at(run_set_id: str) -> str:
    """The most recent activity date across every scenario in this run set
    (its latest run's finished_at, or started_at if that run never finished),
    as a plain YYYY-MM-DD -- so "when was this last touched" is read from
    run_metadata.json rather than hand-maintained, and stays accurate as new
    runs/imports land. Empty string if the run set has no runs yet."""
    runs = latest_run_per_scenario(run_set_id)
    if not runs:
        return ""
    latest = max(r.get("finished_at") or r["started_at"] for r in runs)
    return latest[:10]


def run_set_byline(run_set_id: str) -> str:
    """'Prepared by <author> · Last updated <date>' (or just one half, or
    empty) -- shown under each run set's own heading in reports instead of a
    single page-wide author/date, since different run sets may be maintained
    by different people."""
    author = run_set_author(run_set_id)
    updated = run_set_latest_run_at(run_set_id)
    parts = []
    if author:
        parts.append(f"Prepared by {author}")
    if updated:
        parts.append(f"last updated {updated}")
    return " · ".join(parts)


def scenario_count(run_set_id: str) -> int:
    scenarios_dir = REPO_ROOT / "run_sets" / run_set_id / "scenarios"
    if not scenarios_dir.is_dir():
        return 0
    return len(list(scenarios_dir.glob("*.yaml")))


def latest_run_per_scenario(run_set_id: str) -> list:
    """One row per scenario: its most recent run, newest-first by run_id."""
    run_set_runs_dir = REPO_ROOT / "runs" / run_set_id
    if not run_set_runs_dir.is_dir():
        return []
    rows = []
    for scenario_dir in sorted(run_set_runs_dir.iterdir()):
        if not scenario_dir.is_dir():
            continue
        run_dirs = sorted(
            (d for d in scenario_dir.iterdir() if (d / "run_metadata.json").is_file()),
            key=lambda d: d.name, reverse=True,
        )
        if not run_dirs:
            continue
        with open(run_dirs[0] / "run_metadata.json") as f:
            rows.append(json.load(f))
    return rows


def all_overrides(run: dict) -> dict:
    cc = run.get("control_center", {})
    merged = {}
    merged.update(cc.get("run_set_overrides", {}))
    merged.update(cc.get("scenario_overrides", {}))
    return merged


def snapshot_dir(run_set_id: str) -> Path:
    return REPO_ROOT / "run_sets" / run_set_id / "snapshot"


def is_retired(run_set_id: str) -> bool:
    """True once a run set has a populated snapshot/ directory -- written by
    `tdmruns snapshot-run-set`, the first (safe, repeatable) step of
    retiring a run set. Per-run-set report loaders check this to prefer the
    frozen snapshot over live runs/ reads, whether or not the raw curated
    outputs have actually been purged yet."""
    d = snapshot_dir(run_set_id)
    return d.is_dir() and any(p.is_file() for p in d.iterdir())


def curated_output_paths(run: dict) -> list:
    repo_root_str = str(REPO_ROOT)
    paths = []
    for entry in run.get("outputs", {}).get("curated", []):
        repo_path = entry.get("repo_path", "")
        if repo_path.startswith(repo_root_str):
            repo_path = repo_path[len(repo_root_str):].lstrip("/\\")
        paths.append(repo_path)
    return paths
