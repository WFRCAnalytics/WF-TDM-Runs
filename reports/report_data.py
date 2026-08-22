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


def _latest_run_info_path(scenario_dir: Path) -> Path:
    """The most recent attempt's metadata file under scenario_dir/run_info/
    (run_id is timestamp-prefixed, so the lexicographically-greatest
    filename is the latest), or None if there's no run_info/ yet. Does not
    import tdmruns.metadata -- this module deliberately duplicates that
    package's directory-walking logic rather than depending on it, since
    reports/ is published by GitHub Actions without the tdmruns package
    installed (see publish-report.yml)."""
    run_info_dir = scenario_dir / "run_info"
    if not run_info_dir.is_dir():
        return None
    candidates = sorted(run_info_dir.glob("*.json"))
    return candidates[-1] if candidates else None


def latest_run_per_scenario(run_set_id: str) -> list:
    """One row per scenario: its most recent run."""
    run_set_runs_dir = REPO_ROOT / "runs" / run_set_id
    if not run_set_runs_dir.is_dir():
        return []
    rows = []
    for scenario_dir in sorted(run_set_runs_dir.iterdir()):
        if not scenario_dir.is_dir():
            continue
        latest_path = _latest_run_info_path(scenario_dir)
        if latest_path is None:
            continue
        with open(latest_path) as f:
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
    this is every attempt (from run_info/, which keeps one permanently per
    attempt regardless of outcome) so the detail view can show each one's
    own date/time rather than just the latest."""
    run_info_dir = REPO_ROOT / "runs" / run_set_id / scenario_id / "run_info"
    if not run_info_dir.is_dir():
        return []
    attempts = []
    for p in sorted(run_info_dir.glob("*.json"), reverse=True):
        with open(p) as f:
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

# Explicit column widths -- table-layout: fixed makes the table honor these
# instead of auto-sizing from content. The last column (Results) is left
# flexible to absorb whatever space remains.
_COLGROUP = (
    "<colgroup>"
    '<col style="width:10em">'
    '<col style="width:5.5em">'
    '<col style="width:12em">'
    '<col style="width:9em">'
    '<col style="width:4.5em">'
    "<col>"
    "</colgroup>\n"
)

# Toggles a scenario's earlier-attempt rows (class "attempts-<run_set_id>-
# <scenario_id>", start hidden via inline style) between shown/hidden, and
# flips the clicked triangle to match. A first version nested a whole
# second <table> inside the Scenario cell instead of this -- abandoned
# because table-layout: fixed renders a table at *least* as wide as its own
# colgroup regardless of how narrow the cell it's nested in is, so it just
# overflowed the ~10em Scenario column instead of lining up with anything.
# Real sibling <tr>s in the same table can't have that problem: same table,
# same columns, always aligned. Uses the *small* triangle characters
# (U+25B8 ▸ / U+25BE ▾), not the large ▶/▼ (U+25B6/U+25BC) tried first --
# the large ones are in Unicode's emoji-eligible set, so some fonts/
# browsers render them as colorful pictographic glyphs instead of plain
# text; the small triangle variants aren't emoji-eligible and always
# render as plain text. Literal characters are used directly (not JS
# \uXXXX escapes) because this whole block is later parsed as markdown by
# Quarto's Pandoc pass, which has been observed to eat backslashes even
# inside raw HTML/script content. _scenario_rows_html()'s initial
# (collapsed) toggle span must use this exact same ▸ character -- a
# different code point (even another triangle) would make the icon appear
# to change shape the first time it's clicked, instead of just rotating.
_TOGGLE_SCRIPT = """
<script>
function tdmToggleAttempts(el, cls) {
    var show = el.dataset.expanded !== 'true';
    document.querySelectorAll('.' + cls).forEach(function (tr) {
        tr.style.display = show ? 'table-row' : 'none';
    });
    el.textContent = show ? '▾' : '▸';
    el.dataset.expanded = show ? 'true' : 'false';
}
</script>
"""


def _row_html(scenario_cell: str, cells: dict, row_class: str = None) -> str:
    """One <tr> in the shared column layout (_HEADERS). row_class, when
    given, marks this as one of a scenario's earlier-attempt rows: starts
    hidden and is toggled by _TOGGLE_SCRIPT's tdmToggleAttempts()."""
    attrs = f' class="{row_class}" style="display:none"' if row_class else ""
    return (
        f"<tr{attrs}>"
        f"<td>{scenario_cell}</td>"
        f"<td>{cells['status']}</td><td>{cells['run']}</td>"
        f"<td>{cells['finished']}</td>"
        f"<td>{cells['run_time']}</td>"
        f"<td>{cells['results']}</td>"
        "</tr>\n"
    )


