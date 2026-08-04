# Description:
#     Redistributes the longest-distance HBW (home-based work) trips,
#     selected region-wide (not per origin), toward destinations near the
#     regional median commute distance. Reads hbw_trip_redistribution_portion
#     from the scenario's own ShortenXX.yaml `variables:` block (documentation
#     -only to the framework -- this script is the thing that actually
#     consumes it).
#
#     Distance basis is skm_auto_Pk.mtx's dist_GP core -- the same skim
#     tdm/2_ModelScripts/_Python/mc_HBW_dest_choice.py already uses in the
#     HBW destination-choice utility function, so "how far this trip is" is
#     defined identically to how the model itself placed it. It's also the
#     only distance skim that already exists at this point in the pipeline --
#     the 5_AssignHwy period skims aren't produced until step 5, long after
#     this script runs. Cells at or beyond SKIM_NOACCESS_SENTINEL (Cube's
#     NOACCESS value for unconnected zone pairs) are excluded from selection,
#     the median, and the receiving band, matching the convention already
#     used for the trip-length distribution in
#     bring-work-trips-closer-to-home/report_loader.py.
#
#     Selection is region-wide, not per origin: every OD cell with nonzero
#     HBW trips (summed across HBW0+HBW1+HBW2, since distance is a property
#     of the OD pair, not the vehicle-ownership segment) is ranked by
#     distance descending; cells are taken off the top of that ranking until
#     their cumulative trip volume reaches hbw_trip_redistribution_portion of
#     the region-wide HBW total, splitting the boundary cell fractionally so
#     the amount selected is exact. That produces one move_fraction per cell,
#     applied identically to each of HBW0/HBW1/HBW2 at that cell -- distance
#     doesn't depend on vehicle-ownership segment, only the OD pair does.
#
#     Selected volume is grouped by origin row and moved onto that row's own
#     destinations within +-DISTANCE_BAND_MILES of the region-wide median HBW
#     distance (also computed from this run's own pre-redistribution matrix,
#     not a hardcoded constant -- since start_from_copy seeds every ShortenXX
#     scenario from an untouched copy of Shorten00's baseline, this is always
#     the true baseline distribution), distributed proportional to each
#     core's own existing pattern there. A row with selected volume but no
#     existing trips in its own median band is left untouched (nothing
#     sensible to scale a distribution against) and counted as skipped, same
#     as bring-work-trips-closer-to-home/scripts/redistribute_hbw_trips.py's
#     "no inside pattern" skip.
#
#     Operates on pa_HBW_NumVeh_noXI.mtx's vehicle-ownership-segmented HBW
#     cores (HBW0/HBW1/HBW2) -- the file 08_TripTablesByPeriod.s actually
#     reads forward into mode choice/assignment. pa_AllPurp.2.DestChoice.mtx's
#     own "HBW" core is still updated afterward (recomputed as
#     HBW0+HBW1+HBW2) purely so its P/A-balance reporting reflects the same
#     numbers mode choice actually uses -- see
#     redistribute_hbw_trips.py's module docstring for the full history of
#     why (this run set's scenarios seed their raw folder from
#     bring-work-trips-closer-to-home's Closer00 run, so that bug history
#     carries over).
#
#     Converts to OMX and back via CONVERTMAT the same way
#     redistribute_hbw_trips.py does, since numpy/openmatrix can't read TPP
#     directly.

import argparse
import subprocess
import sys
from pathlib import Path

import numpy as np
import openmatrix as omx
import yaml

# Matches the hardcoded Cube Voyager install location used by the TDM's own
# _Python scripts (mc_HBW_dest_choice.py, _parcel_volume.py) -- not
# configurable at this layer, consistent with those.
VOYAGER_DIR = r"C:\Program Files\Citilabs\CubeVoyager"

# The three vehicle-ownership-segmented HBW cores in pa_HBW_NumVeh_noXI.mtx
# that 08_TripTablesByPeriod.s actually reads forward into mode choice.
VEHICLE_CORES = ["HBW0", "HBW1", "HBW2"]

# Core name in skm_auto_Pk.mtx holding auto distance -- matches
# tdm/2_ModelScripts/_Python/mc_HBW_dest_choice.py's own "dist_GP" read.
DISTANCE_CORE = "dist_GP"

# Half-width, in miles, of the band around the regional median HBW distance
# that counts as "near average" and eligible to receive redistributed trips.
DISTANCE_BAND_MILES = 2.0

