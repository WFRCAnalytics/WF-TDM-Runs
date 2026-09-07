"""Shared report_snapshot_script logic for the "HBW sketch-level trip
redistribution" family of run sets -- bring-work-trips-closer-to-home,
shorten-lengthen-all-work-trips, shorten-longest-commutes, and any future
run set sharing the same curated-output shape (same run_set.yaml
outputs.include: trips/shares/segid/taz_metrics/transit_route CSVs +
Peak/Off-Peak final skims and HBW trip matrices). Each such run set's own
report_snapshot.py is a thin wrapper (see any of the three above) that
imports its own report_loader module -- resolved via that wrapper's local
sys.path insert, so `import report_loader` picks up whichever run set's
folder the wrapper sits in -- and calls snapshot_hbw_run_set() here with
it. Extracted after the first three run sets' report_snapshot.py files
turned out to be identical in every line except the module docstring, per
the project's standing preference for one reusable mechanism over
copy-pasted scripts (see CLAUDE.md / project memory on this).

Freezes, per scenario: trips/shares/segid/taz_metrics/transit_route CSVs,
plus compressed Peak/Off-Peak GP_Dist distance arrays and HBW trip
matrices; plus one hh_by_taz.csv for the whole run set (from the baseline
scenario's SE_File -- land use is identical across every scenario in this
run-set family, only HBW trip destinations move).

Daily is deliberately NOT frozen as its own array -- each run set's own
report_loader.py derives it from Peak/Off-Peak at read time instead
(exact, not approximate: mean(Peak, Off-Peak) == mean(AM,PM,MD,EV) for
GP_Dist, Peak + Off-Peak == Daily for HBW trips, matching each
load_*_from_runs()'s own live-path math). Freezing a third ~35 MB array
per scenario purely to duplicate that arithmetic isn't worth the disk.

Compression: a first pass at this (before it was centralized here) used
bare np.save on float64 3629x3629 arrays -- ~105 MB each, producing an
11+ GB snapshot across the first three run sets sharing this template,
*larger* than the ~3.8 GB purging was supposed to free. float32 + zlib
(np.savez_compressed) lands around 33 MB (GP_Dist, dense) and 7 MB (HBW
trips, mostly-zero) per array -- comparable to the original curated .omx
files' own HDF5 compression (confirmed empirically: Skm_AM.omx was 37 MB,
HBW_trips_allsegs_Pk.omx was 12 MB for the same scenario).
"""
import os

import numpy as np

PERIODS = ("Peak", "Off-Peak")


def snapshot_hbw_run_set(loader, snapshot_dir: str) -> None:
    """loader is the calling run set's own already-imported report_loader
    module; snapshot_dir is the directory to write into (the caller has
    already created it)."""
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
