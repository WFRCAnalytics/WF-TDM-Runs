"""Shared data-loading and aggregation logic for reports/run_sets/
shorten-lengthen-all-work-trips's summary.qmd and slides.qmd.

Retirement-aware at the leaf loaders only (load_trips, load_shares,
load_segid, load_taz_metrics, load_transit_route, load_hh): each prefers a
frozen snapshot (written by `tdmruns snapshot-run-set`, read via
report_data.is_retired()) once one exists, falling back to a live read from
whatever `tdmruns run-scenario`/`import-manual-run` most recently curated
under runs/. Everything above that -- aggregation, deltas, chart-ready
tables -- is unchanged business logic shared by both the live and retired
cases.

Mirrors shorten-longest-commutes/report_loader.py's structure and most of
its build_* functions verbatim (same TDM version/network, same curated
output shapes) -- but this run set's shift_pct is SIGNED (-10/-5/0/5/10),
spans every origin's trips (not a selected percentile subset), and has no
"portion of trips redistributed" concept, so compute_target_shift_diagnostics()
replaces compute_region_wide_shift_trips(): it re-runs the actual per-row
tilt algorithm (scripts/shift_hbw_trip_length.py) against curated baseline
data as a "did the mechanism do roughly what it claims" sanity check, rather
than reporting a volume moved.

load() discovers which scenarios actually have a curated run and builds
every table from just those -- so this module works unmodified if the
scenario set ever changes; nothing here needs to change beyond adding a
scenario's row to SCENARIO_META.
"""
import os
import sys

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.join(_HERE, "..", "..")
sys.path.insert(0, os.path.join(REPO_ROOT, "reports"))
import report_data as rd  # noqa: E402

sys.path.insert(0, os.path.join(_HERE, "scripts"))
import shift_hbw_trip_length as algo  # noqa: E402

RUN_SET_ID = "shorten-lengthen-all-work-trips"

# scenario_id -> signed shift level, per run_set.yaml's scenario design (a
# no-shift baseline plus a symmetric -10%/-5%/+5%/+10% per-origin
# trip-length shift).
SCENARIO_META = pd.DataFrame([
    {"scenario_id": "ShiftM10", "shift_pct": -10},
    {"scenario_id": "ShiftM05", "shift_pct":  -5},
    {"scenario_id": "Shift00",  "shift_pct":   0},
    {"scenario_id": "ShiftP05", "shift_pct":   5},
    {"scenario_id": "ShiftP10", "shift_pct":  10},
])
BASELINE_SCENARIO = "Shift00"

CORRIDOR_CROSSWALK_CSV = os.path.join(_HERE, "inputs", "corridor_segid_crosswalk.csv")

# Curated filenames actually written by outputs.py -- column-filtered entries
# get a "_filtered" suffix (see run_set.yaml's outputs.include), plain-copy
# entries keep their original name. Identical to the companion run sets --
# same run_set.yaml outputs.include, same TDM version.
_SUFFIX_TRIPS = "_ZoneSummary_TripsByMode_filtered.csv"
_SUFFIX_SHARES = "Shares_Summary_long.csv"
_SUFFIX_SEGID = "Summary_SEGID_filtered.csv"
_SUFFIX_TAZ_METRICS = "TAZ-Based Metrics_filtered.csv"
_SUFFIX_TRANSIT_ROUTE = "_transit_brding_summary_route.csv"
_SUFFIX_SE_FILE = "SE_File.dbf"

# HBW_trips_allsegs_*.mtx's "motor"/"nonmotor" tables are stored at 100x
# scale -- see bring-work-trips-closer-to-home/report_loader.py's own
# HBW_MATRIX_SCALE docstring for the empirical confirmation; same TDM
# version, same Cube Voyager fixed-point convention.
HBW_MATRIX_SCALE = 100

# Cube's NOACCESS sentinel for unconnected zone pairs -- matches
# scripts/shift_hbw_trip_length.py's own SKIM_NOACCESS_SENTINEL, excluded
# from the trip-length distribution and the target-shift diagnostic so a
# handful of technically-unconnected cells can't distort either.
SKIM_NOACCESS_SENTINEL = 9999

DISTANCE_BIN_EDGES = list(range(0, 52, 2)) + [float("inf")]
DISTANCE_BIN_LABELS = [f"{e}-{e + 2} mi" for e in range(0, 50, 2)] + ["50+ mi"]

# Named routes -- see bring-work-trips-closer-to-home/report_loader.py's own
# docstring for the RAIL_MODES/BUS_LABEL rollup rationale.
TRANSIT_ROUTE_LABELS = {
    "Blue": "TRAX Blue Line",
    "Green": "TRAX Green Line",
    "Red": "TRAX Red Line",
    "RCRT_OGPN": "FrontRunner",
}
RAIL_MODES = {7, 8}
BUS_LABEL = "Bus (all non-rail)"

