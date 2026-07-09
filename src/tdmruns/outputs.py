"""Output inventory and curation.

Every file the TDM produces in a run's scenario folder gets inventoried
(path, size) regardless of whether it's curated -- that inventory backs run
metadata's aggregate file count/byte total even for files that never leave
the gitignored working folder. Scenario folders can hold thousands of files
and tens of gigabytes, so this listing is stat()-only and never reads file
contents. A declared, glob-based selection then determines which files
actually get copied into this repo; only those get a checksum (computed at
copy time), and every selected file is checked against a hard size ceiling.

An outputs.include entry is normally just a glob pattern string, copied
byte-for-byte. It may instead be a mapping {"pattern": ..., "columns": [...]}
-- e.g. Cube Voyager's "TAZ-Based Metrics.csv" summaries carry ~18 columns
and run ~200 MB, comfortably over any reasonable size ceiling, when the
handful of columns a report actually reads (e.g. TAZID/Metric/Purpose/
Period/PA/Total) would be a fraction of that. For a pattern like this,
copy_selected() writes a column-filtered copy (named "<stem>_filtered.csv")
instead of copying the file whole. The size ceiling is enforced against the
bytes actually written to the repo -- the filtered size for these entries,
the source size for a plain copy -- not the raw source size in both cases,
since the raw size of a to-be-filtered file says nothing about what's
actually committed.
"""