# Cube's NOACCESS sentinel for unconnected zone pairs (see
# tdm/2_ModelScripts/5_AssignHwy/07_PerformFinalNetSkim.s's PATHLOAD
# NOACCESS=9999, and bring-work-trips-closer-to-home/report_loader.py's
# SKIM_NOACCESS_SENTINEL) -- excluded so a handful of technically-unconnected
# cells can't masquerade as extreme-long trips or skew the regional median.
SKIM_NOACCESS_SENTINEL = 9999


def _run_convertmat(script_path: Path, bat_path: Path):
    with open(bat_path, "w") as f:
        f.write(f'start /w "{VOYAGER_DIR}" VOYAGER.EXE "{script_path.resolve()}" /start -Report\n')
    subprocess.call(str(bat_path), cwd=str(bat_path.parent))


def convert_mtx_to_omx(mtx_path: Path, omx_path: Path):
    work_dir = mtx_path.parent
    script_path = work_dir / f"_convert_in_{mtx_path.stem}.s"
    bat_path = work_dir / f"_convert_in_{mtx_path.stem}.bat"
    with open(script_path, "w") as f:
        f.write(
            f'convertmat from="{mtx_path.resolve()}", to="{omx_path.resolve()}", '
            f'compression=2, format="omx"\n'
        )
    _run_convertmat(script_path, bat_path)
    if not omx_path.exists():
        message = f"CONVERTMAT did not produce {omx_path} -- check {bat_path} output"
        raise RuntimeError(message)


def convert_omx_to_mtx(omx_path: Path, mtx_path: Path):
    work_dir = omx_path.parent
    script_path = work_dir / f"_convert_out_{mtx_path.stem}.s"
    bat_path = work_dir / f"_convert_out_{mtx_path.stem}.bat"
    with open(script_path, "w") as f:
        f.write(f'convertmat from="{omx_path.resolve()}", to="{mtx_path.resolve()}", format=TPP\n')
    _run_convertmat(script_path, bat_path)
    if not mtx_path.exists():
        raise RuntimeError(f"CONVERTMAT did not produce {mtx_path} -- check {bat_path} output")


def load_scenario_variables(run_set_dir: Path, scenario_id: str) -> dict:
    scenario_yaml = run_set_dir / "scenarios" / f"{scenario_id}.yaml"
    with open(scenario_yaml) as f:
        scenario = yaml.safe_load(f)
    return scenario.get("variables", {})


def weighted_median(values: np.ndarray, weights: np.ndarray) -> float:
    order = np.argsort(values)
    values = values[order]
    weights = weights[order]
    cumulative = np.cumsum(weights)
    half = cumulative[-1] / 2.0
    idx = int(np.searchsorted(cumulative, half))
    idx = min(idx, len(values) - 1)
    return float(values[idx])


def select_region_wide(combined: np.ndarray, distance: np.ndarray, pct: float) -> tuple:
    """
    Ranks every OD cell with nonzero, connected HBW trips by distance
    descending, and selects cells off the top until their cumulative trip
    volume reaches pct * region-wide total, splitting the boundary cell
    fractionally so the amount selected is exact. Returns (move_fraction,
    summary) -- move_fraction is a same-shape array giving each cell's
    selected share (0 for untouched cells, up to 1 for cells fully inside
    the tail).
    """
    move_fraction = np.zeros_like(combined, dtype=float)
    valid = (combined > 0) & (distance < SKIM_NOACCESS_SENTINEL)
    total = combined[valid].sum()

    summary = {
        "cells_selected": 0,
        "total_region_trips": float(total),
        "target_moved_trips": 0.0,
        "actual_moved_trips": 0.0,
    }
    if total <= 0 or pct <= 0:
        return move_fraction, summary

    rows, cols = np.nonzero(valid)
    dists = distance[rows, cols]
    vols = combined[rows, cols]

    order = np.argsort(-dists)
    rows, cols, vols = rows[order], cols[order], vols[order]

    cumulative = np.cumsum(vols)
    target = pct * total
    cutoff_idx = int(np.searchsorted(cumulative, target))

    if cutoff_idx >= len(vols):
        move_fraction[rows, cols] = 1.0
    else:
        if cutoff_idx > 0:
            move_fraction[rows[:cutoff_idx], cols[:cutoff_idx]] = 1.0
        prev_cumulative = cumulative[cutoff_idx - 1] if cutoff_idx > 0 else 0.0
        remaining = target - prev_cumulative
        boundary_vol = vols[cutoff_idx]
        if boundary_vol > 0:
            move_fraction[rows[cutoff_idx], cols[cutoff_idx]] = remaining / boundary_vol

    summary["cells_selected"] = int(np.count_nonzero(move_fraction))
    summary["target_moved_trips"] = float(target)
    summary["actual_moved_trips"] = float((move_fraction * combined).sum())
    return move_fraction, summary


