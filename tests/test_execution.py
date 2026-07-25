from pathlib import Path

from tdmruns.execution import decide_status

LOG_PATH = Path("logs/orchestrator_invocation.log")
FOLDER = Path("scenario_folder")


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