# Manual corridor orientation/freeway classification -- identical to the
# companion run sets' own (same network, same TDM version); see those
# modules' docstrings for the full rationale.
CORRIDOR_ORIENTATION = {
    "I-15": "N/S", "Redwood Road": "N/S", "State Street": "N/S",
    "Legacy Parkway": "N/S", "Mountain View Corridor": "N/S",
    "Bangerter Highway": "N/S", "US-89 (north Davis)": "N/S",
    "I-80": "E/W", "SR-201": "E/W", "West Davis Corridor": "E/W",
    "5600 South": "E/W", "Antelope Dr": "E/W", "3300 South": "E/W",
    "9000 South": "E/W", "12300 South": "E/W", "Porter Rockwell": "E/W",
    "2100 N Lehi": "E/W", "SR-73": "E/W", "University Pkwy": "E/W",
    "I-215": "Loop",
}
FREEWAY_CORRIDORS = {
    "I-15", "I-80", "I-215", "US-89 (north Davis)", "Legacy Parkway",
    "Mountain View Corridor", "Bangerter Highway", "SR-201", "West Davis Corridor",
}

# Peak = the two commute peaks (AM+PM); Off-Peak = midday + evening/night
# (MD+EV); Daily = all four sub-periods -- see bring-work-trips-closer-to
# -home/report_loader.py's own docstring for the WFRC 4-period convention.
PERIOD_GROUPS = {"Peak": ["AM", "PM"], "Off-Peak": ["MD", "EV"], "Daily": ["AM", "MD", "PM", "EV"]}
PERIOD_ORDER = list(PERIOD_GROUPS.keys())
PEAK_PERIODS = PERIOD_GROUPS["Peak"]


def _latest_runs() -> dict:
    return {r["scenario_id"]: r for r in rd.latest_run_per_scenario(RUN_SET_ID)}


def available_scenario_ids() -> list:
    """Scenario ids that actually have a curated run right now, in
    SCENARIO_META's declared order."""
    have_runs = set(_latest_runs())
    return [s for s in SCENARIO_META["scenario_id"] if s in have_runs]


def _curated_path(scenario_id: str, suffix: str) -> str:
    run = _latest_runs().get(scenario_id)
    if run is None:
        raise FileNotFoundError(
            f"No recorded run found for {RUN_SET_ID}/{scenario_id} -- run "
            f"`tdmruns run-scenario --run-set {RUN_SET_ID} --scenario {scenario_id}` "
            "(or import-manual-run for Shift00) first."
        )
    matches = [p for p in rd.curated_output_paths(run) if p.endswith(suffix)]
    if not matches:
        raise FileNotFoundError(
            f"Run {run['run_id']} for {RUN_SET_ID}/{scenario_id} has no curated "
            f"output ending in '{suffix}'."
        )
    return os.path.join(REPO_ROOT, matches[0])


def _snapshot_path(name: str):
    return rd.snapshot_dir(RUN_SET_ID) / name


def load_trips_from_runs(scenario_id: str) -> pd.DataFrame:
    df = pd.read_csv(_curated_path(scenario_id, _SUFFIX_TRIPS))
    df["TAZID"] = df["TAZID"].astype(int)
    df["scenario_id"] = scenario_id
    return df


def load_trips(scenario_id: str) -> pd.DataFrame:
    if rd.is_retired(RUN_SET_ID):
        return pd.read_csv(_snapshot_path(f"{scenario_id}_trips.csv"))
    return load_trips_from_runs(scenario_id)


def load_shares_from_runs(scenario_id: str) -> pd.DataFrame:
    df = pd.read_csv(_curated_path(scenario_id, _SUFFIX_SHARES))
    df["scenario_id"] = scenario_id
    return df


def load_shares(scenario_id: str) -> pd.DataFrame:
    if rd.is_retired(RUN_SET_ID):
        return pd.read_csv(_snapshot_path(f"{scenario_id}_shares.csv"))
    return load_shares_from_runs(scenario_id)


def load_segid_from_runs(scenario_id: str) -> pd.DataFrame:
    df = pd.read_csv(_curated_path(scenario_id, _SUFFIX_SEGID), dtype={"SEGID": str})
    df["scenario_id"] = scenario_id
    return df


def load_segid(scenario_id: str) -> pd.DataFrame:
    if rd.is_retired(RUN_SET_ID):
        return pd.read_csv(_snapshot_path(f"{scenario_id}_segid.csv"), dtype={"SEGID": str})
    return load_segid_from_runs(scenario_id)


