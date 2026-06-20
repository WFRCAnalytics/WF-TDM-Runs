#!/usr/bin/env python3
"""Validates every committed runs/**/run_metadata.json against the schema,
and cross-checks that every curated output's checksum still matches the file
on disk -- catching accidental hand-edits or partial commits."""
import hashlib
import json
import sys
from pathlib import Path

import jsonschema

REPO_ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def main():
    schema = json.load(open(REPO_ROOT / "config" / "schemas" / "run_metadata.schema.json"))
    validator = jsonschema.Draft7Validator(schema)

    had_error = False
    for path in sorted(REPO_ROOT.glob("runs/**/run_metadata.json")):
        data = json.load(open(path))
        errors = list(validator.iter_errors(data))
        if errors:
            had_error = True
            print(f"[FAIL] {path}:", file=sys.stderr)
            for e in errors:
                loc = "/".join(str(p) for p in e.path) or "(root)"
                print(f"    {loc}: {e.message}", file=sys.stderr)
            continue

        run_dir = path.parent
        for entry in data.get("outputs", {}).get("curated", []):
            file_path = run_dir / "outputs" / entry["relative_path"]
            if not file_path.is_file():
                had_error = True
                print(f"[FAIL] {path}: curated output missing on disk: {file_path}", file=sys.stderr)
                continue
            actual = sha256(file_path)
            if actual != entry["sha256"]:
                had_error = True
                print(f"[FAIL] {path}: checksum mismatch for {file_path}", file=sys.stderr)

        if not errors:
            print(f"[OK]   {path.relative_to(REPO_ROOT)}")

    sys.exit(1 if had_error else 0)


if __name__ == "__main__":
    main()
