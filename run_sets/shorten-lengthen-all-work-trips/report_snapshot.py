"""report_snapshot_script for shorten-lengthen-all-work-trips (see
run_set.yaml). Invoked by `tdmruns snapshot-run-set --run-set
shorten-lengthen-all-work-trips` as:

    python report_snapshot.py --run-set-dir <abs> --snapshot-dir <abs>

Thin wrapper around reports/hbw_report_snapshot.py's snapshot_hbw_run_set()
-- shared logic for every run set in this "HBW sketch-level trip
redistribution" family (same curated-output shape as
bring-work-trips-closer-to-home / shorten-longest-commutes). See that
module's own docstring for exactly what's frozen, why Daily isn't stored
separately, and why the arrays are compressed float32 rather than bare
np.save. Must be run while runs/shorten-lengthen-all-work-trips still has
curated outputs -- there's nothing left to freeze from otherwise.
"""
import argparse
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
import report_loader as loader  # noqa: E402

sys.path.insert(0, os.path.join(_HERE, "..", "..", "reports"))
from hbw_report_snapshot import snapshot_hbw_run_set  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-set-dir", required=True)
    parser.add_argument("--snapshot-dir", required=True)
    args = parser.parse_args()
    os.makedirs(args.snapshot_dir, exist_ok=True)
    snapshot_hbw_run_set(loader, args.snapshot_dir)


if __name__ == "__main__":
    main()
