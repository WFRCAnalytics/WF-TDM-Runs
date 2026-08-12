# Description:
#     Shifts every origin zone's own trip-volume-weighted mean HBW
#     (home-based work) commute distance by hbw_trip_length_shift_pct, a
#     signed fraction read from the scenario's own ShiftXX.yaml `variables:`
#     block (documentation-only to the framework -- this script is the thing
#     that actually consumes it). Negative shortens, positive lengthens.
#
#     Unlike the companion redistribute_hbw_trips.py (pulls trips into a
#     named geography) and redistribute_longest_hbw_trips.py (trims a
#     region-wide percentile tail of trip volume), this applies to EVERY
#     origin with existing HBW trips, region-wide -- 100% of trip volume,
#     not a selected subset -- and its target is an exact per-origin mean
#     shift, not a portion of volume to move.
#
#     Mechanism: for each origin row and each vehicle-ownership core
#     independently, reweight that row's existing nonzero, connected
#     destinations by an exponential ("entropy") tilt --
#         adjusted[i, j] = trips[i, j] * exp(theta_i * (dist[i, j] - mean_i))
#     -- rescaled so the row's eligible-subset total is conserved exactly.
#     theta_i is solved per row by bisection so the new weighted-mean
#     distance equals old_mean_i * (1 + pct). The weighted mean is provably
#     monotonic in theta (its derivative is the variance of dist, always
#     >= 0), so a bracket search + bisection always converges given a valid
#     target. Destinations with zero existing trips from that origin are
#     never touched -- trips only ever move among destinations an origin
#     already uses, matching both companion scripts' "never invent access"
#     rule.
#
#     Distance basis is skm_auto_Pk.mtx's dist_GP core -- the same skim
#     tdm/2_ModelScripts/_Python/mc_HBW_dest_choice.py already uses in the
#     HBW destination-choice utility function, so "how far this trip is" is
#     defined identically to how the model itself placed it. Cells at or
#     beyond SKIM_NOACCESS_SENTINEL (Cube's NOACCESS value for unconnected
#     zone pairs) are excluded from eligibility and from the mean/target
#     calculation entirely, matching the convention already used by both
#     companion scripts.
#
#     Edge cases, each counted and logged per core:
#       - zero_trips: origin has no existing HBW trips -- row untouched.
#       - single_destination_unreachable: origin has exactly one existing
#         destination -- its mean cannot move in either direction -- row
#         untouched.
#       - clamped: the target mean falls beyond the closest/farthest
#         existing destination (e.g. -10% when the nearest destination is
#         already farther than the target) -- the target is pre-clamped
#         strictly inside (min_dist, max_dist) before the bisection search,
#         so a valid bracket always exists; the row gets as close as
#         physically possible given its existing destination set.
#       - not_converged: bisection did not reach tolerance within the
#         iteration cap -- the best theta found is used; row-total
#         conservation is unaffected either way (it's a hard invariant,
#         asserted separately, not something the per-row mean target search
#         can break).
#
#     Applied independently per vehicle-ownership core (HBW0/HBW1/HBW2),
#     each with its own per-row mean/target/theta -- not a shared theta
#     derived from a combined matrix -- since a target mean shift is a
#     property of a specific core's own distribution (unlike "how far is
#     this OD pair", which redistribute_longest_hbw_trips.py's shared
#     selection can treat as core-independent). Mirrors
#     bring-work-trips-closer-to-home/scripts/redistribute_hbw_trips.py's
#     fully-independent per-core treatment.
#
#     Row totals (within each row's eligible subset) are conserved exactly,
#     asserted via np.allclose -- trips are moved, never created or
#     destroyed.
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
#     Converts to OMX and back via CONVERTMAT the same way the companion
#     scripts do, since numpy/openmatrix can't read TPP directly.
#
#     IMPORTANT: hbw_trip_length_shift_pct is a SIGNED target (-0.10 to
#     +0.10), unlike the companion scripts' non-negative "portion of trips
#     to move" parameter -- the no-op guard here must be `pct == 0`, NOT
#     `pct <= 0` (which would silently no-op every shortening scenario).

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

# Cube's NOACCESS sentinel for unconnected zone pairs (see
# tdm/2_ModelScripts/5_AssignHwy/07_PerformFinalNetSkim.s's PATHLOAD
# NOACCESS=9999, and the companion scripts' own SKIM_NOACCESS_SENTINEL) --
# excluded so a handful of technically-unconnected cells can't distort a
# row's mean or receive reweighted mass.
SKIM_NOACCESS_SENTINEL = 9999

