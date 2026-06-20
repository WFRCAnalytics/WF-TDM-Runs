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
