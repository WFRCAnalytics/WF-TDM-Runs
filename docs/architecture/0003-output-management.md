# 0003: Curated output copies with a hard size ceiling, not external storage

## Context

TDM runs can produce tens of gigabytes of output per scenario, all of it in
the TDM's gitignored `Scenarios/` working folder. Git (even with LFS) is a
poor fit for that scale. Early design considered external storage (cloud
blob storage or a network share) referenced by path from run metadata.

## Decision

Every output the model produces is inventoried (path, size, checksum) in
run metadata regardless of whether it's kept. A declared, glob-based
selection (`outputs.include` in run_set/scenario config) determines which
files are actually copied into this repo, under
`runs/{run_set}/{scenario}/{run_id}/outputs/`. Every selected file is
checked against a hard size ceiling (`config/framework.yaml`
`outputs.max_file_size_mb`, default 100 MB) before the copy happens, and
again by CI on every PR as a backstop against a manual `git add` of
something oversized.

## Consequences

This repo only ever holds small, deliberately-chosen result artifacts plus
metadata. The full-size raw outputs are not preserved by this repo at
all -- they remain wherever they already lived (the gitignored working
folder), which is an explicit, documented tradeoff: if long-term archival of
full raw outputs is ever needed, that is a separate concern (network
storage, backup policy) outside this repo's responsibility, not something
this design tries to solve.

A selected file that exceeds the ceiling fails the run loudly rather than
being silently skipped, on the theory that a selection spec pulling
something too large is a configuration mistake worth surfacing immediately
(exclude it, or have the model produce a smaller summary), not something to
quietly drop.

## Update: checksums only for curated files, not the full inventory

The full inventory was originally described as path/size/checksum for every
file. In practice, run metadata only ever stored the *aggregate* count and
byte total from that inventory (`inventory_count`/`inventory_total_bytes`) --
the per-file checksum was computed for every file (often 1000+ files,
tens of GB, e.g. `non-motorized-2023`'s manually-run scenarios) and then
discarded for anything not selected. The full inventory is now stat()-only
(path + size, no file contents read); `copy_selected()` computes the sha256
only for the files actually selected and copied into the repo, since those
are the only checksums metadata ever keeps.

## Update: an oversized file degrades gracefully instead of failing the run

The original decision above ("fails the run loudly rather than being
silently skipped") was reversed, porting the fix from the sibling
`WF-TDM-Calibration` repo's `tdmcalib` (see its `outputs.py`). In practice
this meant a genuinely successful model run -- every step completed, every
output produced -- was recorded as `status: "failed"` in `run_metadata.json`
purely because one curated output crossed the size ceiling (e.g. a
corrupted/oversized skim), which conflated "the model failed" with "an
output happened to be big" and required a manual re-curation once the
`outputs.include` pattern or the file itself was fixed.

A selected file that exceeds `outputs.max_file_size_mb` once actually
written is now kept on disk (not deleted) with `"committed": false` in its
`curated[]` manifest entry, and `outputs/.gitignore` is regenerated on every
curation run to list exactly the currently-oversized files -- so the file
never reaches git, but is still usable locally (e.g. a report rendered on
the machine that curated it can still read it). CI's `check_file_sizes.py`
backstop is unaffected, since a gitignored file is never tracked in the
first place. `scripts/validate_run_metadata.py` skips the on-disk checksum
check for `"committed": false` entries, the same way it already skips it for
retired runs, since a fresh checkout won't have the file.

Genuine curation failures -- a filename collision, a declared column/tab/
field that doesn't exist in the source file, or Voyager not being configured
for a matrix/network entry -- still raise and still fail the run; only the
"file turned out to be too big" case changed.

## Update: curated outputs move to `outputs/`, one level up from `{run_id}/`

The `runs/{run_set}/{scenario}/{run_id}/outputs/` path in this ADR's
original Decision is no longer current -- curated outputs now live at
`runs/{run_set}/{scenario}/outputs/` (no `{run_id}` level), holding only the
latest attempt's files; per-attempt metadata moved to its own permanent
`run_info/{run_id}.json`. See `docs/architecture/0004-run-metadata-storage.md`'s
own update note for the full rationale -- this ADR's actual subject (the
selection/checksumming/size-ceiling mechanics above) is otherwise unchanged.