def load_taz_metrics_from_runs(scenario_id: str) -> pd.DataFrame:
    df = pd.read_csv(_curated_path(scenario_id, _SUFFIX_TAZ_METRICS))
    df["TAZID"] = df["TAZID"].astype(int)
    df["scenario_id"] = scenario_id
    return df


def load_taz_metrics(scenario_id: str) -> pd.DataFrame:
    if rd.is_retired(RUN_SET_ID):
        return pd.read_csv(_snapshot_path(f"{scenario_id}_taz_metrics.csv"))
    return load_taz_metrics_from_runs(scenario_id)


def load_transit_route_from_runs(scenario_id: str) -> pd.DataFrame:
    df = pd.read_csv(_curated_path(scenario_id, _SUFFIX_TRANSIT_ROUTE))
    df["scenario_id"] = scenario_id
    return df


def load_transit_route(scenario_id: str) -> pd.DataFrame:
    if rd.is_retired(RUN_SET_ID):
        return pd.read_csv(_snapshot_path(f"{scenario_id}_transit_route.csv"))
    return load_transit_route_from_runs(scenario_id)


def load_hh_from_runs() -> pd.DataFrame:
    """Household counts by county, from the baseline scenario's SE_File
    only -- land use is identical across every scenario in this run set (only
    HBW trip destinations move), so there's no per-scenario version to load."""
    import geopandas as gpd
    gdf = gpd.read_file(_curated_path(BASELINE_SCENARIO, _SUFFIX_SE_FILE))
    out = pd.DataFrame(gdf[["Z", "CO_FIPS", "CO_NAME", "TOTHH"]])
    out = out.rename(columns={"Z": "TAZID"})
    out["TAZID"] = out["TAZID"].astype(int)
    out["CO_FIPS"] = out["CO_FIPS"].astype(int)
    out["CO_NAME"] = out["CO_NAME"].str.title()
    out["TOTHH"] = out["TOTHH"].astype(float)
    return out


def load_hh() -> pd.DataFrame:
    if rd.is_retired(RUN_SET_ID):
        return pd.read_csv(_snapshot_path("hh_by_taz.csv"))
    return load_hh_from_runs()


def load_corridor_crosswalk() -> pd.DataFrame:
    return pd.read_csv(CORRIDOR_CROSSWALK_CSV, dtype={"SEGID": str})


# 5_AssignHwy/5_FinalNetSkims/*Skm_<sub_period>.mtx, one file per
# final-assignment time period, each carrying a GP_Dist table.
_SUFFIX_SKIM_SUB_PERIOD = {"AM": "Skm_AM.omx", "MD": "Skm_MD.omx", "PM": "Skm_PM.omx", "EV": "Skm_EV.omx"}

# 4_ModeChoice/2_DetailedTripMatrices/*HBW_trips_allsegs_<Pk|Ok>.mtx -- HBW
# trips are only ever split this coarsely (Peak/Off-Peak).
_SUFFIX_HBW_MATRIX_PERIOD = {"Peak": "HBW_trips_allsegs_Pk.omx", "Off-Peak": "HBW_trips_allsegs_Ok.omx"}


def load_distance_skim_sub_period_from_runs(scenario_id: str, sub_period: str) -> np.ndarray:
    """Full TAZ x TAZ GP_Dist array for one of the 4 final-skim time periods
    (sub_period in "AM"/"MD"/"PM"/"EV")."""
    import openmatrix as omx
    f = omx.open_file(_curated_path(scenario_id, _SUFFIX_SKIM_SUB_PERIOD[sub_period]), "r")
    try:
        return np.array(f["GP_Dist"])
    finally:
        f.close()


def load_distance_skim_for_period_from_runs(scenario_id: str, period: str) -> np.ndarray:
    """Peak (AM+PM) or Off-Peak (MD+EV) distance skim -- an unweighted
    average of its two constituent sub-periods' GP_Dist arrays. See
    bring-work-trips-closer-to-home/report_loader.py's own docstring for
    why this is a reasonable simplification (GP_Dist barely varies by
    period)."""
    parts = [load_distance_skim_sub_period_from_runs(scenario_id, p) for p in PERIOD_GROUPS[period]]
    return np.mean(parts, axis=0)


def load_distance_skim_for_period(scenario_id: str, period: str) -> np.ndarray:
    if rd.is_retired(RUN_SET_ID):
        return np.load(_snapshot_path(f"{scenario_id}_gp_dist_{period}.npy"))
    return load_distance_skim_for_period_from_runs(scenario_id, period)


