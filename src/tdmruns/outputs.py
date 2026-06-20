"""Output inventory and curation.

Every file the TDM produces in a run's scenario folder gets inventoried
(path, size, checksum) regardless of whether it's curated -- that inventory
is part of run metadata even for files that never leave the gitignored
working folder. A declared, glob-based selection then determines which
files actually get copied into this repo, and every selected file is
checked against a hard size ceiling before the copy happens.
"""

import fnmatch
import hashlib
import shutil
from pathlib import Path

from tdmruns.exceptions import OutputCollectionError

CHECKSUM_CHUNK_BYTES = 1024 * 1024


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(CHECKSUM_CHUNK_BYTES):
            h.update(chunk)
    return h.hexdigest()


def inventory(scenario_folder: Path) -> list:
    """Full listing of every file produced in the scenario folder, with size
    and checksum. Does not copy anything."""
    entries = []
    for path in sorted(scenario_folder.rglob("*")):
        if path.is_file():
            rel = path.relative_to(scenario_folder).as_posix()
            entries.append(
                {"relative_path": rel, "size_bytes": path.stat().st_size, "sha256": _sha256(path)}
            )
    return entries


def select(entries: list, include_patterns: list) -> list:
    """Filters the full inventory down to entries matching at least one glob
    pattern, evaluated against each file's path relative to the scenario folder."""
    if not include_patterns:
        return []
    selected = []
    for entry in entries:
        if any(fnmatch.fnmatch(entry["relative_path"], pat) for pat in include_patterns):
            selected.append(entry)
    return selected


def validate_size_limit(selected: list, max_file_size_mb: float):
    max_bytes = int(max_file_size_mb * 1024 * 1024)
    too_big = [e for e in selected if e["size_bytes"] > max_bytes]
    if too_big:
        lines = [
            f"{len(too_big)} selected output file(s) exceed the "
            f"{max_file_size_mb} MB limit and cannot be committed to the repo:"
        ]
        for e in too_big:
            mb = e["size_bytes"] / (1024 * 1024)
            lines.append(f"  - {e['relative_path']} ({mb:.1f} MB)")
        lines.append(
            "Exclude this file from the output selection, or have the model "
            "produce a smaller summary instead of the full file."
        )
        raise OutputCollectionError("\n".join(lines))


def copy_selected(scenario_folder: Path, selected: list, dest_dir: Path) -> list:
    """Copies each selected file into dest_dir, preserving its relative path,
    and returns the manifest entries augmented with the repo-relative
    destination path."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    curated = []
    for entry in selected:
        src = scenario_folder / entry["relative_path"]
        dst = dest_dir / entry["relative_path"]
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        curated.append({**entry, "repo_path": dst.as_posix()})
    return curated
