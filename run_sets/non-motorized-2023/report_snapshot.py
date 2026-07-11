"""report_snapshot_script for non-motorized-2023 (see run_set.yaml). Invoked
by `tdmruns snapshot-run-set --run-set non-motorized-2023` as:

    python report_snapshot.py --run-set-dir <abs> --snapshot-dir <abs>

Freezes everything report_loader.py otherwise reads live -- from runs/: the
filtered ZoneSummary rows for scenarios S01-S13, and the DISTMED/TOTHH
columns from S10/S11's SE_File dbf; from the tdm/ working tree: the base
year (test_id 0) ZoneSummary rows, the small-district TAZ set, the
TAZ->district name mapping, and each district's area_acres -- into small
CSVs under --snapshot-dir. Once those files exist, report_loader's leaf
functions (load_scenario/load_se/smldst_tazs/taz_dist_table/
dist_areas_table) read them instead of runs/ or tdm/, so
`tdmruns purge-run-set-outputs` can delete curated outputs, and reports
render correctly even where tdm/ isn't checked out with real data (e.g.
CI) -- both were confirmed to actually matter, not just theoretical: the
first is what retirement is for, the second is what broke GitHub Actions'
publish-report.yml before this was added. Must be run while runs/
non-motorized-2023 still has curated outputs and tdm/ is checked out with
real data -- there's nothing left to freeze from otherwise.
"""
import argparse
import os
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import report_loader as loader  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-set-dir", required=True)
    parser.add_argument("--snapshot-dir", required=True)
    args = parser.parse_args()
    snapshot_dir = Path(args.snapshot_dir)
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    df = loader.load_baseline_from_tdm()
    df.to_csv(snapshot_dir / "S00_trips.csv", index=False)
    print(f"wrote S00_trips.csv ({len(df)} rows)")

    for test_id in range(1, 14):
        df = loader.load_scenario_from_runs(test_id)
        df.to_csv(snapshot_dir / f"S{test_id:02d}_trips.csv", index=False)
        print(f"wrote S{test_id:02d}_trips.csv ({len(df)} rows)")

    for scenario_id in ("S10", "S11"):
        df = loader.load_se_from_runs(scenario_id)
        df.to_csv(snapshot_dir / f"{scenario_id}_se.csv", index=False)
        print(f"wrote {scenario_id}_se.csv ({len(df)} rows)")

    tazs = loader.smldst_tazs_from_tdm()
    pd.DataFrame({"TAZID": sorted(tazs)}).to_csv(snapshot_dir / "smldst_tazs.csv", index=False)
    print(f"wrote smldst_tazs.csv ({len(tazs)} rows)")

    taz_dist = loader.taz_dist_from_tdm()
    taz_dist.to_csv(snapshot_dir / "taz_dist.csv", index=False)
    print(f"wrote taz_dist.csv ({len(taz_dist)} rows)")

    dist_areas = loader.dist_areas_from_tdm()
    dist_areas.to_csv(snapshot_dir / "dist_areas.csv", index=False)
    print(f"wrote dist_areas.csv ({len(dist_areas)} rows)")


if __name__ == "__main__":
    main()