def load_hbw_trip_matrix_for_period_from_runs(scenario_id: str, period: str) -> np.ndarray:
    """Full TAZ x TAZ HBW trip-volume array for Peak, Off-Peak, or Daily,
    from the curated two-tab OMX, scaled down by HBW_MATRIX_SCALE. Daily is
    built as Peak + Off-Peak's sum -- no separate all-day OMX is curated."""
    if period == "Daily":
        return sum(load_hbw_trip_matrix_for_period_from_runs(scenario_id, p) for p in ("Peak", "Off-Peak"))
    import openmatrix as omx
    f = omx.open_file(_curated_path(scenario_id, _SUFFIX_HBW_MATRIX_PERIOD[period]), "r")
    try:
        motor = np.array(f["motor"])
        nonmotor = np.array(f["nonmotor"])
    finally:
        f.close()
    return (motor + nonmotor) / HBW_MATRIX_SCALE


def load_hbw_trip_matrix_for_period(scenario_id: str, period: str) -> np.ndarray:
    if rd.is_retired(RUN_SET_ID):
        return np.load(_snapshot_path(f"{scenario_id}_hbw_matrix_{period}.npy"))
    return load_hbw_trip_matrix_for_period_from_runs(scenario_id, period)


def compute_target_shift_diagnostics(shift_pct: float) -> dict:
    """Reproduces scripts/shift_hbw_trip_length.py's own per-row tilt
    algorithm against the curated baseline HBW trip matrix (Daily =
    Peak+Off-Peak) and Peak distance skim -- a report-side "did the
    mechanism do roughly what it claims" check, not a read of the actual
    run's own console output (the shift script's print()s go to Cube's own
    console window, not to anything committed -- see CLAUDE.md).

    Uses the curated Peak-period distance skim (average of the AM/PM final
    assignment skims' GP_Dist) as a stand-in for the real shift step's
    actual basis (skm_auto_Pk.mtx's dist_GP, a pre-mode-choice highway skim
    that isn't curated into runs/ -- only the post-assignment final skims
    are). Both should be close: GP_Dist is a largely static network-distance
    attribute along whichever path was assigned, not something that moves
    much between the pre-mode-choice and post-assignment network states
    (same simplification bring-work-trips-closer-to-home/report_loader.py's
    own distance-skim docstring already documents, confirmed there to
    differ by well under 1% across periods). Treat this as an
    order-of-magnitude check that the algorithm behaved sensibly on real
    data, not an exact replay of what happened inside the model run.

    shift_pct here is a whole-number percent (e.g. -10, 10), matching
    SCENARIO_META's convention -- converted to the algorithm's own fraction
    convention (e.g. -0.10) before calling shift_core.
    """
    combined = load_hbw_trip_matrix_for_period(BASELINE_SCENARIO, "Daily")
    distance = load_distance_skim_for_period(BASELINE_SCENARIO, "Peak")

    valid = (combined > 0) & (distance < SKIM_NOACCESS_SENTINEL)
    baseline_mean = float((combined[valid] * distance[valid]).sum() / combined[valid].sum())

    pct = shift_pct / 100
    adjusted, summary = algo.shift_core(combined, distance, pct)
    achieved_mean = float((adjusted[valid] * distance[valid]).sum() / combined[valid].sum())

    return {
        "shift_pct": shift_pct,
        "baseline_mean_distance": baseline_mean,
        "achieved_mean_distance": achieved_mean,
        "achieved_shift_pct": (achieved_mean - baseline_mean) / baseline_mean * 100,
        "total_trips_reallocated": summary["total_trips_reallocated"],
        "rows_ok": summary["ok"],
        "rows_zero_trips": summary["zero_trips"],
        "rows_single_destination": summary["single_destination_unreachable"],
        "rows_clamped": summary["clamped"],
        "rows_not_converged": summary["not_converged"],
    }


