# Description:
#     Redistributes a share of HBW (home-based work) trips from each origin
#     zone toward destinations within that zone's own geography unit
#     (city area / medium district / workshop area), pulling the moved
#     trips out of destinations outside that unit. Reads
#     hbw_trip_redistribution_portion / geography_type from the scenario's own
#     CloseXX.yaml `variables:` block (these are documentation-only to the
#     framework -- this script is the thing that actually consumes them).
#
#     Operates on pa_HBW_NumVeh_noXI.mtx's vehicle-ownership-segmented HBW
#     cores (HBW0/HBW1/HBW2) -- NOT pa_AllPurp.2.DestChoice.mtx's aggregate
#     "HBW" core, which an earlier version of this script edited. That was a
#     bug: 08_TripTablesByPeriod.s (and everything after it -- mode choice,
#     assignment) reads pa_HBW_NumVeh_noXI.mtx's HBW0/HBW1/HBW2 directly and
#     never re-derives them from pa_AllPurp.2.DestChoice.mtx, so editing only
#     the DestChoice core had no effect on any downstream zone metric. See
#     08_TripTablesByPeriod.s:94-96, 09_Segmnt_PA_HBbyMC.s:45,
#     10_ConvertSomeXI2HBW.s:17-18, 11_MC_HBW_HBO_NHB_HBC.s:33-38,90-92.
#
#     pa_AllPurp.2.DestChoice.mtx's own "HBW" core is still updated afterward
#     (recomputed as HBW0+HBW1+HBW2) purely so its P/A-balance reporting
#     (_checkPABalance.dbf, _LogFile.txt via 10_ConvertSomeXI2HBW.s) reflects
#     the same numbers mode choice actually uses, even though nothing reads
#     that core back into the model stream.
#
#     Converts to OMX and back via CONVERTMAT the same way
#     mc_HBW_dest_choice.py does -- writing a small .s + .bat and shelling
#     out to VOYAGER.EXE -- since numpy/openmatrix can't read TPP directly.
#     Every core in each file is carried through to the output, with only
#     the target cores adjusted, so nothing downstream loses the other
#     purposes/segments carried in the same matrix file.

import argparse
import subprocess
import sys
from pathlib import Path

import numpy as np
import openmatrix as omx
import pandas as pd
import yaml
from dbfread import DBF

# Matches the hardcoded Cube Voyager install location used by the TDM's own
# _Python scripts (mc_HBW_dest_choice.py, _parcel_volume.py) -- not
# configurable at this layer, consistent with those.
VOYAGER_DIR = r"C:\Program Files\Citilabs\CubeVoyager"

# geography_type values (scenario `variables:`) known to map 1:1 onto a
# WFv1000_TAZ.dbf field name. Guards against a typo in geography_type that
# would otherwise silently match some unrelated dbf column (e.g. TAZID).
KNOWN_GEOGRAPHY_TYPES = {"CITY_UGRC", "DISTMED", "CITYGRP"}

# The three vehicle-ownership-segmented HBW cores in pa_HBW_NumVeh_noXI.mtx
# that 08_TripTablesByPeriod.s actually reads forward into mode choice.
VEHICLE_CORES = ["HBW0", "HBW1", "HBW2"]


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


def load_geography_lookup(taz_dbf_path: Path, field_name: str, num_zones: int) -> np.ndarray:
    """
    Build a length-num_zones lookup of geography-unit id per zone index
    (0-based; zone index z holds TAZID z+1). None marks zones with no
    geography assignment (dummy/external zones, or blank field values) --
    such zones never participate as a redistribution "inside" target and
    their own row (if any) is skipped entirely.
    """
    df = pd.DataFrame(iter(DBF(taz_dbf_path)))
    if field_name not in df.columns:
        raise KeyError(
            f"'{field_name}' not found in {taz_dbf_path} (available: {list(df.columns)})"
        )

    lookup = np.full(num_zones, None, dtype=object)
    for _, row in df[["TAZID", field_name]].iterrows():
        taz_index = int(row["TAZID"]) - 1
        if taz_index < 0 or taz_index >= num_zones:
            continue
        value = row[field_name]
        if value is None:
            continue
        if isinstance(value, str):
            value = value.strip()
            if value == "":
                continue
        elif value == 0:
            continue
        lookup[taz_index] = value
    return lookup


def redistribute_hbw_trips(matrix: np.ndarray, geography: np.ndarray, pct: float) -> tuple:
    """
    For each origin row i with a valid geography assignment, moves `pct`
    of the trips currently ending outside geography[i] into destinations
    inside geography[i], distributed proportional to the existing inside
    trip pattern for that row. Row totals are conserved exactly. Returns
    (adjusted_matrix, summary dict).
    """
    adjusted = matrix.copy()
    num_zones = matrix.shape[0]

    rows_adjusted = 0
    rows_skipped_no_geography = 0
    rows_skipped_no_inside_pattern = 0
    total_trips_moved = 0.0

    for i in range(num_zones):
        home_geography = geography[i]
        if home_geography is None:
            rows_skipped_no_geography += 1
            continue

        inside_mask = geography == home_geography
        outside_mask = ~inside_mask

        row = adjusted[i, :]
        outside_trips = row[outside_mask]
        total_outside = outside_trips.sum()
        move_amount = pct * total_outside
        if move_amount <= 0:
            continue

        inside_trips = row[inside_mask]
        total_inside = inside_trips.sum()
        if total_inside <= 0:
            # No existing internal pattern to scale against -- nothing
            # sensible to redistribute onto, so leave this row untouched
            # rather than guessing a distribution.
            rows_skipped_no_inside_pattern += 1
            continue

        adjusted[i, outside_mask] = row[outside_mask] * (1 - pct)
        adjusted[i, inside_mask] = row[inside_mask] + move_amount * (inside_trips / total_inside)

        rows_adjusted += 1
        total_trips_moved += move_amount

    original_row_sums = matrix.sum(axis=1)
    adjusted_row_sums = adjusted.sum(axis=1)
    if not np.allclose(original_row_sums, adjusted_row_sums, atol=1e-6):
        raise AssertionError("Row totals were not conserved during redistribution")

    summary = {
        "rows_adjusted": rows_adjusted,
        "rows_skipped_no_geography": rows_skipped_no_geography,
        "rows_skipped_no_inside_pattern": rows_skipped_no_inside_pattern,
        "total_trips_moved": total_trips_moved,
        "total_trips_before": matrix.sum(),
        "total_trips_after": adjusted.sum(),
    }
    return adjusted, summary


