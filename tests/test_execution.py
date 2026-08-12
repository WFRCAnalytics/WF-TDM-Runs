import threading
import time
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import pytest

from tdmruns import execution as ex
from tdmruns import submodule as sub
from tdmruns.execution import decide_status
from tdmruns.exceptions import ExecutionError, VersionResolutionError

LOG_PATH = Path("logs/orchestrator_invocation.log")
FOLDER = Path("scenario_folder")
FAKE_REPO_ROOT = Path("/fake-repo")


def _version_state(ref: str) -> sub.TdmVersionState:
    return sub.TdmVersionState(
        requested_ref=ref, resolved_commit="deadbeef", resolved_tag=None,
        branch=None, detached_head=True, dirty=False,
    )


# --- run_scenarios(): grouped-by-ref, bounded-concurrency dispatch --------
#
# Fully isolated from the real TDM submodule and Cube Voyager -- cfg/sub/
# run_scenario are all patched, so these never touch git or launch a
# subprocess. They exist to verify the mechanism wired up for simultaneous
# scenario execution: exactly one checkout per distinct tdm_ref (never once
# per scenario, never concurrently), scenarios within a ref group bounded by
# max_parallel_runs, ref groups themselves never overlapping in time, and
# result ordering/failure isolation preserved regardless of completion order.

def _patch_run_scenarios(stack, run_set_extra=None, scenario_refs=None, resolve_version=None, run_scenario=None):
    run_set = {"run_set_id": "rs", **(run_set_extra or {})}
    scenario_refs = scenario_refs or {}
    stack.enter_context(patch("tdmruns.execution.cfg.load_run_set", return_value=run_set))
    stack.enter_context(patch("tdmruns.execution.cfg.load_framework_config", return_value={"tdm_submodule_path": "tdm"}))
    stack.enter_context(patch("tdmruns.execution.cfg.list_scenario_ids", return_value=list(scenario_refs)))
    stack.enter_context(patch("tdmruns.execution.cfg.load_scenario", side_effect=lambda _rr, _rsid, sid: {"scenario_id": sid}))
    stack.enter_context(patch("tdmruns.execution.cfg.resolved_tdm_ref", side_effect=lambda _rs, scen: scenario_refs[scen["scenario_id"]]))
    stack.enter_context(patch("tdmruns.execution.sub.resolve_version", side_effect=resolve_version))
    stack.enter_context(patch("tdmruns.execution.run_scenario", side_effect=run_scenario))


def test_run_scenarios_groups_by_ref_and_checks_out_once_per_group():
    checkout_calls = []

    def fake_resolve_version(repo_root, tdm_path, ref):
        checkout_calls.append(ref)
        return _version_state(ref)

    def fake_run_scenario(repo_root, run_set_id, scenario_id, force=False, version_state=None):
        assert version_state is not None
        assert version_state.requested_ref == scenario_refs[scenario_id]
        return {"scenario_id": scenario_id, "status": "success", "run_id": "x"}

    scenario_refs = {"S01": "refA", "S02": "refA", "S03": "refB"}
    with ExitStack() as stack:
        _patch_run_scenarios(
            stack, scenario_refs=scenario_refs, resolve_version=fake_resolve_version, run_scenario=fake_run_scenario,
        )
        results = ex.run_scenarios(FAKE_REPO_ROOT, "rs")

    # exactly one checkout per distinct ref, in first-seen order -- never
    # once per scenario
    assert checkout_calls == ["refA", "refB"]
    # results come back in original scenario order, not completion order
    assert [r["scenario_id"] for r in results] == ["S01", "S02", "S03"]
    assert all(r["status"] == "success" for r in results)


def test_run_scenarios_respects_max_parallel_runs_concurrency_cap():
    active = 0
    peak = 0
    lock = threading.Lock()

    def fake_run_scenario(repo_root, run_set_id, scenario_id, force=False, version_state=None):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep(0.15)
        with lock:
            active -= 1
        return {"scenario_id": scenario_id, "status": "success", "run_id": "x"}

    scenario_refs = {"S01": "refA", "S02": "refA", "S03": "refA", "S04": "refA"}
    with ExitStack() as stack:
        _patch_run_scenarios(
            stack, run_set_extra={"max_parallel_runs": 3}, scenario_refs=scenario_refs,
            resolve_version=lambda _rr, _tp, ref: _version_state(ref), run_scenario=fake_run_scenario,
        )
        ex.run_scenarios(FAKE_REPO_ROOT, "rs")

    assert peak == 3  # bounded exactly at the configured max, not more


def test_run_scenarios_default_max_parallel_is_sequential():
    active = 0
    peak = 0
    lock = threading.Lock()

    def fake_run_scenario(repo_root, run_set_id, scenario_id, force=False, version_state=None):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep(0.1)
        with lock:
            active -= 1
        return {"scenario_id": scenario_id, "status": "success", "run_id": "x"}

    scenario_refs = {"S01": "refA", "S02": "refA", "S03": "refA"}
    # no max_parallel_runs declared -- must default to fully sequential
    with ExitStack() as stack:
        _patch_run_scenarios(
            stack, scenario_refs=scenario_refs,
            resolve_version=lambda _rr, _tp, ref: _version_state(ref), run_scenario=fake_run_scenario,
        )
        ex.run_scenarios(FAKE_REPO_ROOT, "rs")

    assert peak == 1