# Keeps exp()'s argument comfortably under float64's ~709 overflow point,
# even after a row-specific theta_cap (see solve_row_theta) scales it by
# that row's own distance span.
MAX_EXP_ARG = 700.0

# Bisection stops once the achieved weighted mean is within this many miles
# of the target -- far tighter than any distance figure this framework
# reports to a decimal place, kept simple rather than tuned tight.
THETA_TOL_MILES = 1e-4

# Bisection halves its bracket each iteration; 60 is far more than needed
# for float64 precision on a bracket seeded at BRACKET_SEED and expanded by
# BRACKET_EXPAND_FACTOR, kept generous rather than tuned tight.
MAX_BISECTION_ITER = 60
BRACKET_SEED = 1e-3
BRACKET_EXPAND_FACTOR = 2.0


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


def solve_row_theta(trips_row: np.ndarray, dist_row: np.ndarray, pct: float,
                     sentinel: float = SKIM_NOACCESS_SENTINEL) -> tuple:
    """Solves for theta such that reweighting trips_row's eligible
    (nonzero, connected) entries by exp(theta * (dist - old_mean)) shifts
    the weighted mean distance to old_mean * (1 + pct). Returns
    (theta_or_None, status) -- theta is None when the row can't be
    adjusted at all (zero_trips / single_destination_unreachable), in
    which case the caller leaves that row untouched."""
    eligible = (trips_row > 0) & (dist_row < sentinel)
    n_eligible = int(eligible.sum())

    if n_eligible == 0:
        return None, "zero_trips"

    d = dist_row[eligible]
    w = trips_row[eligible]
    old_mean = float((w * d).sum() / w.sum())

    if pct == 0:
        return 0.0, "ok"

    if n_eligible == 1:
        return None, "single_destination_unreachable"

    d_min, d_max = float(d.min()), float(d.max())
    target_mean = old_mean * (1.0 + pct)

    # The tilted mean can only asymptotically approach d_min/d_max (theta ->
    # +/-inf), never reach them exactly, so clamp the target strictly inside
    # (d_min, d_max) before searching -- guarantees a bracket exists and
    # bisection can't chase an unreachable point forever. Handles both "-10%
    # but the closest destination is already farther than the target" and
    # the mirror "+10% but the farthest destination is already closer".
    span = max(d_max - d_min, 1e-9)
    eps = min(1e-6 * span, span / 4)
    clamped_target = min(max(target_mean, d_min + eps), d_max - eps)
    was_clamped = abs(clamped_target - target_mean) > 1e-9

    # Row-specific overflow-safe bound on |theta| -- keeps
    # theta * (d - old_mean) under MAX_EXP_ARG even at the cap.
    theta_cap = MAX_EXP_ARG / span

    def weighted_mean_at(theta):
        wt = w * np.exp(np.clip(theta * (d - old_mean), -MAX_EXP_ARG, MAX_EXP_ARG))
        return float((wt * d).sum() / wt.sum())

    # Monotonic in theta (derivative = variance of d under the tilted
    # weights, always >= 0), so a simple exponential bracket expansion from
    # 0 always finds a valid [lo, hi] straddling clamped_target.
    if clamped_target > old_mean:
        lo, hi = 0.0, BRACKET_SEED
        while weighted_mean_at(hi) < clamped_target and hi < theta_cap:
            hi = min(hi * BRACKET_EXPAND_FACTOR, theta_cap)
    else:
        lo, hi = -BRACKET_SEED, 0.0
        while weighted_mean_at(lo) > clamped_target and lo > -theta_cap:
            lo = max(lo * BRACKET_EXPAND_FACTOR, -theta_cap)

    theta = 0.0
    converged = False
    for _ in range(MAX_BISECTION_ITER):
        theta = (lo + hi) / 2.0
        m = weighted_mean_at(theta)
        if abs(m - clamped_target) < THETA_TOL_MILES:
            converged = True
            break
        if m < clamped_target:
            lo = theta
        else:
            hi = theta

    status = "ok"
    if was_clamped:
        status = "clamped"
    if not converged:
        status = "not_converged"
    return theta, status


