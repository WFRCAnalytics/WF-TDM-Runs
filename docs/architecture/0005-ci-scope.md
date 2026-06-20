# 0005: GitHub Actions for validation and reporting only, never model execution

## Context

The brief lists "automated GitHub Actions workflows" as a future capability.
Hosted GitHub Actions runners have a hard job-time ceiling, ephemeral
storage, and no Cube Voyager license -- none of which fit a TDM run that
can take hours and needs licensed, installed software.

## Decision

CI is scoped to three things, none of which touch the TDM submodule's
execution path: validating run_set/scenario config and the repo-wide file
size ceiling on every PR (`validate-config.yml`), schema- and checksum-
validating committed run metadata on every PR that touches `runs/`
(`validate-run-metadata.yml`), and building/publishing the Quarto site on
every push to `main` (`publish-report.yml`). Actual model execution happens
on a researcher's machine or on-prem infrastructure, outside CI.

## Consequences

If self-hosted runners with Cube Voyager licensed and installed ever become
available, scheduled or triggered execution becomes possible without
redesigning anything here -- it would be a new workflow calling
`tdmruns run-set`, subject to the same validation this design already
enforces. Until then, no one should design toward "CI runs the model."

`validate-config.yml` checks out the TDM submodule (to read
`Scenarios/_default/` baselines for validation), which means it needs
repository access if the TDM repo is private -- a deploy key or PAT
configured as a repository secret, passed to `actions/checkout`'s `token:`
input. `validate-run-metadata.yml` and `publish-report.yml` do not check out
the submodule at all, since they only read committed metadata and curated
outputs in this repo.