def build_hbw_trip_length_distribution(scenario_ids: list) -> dict:
    """Trip-volume-weighted HBW trip-length frequency distribution, one
    curve per scenario x period (Peak/Off-Peak), plus a weighted-average
    trip length per scenario x period. See bring-work-trips-closer-to-home/
    report_loader.py's own docstring for the full methodology (identical
    here -- same curated matrix/skim shapes, same NOACCESS exclusion, same
    2-mile bins). The single most direct visual confirmation that this run
    set's mechanism (shift every origin's own average commute length by a
    fixed percentage) actually did what it was built to do."""
    required_suffixes = [*_SUFFIX_SKIM_SUB_PERIOD.values(), *_SUFFIX_HBW_MATRIX_PERIOD.values()]
    have_matrices = []
    for scenario_id in scenario_ids:
        run = _latest_runs().get(scenario_id)
        paths = rd.curated_output_paths(run) if run else []
        if all(any(p.endswith(suffix) for p in paths) for suffix in required_suffixes):
            have_matrices.append(scenario_id)

    dist_rows = []
    avg_rows = []
    for scenario_id in have_matrices:
        for period in PERIOD_GROUPS:
            dist = load_distance_skim_for_period(scenario_id, period)
            trips = load_hbw_trip_matrix_for_period(scenario_id, period)

            valid = dist < SKIM_NOACCESS_SENTINEL
            flat_dist = dist[valid]
            flat_trips = trips[valid]
            total_trips = flat_trips.sum()

            bin_trips, _ = np.histogram(flat_dist, bins=DISTANCE_BIN_EDGES, weights=flat_trips)
            for label, t in zip(DISTANCE_BIN_LABELS, bin_trips):
                dist_rows.append({
                    "scenario_id": scenario_id, "bin_label": label, "period": period, "trips": t,
                    "share_pct": (t / total_trips * 100) if total_trips else float("nan"),
                })

            weighted_avg = (flat_dist * flat_trips).sum() / total_trips if total_trips else float("nan")
            avg_rows.append({"scenario_id": scenario_id, "period": period, "weighted_avg_trip_length": weighted_avg})

    distribution = _add_delta(_with_meta(pd.DataFrame(dist_rows)), ["bin_label", "period"], ["trips", "share_pct"])
    average = _add_delta(_with_meta(pd.DataFrame(avg_rows)), ["period"], ["weighted_avg_trip_length"])
    return {"distribution": distribution, "average": average}


def _with_meta(df: pd.DataFrame) -> pd.DataFrame:
    return df.merge(SCENARIO_META, on="scenario_id")


def _add_period_dim(df: pd.DataFrame, group_cols: list, metric_cols: dict) -> pd.DataFrame:
    """Expands one row per group_cols into two rows per group -- one per
    PERIOD_GROUPS key -- adding a "period" column. See bring-work-trips
    -closer-to-home/report_loader.py's own docstring for the full
    rationale (identical here)."""
    frames = []
    for period, periods in PERIOD_GROUPS.items():
        sub = df[group_cols].copy()
        sub["period"] = period
        for out_col, metric in metric_cols.items():
            sub[out_col] = df[[f"{p}_{metric}" for p in periods]].sum(axis=1)
        frames.append(sub)
    return pd.concat(frames, ignore_index=True)


def _add_delta(df: pd.DataFrame, group_cols: list, value_cols: list) -> pd.DataFrame:
    """Adds delta_<col> = <col> - baseline's <col>, matched on group_cols
    (excluding scenario_id/shift_pct, which differ from the baseline row by
    definition)."""
    join_cols = [c for c in group_cols if c not in ("scenario_id", "shift_pct")]
    base = df[df["scenario_id"] == BASELINE_SCENARIO][join_cols + value_cols].rename(
        columns={c: f"base_{c}" for c in value_cols}
    )
    merged = df.merge(base, on=join_cols, how="left") if join_cols else df.assign(
        **{f"base_{c}": df.loc[df["scenario_id"] == BASELINE_SCENARIO, c].iloc[0] for c in value_cols}
    )
    for c in value_cols:
        merged[f"delta_{c}"] = merged[c] - merged[f"base_{c}"]
    return merged


def build_county_hh(hh_df: pd.DataFrame) -> pd.DataFrame:
    """Households by county + region total -- used to normalize VHT/HH."""
    by_county = hh_df.groupby(["CO_FIPS", "CO_NAME"], as_index=False)["TOTHH"].sum()
    region = pd.DataFrame([{"CO_FIPS": -1, "CO_NAME": "Region", "TOTHH": hh_df["TOTHH"].sum()}])
    return pd.concat([by_county, region], ignore_index=True)


def build_corridor_volumes(segid_df: pd.DataFrame, crosswalk: pd.DataFrame) -> pd.DataFrame:
    """Volume/VMT/VHD by named corridor and scenario, region-wide. Adds a
    "period" column (Peak=AM+PM / Off-Peak=MD+EV) for a Peak/Off-Peak chart
    toggle -- DY_Vol/DY_VMT/DY_VHD keep their original names but now hold
    period-specific sums, not true daily ones; see _add_period_dim."""
    merged = segid_df.merge(crosswalk[["SEGID", "corridor_label"]], on="SEGID", how="inner")
    period_agg_cols = {f"{p}_{m}": (f"{p}_{m}", "sum") for p in ("AM", "MD", "PM", "EV") for m in ("Vol", "VMT", "VHD")}
    agg = merged.groupby(["scenario_id", "corridor_label"], as_index=False).agg(**period_agg_cols)
    agg = _add_period_dim(agg, ["scenario_id", "corridor_label"], {"DY_Vol": "Vol", "DY_VMT": "VMT", "DY_VHD": "VHD"})
    agg = _with_meta(agg)
    return _add_delta(agg, ["corridor_label", "period"], ["DY_Vol", "DY_VMT", "DY_VHD"])


