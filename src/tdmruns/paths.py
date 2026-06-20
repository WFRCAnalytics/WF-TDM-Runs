"""Shared path resolution. The CLI can be invoked from anywhere inside the
repo; these helpers find the repo root by looking for config/framework.yaml,
rather than assuming the current working directory is the root."""

from pathlib import Path

from tdmruns.exceptions import tdmrunsError


def find_repo_root(start: Path = None) -> Path:
    start = Path(start or Path.cwd()).resolve()
    for candidate in [start, *start.parents]:
        if (candidate / "config" / "framework.yaml").is_file():
            return candidate
    raise tdmrunsError(
        f"Could not find a tdmruns repo root above {start} (looked for config/framework.yaml)."
    )


def run_set_dir(repo_root: Path, run_set_id: str) -> Path:
    return repo_root / "run_sets" / run_set_id


def run_set_file(repo_root: Path, run_set_id: str) -> Path:
    return run_set_dir(repo_root, run_set_id) / "run_set.yaml"


def scenario_file(repo_root: Path, run_set_id: str, scenario_id: str) -> Path:
    return run_set_dir(repo_root, run_set_id) / "scenarios" / f"{scenario_id}.yaml"


def scenarios_dir(repo_root: Path, run_set_id: str) -> Path:
    return run_set_dir(repo_root, run_set_id) / "scenarios"


def runs_dir(repo_root: Path, run_set_id: str, scenario_id: str = None, run_id: str = None) -> Path:
    p = repo_root / "runs" / run_set_id
    if scenario_id:
        p = p / scenario_id
        if run_id:
            p = p / run_id
    return p