def redistribute_matrix_file(
    mtx_path: Path, taz_dbf_path: Path, field_name: str, pct: float, core_names: list
) -> tuple:
    """
    Converts mtx_path to OMX, redistributes the named cores in place
    (every other core is carried through unchanged), converts back to the
    same mtx_path. Returns ({core_name: summary}, cores) for the
    redistributed cores. Builds the geography lookup itself, once the
    converted OMX file's zone count is known -- the raw .mtx is Cube's
    native TPP format and can't be opened directly to peek at it.
    """
    work_dir = mtx_path.parent
    input_omx = work_dir / f"{mtx_path.stem}_redistribute_in.omx"
    output_omx = work_dir / f"{mtx_path.stem}_redistribute_out.omx"

    print(f"Converting {mtx_path.name} to OMX...")
    convert_mtx_to_omx(mtx_path, input_omx)

    with omx.open_file(input_omx, "r") as f_in:
        available = f_in.list_matrices()
        for core_name in core_names:
            if core_name not in available:
                message = f"Core '{core_name}' not found in {input_omx} (found: {available})"
                raise KeyError(message)
        cores = {name: np.array(f_in[name][:]) for name in available}

    num_zones = cores[core_names[0]].shape[0]
    geography = load_geography_lookup(taz_dbf_path, field_name, num_zones)

    summaries = {}
    for core_name in core_names:
        adjusted, summary = redistribute_hbw_trips(cores[core_name], geography, pct)
        cores[core_name] = adjusted
        summaries[core_name] = summary
        print(
            f"  {core_name}: rows adjusted: {summary['rows_adjusted']}, "
            f"skipped (no geography): {summary['rows_skipped_no_geography']}, "
            f"skipped (no inside pattern): {summary['rows_skipped_no_inside_pattern']}, "
            f"trips moved: {summary['total_trips_moved']:.1f}"
        )

    with omx.open_file(output_omx, "w") as f_out:
        for name, data in cores.items():
            f_out[name] = data

    print(f"Converting adjusted matrix back to {mtx_path.name}...")
    convert_omx_to_mtx(output_omx, mtx_path)
    return summaries, cores


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
    parser.add_argument("--taz-dbf", required=True, type=Path)
    parser.add_argument(
        "--geography-field",
        help="Override the TAZ dbf field name to use instead of geography_type.",
    )
    args = parser.parse_args()

    variables = load_scenario_variables(args.run_set_dir, args.scenario_id)
    pct = float(variables.get("hbw_trip_redistribution_portion", 0))
    geography_type = variables.get("geography_type", "")

    if pct <= 0 or not geography_type:
        print(
            f"{args.scenario_id}: hbw_trip_redistribution_portion={pct}, "
            f"geography_type='{geography_type}' -- nothing to redistribute, leaving matrices unchanged."
        )
        sys.exit(0)

    if not args.geography_field and geography_type not in KNOWN_GEOGRAPHY_TYPES:
        message = (
            f"Unknown geography_type '{geography_type}' -- expected one of "
            f"{sorted(KNOWN_GEOGRAPHY_TYPES)}, or pass --geography-field explicitly."
        )
        raise ValueError(message)

    field_name = args.geography_field or geography_type

    print(
        f"{args.scenario_id}: redistributing {pct:.0%} of outside-{geography_type} HBW trips "
        f"toward home {geography_type} for each origin, per vehicle-ownership segment."
    )
    numveh_summaries, numveh_cores = redistribute_matrix_file(
        args.numveh_mtx, args.taz_dbf, field_name, pct, VEHICLE_CORES
    )
    hbw_total_adjusted = sum(numveh_cores[core] for core in VEHICLE_CORES)

    # Sync pa_AllPurp.2.DestChoice.mtx's aggregate "HBW" core (reporting only --
    # nothing downstream of 07_HBW_dest_choice.s reads this file's HBW core back
    # into the model; see module docstring).
    work_dir = args.destchoice_mtx.parent
    dc_input_omx = work_dir / f"{args.destchoice_mtx.stem}_redistribute_in.omx"
    dc_output_omx = work_dir / f"{args.destchoice_mtx.stem}_redistribute_out.omx"
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

    total_moved = sum(summary["total_trips_moved"] for summary in numveh_summaries.values())
    print(f"{args.scenario_id}: done. total HBW trips moved across all vehicle segments: {total_moved:.1f}")


if __name__ == "__main__":
    main()
