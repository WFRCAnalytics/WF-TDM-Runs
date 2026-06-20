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


def run_set_description(run_set_id: str) -> str:
    import yaml
    path = REPO_ROOT / "run_sets" / run_set_id / "run_set.yaml"
    if not path.is_file():
        return ""
    data = yaml.safe_load(open(path))
    return (data.get("description") or "").strip()


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


def curated_output_paths(run: dict) -> list:
    repo_root_str = str(REPO_ROOT)
    paths = []
    for entry in run.get("outputs", {}).get("curated", []):
        repo_path = entry.get("repo_path", "")
        if repo_path.startswith(repo_root_str):
            repo_path = repo_path[len(repo_root_str):].lstrip("/\\")
        paths.append(repo_path)
    return paths
