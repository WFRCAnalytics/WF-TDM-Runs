"""report_snapshot_script for shorten-lengthen-all-work-trips (see
run_set.yaml). Invoked by `tdmruns snapshot-run-set --run-set
shorten-lengthen-all-work-trips` as:

    python report_snapshot.py --run-set-dir <abs> --snapshot-dir <abs>

Freezes everything report_loader.py's retirement-aware leaf loaders
otherwise read live from runs/ -- per-scenario trips/shares/segid/
taz_metrics/transit_route CSVs, the baseline's household-by-TAZ table, and
per-scenario Peak/Off-Peak GP_Dist distance arrays + HBW trip matrices --
into files under --snapshot-dir. Once those exist, report_loader's leaf
functions (load_trips/load_shares/load_segid/load_taz_metrics/
load_transit_route/load_hh/load_distance_skim_for_period/
load_hbw_trip_matrix_for_period) read them instead of runs/, so
`tdmruns purge-run-set-outputs` can delete the ~200 MB of curated outputs
per scenario. Must be run while runs/shorten-lengthen-all-work-trips still
has curated outputs -- there's nothing left to freeze from otherwise.
Mirrors bring-work-trips-closer-to-home/report_snapshot.py exactly -- same
report_loader.py leaf-loader shapes, same curated output suffixes.

Daily is deliberately NOT frozen as its own array -- report_loader.py
derives it from Peak/Off-Peak instead (exact, not approximate; see its own
docstring). The two arrays that are frozen are written float32 + zlib
(np.savez_compressed), not bare np.save: a raw float64 3629x3629 array is
~105 MB, and a first pass at this script that used plain np.save produced
an 11+ GB snapshot across the three run sets sharing this template --
*larger* than the ~3.8 GB just freed by purging, defeating the entire
point. Compressed float32 lands around 33 MB (GP_Dist, dense) and 7 MB
(HBW trips, mostly-zero) per array -- comparable to the original curated
.omx files' own HDF5 compression.
"""
import argparse
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import report_loader as loader  # noqa: E402

PERIODS = ("Peak", "Off-Peak")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-set-dir", required=True)
    parser.add_argument("--snapshot-dir", required=True)
    args = parser.parse_args()
    snapshot_dir = args.snapshot_dir
    os.makedirs(snapshot_dir, exist_ok=True)

    def out(name):
        return os.path.join(snapshot_dir, name)

    scenario_ids = loader.available_scenario_ids()
    for scenario_id in scenario_ids:
        loader.load_trips_from_runs(scenario_id).to_csv(out(f"{scenario_id}_trips.csv"), index=False)
        loader.load_shares_from_runs(scenario_id).to_csv(out(f"{scenario_id}_shares.csv"), index=False)
        loader.load_segid_from_runs(scenario_id).to_csv(out(f"{scenario_id}_segid.csv"), index=False)
        loader.load_taz_metrics_from_runs(scenario_id).to_csv(out(f"{scenario_id}_taz_metrics.csv"), index=False)
        loader.load_transit_route_from_runs(scenario_id).to_csv(out(f"{scenario_id}_transit_route.csv"), index=False)
        print(f"wrote {scenario_id} trips/shares/segid/taz_metrics/transit_route CSVs")

        for period in PERIODS:
            gp_dist = loader.load_distance_skim_for_period_from_runs(scenario_id, period).astype(np.float32)
            np.savez_compressed(out(f"{scenario_id}_gp_dist_{period}.npz"), arr=gp_dist)
            hbw_matrix = loader.load_hbw_trip_matrix_for_period_from_runs(scenario_id, period).astype(np.float32)
            np.savez_compressed(out(f"{scenario_id}_hbw_matrix_{period}.npz"), arr=hbw_matrix)
        print(f"wrote {scenario_id} gp_dist/hbw_matrix arrays for {', '.join(PERIODS)}")

    loader.load_hh_from_runs().to_csv(out("hh_by_taz.csv"), index=False)
    print("wrote hh_by_taz.csv")


if __name__ == "__main__":
    main()
