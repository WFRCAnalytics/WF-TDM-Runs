# Architecture decision records

Short records of why key decisions were made, written as they were decided
rather than reconstructed afterward. Read these before changing any of the
decisions below -- the reasoning was specific to this TDM's existing
workflow (Cube Voyager, a fixed batch entry point, manually-maintained
Control Center defaults) and may not generalize the way it looks like it
should.

- [0001 - In-place sequential submodule checkout, not git worktrees](0001-submodule-execution-model.md)
- [0002 - Run set/scenario override layers, not manual Control Center editing](0002-override-model.md)
- [0003 - Curated output copies with a hard size ceiling, not external storage](0003-output-management.md)
- [0004 - Flat, schema-versioned JSON files as the source of truth, not a database](0004-run-metadata-storage.md)
- [0005 - GitHub Actions for validation and reporting only, never model execution](0005-ci-scope.md)
- [0006 - What v1 leaves out, and why it should still be addable later](0006-future-scalability.md)
