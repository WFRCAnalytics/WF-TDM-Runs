import textwrap

import pytest
import yaml

from tdmruns import execution as ex
from tdmruns import prep
from tdmruns.exceptions import PrepScriptError


def _write_script(path, exit_code=0, sentinel=None):
    """Write a minimal prep script that optionally writes a sentinel file."""
    lines = ["import argparse, sys, pathlib"]
    lines.append("p = argparse.ArgumentParser()")
    lines.append("p.add_argument('--run-set-dir')")
    lines.append("p.add_argument('--scenario-id')")
    lines.append("args = p.parse_args()")
    if sentinel:
        lines.append(f"pathlib.Path(args.run_set_dir, {sentinel!r}).touch()")
    lines.append(f"sys.exit({exit_code})")
    path.write_text(textwrap.dedent("\n".join(lines)))


# ---------------------------------------------------------------------------
# Unit tests for prep.run_prep_scripts
# ---------------------------------------------------------------------------


def test_no_scripts_is_a_noop(tmp_path):
    run_set = {"run_set_id": "x"}
    scenario = {"scenario_id": "S01"}
    prep.run_prep_scripts(run_set, scenario, tmp_path, "S01")  # must not raise


def test_run_set_script_runs_on_success(tmp_path):
    script = tmp_path / "prep_all.py"
    _write_script(script, exit_code=0, sentinel="rs_ran.txt")
    run_set = {"run_set_id": "x", "prep_script": "prep_all.py"}
    scenario = {"scenario_id": "S01"}
    prep.run_prep_scripts(run_set, scenario, tmp_path, "S01")
    assert (tmp_path / "rs_ran.txt").exists()


def test_scenario_script_runs_on_success(tmp_path):
    script = tmp_path / "prep_s01.py"
    _write_script(script, exit_code=0, sentinel="sc_ran.txt")
    run_set = {"run_set_id": "x"}
    scenario = {"scenario_id": "S01", "prep_script": "prep_s01.py"}
    prep.run_prep_scripts(run_set, scenario, tmp_path, "S01")
    assert (tmp_path / "sc_ran.txt").exists()


def test_run_set_script_runs_before_scenario_script(tmp_path):
    order = tmp_path / "order.txt"
    for name, label in [("prep_rs.py", "rs"), ("prep_sc.py", "sc")]:
        script = tmp_path / name
        lines = [
            "import argparse, pathlib",
            "p = argparse.ArgumentParser()",
            "p.add_argument('--run-set-dir')",
            "p.add_argument('--scenario-id')",
            "args = p.parse_args()",
            f"pathlib.Path(args.run_set_dir, 'order.txt').open('a').write({label!r} + ',')",
        ]
        script.write_text("\n".join(lines))
    run_set = {"run_set_id": "x", "prep_script": "prep_rs.py"}
    scenario = {"scenario_id": "S01", "prep_script": "prep_sc.py"}
    prep.run_prep_scripts(run_set, scenario, tmp_path, "S01")
    assert order.read_text() == "rs,sc,"


def test_run_set_script_failure_raises_prep_script_error(tmp_path):
    script = tmp_path / "bad.py"
    _write_script(script, exit_code=1)
    run_set = {"run_set_id": "x", "prep_script": "bad.py"}
    scenario = {"scenario_id": "S01"}
    with pytest.raises(PrepScriptError, match="exited with code 1"):
        prep.run_prep_scripts(run_set, scenario, tmp_path, "S01")


def test_scenario_script_failure_raises_prep_script_error(tmp_path):
    script = tmp_path / "bad.py"
    _write_script(script, exit_code=2)
    run_set = {"run_set_id": "x"}
    scenario = {"scenario_id": "S01", "prep_script": "bad.py"}
    with pytest.raises(PrepScriptError, match="exited with code 2"):
        prep.run_prep_scripts(run_set, scenario, tmp_path, "S01")


def test_missing_script_raises_prep_script_error(tmp_path):
    run_set = {"run_set_id": "x", "prep_script": "does_not_exist.py"}
    scenario = {"scenario_id": "S01"}
    with pytest.raises(PrepScriptError, match="not found"):
        prep.run_prep_scripts(run_set, scenario, tmp_path, "S01")


def test_run_set_failure_skips_scenario_script(tmp_path):
    bad = tmp_path / "bad.py"
    _write_script(bad, exit_code=1)
    sentinel = tmp_path / "sc_ran.py"
    _write_script(sentinel, exit_code=0, sentinel="sc_ran.txt")
    run_set = {"run_set_id": "x", "prep_script": "bad.py"}
    scenario = {"scenario_id": "S01", "prep_script": "sc_ran.py"}
    with pytest.raises(PrepScriptError):
        prep.run_prep_scripts(run_set, scenario, tmp_path, "S01")
    assert not (tmp_path / "sc_ran.txt").exists()


# ---------------------------------------------------------------------------
# Integration: prep script failure stops run_scenario before execution
# ---------------------------------------------------------------------------


def test_prep_script_failure_stops_run_before_execution(framework_repo):
    script = framework_repo / "run_sets" / "test-run-set" / "fail_prep.py"
    script.write_text("import sys; sys.exit(1)\n")

    run_set_path = framework_repo / "run_sets" / "test-run-set" / "run_set.yaml"
    data = yaml.safe_load(run_set_path.read_text())
    data["prep_script"] = "fail_prep.py"
    run_set_path.write_text(yaml.safe_dump(data, sort_keys=False))

    with pytest.raises(PrepScriptError):
        ex.run_scenario(framework_repo, "test-run-set", "S01")

    assert not (framework_repo / "runs" / "test-run-set" / "S01").exists()


def test_prep_script_success_allows_run(framework_repo):
    script = framework_repo / "run_sets" / "test-run-set" / "ok_prep.py"
    script.write_text("import sys; sys.exit(0)\n")

    run_set_path = framework_repo / "run_sets" / "test-run-set" / "run_set.yaml"
    data = yaml.safe_load(run_set_path.read_text())
    data["prep_script"] = "ok_prep.py"
    run_set_path.write_text(yaml.safe_dump(data, sort_keys=False))

    result = ex.run_scenario(framework_repo, "test-run-set", "S01")
    assert result["status"] == "success"