def shift_core(core: np.ndarray, distance: np.ndarray, pct: float,
                sentinel: float = SKIM_NOACCESS_SENTINEL) -> tuple:
    """Shifts every origin row's weighted-mean distance by pct, by
    reweighting each row's existing nonzero, connected destinations via an
    exponential tilt (see solve_row_theta). Row totals (over each row's
    eligible subset) are conserved exactly."""
    adjusted = core.copy()
    num_zones = core.shape[0]
    counts = {"ok": 0, "zero_trips": 0, "single_destination_unreachable": 0,
              "clamped": 0, "not_converged": 0}
    total_moved = 0.0

    for i in range(num_zones):
        trips_row = core[i, :]
        dist_row = distance[i, :]
        theta, status = solve_row_theta(trips_row, dist_row, pct, sentinel)
        counts[status] = counts.get(status, 0) + 1
        if theta is None:
            continue

        eligible = (trips_row > 0) & (dist_row < sentinel)
        d = dist_row[eligible]
        w = trips_row[eligible]
        if theta == 0.0:
            continue  # true no-op for this row (pct == 0, or an already-clamped edge)

        old_mean = float((w * d).sum() / w.sum())
        wt = w * np.exp(np.clip(theta * (d - old_mean), -MAX_EXP_ARG, MAX_EXP_ARG))
        wt *= w.sum() / wt.sum()  # rescale to conserve this row's eligible subtotal exactly
        adjusted[i, eligible] = wt
        total_moved += float(np.abs(wt - w).sum()) / 2.0

    original_row_sums = core.sum(axis=1)
    adjusted_row_sums = adjusted.sum(axis=1)
    if not np.allclose(original_row_sums, adjusted_row_sums, atol=1e-6):
        raise AssertionError("Row totals were not conserved during trip-length shift")

    summary = {
        **counts,
        "total_trips_reallocated": total_moved,
        "total_trips_before": float(core.sum()),
        "total_trips_after": float(adjusted.sum()),
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
    pct = float(variables.get("hbw_trip_length_shift_pct", 0))

    # Signed target -- 0 is the only no-op value. Do NOT use `pct <= 0`
    # here (see module docstring): that would silently no-op every
    # shortening scenario.
    if pct == 0:
        print(
            f"{args.scenario_id}: hbw_trip_length_shift_pct=0 -- "
            "no trip-length shift requested, leaving matrices unchanged."
        )
        sys.exit(0)

    work_dir = args.numveh_mtx.parent

    print(f"Converting {args.numveh_mtx.name} to OMX...")
    numveh_omx_in = work_dir / f"{args.numveh_mtx.stem}_shiftlength_in.omx"
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
    skim_omx = work_dir / f"{args.skim_mtx.stem}_shiftlength_skim.omx"
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

    print(
        f"{args.scenario_id}: shifting every origin's mean HBW trip length by "
        f"{pct:+.0%}, reweighting each origin's existing destination pattern."
    )

    adjusted_cores = {}
    core_summaries = {}
    for core_name in VEHICLE_CORES:
        adjusted, summary = shift_core(cores[core_name], distance, pct)
        adjusted_cores[core_name] = adjusted
        cores[core_name] = adjusted
        core_summaries[core_name] = summary
        print(
            f"  {core_name}: ok: {summary['ok']}, zero_trips: {summary['zero_trips']}, "
            f"single_destination_unreachable: {summary['single_destination_unreachable']}, "
            f"clamped: {summary['clamped']}, not_converged: {summary['not_converged']}, "
            f"trips reallocated: {summary['total_trips_reallocated']:.1f}"
        )

    print(f"Converting adjusted matrix back to {args.numveh_mtx.name}...")
    numveh_omx_out = work_dir / f"{args.numveh_mtx.stem}_shiftlength_out.omx"
    with omx.open_file(numveh_omx_out, "w") as f_out:
        for name, data in cores.items():
            f_out[name] = data
    convert_omx_to_mtx(numveh_omx_out, args.numveh_mtx)

    hbw_total_adjusted = sum(adjusted_cores[c] for c in VEHICLE_CORES)

    # Sync pa_AllPurp.2.DestChoice.mtx's aggregate "HBW" core (reporting only --
    # nothing downstream of 07_HBW_dest_choice.s reads this file's HBW core back
    # into the model; see module docstring).
    dc_work_dir = args.destchoice_mtx.parent
    dc_input_omx = dc_work_dir / f"{args.destchoice_mtx.stem}_shiftlength_in.omx"
    dc_output_omx = dc_work_dir / f"{args.destchoice_mtx.stem}_shiftlength_out.omx"
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

    total_reallocated = sum(s["total_trips_reallocated"] for s in core_summaries.values())
    print(f"{args.scenario_id}: done. total HBW trips reallocated across all vehicle segments: {total_reallocated:.1f}")


if __name__ == "__main__":
    main()
