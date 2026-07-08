# Description:
#     Redistributes a share of HBW (home-based work) trips from each origin
#     zone toward destinations within that zone's own geography unit
#     (city area / medium district / workshop area), pulling the moved
#     trips out of destinations outside that unit. Reads
#     HBW_TripRedistributionPct / GeographyType from the scenario's own
#     CloseXX.yaml `variables:` block (these are documentation-only to the
#     framework -- this script is the thing that actually consumes them).
#
#     Operates on the HBW core of pa_AllPurp.2.DestChoice.mtx (Cube's native
#     TPP format). Converts to OMX and back via CONVERTMAT the same way
#     mc_HBW_dest_choice.py does -- writing a small .s + .bat and shelling
#     out to VOYAGER.EXE -- since numpy/openmatrix can't read TPP directly.
#     Every core in the file is carried through to the output, with only the
#     target core adjusted, so nothing downstream loses the other
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

# GeographyType (scenario `variables:`) -> field name in WFv1000_TAZ.dbf.
# Confirmed against the TDM's TAZ dbf: CITYAREA has no literal field of its
# own and maps to CITY_UGRC; DISTMED and CITYGRP are literal field name
# matches.
GEOGRAPHY_FIELD_MAP = {
    "CITYAREA": "CITY_UGRC",
    "DISTMED": "DISTMED",
    "CITYGRP": "CITYGRP",
}


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
            f'compression=2, format="omx"\n',
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
    """Build a length-num_zones lookup of geography-unit id per zone index
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
    """For each origin row i with a valid geography assignment, moves `pct`
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-set-dir", required=True, type=Path)
    parser.add_argument("--scenario-id", required=True)
    parser.add_argument("--input-mtx", required=True, type=Path)
    parser.add_argument("--output-mtx", type=Path, help="Defaults to --input-mtx (in place).")
    parser.add_argument("--core", default="HBW", help="Matrix core to redistribute. Default: HBW.")
    parser.add_argument("--taz-dbf", required=True, type=Path)
    parser.add_argument(
        "--geography-field",
        help="Override the TAZ dbf field name to use instead of looking up GeographyType "
        "in GEOGRAPHY_FIELD_MAP.",
    )
    args = parser.parse_args()

    output_mtx = args.output_mtx or args.input_mtx

    variables = load_scenario_variables(args.run_set_dir, args.scenario_id)
    pct = float(variables.get("HBW_TripRedistributionPct", 0))
    geography_type = variables.get("GeographyType", "")

    if pct <= 0 or not geography_type:
        print(
            f"{args.scenario_id}: HBW_TripRedistributionPct={pct}, "
            f"GeographyType='{geography_type}' -- nothing to redistribute, leaving matrix unchanged."
        )
        if output_mtx != args.input_mtx:
            output_mtx.write_bytes(args.input_mtx.read_bytes())
        sys.exit(0)

    field_name = args.geography_field or GEOGRAPHY_FIELD_MAP.get(geography_type)
    if field_name is None:
        raise ValueError(
            f"Unknown GeographyType '{geography_type}' -- add it to GEOGRAPHY_FIELD_MAP "
            "or pass --geography-field explicitly."
        )

    work_dir = args.input_mtx.parent
    input_omx = work_dir / f"{args.input_mtx.stem}_redistribute_in.omx"
    output_omx = work_dir / f"{args.input_mtx.stem}_redistribute_out.omx"

    print(f"Converting {args.input_mtx.name} to OMX...")
    convert_mtx_to_omx(args.input_mtx, input_omx)

    with omx.open_file(input_omx, "r") as f_in:
        core_names = f_in.list_matrices()
        if args.core not in core_names:
            message = f"Core '{args.core}' not found in {input_omx} (found: {core_names})"
            raise KeyError(message)
        cores = {name: np.array(f_in[name][:]) for name in core_names}
        num_zones = cores[args.core].shape[0]

    geography = load_geography_lookup(args.taz_dbf, field_name, num_zones)
    adjusted, summary = redistribute_hbw_trips(cores[args.core], geography, pct)
    cores[args.core] = adjusted

    print(
        f"{args.scenario_id}: redistributed {pct:.0%} of outside-{geography_type} HBW trips "
        f"toward home {geography_type} for each origin."
    )
    print(
        f"  rows adjusted: {summary['rows_adjusted']}, "
        f"skipped (no geography): {summary['rows_skipped_no_geography']}, "
        f"skipped (no inside pattern): {summary['rows_skipped_no_inside_pattern']}"
    )
    print(
        f"  trips moved: {summary['total_trips_moved']:.1f} "
        f"(total before: {summary['total_trips_before']:.1f}, "
        f"total after: {summary['total_trips_after']:.1f})"
    )

    with omx.open_file(output_omx, "w") as f_out:
        for name, data in cores.items():
            f_out[name] = data

    print(f"Converting adjusted matrix back to {output_mtx.name}...")
    convert_omx_to_mtx(output_omx, output_mtx)


if __name__ == "__main__":
    main()