def _table_html(rows_html: str) -> str:
    thead = f"<thead><tr>{''.join(f'<th>{h}</th>' for h in _HEADERS)}</tr></thead>\n"
    return (
        '<table class="table table-sm table-striped" '
        'style="table-layout:fixed;width:100%;word-break:break-word;overflow-wrap:anywhere">\n'
        f"{_COLGROUP}{thead}<tbody>\n{rows_html}</tbody>\n</table>\n"
    )


def _scenario_rows_html(run_set_id: str, scenario_id: str, attempts: list) -> str:
    """This scenario's rows in the outer table: one always-visible summary
    row -- Scenario cell shows "<id> (<N>)" (N being that row's own attempt
    number, latest = N counting down to 1 for the first-ever attempt) plus
    a toggle (only when there's more than one attempt), the rest of the row
    already shows the latest attempt's own columns directly, no click
    needed -- followed by N-1 ordinary <tr>s, one per earlier attempt
    (newest of those first, each labeled with its own attempt number too),
    that start hidden and are revealed by the toggle. The latest attempt is
    never repeated in those hidden rows -- it's already on the summary row."""
    safe_scenario = _safe(scenario_id)
    n = len(attempts)
    latest_cells = _attempt_cells(attempts[0])
    earlier = attempts[1:]

    if earlier:
        row_class = f"attempts-{run_set_id}-{scenario_id}"
        toggle = (
            f'<span class="row-toggle" style="cursor:pointer" '
            f"onclick=\"tdmToggleAttempts(this, '{row_class}')\">▸</span> "
        )
        scenario_cell = f"{toggle}{safe_scenario} ({n})"
        hidden_rows = "".join(
            _row_html(f"{safe_scenario} ({n - 1 - i})", _attempt_cells(a), row_class)
            for i, a in enumerate(earlier)
        )
    else:
        scenario_cell = f"{safe_scenario} ({n})"
        hidden_rows = ""

    return _row_html(scenario_cell, latest_cells) + hidden_rows


def run_history_html(run_set_id: str) -> str:
    """A "TDM Version: ..." line (the whole run set's own most recently
    recorded attempt's version) followed by a <details> block listing every
    scenario with at least one recorded run, collapsed by default. The
    body is a single real <table> -- see _scenario_rows_html() -- one
    always-visible row per scenario (showing its latest attempt directly,
    no click needed) plus, only for scenarios with more than one attempt, a
    toggle that reveals the rest of that scenario's history as ordinary
    sibling rows in the same table, so columns always stay aligned.

    Used to be an always-visible table on the main reports page; with 13+
    scenarios per run set (and every scenario often needing several
    attempts) that ate too much room, so it's now tucked behind a click
    instead of dropped entirely. Empty string if the run set has no runs.
    """
    run_set_runs_dir = REPO_ROOT / "runs" / run_set_id
    if not run_set_runs_dir.is_dir():
        return ""
    scenario_ids = sorted(p.name for p in run_set_runs_dir.iterdir() if p.is_dir())
    all_rows = []
    total_attempts = 0
    latest_overall = None
    for scenario_id in scenario_ids:
        attempts = _all_attempts(run_set_id, scenario_id)
        if not attempts:
            continue
        total_attempts += len(attempts)
        all_rows.append(_scenario_rows_html(run_set_id, scenario_id, attempts))
        if latest_overall is None or attempts[0]["run_id"] > latest_overall["run_id"]:
            latest_overall = attempts[0]
    if not all_rows:
        return ""
    scenario_count = len(all_rows)
    version_line = f"**TDM Version:** {_safe(_tdm_version(latest_overall))}\n\n"
    return (
        f"{version_line}"
        f"<details>\n<summary>Run history ({scenario_count} scenario"
        f"{'s' if scenario_count != 1 else ''}, {total_attempts} attempt"
        f"{'s' if total_attempts != 1 else ''})</summary>\n\n"
        f"{_TOGGLE_SCRIPT}\n"
        f"{_table_html(''.join(all_rows))}\n</details>\n"
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