import csv
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
    but no checksum -- scenario folders are routinely tens of GB across
    thousands of files, and hashing all of it just to report an aggregate
    count/byte total (the only thing run metadata keeps from this) would
    read every byte for no benefit. Does not copy anything."""
    entries = []
    for path in sorted(scenario_folder.rglob("*")):
        if path.is_file():
            rel = path.relative_to(scenario_folder).as_posix()
            entries.append({"relative_path": rel, "size_bytes": path.stat().st_size})
    return entries


def _dest_filename(entry: dict) -> str:
    src_name = Path(entry["relative_path"])
    if entry.get("columns"):
        return f"{src_name.stem}_filtered{src_name.suffix}"
    return src_name.name


def select(entries: list, include_patterns: list) -> list:
    """Filters the full inventory down to entries matching at least one glob
    pattern, evaluated against each file's path relative to the scenario
    folder. A pattern is normally a plain string; it may instead be a mapping
    {"pattern": ..., "columns": [...]} declaring that the matched file(s)
    should be column-filtered rather than copied whole -- the resulting
    selected entries carry a "columns" key (None for a plain-string pattern)
    that copy_selected() acts on."""
    if not include_patterns:
        return []
    normalized = [
        (p, None) if isinstance(p, str) else (p["pattern"], p["columns"])
        for p in include_patterns
    ]
    selected = []
    for entry in entries:
        for pattern, columns in normalized:
            if fnmatch.fnmatch(entry["relative_path"], pattern):
                selected.append({**entry, "columns": columns})
                break
    return selected


def _raise_too_big(entries: list, max_file_size_mb: float):
    lines = [
        f"{len(entries)} selected output file(s) exceed the "
        f"{max_file_size_mb} MB limit and cannot be committed to the repo:"
    ]
    for e in entries:
        mb = e["size_bytes"] / (1024 * 1024)
        lines.append(f"  - {e['relative_path']} ({mb:.1f} MB)")
    lines.append(
        "Exclude this file from the output selection, or have the model "
        "produce a smaller summary instead of the full file."
    )
    raise OutputCollectionError("\n".join(lines))


def validate_size_limit(selected: list, max_file_size_mb: float):
    """Checks selected entries against the size ceiling using each entry's
    (pre-copy) size_bytes. Only meaningful for plain, unfiltered entries --
    a to-be-filtered entry's raw source size says nothing about what will
    actually be committed, so those are skipped here and checked instead
    against the actual written size inside copy_selected()."""
    max_bytes = int(max_file_size_mb * 1024 * 1024)
    too_big = [
        e for e in selected if not e.get("columns") and e["size_bytes"] > max_bytes
    ]
    if too_big:
        _raise_too_big(too_big, max_file_size_mb)


def _write_filtered_csv(src: Path, dst: Path, columns: list):
    with open(src, newline="") as fin, open(dst, "w", newline="") as fout:
        reader = csv.DictReader(fin)
        missing = [c for c in columns if c not in (reader.fieldnames or [])]
        if missing:
            raise OutputCollectionError(
                f"columns {missing} not found in {src.name} "
                f"(available: {reader.fieldnames})"
            )
        writer = csv.DictWriter(fout, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in reader:
            writer.writerow(row)


def copy_selected(
    scenario_folder: Path, selected: list, dest_dir: Path, max_file_size_mb: float
) -> list:
    """Copies each selected file directly into dest_dir, flattened to just
    its filename -- curated outputs don't preserve the model's internal
    folder structure. An entry with a "columns" list (see select()) is
    written as a column-filtered copy ("<stem>_filtered.csv") instead of a
    byte-for-byte copy. Returns the manifest entries augmented with a sha256
    checksum, the repo-relative destination path, and size_bytes updated to
    the actual bytes written (only these, the ones actually committed, get a
    checksum -- computed here, not in inventory(), since only the typically
    handful of selected files ever need one). Raises OutputCollectionError
    if flattening would collide two selected files onto the same filename,
    or if any file, once actually written to dest_dir, exceeds
    max_file_size_mb -- deleting that file before raising."""
    seen = {}
    for entry in selected:
        name = _dest_filename(entry)
        if name in seen:
            raise OutputCollectionError(
                f"Selected outputs '{seen[name]}' and '{entry['relative_path']}' both "
                f"flatten to the filename '{name}' -- refusing to let one overwrite the "
                "other. Narrow the outputs.include patterns so each selected file is unique."
            )
        seen[name] = entry["relative_path"]

    dest_dir.mkdir(parents=True, exist_ok=True)
    curated = []
    for entry in selected:
        src = scenario_folder / entry["relative_path"]
        dst = dest_dir / _dest_filename(entry)
        if entry.get("columns"):
            _write_filtered_csv(src, dst, entry["columns"])
        else:
            shutil.copy2(src, dst)

        size_bytes = dst.stat().st_size
        if size_bytes > int(max_file_size_mb * 1024 * 1024):
            dst.unlink()
            _raise_too_big([{**entry, "size_bytes": size_bytes}], max_file_size_mb)

        curated.append(
            {
                **entry,
                "size_bytes": size_bytes,
                "sha256": _sha256(dst),
                "repo_path": dst.as_posix(),
            }
        )
    return curated


def curate(
    scenario_folder: Path,
    full_inventory: list,
    output_spec: dict,
    run_dir: Path,
    status: str,
    error: str,
) -> tuple:
    """Selects+copies whatever outputs.include matches out of full_inventory
    (already produced by inventory(scenario_folder) -- passed in rather than
    recomputed here, since the caller also needs it for the aggregate
    inventory_count/inventory_total_bytes in run metadata, and a scenario
    folder can hold thousands of files, not worth walking twice). Folds the
    result into the execution status/error decided so far (e.g. from the
    TDM's exit code, or "success"/None for a manual import). Returns
    (status, error, curated) for the caller to pass straight into
    metadata.build().

    An exit code of 0 (or a manual import) alone isn't "success" if
    outputs.include declared patterns but none of them matched anything on
    disk -- e.g. the model didn't reach the step that produces them. That's
    treated as a failure here rather than passed through unexamined.
    """
    selected = select(full_inventory, output_spec["include"])
    curated = []
    if selected:
        try:
            validate_size_limit(selected, output_spec["max_file_size_mb"])
            curated = copy_selected(
                scenario_folder, selected, run_dir / "outputs", output_spec["max_file_size_mb"]
            )
        except Exception as e:  # noqa: BLE001 -- recorded in metadata, not swallowed silently
            status = "failed"
            error = (error + " " if error else "") + f"Output curation failed: {e}"
    elif output_spec["include"]:
        status = "failed"
        error = (
            (error + " " if error else "")
            + f"No files under {scenario_folder} matched outputs.include "
            f"{output_spec['include']!r}."
        )
    return status, error, curated
