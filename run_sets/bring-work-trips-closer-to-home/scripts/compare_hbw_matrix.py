# Description:
#     Compares the HBW core of pa_AllPurp.2.DestChoice.mtx before and after
#     redistribute_hbw_trips.py ran for a scenario, using the OMX
#     conversions the live run already left behind in Temp/4_ModeChoice/
#     (pa_AllPurp.2.DestChoice_redistribute_in.omx /
#     _redistribute_out.omx) -- no CONVERTMAT/Voyager call needed.
#
#     Reuses load_geography_lookup() from redistribute_hbw_trips.py so the
#     "own city" grouping matches exactly what the redistribution itself
#     used: for each origin zone, "inside" means "same geography-field
#     value as that zone's own value" (e.g. same CITY_UGRC city), not a
#     single region-wide target area.

import argparse
from pathlib import Path

import numpy as np
import openmatrix as omx
import pandas as pd

from redistribute_hbw_trips import load_geography_lookup

SCENARIO_ROOT = (
    Path(__file__).resolve().parents[3] / "tdm" / "Scenarios" / "bring-work-trips-closer-to-home"
)
DEFAULT_BEFORE = (
    SCENARIO_ROOT
    / "Closer01"
    / "Temp"
    / "4_ModeChoice"
    / "pa_AllPurp.2.DestChoice_redistribute_in.omx"
)
DEFAULT_AFTER = (
    SCENARIO_ROOT
    / "Closer01"
    / "Temp"
    / "4_ModeChoice"
    / "pa_AllPurp.2.DestChoice_redistribute_out.omx"
)
DEFAULT_TAZ_DBF = (
    Path(__file__).resolve().parents[3] / "tdm" / "1_Inputs" / "1_TAZ" / "WFv1000_TAZ.dbf"
)


def load_core(omx_path: Path, core: str) -> np.ndarray:
    with omx.open_file(omx_path, "r") as f:
        if core not in f.list_matrices():
            raise KeyError(f"Core '{core}' not found in {omx_path} (found: {f.list_matrices()})")
        return np.array(f[core][:])


def same_city_totals(matrix: np.ndarray, geography: np.ndarray) -> np.ndarray:
    """
    Per origin row i, total trips landing in the same geography-unit as
    zone i (NaN where zone i has no geography assignment). Vectorized via
    one-hot city membership rather than a per-row Python loop.
    """
    codes, uniques = pd.factorize(pd.Series(geography), sort=False)
    num_zones = matrix.shape[0]
    num_cities = len(uniques)
    membership = np.zeros((num_zones, num_cities))
    valid = codes >= 0
    membership[np.nonzero(valid)[0], codes[valid]] = 1.0

    trips_by_dest_city = matrix @ membership  # (num_zones, num_cities)
    result = np.full(num_zones, np.nan)
    result[valid] = trips_by_dest_city[np.nonzero(valid)[0], codes[valid]]
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before-omx", type=Path, default=DEFAULT_BEFORE)
    parser.add_argument("--after-omx", type=Path, default=DEFAULT_AFTER)
    parser.add_argument("--taz-dbf", type=Path, default=DEFAULT_TAZ_DBF)
    parser.add_argument("--geography-field", default="CITY_UGRC")
    parser.add_argument("--core", default="HBW")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--top-n", type=int, default=15)
    args = parser.parse_args()

    before = load_core(args.before_omx, args.core)
    after = load_core(args.after_omx, args.core)
    if before.shape != after.shape:
        raise ValueError(f"Shape mismatch: before {before.shape} vs after {after.shape}")
    num_zones = before.shape[0]

    row_totals_before = before.sum(axis=1)
    row_totals_after = after.sum(axis=1)
    if not np.allclose(row_totals_before, row_totals_after, atol=1e-6):
        max_diff = np.max(np.abs(row_totals_before - row_totals_after))
        print(f"WARNING: row totals not conserved -- max diff {max_diff:.4f}")

    geography = load_geography_lookup(args.taz_dbf, args.geography_field, num_zones)

    same_before = same_city_totals(before, geography)
    same_after = same_city_totals(after, geography)
    outside_before = row_totals_before - same_before
    outside_after = row_totals_after - same_after
    trips_moved_in = same_after - same_before  # per origin row

    taz_ids = np.arange(1, num_zones + 1)
    has_geo = geography != None  # noqa: E711  (object array; np.not_equal(None) below is elementwise)

    print("=== Grand totals ===")
    print(f"  before: {before.sum():.1f}")
    print(f"  after:  {after.sum():.1f}")
    print(
        f"  diff:   {after.sum() - before.sum():.4f}  (should be ~0 -- redistribution only moves trips)"
    )

    print("\n=== Same-city vs. other-city HBW destinations (zones with a geography assignment) ===")
    print(f"  zones with '{args.geography_field}' assigned: {has_geo.sum()} of {num_zones}")
    print(
        f"  same-city trips  before: {np.nansum(same_before):.1f}   after: {np.nansum(same_after):.1f}"
    )
    print(
        f"  other-city trips before: {np.nansum(outside_before):.1f}   after: {np.nansum(outside_after):.1f}"
    )
    print(f"  total trips moved into own city: {np.nansum(trips_moved_in):.1f}")
    rows_adjusted = int(np.sum(trips_moved_in > 1e-6))
    print(f"  origin rows with a measurable shift: {rows_adjusted}")

    dest_totals_before = before.sum(axis=0)
    dest_totals_after = after.sum(axis=0)
    dest_delta = dest_totals_after - dest_totals_before

    origin_df = pd.DataFrame(
        {
            "TAZID": taz_ids,
            "own_geography": geography,
            "row_total": row_totals_before,
            "same_city_before": same_before,
            "same_city_after": same_after,
            "other_city_before": outside_before,
            "other_city_after": outside_after,
            "trips_moved_into_own_city": trips_moved_in,
        }
    )

    dest_df = pd.DataFrame(
        {
            "TAZID": taz_ids,
            "own_geography": geography,
            "received_before": dest_totals_before,
            "received_after": dest_totals_after,
            "delta": dest_delta,
        }
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    origin_path = args.output_dir / "hbw_matrix_compare_origin.csv"
    dest_path = args.output_dir / "hbw_matrix_compare_destination.csv"
    origin_df.to_csv(origin_path, index=False)
    dest_df.to_csv(dest_path, index=False)
    print(f"\nWrote {origin_path}")
    print(f"Wrote {dest_path}")

    print(f"\n=== Top {args.top_n} destination zones by trip gain ===")
    print(dest_df.sort_values("delta", ascending=False).head(args.top_n).to_string(index=False))

    print(f"\n=== Top {args.top_n} destination zones by trip loss ===")
    print(dest_df.sort_values("delta", ascending=True).head(args.top_n).to_string(index=False))


if __name__ == "__main__":
    main()
