import string
from pathlib import Path

import pytest

from tdmruns import controlcenter as cc
from tdmruns.exceptions import ControlCenterError


def test_validate_overrides_rejects_unknown_key():
    baseline = {"A": 1, "B": 2}
    with pytest.raises(ControlCenterError):
        cc.validate_overrides(baseline, {"C": 3}, "test")


def test_validate_overrides_allows_known_key():
    baseline = {"A": 1, "B": 2}
    cc.validate_overrides(baseline, {"A": 5}, "test")  # should not raise


def test_validate_override_paths_rejects_unreachable_drive():
    # Mirrors v10.0-beta.2's stale 'M:\...' vizToolDir left over from a
    # different workstation's drive layout. Picks a drive letter not
    # actually mapped on whichever machine runs this test, rather than
    # hardcoding one, since that set varies by machine.
    unused = next(
        d for d in string.ascii_uppercase if not Path(f"{d}:\\").exists()
    )
    with pytest.raises(ControlCenterError):
        cc.validate_override_paths(
            {"vizToolDir": f"{unused}:\\GitHub\\WF-TDM-Runs\\runs\\v10.0-beta.2\\.vizTool"}, "test"
        )


def test_validate_override_paths_allows_reachable_but_not_yet_created_path(tmp_path):
    # The leaf folder itself need not exist yet -- e.g. vizToolDir is
    # created on demand by the model's own vizTool setup step -- only some
    # ancestor needs to be reachable on this machine.
    cc.validate_override_paths({"vizToolDir": str(tmp_path / "not_yet_created")}, "test")


def test_validate_override_paths_ignores_non_path_values():
    cc.validate_override_paths({"HOT_Toll_Min": 0.05, "RunDescription": "a plain string"}, "test")


def test_render_precedence():
    baseline = {"A": 1, "B": 2, "C": 3, "D": 4, "ScenarioName": "baseline-name"}
    run_set_overrides = {"B": 20}
    scenario_overrides = {"C": 30}
    local_layer = {"D": 40}
    identity_fields = {"ScenarioName": "S01"}
    merged = cc.render(
        baseline, run_set_overrides, scenario_overrides, local_layer, identity_fields
    )
    assert merged["A"] == 1  # untouched baseline value
    assert merged["B"] == 20  # run set override applied
    assert merged["C"] == 30  # scenario override applied
    assert merged["D"] == 40  # local/machine value applied
    assert merged["ScenarioName"] == "S01"  # identity field always wins


def test_render_identity_wins_over_scenario_override():
    baseline = {"ScenarioName": "baseline-name"}
    scenario_overrides = {"ScenarioName": "accidental-override"}
    identity_fields = {"ScenarioName": "S01"}
    merged = cc.render(baseline, {}, scenario_overrides, {}, identity_fields)
    assert merged["ScenarioName"] == "S01"


def test_load_baseline_missing_file_raises(tmp_path):
    with pytest.raises(ControlCenterError):
        cc.load_baseline(tmp_path, "Scenarios/_defaults", "does-not-exist.block")


def test_write_and_reload_block_file_roundtrip(tmp_path):
    import yaml

    rendered = {"A": 1, "Path": "D:\\GitHub\\Foo\\"}
    out_path = tmp_path / "_ControlCenter.yaml"
    cc.write_block_file(rendered, out_path)
    reloaded = yaml.safe_load(out_path.read_text())
    assert reloaded == rendered


def test_render_assignment_lines_formats_key_value_pairs():
    lines = cc.render_assignment_lines({"ZoneMsgRate": 100, "UsedZones": "3629"})
    assert lines == ["    ZoneMsgRate = 100", "    UsedZones = '3629'"]


def test_render_assignment_lines_respects_custom_indent():
    lines = cc.render_assignment_lines({"A": 1}, indent="  ")
    assert lines == ["  A = 1"]


def test_render_assignment_lines_empty_dict():
    assert cc.render_assignment_lines({}) == []
