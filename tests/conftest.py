"""Shared fixtures. Each test gets its own throwaway TDM repo and framework
repo under tmp_path, so tests never touch the real example run_set/mock TDM
checked into this repository and can run in parallel safely."""
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]

BASELINE_CONTROL_CENTER = {
    "UserName": "",
    "UserCompany": "",
    "ModelVersion": "TestModel",
    "ScenarioName": "BY",
    "RunYear": 2023,
    "RunDescription": "Base Year test scenario",
    "ParentDir": "placeholder",
    "ScenarioDir": "placeholder",
    "Voyager_EXE": "placeholder",
    "WFRC_SEFile": "SE_2023.csv",
    "HOT_Toll_Min": 25,
    "HOT_Toll_Max": 200,
    "CAV_MPR": 0,
    "Run_Documentation": 1,
}


def _git(args, cwd):
    subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True, text=True)


@pytest.fixture
def tdm_repo(tmp_path):
    """A minimal, real git repo standing in for the TDM, with a defaults
    library, a stub batch entry point, and a tagged version."""
    repo = tmp_path / "mock-tdm"
    (repo / "Scenarios" / "_defaults").mkdir(parents=True)
    with open(repo / "Scenarios" / "_defaults" / "1ControlCenter - BY_2023.block", "w") as f:
        yaml.safe_dump(BASELINE_CONTROL_CENTER, f, sort_keys=False)

    stub_src = REPO_ROOT / "tdm" / "RunModel_stub.py"
    stub_dst = repo / "RunModel_stub.py"
    shutil.copy2(stub_src, stub_dst)
    stub_dst.chmod(0o755)

    (repo / ".gitignore").write_text("Scenarios/*\n!Scenarios/_defaults\n")

    _git(["init", "-q"], repo)
    _git(["config", "user.email", "test@example.com"], repo)
    _git(["config", "user.name", "Test"], repo)
    _git(["add", "-A"], repo)
    _git(["commit", "-q", "-m", "initial"], repo)
    _git(["tag", "v1.0"], repo)
    return repo


@pytest.fixture
def framework_repo(tmp_path, tdm_repo):
    """A framework repo wired up against the throwaway tdm_repo, with one
    run set and one scenario, ready to run."""
    repo = tmp_path / "framework"
    (repo / "config" / "schemas").mkdir(parents=True)
    (repo / "run_sets" / "test-run-set" / "scenarios").mkdir(parents=True)

    shutil.copytree(REPO_ROOT / "config" / "schemas", repo / "config" / "schemas", dirs_exist_ok=True)

    framework_yaml = {
        "tdm_submodule_path": "tdm",
        "control_center_defaults_dir": "Scenarios/_defaults",
        "scenario_folder_template": "Scenarios/{resolved_version}/{scenario_id}__{run_id}",
        "execution": {
            "entry_point": "RunModel_stub.py",
            "args": ["{control_center_path}", "{scenario_folder}"],
            "timeout_seconds": 30,
        },
        "outputs": {"max_file_size_mb": 25},
        "run_metadata_schema_version": 1,
    }
    with open(repo / "config" / "framework.yaml", "w") as f:
        yaml.safe_dump(framework_yaml, f, sort_keys=False)

    run_set_yaml = {
        "run_set_id": "test-run-set",
        "description": "Test run set",
        "tdm_ref": "v1.0",
        "baseline_control_center": "1ControlCenter - BY_2023.block",
        "overrides": {"Run_Documentation": 0},
        "outputs": {"include": ["reports/*.csv", "logs/RunModel.log"], "max_file_size_mb": 10},
    }
    with open(repo / "run_sets" / "test-run-set" / "run_set.yaml", "w") as f:
        yaml.safe_dump(run_set_yaml, f, sort_keys=False)

    scenario_yaml = {
        "scenario_id": "S01",
        "description": "Test scenario",
        "overrides": {"RunDescription": "S01 test", "HOT_Toll_Min": 50},
    }
    with open(repo / "run_sets" / "test-run-set" / "scenarios" / "S01.yaml", "w") as f:
        yaml.safe_dump(scenario_yaml, f, sort_keys=False)

    _git(["init", "-q"], repo)
    _git(["config", "user.email", "test@example.com"], repo)
    _git(["config", "user.name", "Test"], repo)
    _git(["-c", "protocol.file.allow=always", "submodule", "add", str(tdm_repo), "tdm"], repo)
    _git(["add", "-A"], repo)
    _git(["commit", "-q", "-m", "initial"], repo)

    return repo
