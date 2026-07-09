import pytest

from tdmruns import config as cfg
from tdmruns.exceptions import ConfigValidationError


def test_load_run_set_valid(framework_repo):
    run_set = cfg.load_run_set(framework_repo, "test-run-set")
    assert run_set["tdm_ref"] == "v1.0"
    assert run_set["overrides"]["Run_Documentation"] == 0


def test_load_run_set_missing(framework_repo):
    with pytest.raises(ConfigValidationError):
        cfg.load_run_set(framework_repo, "does-not-exist")


def test_load_scenario_valid(framework_repo):
    scenario = cfg.load_scenario(framework_repo, "test-run-set", "S01")
    assert scenario["overrides"]["HOT_Toll_Min"] == 50


def test_run_set_rejects_unknown_top_level_key(framework_repo):
    path = framework_repo / "run_sets" / "test-run-set" / "run_set.yaml"
    content = path.read_text() + "\nthis_key_does_not_exist: true\n"
    path.write_text(content)
    with pytest.raises(ConfigValidationError):
        cfg.load_run_set(framework_repo, "test-run-set")


def test_list_scenario_ids(framework_repo):
    assert cfg.list_scenario_ids(framework_repo, "test-run-set") == ["S01"]


def test_resolved_tdm_ref_scenario_override(framework_repo):
    run_set = cfg.load_run_set(framework_repo, "test-run-set")
    scenario = cfg.load_scenario(framework_repo, "test-run-set", "S01")
    assert cfg.resolved_tdm_ref(run_set, scenario) == "v1.0"
    scenario["tdm_ref"] = "v2.0"
    assert cfg.resolved_tdm_ref(run_set, scenario) == "v2.0"


def test_output_spec_cannot_exceed_framework_ceiling(framework_repo):
    framework = cfg.load_framework_config(framework_repo)
    run_set = cfg.load_run_set(framework_repo, "test-run-set")
    scenario = cfg.load_scenario(framework_repo, "test-run-set", "S01")
    scenario["outputs"] = {"include": [{"file": "*"}], "max_file_size_mb": 999999}
    with pytest.raises(ConfigValidationError):
        cfg.resolved_output_spec(framework, run_set, scenario)


def test_resolved_manual_scenario_folder_defaults_to_convention(tmp_path):
    # A scenario with no manual_scenario_folder declared (e.g. Closer00) falls
    # back to the same Scenarios/<run_set_id>/<scenario_id> convention used
    # for CLI-driven runs, instead of requiring every scenario to spell it out.
    framework = {"scenario_folder_template": "Scenarios/{run_set_id}/{scenario_id}"}
    result = cfg.resolved_manual_scenario_folder(
        tmp_path, framework, "bring-work-trips-closer-to-home", "Closer00", {}
    )
    assert result == tmp_path / "Scenarios" / "bring-work-trips-closer-to-home" / "Closer00"


def test_resolved_manual_scenario_folder_prefers_declared_value(tmp_path):
    # non-motorized-2023's raw folders don't follow scenario_id naming
    # (BY_2019_SensitivityTest_NN), so an explicit declaration must still win.
    framework = {"scenario_folder_template": "Scenarios/{run_set_id}/{scenario_id}"}
    scenario = {"manual_scenario_folder": "Scenarios/non-motorized-2023/BY_2019_SensitivityTest_01"}
    result = cfg.resolved_manual_scenario_folder(
        tmp_path, framework, "non-motorized-2023", "S01", scenario
    )
    assert result == tmp_path / "Scenarios" / "non-motorized-2023" / "BY_2019_SensitivityTest_01"
