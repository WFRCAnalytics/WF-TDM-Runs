"""Quarto project pre-render hook (see reports/_quarto.yml project.pre-render).

Writes a per-run-set _title_metadata.yml under each reports/run_sets/<id>/
directory containing that run set's author and last-updated date (same
values report_data.run_set_byline() computes), so a custom report page can
opt in via its own `metadata-files:` declaration and have Quarto put author
and date on its native title slide/title block instead of hand-computing
and printing a byline paragraph in the document body.

Runs before every `quarto render`, so these stay accurate as new runs land
without anyone re-running a one-off script.
"""
import sys
from pathlib import Path

REPORTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(REPORTS_DIR))
import report_data as rd


def main():
    run_sets_dir = REPORTS_DIR / "run_sets"
    if not run_sets_dir.is_dir():
        return
    for run_set_dir in sorted(run_sets_dir.iterdir()):
        if not run_set_dir.is_dir():
            continue
        run_set_id = run_set_dir.name
        author = rd.run_set_author(run_set_id)
        date = rd.run_set_latest_run_at(run_set_id)

        lines = []
        if author:
            lines.append(f'author: "{author}"')
        if date:
            lines.append(f'date: "{date}"')

        (run_set_dir / "_title_metadata.yml").write_text(
            "\n".join(lines) + ("\n" if lines else ""), encoding="utf-8"
        )


if __name__ == "__main__":
    main()