def build_freeway_corridors_by_county(segid_df: pd.DataFrame, crosswalk: pd.DataFrame, hh_df: pd.DataFrame) -> pd.DataFrame:
    """Volume/VMT/VHD for the named freeway/expressway corridors
    (FREEWAY_CORRIDORS), broken out by the county each segment actually
    sits in. Adds a "period" column, see build_corridor_volumes."""
    fips_to_name = hh_df[["CO_FIPS", "CO_NAME"]].drop_duplicates().set_index("CO_FIPS")["CO_NAME"]
    merged = segid_df.merge(crosswalk[["SEGID", "corridor_label"]], on="SEGID", how="inner")
    merged = merged[merged["corridor_label"].isin(FREEWAY_CORRIDORS)].copy()
    merged["CO_NAME"] = merged["CO_FIPS"].map(fips_to_name)
    period_agg_cols = {f"{p}_{m}": (f"{p}_{m}", "sum") for p in ("AM", "MD", "PM", "EV") for m in ("Vol", "VMT", "VHD")}
    agg = merged.groupby(["scenario_id", "corridor_label", "CO_NAME"], as_index=False).agg(**period_agg_cols)
    agg = _add_period_dim(agg, ["scenario_id", "corridor_label", "CO_NAME"], {"DY_Vol": "Vol", "DY_VMT": "VMT", "DY_VHD": "VHD"})
    agg = _with_meta(agg)
    return _add_delta(agg, ["corridor_label", "CO_NAME", "period"], ["DY_Vol", "DY_VMT", "DY_VHD"])


def build_corridor_orientation_summary(segid_df: pd.DataFrame, crosswalk: pd.DataFrame) -> pd.DataFrame:
    """VMT/VHD summed across all named corridors sharing the same
    predominant orientation. Adds a "period" column, see
    build_corridor_volumes."""
    merged = segid_df.merge(crosswalk[["SEGID", "corridor_label"]], on="SEGID", how="inner")
    merged["orientation"] = merged["corridor_label"].map(CORRIDOR_ORIENTATION)
    period_agg_cols = {f"{p}_{m}": (f"{p}_{m}", "sum") for p in ("AM", "MD", "PM", "EV") for m in ("Vol", "VMT", "VHD")}
    agg = merged.groupby(["scenario_id", "orientation"], as_index=False).agg(**period_agg_cols)
    agg = _add_period_dim(agg, ["scenario_id", "orientation"], {"DY_Vol": "Vol", "DY_VMT": "VMT", "DY_VHD": "VHD"})
    agg = _with_meta(agg)
    return _add_delta(agg, ["orientation", "period"], ["DY_Vol", "DY_VMT", "DY_VHD"])


def build_vmt_vhd_by_county_facility(segid_df: pd.DataFrame, hh_df: pd.DataFrame) -> pd.DataFrame:
    """VMT/VHD by county + facility type, plus a Region row per facility
    type. Excludes FTCLASS == "Local". Adds a "period" column, see
    build_corridor_volumes."""
    fips_to_name = hh_df[["CO_FIPS", "CO_NAME"]].drop_duplicates().set_index("CO_FIPS")["CO_NAME"]
    df = segid_df[segid_df["FTCLASS"] != "Local"].copy()
    df["CO_NAME"] = df["CO_FIPS"].map(fips_to_name)

    period_agg_cols = {f"{p}_{m}": (f"{p}_{m}", "sum") for p in ("AM", "MD", "PM", "EV") for m in ("VMT", "VHD")}
    by_county = df.groupby(["scenario_id", "CO_NAME", "FTCLASS"], as_index=False).agg(**period_agg_cols)
    region = df.groupby(["scenario_id", "FTCLASS"], as_index=False).agg(**period_agg_cols)
    region["CO_NAME"] = "Region"
    combined = pd.concat([by_county, region], ignore_index=True)
    combined = _add_period_dim(combined, ["scenario_id", "CO_NAME", "FTCLASS"], {"DY_VMT": "VMT", "DY_VHD": "VHD"})
    combined = _with_meta(combined)
    return _add_delta(combined, ["CO_NAME", "FTCLASS", "period"], ["DY_VMT", "DY_VHD"])


