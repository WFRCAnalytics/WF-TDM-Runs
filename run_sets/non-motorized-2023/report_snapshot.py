"""report_snapshot_script for non-motorized-2023 (see run_set.yaml). Invoked
by `tdmruns snapshot-run-set --run-set non-motorized-2023` as:

    python report_snapshot.py --run-set-dir <abs> --snapshot-dir <abs>

Freezes the test-scenario data report_loader.py otherwise reads live from
runs/ -- the filtered ZoneSummary rows for scenarios S01-S13, and the
DISTMED/TOTHH columns from S10/S11's SE_File dbf -- into small CSVs under
--snapshot-dir. Once those files exist, report_loader.load_scenario()/
load_se() read them instead of the (much larger) curated files under runs/,
so `tdmruns purge-run-set-outputs` can delete those without breaking the
reports. Must be run while runs/non-motorized-2023 still has curated
outputs -- there's nothing left to freeze from afterward.
"""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import report_loader as loader  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-set-dir", required=True)
    parser.add_argument("--snapshot-dir", required=True)
    args = parser.parse_args()
    snapshot_dir = Path(args.snapshot_dir)
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    for test_id in range(1, 14):
        df = loader.load_scenario_from_runs(test_id)
        df.to_csv(snapshot_dir / f"S{test_id:02d}_trips.csv", index=False)
        print(f"wrote S{test_id:02d}_trips.csv ({len(df)} rows)")

    for scenario_id in ("S10", "S11"):
        df = loader.load_se_from_runs(scenario_id)
        df.to_csv(snapshot_dir / f"{scenario_id}_se.csv", index=False)
        print(f"wrote {scenario_id}_se.csv ({len(df)} rows)")


if __name__ == "__main__":
    main()
