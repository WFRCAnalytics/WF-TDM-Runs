from pathlib import Path

from tdmruns import model_log as mlog

SUCCESS_ENTRY = (
    "=======================================================================\n"
    "                           MODEL RUNTIME REPORT\n"
    "=======================================================================\n\n"
    "TOTAL MODEL RUN TIME\n"
    "    Beg Time:  2026-07-09,  15:53:57\n"
    "    End Time:  2026-07-09,  22:43:03\n"
    "    Run Time:  006:49:06\n\n\n"
)

CRASHED_ENTRY = (
    "=======================================================================\n"
    " -- Model Crashed --\n"
    "The model crashed in:  STEP 5 - Highway Assignment\n\n"
    "TOTAL MODEL RUN TIME\n"
    "    Beg Time:  2026-07-10,  09:00:00\n"
    "    End Time:  2026-07-10,  09:47:12\n"
    "    Run Time:  000:47:12\n\n\n"
)


def _write_log(tmp_path: Path, text: str) -> Path:
    folder = tmp_path / "scenario"
    (folder / "_Log").mkdir(parents=True)
    (folder / "_Log" / "_RunTime.txt").write_text(text)
    return folder


def test_missing_log_file_returns_none(tmp_path):
    assert mlog.read_model_log(tmp_path / "no_such_scenario") is None


def test_log_with_no_completion_entry_returns_none(tmp_path):
    folder = _write_log(tmp_path, "some partial step output but no completion entry\n")
    assert mlog.read_model_log(folder) is None


def test_success_entry(tmp_path):
    folder = _write_log(tmp_path, SUCCESS_ENTRY)
    result = mlog.read_model_log(folder)
    assert result["outcome"] == "success"
    assert result["crashed_step"] is None
    assert result["started_at"] == "2026-07-09,  15:53:57"
    assert result["finished_at"] == "2026-07-09,  22:43:03"
    assert result["run_time"] == "006:49:06"


def test_crashed_entry(tmp_path):
    folder = _write_log(tmp_path, CRASHED_ENTRY)
    result = mlog.read_model_log(folder)
    assert result["outcome"] == "crashed"
    assert result["crashed_step"] == "STEP 5 - Highway Assignment"
    assert result["run_time"] == "000:47:12"


SUCCESS_MARKER_ENTRY = (
    "TOTAL MODEL RUN TIME\n"
    "    Beg Time:  2026-08-06,  08:00:35\n"
    "    End Time:  2026-08-06,  09:43:31\n"
    "    Run Time:  001:42:56\n\n"
    "MODEL RUN SUCCESSFUL"
)

STEP_ACTIVITY_LINE = "    Boardings Report                   2026-08-06,  09:52:21,  000:01:10\n"


def test_crash_checkpoint_superseded_by_further_activity_is_unresolved(tmp_path):
    """Resumable Hail Mary case: a step crashes, is caught, and the model
    keeps going past it -- more step activity gets logged after the
    crash+total checkpoint, with no final marker yet. This must NOT be read
    as this attempt's outcome (a caller trusting it here would wrongly call
    a still-running or later-crashed attempt "failed at STEP 5" using a
    superseded checkpoint)."""
    text = CRASHED_ENTRY + STEP_ACTIVITY_LINE
    folder = _write_log(tmp_path, text)
    assert mlog.read_model_log(folder) is None


def test_success_after_earlier_superseded_crash_checkpoint(tmp_path):
    """A crash+retry checkpoint earlier in the file must not leak into the
    outcome once a later, final checkpoint is reached."""
    text = CRASHED_ENTRY + STEP_ACTIVITY_LINE + SUCCESS_ENTRY
    folder = _write_log(tmp_path, text)
    result = mlog.read_model_log(folder)
    assert result["outcome"] == "success"


def test_marker_success_is_conclusive(tmp_path):
    """Newer TDM pins: the trailing MODEL RUN SUCCESSFUL line alone is
    conclusive, preferred over the older totals-based heuristic."""
    folder = _write_log(tmp_path, SUCCESS_MARKER_ENTRY)
    result = mlog.read_model_log(folder)
    assert result["outcome"] == "success"
    assert result["crashed_step"] is None
    assert result["run_time"] == "001:42:56"


def test_marker_success_wins_over_earlier_crash_retries(tmp_path):
    """Any number of caught-and-retried crash checkpoints before the final
    MODEL RUN SUCCESSFUL line don't matter -- the marker alone decides."""
    text = CRASHED_ENTRY + STEP_ACTIVITY_LINE + SUCCESS_MARKER_ENTRY
    folder = _write_log(tmp_path, text)
    result = mlog.read_model_log(folder)
    assert result["outcome"] == "success"


def test_marker_not_at_true_tail_falls_back(tmp_path):
    """A MODEL RUN SUCCESSFUL line followed by more content (shouldn't
    happen for a real run, since it's the last thing :ENDMODEL writes) isn't
    trusted -- falls back to the older heuristic instead of assuming it's
    still the final word."""
    text = SUCCESS_MARKER_ENTRY + "\nmore output after the marker\n"
    folder = _write_log(tmp_path, text)
    assert mlog.read_model_log(folder) is None


def test_only_the_latest_appended_attempt_is_read(tmp_path):
    """The log is APPEND=T and reused across CLI-driven retries of a given
    scenario_id -- a crash followed by a clean retry must read as success,
    and a success followed by a crashed retry must read as crashed, without
    either attempt's crash marker bleeding into the other's result."""
    folder = _write_log(tmp_path, CRASHED_ENTRY + SUCCESS_ENTRY)
    result = mlog.read_model_log(folder)
    assert result["outcome"] == "success"
    assert result["run_time"] == "006:49:06"

    folder2 = _write_log(tmp_path.parent / "other_order", SUCCESS_ENTRY + CRASHED_ENTRY)
    result2 = mlog.read_model_log(folder2)
    assert result2["outcome"] == "crashed"
    assert result2["crashed_step"] == "STEP 5 - Highway Assignment"
