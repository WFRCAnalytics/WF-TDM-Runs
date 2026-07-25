"""Data discovery for the Quarto reporting site. Reads only committed
run_metadata.json files under runs/ -- never the TDM submodule, never the
gitignored scenario working folders. This is what makes the reporting layer
fully decoupled from execution: a new run set shows up here automatically
the moment it has at least one committed run, with no reporting code change."""
import html
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

REPORTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = REPORTS_DIR.parent

_MOUNTAIN = ZoneInfo("America/Denver")


def _mountain_time(iso_str: str) -> str:
    """Formats a UTC ISO8601 timestamp (run_metadata.json's started_at/
    finished_at, written by metadata.utc_now_iso()) as a plain date and
    time in Mountain Time (America/Denver, DST-aware) -- e.g.
    '2026-07-11 01:02:48' -- instead of the verbose UTC ISO string with
    microseconds and a +00:00 offset. Returns None (not "?") for empty
    input so callers can supply their own fallback text."""
    if not iso_str:
        return None
    dt = datetime.fromisoformat(iso_str)
    return dt.astimezone(_MOUNTAIN).strftime("%Y-%m-%d %H:%M:%S")


def _run_duration(started_at: str, finished_at: str) -> str:
    r"""The wall-clock duration of one attempt as 'H:MM:SS', computed as the
    plain difference between the recorded started_at/finished_at timestamps
    -- not the model's own self-reported _Log\_RunTime.txt duration (which
    only covers time actually spent inside Cube, not the orchestrator's
    setup/curation around it). None if either timestamp is missing (e.g.
    the run never finished)."""
    if not started_at or not finished_at:
        return None
    total_seconds = int(
        (datetime.fromisoformat(finished_at) - datetime.fromisoformat(started_at)).total_seconds()
    )
    hours, remainder = divmod(max(total_seconds, 0), 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}"


def discover_run_set_ids() -> list:
    runs_dir = REPO_ROOT / "runs"
    if not runs_dir.is_dir():
        return []
    return sorted(p.name for p in runs_dir.iterdir() if p.is_dir())


def has_custom_report_pages(run_set_id: str) -> bool:
    """True if this run set has its own reports/run_sets/<id>/ directory of
    hand-written pages (e.g. non-motorized-2023's slides.qmd/summary.qmd)
    instead of the generic data-driven reports/run_sets/<id>.qmd template.
    Callers that auto-list run sets from runs/ should skip these -- they're
    linked in manually wherever they're introduced instead."""
    return (REPORTS_DIR / "run_sets" / run_set_id).is_dir()


def _load_run_set_yaml(run_set_id: str) -> dict:
    import yaml
    path = REPO_ROOT / "run_sets" / run_set_id / "run_set.yaml"
    if not path.is_file():
        return {}
    return yaml.safe_load(open(path, encoding="utf-8-sig")) or {}


def run_set_description(run_set_id: str) -> str:
    return (_load_run_set_yaml(run_set_id).get("description") or "").strip()


def run_set_author(run_set_id: str) -> str:
    return (_load_run_set_yaml(run_set_id).get("author") or "").strip()


def run_set_latest_run_at(run_set_id: str) -> str:
    """The most recent activity date across every scenario in this run set
    (its latest run's finished_at, or started_at if that run never finished),
    as a plain YYYY-MM-DD -- so "when was this last touched" is read from
    run_metadata.json rather than hand-maintained, and stays accurate as new
    runs/imports land. Empty string if the run set has no runs yet."""
    runs = latest_run_per_scenario(run_set_id)
    if not runs:
        return ""
    latest = max(r.get("finished_at") or r["started_at"] for r in runs)
    return latest[:10]


def run_set_byline(run_set_id: str) -> str:
    """'Prepared by <author> · Last updated <date>' (or just one half, or
    empty) -- shown under each run set's own heading in reports instead of a
    single page-wide author/date, since different run sets may be maintained
    by different people."""
    author = run_set_author(run_set_id)
    updated = run_set_latest_run_at(run_set_id)
    parts = []
    if author:
        parts.append(f"Prepared by {author}")
    if updated:
        parts.append(f"last updated {updated}")
    return " · ".join(parts)


def scenario_count(run_set_id: str) -> int:
    scenarios_dir = REPO_ROOT / "run_sets" / run_set_id / "scenarios"
    if not scenarios_dir.is_dir():
        return 0
    return len(list(scenarios_dir.glob("*.yaml")))


def latest_run_per_scenario(run_set_id: str) -> list:
    """One row per scenario: its most recent run, newest-first by run_id."""
    run_set_runs_dir = REPO_ROOT / "runs" / run_set_id
    if not run_set_runs_dir.is_dir():
        return []
    rows = []
    for scenario_dir in sorted(run_set_runs_dir.iterdir()):
        if not scenario_dir.is_dir():
            continue
        run_dirs = sorted(
            (d for d in scenario_dir.iterdir() if (d / "run_metadata.json").is_file()),
            key=lambda d: d.name, reverse=True,
        )
        if not run_dirs:
            continue
        with open(run_dirs[0] / "run_metadata.json") as f:
            rows.append(json.load(f))
    return rows


