#!/usr/bin/env python3
"""CI backstop for the framework's "no file over the size ceiling" rule.

The orchestrator already enforces this before copying any output into
runs/, but this script re-checks every tracked file in the repo on every PR,
so a manual `git add` of something oversized still gets caught before merge
rather than relying solely on the orchestrator having been used correctly.
"""
import subprocess
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]


def max_bytes() -> int:
    framework = yaml.safe_load(open(REPO_ROOT / "config" / "framework.yaml"))
    return int(framework["outputs"]["max_file_size_mb"] * 1024 * 1024)


def tracked_files() -> list:
    result = subprocess.run(
        ["git", "ls-files"], cwd=str(REPO_ROOT), capture_output=True, text=True, check=True
    )
    return [REPO_ROOT / line for line in result.stdout.splitlines() if line]


def main():
    limit = max_bytes()
    offenders = []
    for path in tracked_files():
        if path.is_file() and path.stat().st_size > limit:
            offenders.append((path, path.stat().st_size))
    if offenders:
        print(f"The following tracked file(s) exceed the {limit / (1024*1024):.0f} MB limit "
              f"set in config/framework.yaml:", file=sys.stderr)
        for path, size in offenders:
            print(f"  - {path.relative_to(REPO_ROOT)} ({size / (1024*1024):.1f} MB)", file=sys.stderr)
        sys.exit(1)
    print(f"OK: no tracked file exceeds {limit / (1024*1024):.0f} MB.")


if __name__ == "__main__":
    main()