def build_congested_miles(segid_df: pd.DataFrame, hh_df: pd.DataFrame) -> pd.DataFrame:
    """Miles of roadway with volume/capacity (V/C) > 1.0, by county +
    facility type (plus a Region row), for Peak, Off-Peak, and Daily. See
    bring-work-trips-closer-to-home/report_loader.py's own docstring for
    the full rationale (identical here)."""
    fips_to_name = hh_df[["CO_FIPS", "CO_NAME"]].drop_duplicates().set_index("CO_FIPS")["CO_NAME"]
    df = segid_df[segid_df["FTCLASS"] != "Local"].copy()
    df["CO_NAME"] = df["CO_FIPS"].map(fips_to_name)

    period_vc = {
        "Peak": df[["AM_VC", "PM_VC"]].max(axis=1),
        "Off-Peak": df[["MD_VC", "EV_VC"]].max(axis=1),
        "Daily": df["MAX_VC"],
    }

    frames = []
    for period, vc in period_vc.items():
        sub = df[["scenario_id", "CO_NAME", "FTCLASS"]].copy()
        sub["period"] = period
        sub["congested_miles"] = df["DISTANCE"].where(vc > 1.0, 0.0)
        frames.append(sub)
    long_df = pd.concat(frames, ignore_index=True)

    by_county = long_df.groupby(["scenario_id", "CO_NAME", "FTCLASS", "period"], as_index=False)["congested_miles"].sum()
    region = long_df.groupby(["scenario_id", "FTCLASS", "period"], as_index=False)["congested_miles"].sum()
    region["CO_NAME"] = "Region"
    combined = pd.concat([by_county, region], ignore_index=True)
    combined = _with_meta(combined)
    return _add_delta(combined, ["CO_NAME", "FTCLASS", "period"], ["congested_miles"])


def build_vht_per_household(segid_df: pd.DataFrame, hh_df: pd.DataFrame) -> pd.DataFrame:
    """Peak-period (AM+PM) VHT per household, by county + region, plus the
    Off-Peak counterpart. Adds a "period" column, see build_corridor_volumes."""
    fips_to_name = hh_df[["CO_FIPS", "CO_NAME"]].drop_duplicates().set_index("CO_FIPS")["CO_NAME"]
    df = segid_df.copy()
    df["CO_NAME"] = df["CO_FIPS"].map(fips_to_name)

    period_agg_cols = {f"{p}_VHT": (f"{p}_VHT", "sum") for p in ("AM", "MD", "PM", "EV")}
    by_county = df.groupby(["scenario_id", "CO_NAME"], as_index=False).agg(**period_agg_cols)
    region = df.groupby("scenario_id", as_index=False).agg(**period_agg_cols)
    region["CO_NAME"] = "Region"
    combined = pd.concat([by_county, region], ignore_index=True)
    combined = _add_period_dim(combined, ["scenario_id", "CO_NAME"], {"VHT": "VHT"})

    hh = build_county_hh(hh_df)[["CO_NAME", "TOTHH"]]
    combined = combined.merge(hh, on="CO_NAME", how="left")
    combined["VHT_PER_HH"] = combined["VHT"] / combined["TOTHH"]
    combined = _with_meta(combined)
    return _add_delta(combined, ["CO_NAME", "period"], ["VHT", "VHT_PER_HH"])


def build_transit_ridership(route_df: pd.DataFrame) -> pd.DataFrame:
    """Daily (pk+ok) boardings for TRAX + FrontRunner plus a "Bus"
    aggregate. See bring-work-trips-closer-to-home/report_loader.py's own
    docstring for the full rationale (identical here)."""
    named = route_df[route_df["Name"].isin(TRANSIT_ROUTE_LABELS)].copy()
    named["line_label"] = named["Name"].map(TRANSIT_ROUTE_LABELS)

    bus = route_df[~route_df["Mode"].round().astype(int).isin(RAIL_MODES)].copy()
    bus["line_label"] = BUS_LABEL

    df = pd.concat([named, bus], ignore_index=True)
    agg = df.groupby(["scenario_id", "line_label"], as_index=False)["Boardings"].sum()
    agg = _with_meta(agg)
    return _add_delta(agg, ["line_label"], ["Boardings"])


# ZoneSummary_TripsByMode.csv's own Period values are already Peak/Off-Peak/
# Daily.
_TRIPS_PERIOD_LABEL = {"Peak": "Pk", "Off-Peak": "Ok", "Daily": "Dy"}


