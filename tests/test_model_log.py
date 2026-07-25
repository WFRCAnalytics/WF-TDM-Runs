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