def all_overrides(run: dict) -> dict:
    cc = run.get("control_center", {})
    merged = {}
    merged.update(cc.get("run_set_overrides", {}))
    merged.update(cc.get("scenario_overrides", {}))
    return merged


def snapshot_dir(run_set_id: str) -> Path:
    return REPO_ROOT / "run_sets" / run_set_id / "snapshot"


def is_retired(run_set_id: str) -> bool:
    """True once a run set has a populated snapshot/ directory -- written by
    `tdmruns snapshot-run-set`, the first (safe, repeatable) step of
    retiring a run set. Per-run-set report loaders check this to prefer the
    frozen snapshot over live runs/ reads, whether or not the raw curated
    outputs have actually been purged yet."""
    d = snapshot_dir(run_set_id)
    return d.is_dir() and any(p.is_file() for p in d.iterdir())


def _all_attempts(run_set_id: str, scenario_id: str) -> list:
    """Every recorded run for one scenario, newest-first by run_id -- unlike
    latest_run_per_scenario(), which keeps only the newest per scenario,
    this is every attempt so the detail view can show each one's own
    date/time rather than just the latest."""
    scenario_dir = REPO_ROOT / "runs" / run_set_id / scenario_id
    if not scenario_dir.is_dir():
        return []
    run_dirs = sorted(
        (d for d in scenario_dir.iterdir() if (d / "run_metadata.json").is_file()),
        key=lambda d: d.name, reverse=True,
    )
    attempts = []
    for d in run_dirs:
        with open(d / "run_metadata.json") as f:
            attempts.append(json.load(f))
    return attempts


def _safe(value) -> str:
    r"""HTML-escapes a piece of dynamic run data before it's embedded in the
    run-history HTML. Required beyond the usual '<'/'>'/'&' reasons: this
    whole blob is handed to `display(Markdown(...))` under `output: asis`,
    and Quarto's Pandoc pass parses it as markdown -- including backslash
    escape sequences -- even where it's raw HTML we generated ourselves. A
    literal Windows path like 'M:\GitHub\...\orchestrator_invocation.log'
    (a real recorded error message) was silently mangled into
    'M:-...-invocation.log' before every backslash here got replaced with
    its HTML entity, which Pandoc leaves alone."""
    return html.escape(str(value)).replace("\\", "&#92;")


def _tdm_version(attempt: dict) -> str:
    return attempt["tdm"].get("resolved_tag") or attempt["tdm"]["resolved_commit"][:8]


def _attempt_cells(run: dict) -> dict:
    """The individual fields shown for one attempt, as plain (already
    _safe()-escaped) strings ready to drop into <td> cells. finished_at is
    converted from the recorded UTC ISO timestamp to plain Mountain Time
    via _mountain_time(); run_time is finished_at - started_at (see
    _run_duration())."""
    curated = run.get("outputs", {}).get("curated") or []
    if curated:
        results = f"{len(curated)} output file{'s' if len(curated) != 1 else ''} curated"
    elif run.get("status") == "success":
        results = "no outputs curated"
    else:
        results = ""

    return {
        "run": _safe(run["run_id"]),
        "status": _safe(run["status"]),
        "finished": _safe(_mountain_time(run.get("finished_at")) or "(never finished)"),
        "run_time": _safe(_run_duration(run.get("started_at"), run.get("finished_at")) or ""),
        "results": results,
    }


_HEADERS = ("Scenario", "Status", "Run", "Finished (MT)", "Run time", "Results")

# Explicit, identical widths for the outer table and every nested table --
# table-layout: fixed makes a <table> honor these instead of auto-sizing
# each table's columns from its own content, which is what made the outer
# and nested tables drift out of alignment even though they share headers.
# The last column (Results) is left flexible to absorb whatever space remains.
_COLGROUP = (
    "<colgroup>"
    '<col style="width:10em">'
    '<col style="width:5.5em">'
    '<col style="width:12em">'
    '<col style="width:9em">'
    '<col style="width:6.5em">'
    "<col>"
    "</colgroup>\n"
)


def _row_html(scenario_cell: str, cells: dict) -> str:
    """One <tr> in the shared column layout (_HEADERS) -- used for both the
    outer, always-visible per-scenario row (scenario_cell holds the
    scenario's expand toggle) and every row inside that nested table
    (scenario_cell is just the plain scenario id), so the expanded detail
    lines up in exactly the same columns as the collapsed row instead of
    having its own, different column set."""
    return (
        "<tr>"
        f"<td>{scenario_cell}</td>"
        f"<td>{cells['status']}</td><td>{cells['run']}</td>"
        f"<td>{cells['finished']}</td>"
        f"<td>{cells['run_time']}</td>"
        f"<td>{cells['results']}</td>"
        "</tr>\n"
    )


