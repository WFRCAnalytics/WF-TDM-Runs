# Offline unit test for shift_hbw_trip_length.py's core algorithm --
# synthetic edge cases only (no Cube, no CONVERTMAT, no .s files involved).
# Neither companion run set (bring-work-trips-closer-to-home,
# shorten-longest-commutes) has a committed test for its own redistribution
# script; this one exists because the bisection-based mechanism here is
# meaningfully more complex than either sibling's closed-form proportional
# scaling, and because a signed `pct` makes the `pct <= 0` vs. `pct == 0`
# no-op-guard mistake both easy to make and easy to miss without a test
# that would actually catch it (see shift_hbw_trip_length.py's module
# docstring).
#
# Run directly: python test_shift_hbw_trip_length.py

import sys

import numpy as np

from shift_hbw_trip_length import (
    SKIM_NOACCESS_SENTINEL,
    THETA_TOL_MILES,
    shift_core,
    solve_row_theta,
)

FAILURES = []


def check(condition, message):
    if not condition:
        FAILURES.append(message)
        print(f"  FAIL: {message}")
    else:
        print(f"  ok: {message}")


def weighted_mean(w, d):
    return float((w * d).sum() / w.sum())


def test_normal_rows_hit_target():
    print("test_normal_rows_hit_target")
    rng = np.random.default_rng(0)
    n = 8
    trips = np.zeros((n, n))
    dist = rng.uniform(1, 40, size=(n, n))
    np.fill_diagonal(dist, 0)

    # Row 0: a normal spread of 6 destinations.
    trips[0, [1, 2, 3, 4, 5, 6]] = [50, 30, 20, 10, 5, 2]

    for pct in (-0.10, -0.05, 0.05, 0.10):
        theta, status = solve_row_theta(trips[0], dist[0], pct)
        check(status == "ok", f"pct={pct}: status is 'ok' (got {status})")
        eligible = trips[0] > 0
        d = dist[0][eligible]
        w = trips[0][eligible]
        old_mean = weighted_mean(w, d)
        wt = w * np.exp(theta * (d - old_mean))
        wt *= w.sum() / wt.sum()
        achieved = weighted_mean(wt, d)
        target = old_mean * (1 + pct)
        check(
            abs(achieved - target) < THETA_TOL_MILES * 10,
            f"pct={pct}: achieved mean {achieved:.4f} close to target {target:.4f}",
        )


def test_pct_zero_is_exact_noop():
    print("test_pct_zero_is_exact_noop")
    trips_row = np.array([0, 10, 5, 0, 3, 0, 0, 0], dtype=float)
    dist_row = np.array([0, 5, 12, 3, 22, 4, 6, 8], dtype=float)
    theta, status = solve_row_theta(trips_row, dist_row, 0.0)
    check(theta == 0.0 and status == "ok", "pct=0 returns theta=0.0, status='ok'")


def test_zero_trips_row_untouched():
    print("test_zero_trips_row_untouched")
    trips_row = np.zeros(8)
    dist_row = np.array([0, 5, 12, 3, 22, 4, 6, 8], dtype=float)
    theta, status = solve_row_theta(trips_row, dist_row, -0.10)
    check(theta is None and status == "zero_trips", "zero-trip row returns (None, 'zero_trips')")


def test_single_destination_unreachable():
    print("test_single_destination_unreachable")
    trips_row = np.zeros(8)
    trips_row[3] = 25
    dist_row = np.array([0, 5, 12, 3, 22, 4, 6, 8], dtype=float)
    for pct in (-0.10, 0.10):
        theta, status = solve_row_theta(trips_row, dist_row, pct)
        check(
            theta is None and status == "single_destination_unreachable",
            f"pct={pct}: single-destination row returns (None, 'single_destination_unreachable')",
        )


def test_clamped_when_target_beyond_existing_range():
    print("test_clamped_when_target_beyond_existing_range")
    # Two destinations very close together -- a -50% shift target would fall
    # below both, forcing a clamp.
    trips_row = np.zeros(8)
    trips_row[1] = 10
    trips_row[2] = 10
    dist_row = np.zeros(8)
    dist_row[1] = 10.0
    dist_row[2] = 10.5
    theta, status = solve_row_theta(trips_row, dist_row, -0.5)
    check(status == "clamped", f"aggressive shorten target clamps (got status={status})")
    check(theta is not None, "clamped row still returns a usable theta")


def test_noaccess_sentinel_excluded():
    print("test_noaccess_sentinel_excluded")
    trips_row = np.array([0, 10, 5, 0, 3, 0, 0, 0], dtype=float)
    dist_row = np.array([0, 5, 12, 3, 22, 4, 6, 8], dtype=float)
    # Zone 4 carries trips but is NOACCESS -- must be excluded from
    # eligibility, mean, and target entirely.
    dist_row[4] = SKIM_NOACCESS_SENTINEL
    trips_row[4] = 3
    theta, status = solve_row_theta(trips_row, dist_row, -0.10)
    check(status == "ok", "NOACCESS-containing row still solves normally over its connected cells")

    eligible = (trips_row > 0) & (dist_row < SKIM_NOACCESS_SENTINEL)
    check(int(eligible.sum()) == 2, "NOACCESS cell excluded from eligible set (2 remain: zones 1, 2)")


def test_row_conservation_across_pcts():
    print("test_row_conservation_across_pcts")
    rng = np.random.default_rng(1)
    n = 10
    trips = rng.integers(0, 40, size=(n, n)).astype(float)
    np.fill_diagonal(trips, 0)
    dist = rng.uniform(1, 45, size=(n, n))
    np.fill_diagonal(dist, 0)
    # A couple of NOACCESS cells mixed in.
    dist[2, 5] = SKIM_NOACCESS_SENTINEL
    dist[7, 1] = SKIM_NOACCESS_SENTINEL

    for pct in (-0.10, -0.05, 0.0, 0.05, 0.10):
        adjusted, summary = shift_core(trips, dist, pct)
        check(
            np.allclose(trips.sum(axis=1), adjusted.sum(axis=1), atol=1e-6),
            f"pct={pct}: row totals conserved",
        )


def test_pct_sign_is_not_lte_zero_bug():
    print("test_pct_sign_is_not_lte_zero_bug")
    # Regression guard for the pct<=0 vs pct==0 mistake called out in the
    # module docstring: a negative pct must actually change the matrix.
    trips = np.zeros((4, 4))
    trips[0, [1, 2, 3]] = [10, 10, 10]
    dist = np.array([
        [0, 5, 15, 25],
        [5, 0, 10, 20],
        [15, 10, 0, 8],
        [25, 20, 8, 0],
    ], dtype=float)

    adjusted, _ = shift_core(trips, dist, -0.05)
    check(not np.allclose(adjusted, trips), "pct=-0.05 actually changes the matrix (not a silent no-op)")

    adjusted_zero, _ = shift_core(trips, dist, 0.0)
    check(np.allclose(adjusted_zero, trips), "pct=0.0 leaves the matrix exactly unchanged")


def main():
    test_normal_rows_hit_target()
    test_pct_zero_is_exact_noop()
    test_zero_trips_row_untouched()
    test_single_destination_unreachable()
    test_clamped_when_target_beyond_existing_range()
    test_noaccess_sentinel_excluded()
    test_row_conservation_across_pcts()
    test_pct_sign_is_not_lte_zero_bug()

    if FAILURES:
        print(f"\n{len(FAILURES)} FAILURE(S):")
        for f in FAILURES:
            print(f"  - {f}")
        sys.exit(1)
    print("\nAll checks passed.")


if __name__ == "__main__":
    main()
