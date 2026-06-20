import yaml

from tdmruns import execution as ex
from tdmruns import metadata as md


def test_run_scenario_succeeds_and_writes_metadata(framework_repo):
    result = ex.run_scenario(framework_repo, "test-run-set", "S01")
    assert result["status"] == "success"
    assert result["control_center"]["scenario_overrides"]["HOT_Toll_Min"] == 50
    assert result["control_center"]["run_set_overrides"]["Run_Documentation"] == 0

    run_dir = framework_repo / "runs" / "test-run-set" / "S01" / result["run_id"]
    assert (run_dir / "run_metadata.json").is_file()
    assert (run_dir / "outputs" / "reports" / "assignment_summary.csv").is_file()
    assert (run_dir / "outputs" / "logs" / "RunModel.log").is_file()
    assert not (run_dir / "outputs" / "skims").exists()


def test_rendered_control_center_has_correct_identity_and_overrides(framework_repo):
    result = ex.run_scenario(framework_repo, "test-run-set", "S01")
    rendered_path = result["control_center"]["rendered_path"]
    rendered = yaml.safe_load(open(rendered_path))
    assert rendered["ScenarioName"] == "S01"
    assert rendered["HOT_Toll_Min"] == 50  # scenario override
    assert rendered["Run_Documentation"] == 0  # run set override
    assert rendered["HOT_Toll_Max"] == 200  # untouched baseline value
    assert rendered["RunYear"] == 2023  # untouched baseline value


def test_run_records_resolved_tdm_version(framework_repo):
    result = ex.run_scenario(framework_repo, "test-run-set", "S01")
    assert result["tdm"]["requested_ref"] == "v1.0"
    assert result["tdm"]["resolved_tag"] == "v1.0"
    assert result["tdm"]["dirty"] is False
    assert len(result["tdm"]["resolved_commit"]) == 40


def test_resume_skips_already_successful_run(framework_repo):
    first = ex.run_scenario(framework_repo, "test-run-set", "S01")
    second = ex.run_scenario(framework_repo, "test-run-set", "S01")
    assert second["run_id"] == first["run_id"]  # not re-run


def test_force_creates_a_new_run(framework_repo):
    first = ex.run_scenario(framework_repo, "test-run-set", "S01")
    second = ex.run_scenario(framework_repo, "test-run-set", "S01", force=True)
    assert second["run_id"] != first["run_id"]


def test_simulated_failure_is_recorded_not_raised(framework_repo):
    scenario_path = framework_repo / "run_sets" / "test-run-set" / "scenarios" / "S01.yaml"
    data = yaml.safe_load(scenario_path.read_text())
    data["overrides"]["RunDescription"] = "FAIL_TEST simulated failure"
    scenario_path.write_text(yaml.safe_dump(data, sort_keys=False))

    result = ex.run_scenario(framework_repo, "test-run-set", "S01", force=True)
    assert result["status"] == "failed"
    assert result["error"] is not None
    assert (
        framework_repo / "runs" / "test-run-set" / "S01" / result["run_id"] / "run_metadata.json"
    ).is_file()


def test_unknown_override_key_fails_before_execution(framework_repo):
    scenario_path = framework_repo / "run_sets" / "test-run-set" / "scenarios" / "S01.yaml"
    data = yaml.safe_load(scenario_path.read_text())
    data["overrides"]["THIS_KEY_DOES_NOT_EXIST"] = 1
    scenario_path.write_text(yaml.safe_dump(data, sort_keys=False))

    import pytest
    from tdmruns.exceptions import ControlCenterError

    with pytest.raises(ControlCenterError):
        ex.run_scenario(framework_repo, "test-run-set", "S01")
    assert not (framework_repo / "runs" / "test-run-set" / "S01").exists()


def test_output_size_limit_violation_fails_run_cleanly(framework_repo):
    run_set_path = framework_repo / "run_sets" / "test-run-set" / "run_set.yaml"
    data = yaml.safe_load(run_set_path.read_text())
    data["outputs"] = {"include": ["reports/*.csv", "skims/*.mtx"], "max_file_size_mb": 1}
    run_set_path.write_text(yaml.safe_dump(data, sort_keys=False))

    result = ex.run_scenario(framework_repo, "test-run-set", "S01")
    assert result["status"] == "failed"
    assert "exceed the 1 MB limit" in result["error"]
    assert result["outputs"]["curated"] == []


def test_run_set_continues_after_one_scenario_fails(framework_repo):
    scen_dir = framework_repo / "run_sets" / "test-run-set" / "scenarios"
    (scen_dir / "S02.yaml").write_text(
        yaml.safe_dump(
            {"scenario_id": "S02", "overrides": {"RunDescription": "FAIL_TEST"}}, sort_keys=False
        )
    )

    results = ex.run_scenarios(framework_repo, "test-run-set")
    statuses = {r["scenario_id"]: r["status"] for r in results}
    assert statuses["S01"] == "success"
    assert statuses["S02"] == "failed"


def test_list_runs_and_latest_run(framework_repo):
    ex.run_scenario(framework_repo, "test-run-set", "S01")
    runs = md.list_runs(framework_repo, "test-run-set", "S01")
    assert len(runs) == 1
    latest = md.latest_run(framework_repo, "test-run-set", "S01")
    assert latest["status"] == "success"