def test_run_scenarios_never_overlaps_scenarios_across_ref_groups():
    timeline = []
    lock = threading.Lock()

    def fake_resolve_version(repo_root, tdm_path, ref):
        with lock:
            timeline.append(("checkout", ref))
        return _version_state(ref)

    def fake_run_scenario(repo_root, run_set_id, scenario_id, force=False, version_state=None):
        with lock:
            timeline.append(("start", scenario_id))
        time.sleep(0.1)
        with lock:
            timeline.append(("end", scenario_id))
        return {"scenario_id": scenario_id, "status": "success", "run_id": "x"}

    scenario_refs = {"S01": "refA", "S02": "refA", "S03": "refB", "S04": "refB"}
    with ExitStack() as stack:
        _patch_run_scenarios(
            stack, run_set_extra={"max_parallel_runs": 4}, scenario_refs=scenario_refs,
            resolve_version=fake_resolve_version, run_scenario=fake_run_scenario,
        )
        ex.run_scenarios(FAKE_REPO_ROOT, "rs")

    checkout_b_idx = timeline.index(("checkout", "refB"))
    for sid in ("S01", "S02"):
        assert timeline.index(("end", sid)) < checkout_b_idx, (
            "refB's checkout must not happen until every refA scenario has finished "
            "(a later group's checkout mutates the same shared submodule tree an "
            "earlier group's still-running Cube process may be reading from)"
        )


def test_run_scenarios_marks_whole_group_failed_on_checkout_error():
    def fake_resolve_version(repo_root, tdm_path, ref):
        if ref == "refA":
            raise VersionResolutionError("boom")
        return _version_state(ref)

    def fake_run_scenario(repo_root, run_set_id, scenario_id, force=False, version_state=None):
        return {"scenario_id": scenario_id, "status": "success", "run_id": "x"}

    scenario_refs = {"S01": "refA", "S02": "refA", "S03": "refB"}
    with ExitStack() as stack:
        _patch_run_scenarios(
            stack, scenario_refs=scenario_refs, resolve_version=fake_resolve_version, run_scenario=fake_run_scenario,
        )
        results = ex.run_scenarios(FAKE_REPO_ROOT, "rs")

    by_id = {r["scenario_id"]: r for r in results}
    assert by_id["S01"]["status"] == "failed"
    assert "boom" in by_id["S01"]["error"]
    assert by_id["S02"]["status"] == "failed"
    assert "boom" in by_id["S02"]["error"]
    assert by_id["S03"]["status"] == "success"  # refB's group is unaffected by refA's checkout failure


# --- run_scenario(): rejects a pre-resolved version_state for the wrong ref

def test_run_scenario_rejects_mismatched_pre_resolved_version_state():
    with patch("tdmruns.execution.cfg.load_framework_config", return_value={"tdm_submodule_path": "tdm"}), \
         patch("tdmruns.execution.cfg.load_run_set", return_value={"run_set_id": "rs", "tdm_ref": "refA"}), \
         patch("tdmruns.execution.cfg.load_scenario", return_value={"scenario_id": "S01"}), \
         patch("tdmruns.execution.md.latest_run", return_value=None), \
         patch("tdmruns.execution.cfg.resolved_tdm_ref", return_value="refA"), \
         patch("tdmruns.execution.cfg.resolved_baseline_filename", return_value="baseline.block"), \
         patch("tdmruns.execution.cfg.merged_control_center_overrides", return_value=({}, {})), \
         patch("tdmruns.execution.cfg.resolved_output_spec", return_value={}), \
         patch("tdmruns.execution.md.utc_now_iso", return_value="2026-01-01T00:00:00Z"), \
         patch("tdmruns.execution.md.framework_commit", return_value="deadbeef"):
        with pytest.raises(ExecutionError, match="wrong TDM version"):
            ex.run_scenario(
                FAKE_REPO_ROOT, "rs", "S01", version_state=_version_state("refB"),
            )


def test_no_model_log_falls_back_to_exit_code_success():
    status, error, source, result = decide_status(0, None, LOG_PATH, FOLDER)
    assert (status, error, source, result) == ("success", None, "exit_code", None)


def test_no_model_log_falls_back_to_exit_code_failure():
    status, error, source, result = decide_status(1, None, LOG_PATH, FOLDER)
    assert status == "failed"
    assert source == "exit_code"
    assert result is None
    assert "code 1" in error


def test_model_log_success_wins_over_nonzero_exit_code():
    """The real-world case this exists for: Voyager returned non-zero, but
    the model's own completion log shows a clean finish -- trust the log."""
    model_log_result = {"outcome": "success", "crashed_step": None}
    status, error, source, result = decide_status(1, model_log_result, LOG_PATH, FOLDER)
    assert status == "success"
    assert error is None
    assert source == "model_log"
    assert result["exit_code_mismatch"] is True


def test_model_log_success_matches_zero_exit_code_no_mismatch():
    model_log_result = {"outcome": "success", "crashed_step": None}
    status, error, source, result = decide_status(0, model_log_result, LOG_PATH, FOLDER)
    assert status == "success"
    assert result["exit_code_mismatch"] is False


def test_model_log_crashed_reports_the_step():
    model_log_result = {"outcome": "crashed", "crashed_step": "STEP 5 - Highway Assignment"}
    status, error, source, result = decide_status(0, model_log_result, LOG_PATH, FOLDER)
    assert status == "failed"
    assert source == "model_log"
    assert "STEP 5 - Highway Assignment" in error
    assert result["exit_code_mismatch"] is True  # crashed but exit code claimed success


def test_model_log_crashed_with_no_step_name_still_reports_failure():
    model_log_result = {"outcome": "crashed", "crashed_step": None}
    status, error, source, result = decide_status(1, model_log_result, LOG_PATH, FOLDER)
    assert status == "failed"
    assert "unrecognized step" in error
    assert result["exit_code_mismatch"] is False  # crashed and exit code agreed