def _table_html(rows_html: str, include_header: bool = True) -> str:
    """include_header=False for the nested per-scenario table -- its
    columns already line up with the outer table's own header row (shared
    _HEADERS/_COLGROUP), so repeating it directly above each scenario's
    attempts would just be visual noise."""
    thead = f"<thead><tr>{''.join(f'<th>{h}</th>' for h in _HEADERS)}</tr></thead>\n" if include_header else ""
    return (
        '<table class="table table-sm table-striped" '
        'style="table-layout:fixed;width:100%;word-break:break-word;overflow-wrap:anywhere">\n'
        f"{_COLGROUP}{thead}<tbody>\n{rows_html}</tbody>\n</table>\n"
    )


def _scenario_row_html(scenario_id: str, attempts: list) -> str:
    """One scenario's row in the outer table: the Scenario cell itself is a
    plain, unstyled <details> (so its native disclosure triangle matches
    the outer "Run history" toggle exactly) with the scenario id followed
    by its attempt count in parens (e.g. "Closer01 (4)") as its summary --
    no separate toggle or attempt-count column. The rest of the row already
    shows the latest attempt's own columns directly (no extra click needed
    to see them). Expanding it reveals a nested table -- built with the
    exact same _HEADERS/_row_html/_COLGROUP as the outer one, so it lines
    up in the same columns -- listing every attempt, successful or not."""
    safe_scenario = _safe(scenario_id)
    latest_cells = _attempt_cells(attempts[0])
    nested_rows = "".join(_row_html(safe_scenario, _attempt_cells(a)) for a in attempts)
    nested_table = _table_html(nested_rows, include_header=False)
    scenario_cell = f"<details><summary>{safe_scenario} ({len(attempts)})</summary>{nested_table}</details>"
    return _row_html(scenario_cell, latest_cells)


def run_history_html(run_set_id: str) -> str:
    """A "TDM Version: ..." line (the whole run set's own most recently
    recorded attempt's version -- not a per-row column anymore, since it's
    effectively constant across a run set's scenarios) followed by a
    <details> block listing every scenario with at least one recorded run,
    collapsed by default. The body is a real <table>, one row per scenario:
    the first cell holds a plain, unstyled <details> (so its native
    disclosure triangle matches the outer "Run history" toggle exactly)
    while the rest of that row already shows the latest attempt's own
    columns -- no click needed to see them when collapsed. Expanding a
    scenario's triangle reveals a nested table, in the exact same columns,
    listing every attempt for it, successful or not (finished in Mountain
    Time, run time, curated results) -- see _scenario_row_html(). No
    further per-run expand/collapse; every
    attempt's detail is directly visible as soon as its scenario is open.

    Used to be an always-visible table on the main reports page; with 13+
    scenarios per run set (and every scenario often needing several
    attempts) that ate too much room, so it's now tucked behind a click
    instead of dropped entirely. Empty string if the run set has no runs.
    """
    run_set_runs_dir = REPO_ROOT / "runs" / run_set_id
    if not run_set_runs_dir.is_dir():
        return ""
    scenario_ids = sorted(p.name for p in run_set_runs_dir.iterdir() if p.is_dir())
    scenario_rows = []
    total_attempts = 0
    latest_overall = None
    for scenario_id in scenario_ids:
        attempts = _all_attempts(run_set_id, scenario_id)
        if not attempts:
            continue
        total_attempts += len(attempts)
        scenario_rows.append(_scenario_row_html(scenario_id, attempts))
        if latest_overall is None or attempts[0]["run_id"] > latest_overall["run_id"]:
            latest_overall = attempts[0]
    if not scenario_rows:
        return ""
    version_line = f"**TDM Version:** {_safe(_tdm_version(latest_overall))}\n\n"
    return (
        f"{version_line}"
        f"<details>\n<summary>Run history ({len(scenario_rows)} scenario"
        f"{'s' if len(scenario_rows) != 1 else ''}, {total_attempts} attempt"
        f"{'s' if total_attempts != 1 else ''})</summary>\n\n"
        f"{_table_html(''.join(scenario_rows))}\n</details>\n"
    )


def curated_output_paths(run: dict) -> list:
    repo_root_str = str(REPO_ROOT)
    paths = []
    for entry in run.get("outputs", {}).get("curated", []):
        repo_path = entry.get("repo_path", "")
        if repo_path.startswith(repo_root_str):
            repo_path = repo_path[len(repo_root_str):].lstrip("/\\")
        paths.append(repo_path)
    return paths
