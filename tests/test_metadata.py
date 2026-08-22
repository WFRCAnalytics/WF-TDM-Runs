from tdmruns import metadata as md


def _build(run_set_id, scenario_id, run_id, status="success"):
    return md.build(
        schema_version=1,
        run_set_id=run_set_id,
        scenario_id=scenario_id,
        run_id=run_id,
        status=status,
        started_at="2026-01-01T00:00:00+00:00",
        framework_commit_sha="deadbeef",
        tdm_state={},
        baseline_file="BY.block",
        run_set_overrides={},
        scenario_overrides={},
    )


def _run_dir(tmp_path, run_set_id="rs", scenario_id="S01"):
    return tmp_path / "runs" / run_set_id / scenario_id


def test_write_lands_under_run_info_by_run_id(tmp_path):
    run_dir = _run_dir(tmp_path)
    md.write(run_dir, _build("rs", "S01", "20260101-000000-aaaa"))
    assert (run_dir / "run_info" / "20260101-000000-aaaa.json").is_file()
    assert not (run_dir / "run_metadata.json").exists()


def test_read_with_explicit_run_id(tmp_path):
    run_dir = _run_dir(tmp_path)
    md.write(run_dir, _build("rs", "S01", "20260101-000000-aaaa"))
    data = md.read(run_dir, run_id="20260101-000000-aaaa")
    assert data["run_id"] == "20260101-000000-aaaa"


def test_read_with_no_run_id_resolves_latest(tmp_path):
    run_dir = _run_dir(tmp_path)
    md.write(run_dir, _build("rs", "S01", "20260101-000000-aaaa"))
    md.write(run_dir, _build("rs", "S01", "20260102-000000-bbbb"))
    assert md.read(run_dir)["run_id"] == "20260102-000000-bbbb"


def test_latest_run_none_when_no_attempts(tmp_path):
    assert md.latest_run(tmp_path, "rs", "S01") is None


def test_latest_run_picks_newest_by_run_id(tmp_path):
    run_dir = _run_dir(tmp_path)
    md.write(run_dir, _build("rs", "S01", "20260101-000000-aaaa"))
    md.write(run_dir, _build("rs", "S01", "20260103-000000-cccc"))
    md.write(run_dir, _build("rs", "S01", "20260102-000000-bbbb"))
    assert md.latest_run(tmp_path, "rs", "S01")["run_id"] == "20260103-000000-cccc"


def test_list_attempts_returns_full_history_newest_first(tmp_path):
    run_dir = _run_dir(tmp_path)
    md.write(run_dir, _build("rs", "S01", "20260101-000000-aaaa"))
    md.write(run_dir, _build("rs", "S01", "20260102-000000-bbbb"))
    attempts = md.list_attempts(tmp_path, "rs", "S01")
    assert [a["run_id"] for a in attempts] == ["20260102-000000-bbbb", "20260101-000000-aaaa"]


def test_list_attempts_empty_when_no_history(tmp_path):
    assert md.list_attempts(tmp_path, "rs", "S01") == []


def test_latest_successful_run_skips_newer_failure(tmp_path):
    run_dir = _run_dir(tmp_path)
    md.write(run_dir, _build("rs", "S01", "20260101-000000-aaaa", status="success"))
    md.write(run_dir, _build("rs", "S01", "20260102-000000-bbbb", status="failed"))
    result = md.latest_successful_run(tmp_path, "rs", "S01")
    assert result["run_id"] == "20260101-000000-aaaa"


def test_latest_successful_run_none_when_none_succeeded(tmp_path):
    run_dir = _run_dir(tmp_path)
    md.write(run_dir, _build("rs", "S01", "20260101-000000-aaaa", status="failed"))
    assert md.latest_successful_run(tmp_path, "rs", "S01") is None


def test_list_runs_returns_latest_per_scenario_only(tmp_path):
    md.write(_run_dir(tmp_path, "rs", "S01"), _build("rs", "S01", "20260101-000000-aaaa"))
    md.write(_run_dir(tmp_path, "rs", "S01"), _build("rs", "S01", "20260102-000000-bbbb"))
    md.write(_run_dir(tmp_path, "rs", "S02"), _build("rs", "S02", "20260101-000000-cccc"))

    runs = md.list_runs(tmp_path, "rs")

    by_scenario = {r["scenario_id"]: r["run_id"] for r in runs}
    assert by_scenario == {"S01": "20260102-000000-bbbb", "S02": "20260101-000000-cccc"}


def test_list_runs_filters_by_scenario(tmp_path):
    md.write(_run_dir(tmp_path, "rs", "S01"), _build("rs", "S01", "20260101-000000-aaaa"))
    md.write(_run_dir(tmp_path, "rs", "S02"), _build("rs", "S02", "20260101-000000-bbbb"))
    runs = md.list_runs(tmp_path, "rs", "S01")
    assert [r["scenario_id"] for r in runs] == ["S01"]


def test_list_runs_empty_when_no_runs_dir(tmp_path):
    assert md.list_runs(tmp_path) == []


def test_build_includes_general_parameters_when_declared():
    data = md.build(
        schema_version=1,
        run_set_id="rs",
        scenario_id="S01",
        run_id="20260101-000000-aaaa",
        status="success",
        started_at="2026-01-01T00:00:00+00:00",
        framework_commit_sha="deadbeef",
        tdm_state={},
        baseline_file="BY.block",
        run_set_overrides={},
        scenario_overrides={},
        general_parameter_overrides={"ZoneMsgRate": 100},
    )
    assert data["general_parameters"] == {"overrides": {"ZoneMsgRate": 100}}


def test_build_omits_general_parameters_when_not_declared():
    data = _build("rs", "S01", "20260101-000000-aaaa")
    assert "general_parameters" not in data
