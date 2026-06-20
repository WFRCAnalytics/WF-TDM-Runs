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


def test_render_precedence():
    baseline = {"A": 1, "B": 2, "C": 3, "D": 4, "ScenarioName": "baseline-name"}
    battery_overrides = {"B": 20}
    scenario_overrides = {"C": 30}
    local_layer = {"D": 40}
    identity_fields = {"ScenarioName": "S01"}
    merged = cc.render(
        baseline, battery_overrides, scenario_overrides, local_layer, identity_fields
    )
    assert merged["A"] == 1  # untouched baseline value
    assert merged["B"] == 20  # battery override applied
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
