import pytest

from tdmruns import driver_script as ds
from tdmruns.exceptions import DriverScriptError


def _make_defaults(tmp_path, filename="_HailMary_1Subfolder.s", content="default script"):
    defaults_dir = tmp_path / "tdm" / "Scenarios" / "_default"
    defaults_dir.mkdir(parents=True)
    (defaults_dir / filename).write_text(content)
    return tmp_path / "tdm", "Scenarios/_default", filename


def test_stage_uses_default_when_none_declared(tmp_path):
    tdm_path, defaults_dir, default_filename = _make_defaults(tmp_path)
    scenario_folder = tmp_path / "scenario"
    scenario_folder.mkdir()

    source_label = ds.stage(
        tmp_path / "run_set", tdm_path, defaults_dir, default_filename, {}, {}, scenario_folder
    )

    assert source_label == f"{defaults_dir}/{default_filename}"
    assert (scenario_folder / default_filename).read_text() == "default script"


def test_stage_uses_declared_custom_script_keeping_its_own_filename(tmp_path):
    tdm_path, defaults_dir, default_filename = _make_defaults(tmp_path)
    run_set_dir = tmp_path / "run_set"
    (run_set_dir / "hail-mary").mkdir(parents=True)
    (run_set_dir / "hail-mary" / "_HailMary_1Subfolder_closer.s").write_text("custom script")
    scenario_folder = tmp_path / "scenario"
    scenario_folder.mkdir()

    scenario = {"driver_script": "hail-mary/_HailMary_1Subfolder_closer.s"}
    source_label = ds.stage(
        run_set_dir, tdm_path, defaults_dir, default_filename, {}, scenario, scenario_folder
    )

    assert source_label == "hail-mary/_HailMary_1Subfolder_closer.s"
    assert (scenario_folder / "_HailMary_1Subfolder_closer.s").read_text() == "custom script"
    assert not (scenario_folder / default_filename).exists()


def test_stage_removes_stale_driver_scripts_from_a_prior_attempt(tmp_path):
    """Regression test: Closer00's scenario folder is reused across every run
    attempt (no run_id in scenario_folder_template). An earlier attempt's
    staged driver script must not be left behind once a later attempt stages
    a different one -- RunModel.bat globs scenario_folder for *.s and picks
    whichever one it finds, so more than one present silently runs the wrong
    script."""
    tdm_path, defaults_dir, default_filename = _make_defaults(tmp_path)
    run_set_dir = tmp_path / "run_set"
    (run_set_dir / "hail-mary").mkdir(parents=True)
    (run_set_dir / "hail-mary" / "_HailMary_1Subfolder_closer.s").write_text("custom script")
    scenario_folder = tmp_path / "scenario"
    scenario_folder.mkdir()

    # First attempt: no driver_script declared yet, stages the default.
    ds.stage(run_set_dir, tdm_path, defaults_dir, default_filename, {}, {}, scenario_folder)
    assert (scenario_folder / default_filename).exists()

    # Second attempt: scenario now declares a custom driver_script.
    scenario = {"driver_script": "hail-mary/_HailMary_1Subfolder_closer.s"}
    ds.stage(run_set_dir, tdm_path, defaults_dir, default_filename, {}, scenario, scenario_folder)

    remaining = sorted(p.name for p in scenario_folder.glob("*.s"))
    assert remaining == ["_HailMary_1Subfolder_closer.s"]


def test_stage_raises_when_declared_script_missing(tmp_path):
    tdm_path, defaults_dir, default_filename = _make_defaults(tmp_path)
    run_set_dir = tmp_path / "run_set"
    scenario_folder = tmp_path / "scenario"
    scenario_folder.mkdir()

    scenario = {"driver_script": "hail-mary/does_not_exist.s"}
    with pytest.raises(DriverScriptError, match="driver_script not found"):
        ds.stage(
            run_set_dir, tdm_path, defaults_dir, default_filename, {}, scenario, scenario_folder
        )