def redistribute_core(core: np.ndarray, move_fraction: np.ndarray, band_mask: np.ndarray) -> tuple:
    """
    For each origin row with selected (move_fraction > 0) trips, moves this
    core's share of that selected volume onto the row's own destinations
    within band_mask (excluding any destination already selected as "long"
    for that row), distributed proportional to this core's existing pattern
    in the band. Row totals are conserved exactly.
    """
    adjusted = core.copy()
    num_zones = core.shape[0]
    selected_mask = move_fraction > 0

    rows_adjusted = 0
    rows_no_selection = 0
    rows_skipped_no_band_pattern = 0
    total_trips_moved = 0.0

    for i in range(num_zones):
        row_selected = selected_mask[i, :]
        if not row_selected.any():
            rows_no_selection += 1
            continue

        moved_amount = float((move_fraction[i, row_selected] * core[i, row_selected]).sum())
        if moved_amount <= 0:
            rows_no_selection += 1
            continue

        receiving_mask = band_mask[i, :] & ~row_selected
        inside_trips = core[i, receiving_mask]
        total_inside = inside_trips.sum()
        if total_inside <= 0:
            rows_skipped_no_band_pattern += 1
            continue

        adjusted[i, row_selected] = core[i, row_selected] * (1 - move_fraction[i, row_selected])
        adjusted[i, receiving_mask] = core[i, receiving_mask] + moved_amount * (inside_trips / total_inside)

        rows_adjusted += 1
        total_trips_moved += moved_amount

    original_row_sums = core.sum(axis=1)
    adjusted_row_sums = adjusted.sum(axis=1)
    if not np.allclose(original_row_sums, adjusted_row_sums, atol=1e-6):
        raise AssertionError("Row totals were not conserved during redistribution")

    summary = {
        "rows_adjusted": rows_adjusted,
        "rows_no_selection": rows_no_selection,
        "rows_skipped_no_band_pattern": rows_skipped_no_band_pattern,
        "total_trips_moved": total_trips_moved,
        "total_trips_before": core.sum(),
        "total_trips_after": adjusted.sum(),
    }
    return adjusted, summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-set-dir", required=True, type=Path)
    parser.add_argument("--scenario-id", required=True)
    parser.add_argument(
        "--numveh-mtx", required=True, type=Path,
        help="pa_HBW_NumVeh_noXI.mtx -- the file 08_TripTablesByPeriod.s actually "
             "reads forward into mode choice/assignment.",
    )
    parser.add_argument(
        "--destchoice-mtx", required=True, type=Path,
        help="pa_AllPurp.2.DestChoice.mtx -- its aggregate HBW core is recomputed "
             "as HBW0+HBW1+HBW2 afterward so P/A-balance reporting stays consistent; "
             "nothing downstream reads it back into the model.",
    )
    parser.add_argument(
        "--skim-mtx", required=True, type=Path,
        help="skm_auto_Pk.mtx -- provides dist_GP, the same distance basis "
             "mc_HBW_dest_choice.py used to place these trips in the first place.",
    )
    args = parser.parse_args()

    variables = load_scenario_variables(args.run_set_dir, args.scenario_id)
    pct = float(variables.get("hbw_trip_redistribution_portion", 0))

    if pct <= 0:
        print(
            f"{args.scenario_id}: hbw_trip_redistribution_portion={pct} -- "
            "nothing to redistribute, leaving matrices unchanged."
        )
        sys.exit(0)

    work_dir = args.numveh_mtx.parent

    print(f"Converting {args.numveh_mtx.name} to OMX...")
    numveh_omx_in = work_dir / f"{args.numveh_mtx.stem}_redistribute_in.omx"
    convert_mtx_to_omx(args.numveh_mtx, numveh_omx_in)
    with omx.open_file(numveh_omx_in, "r") as f_in:
        available = f_in.list_matrices()
        for core_name in VEHICLE_CORES:
            if core_name not in available:
                message = f"Core '{core_name}' not found in {numveh_omx_in} (found: {available})"
                raise KeyError(message)
        cores = {name: np.array(f_in[name][:]) for name in available}

    num_zones = cores[VEHICLE_CORES[0]].shape[0]

    print(f"Converting {args.skim_mtx.name} to OMX...")
    skim_omx = work_dir / f"{args.skim_mtx.stem}_redistribute_skim.omx"
    convert_mtx_to_omx(args.skim_mtx, skim_omx)
    with omx.open_file(skim_omx, "r") as f_in:
        if DISTANCE_CORE not in f_in.list_matrices():
            message = f"Core '{DISTANCE_CORE}' not found in {skim_omx} (found: {f_in.list_matrices()})"
            raise KeyError(message)
        distance = np.array(f_in[DISTANCE_CORE][:])

    if distance.shape != (num_zones, num_zones):
        message = (
            f"Distance skim shape {distance.shape} does not match "
            f"{args.numveh_mtx.name}'s zone count {num_zones}"
        )
        raise ValueError(message)

    combined = sum(cores[c] for c in VEHICLE_CORES)

    move_fraction, selection_summary = select_region_wide(combined, distance, pct)
    print(
        f"{args.scenario_id}: redistributing the longest {pct:.0%} of region-wide HBW trip "
        f"volume toward destinations within {DISTANCE_BAND_MILES:.1f} mi of the regional median."
    )
    print(
        f"  region-wide selection: cells selected: {selection_summary['cells_selected']}, "
        f"target trips: {selection_summary['target_moved_trips']:.1f}, "
        f"actual trips: {selection_summary['actual_moved_trips']:.1f} "
        f"(region total: {selection_summary['total_region_trips']:.1f})"
    )

    valid_mask = (combined > 0) & (distance < SKIM_NOACCESS_SENTINEL)
    median_distance = weighted_median(distance[valid_mask], combined[valid_mask])
    band_mask = (np.abs(distance - median_distance) <= DISTANCE_BAND_MILES) & (distance < SKIM_NOACCESS_SENTINEL)
    print(
        f"  regional median HBW distance: {median_distance:.2f} mi "
        f"(band: {median_distance - DISTANCE_BAND_MILES:.2f}-{median_distance + DISTANCE_BAND_MILES:.2f} mi)"
    )

    adjusted_cores = {}
    core_summaries = {}
    for core_name in VEHICLE_CORES:
        adjusted, summary = redistribute_core(cores[core_name], move_fraction, band_mask)
        adjusted_cores[core_name] = adjusted
        cores[core_name] = adjusted
        core_summaries[core_name] = summary
        print(
            f"  {core_name}: rows adjusted: {summary['rows_adjusted']}, "
            f"rows w/ no selection: {summary['rows_no_selection']}, "
            f"rows skipped (no band pattern): {summary['rows_skipped_no_band_pattern']}, "
            f"trips moved: {summary['total_trips_moved']:.1f}"
        )

    print(f"Converting adjusted matrix back to {args.numveh_mtx.name}...")
    numveh_omx_out = work_dir / f"{args.numveh_mtx.stem}_redistribute_out.omx"
    with omx.open_file(numveh_omx_out, "w") as f_out:
        for name, data in cores.items():
            f_out[name] = data
    convert_omx_to_mtx(numveh_omx_out, args.numveh_mtx)

    hbw_total_adjusted = sum(adjusted_cores[c] for c in VEHICLE_CORES)

    # Sync pa_AllPurp.2.DestChoice.mtx's aggregate "HBW" core (reporting only --
    # nothing downstream of 07_HBW_dest_choice.s reads this file's HBW core back
    # into the model; see module docstring).
    dc_work_dir = args.destchoice_mtx.parent
    dc_input_omx = dc_work_dir / f"{args.destchoice_mtx.stem}_redistribute_in.omx"
    dc_output_omx = dc_work_dir / f"{args.destchoice_mtx.stem}_redistribute_out.omx"
    print(f"Converting {args.destchoice_mtx.name} to OMX...")
    convert_mtx_to_omx(args.destchoice_mtx, dc_input_omx)
    with omx.open_file(dc_input_omx, "r") as f_in:
        dc_available = f_in.list_matrices()
        if "HBW" not in dc_available:
            message = f"Core 'HBW' not found in {dc_input_omx} (found: {dc_available})"
            raise KeyError(message)
        dc_cores = {name: np.array(f_in[name][:]) for name in dc_available}
    dc_cores["HBW"] = hbw_total_adjusted
    with omx.open_file(dc_output_omx, "w") as f_out:
        for name, data in dc_cores.items():
            f_out[name] = data
    print(f"Converting adjusted matrix back to {args.destchoice_mtx.name}...")
    convert_omx_to_mtx(dc_output_omx, args.destchoice_mtx)

    total_moved = sum(summary["total_trips_moved"] for summary in core_summaries.values())
    print(f"{args.scenario_id}: done. total HBW trips moved across all vehicle segments: {total_moved:.1f}")


if __name__ == "__main__":
    main()