def build_hbw_trip_length(taz_metrics_df: pd.DataFrame, trips_df: pd.DataFrame, hh_df: pd.DataFrame) -> pd.DataFrame:
    """Average HBW trip length (PMT / trips) by county + region, with a
    Peak/Off-Peak/Daily "period" column. See bring-work-trips-closer-to
    -home/report_loader.py's own docstring for the full rationale
    (identical here)."""
    taz_to_county = hh_df[["TAZID", "CO_FIPS", "CO_NAME"]].drop_duplicates()

    pmt_rows = taz_metrics_df[
        (taz_metrics_df["Metric"] == "PMT") & (taz_metrics_df["Purpose"] == "HBW") & (taz_metrics_df["PA"] == "P")
    ]
    trips_rows = trips_df[(trips_df["Purpose"] == "HBW") & (trips_df["PA"] == "P")]

    frames = []
    for period, sub_periods in PERIOD_GROUPS.items():
        pmt = pmt_rows[pmt_rows["Period"].isin(sub_periods)]
        pmt_sum = pmt.groupby(["scenario_id", "TAZID"], as_index=False)["Total"].sum().rename(columns={"Total": "PMT"})

        trips = trips_rows[trips_rows["Period"] == _TRIPS_PERIOD_LABEL[period]][
            ["scenario_id", "TAZID", "All"]
        ].rename(columns={"All": "Trips"})

        df = pmt_sum.merge(trips, on=["scenario_id", "TAZID"], how="inner").merge(taz_to_county, on="TAZID", how="left")
        by_county = df.groupby(["scenario_id", "CO_NAME"], as_index=False)[["PMT", "Trips"]].sum()
        region = df.groupby("scenario_id", as_index=False)[["PMT", "Trips"]].sum()
        region["CO_NAME"] = "Region"
        period_df = pd.concat([by_county, region], ignore_index=True)
        period_df["period"] = period
        frames.append(period_df)

    combined = pd.concat(frames, ignore_index=True)
    combined["trip_length"] = combined["PMT"] / combined["Trips"]
    combined = _with_meta(combined)
    return _add_delta(combined, ["CO_NAME", "period"], ["trip_length"])


def build_mode_share(shares_df: pd.DataFrame) -> pd.DataFrame:
    """Supporting context only -- daily (pk+ok) mode share by trip purpose,
    region-wide."""
    agg = shares_df.groupby(["scenario_id", "TRIPPURP", "MODE"], as_index=False)["TRIPS"].sum()
    totals = agg.groupby(["scenario_id", "TRIPPURP"])["TRIPS"].transform("sum")
    agg["share_pct"] = agg["TRIPS"] / totals * 100
    agg = _with_meta(agg)
    return _add_delta(agg, ["TRIPPURP", "MODE"], ["TRIPS", "share_pct"])


def load() -> dict:
    """Everything summary.qmd and slides.qmd need, built from whichever
    scenarios currently have a curated run (always includes the baseline)."""
    scenario_ids = available_scenario_ids()

    trips_df = pd.concat([load_trips(s) for s in scenario_ids], ignore_index=True)
    shares_df = pd.concat([load_shares(s) for s in scenario_ids], ignore_index=True)
    segid_df = pd.concat([load_segid(s) for s in scenario_ids], ignore_index=True)
    taz_metrics_df = pd.concat([load_taz_metrics(s) for s in scenario_ids], ignore_index=True)
    transit_route_df = pd.concat([load_transit_route(s) for s in scenario_ids], ignore_index=True)
    hh_df = load_hh()
    crosswalk = load_corridor_crosswalk()
    trip_length_dist = build_hbw_trip_length_distribution(scenario_ids)

    return {
        "scenario_ids": scenario_ids,
        "scenario_meta": SCENARIO_META[SCENARIO_META["scenario_id"].isin(scenario_ids)],
        "corridor_volumes": build_corridor_volumes(segid_df, crosswalk),
        "freeway_by_county": build_freeway_corridors_by_county(segid_df, crosswalk, hh_df),
        "corridor_orientation": build_corridor_orientation_summary(segid_df, crosswalk),
        "vmt_vhd_by_county_facility": build_vmt_vhd_by_county_facility(segid_df, hh_df),
        "congested_miles": build_congested_miles(segid_df, hh_df),
        "vht_per_household": build_vht_per_household(segid_df, hh_df),
        "transit_ridership": build_transit_ridership(transit_route_df),
        "hbw_trip_length": build_hbw_trip_length(taz_metrics_df, trips_df, hh_df),
        "hbw_trip_length_distribution": trip_length_dist["distribution"],
        "hbw_trip_length_weighted_average": trip_length_dist["average"],
        "mode_share": build_mode_share(shares_df),
    }
