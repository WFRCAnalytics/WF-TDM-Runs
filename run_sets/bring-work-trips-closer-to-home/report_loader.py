"""Shared data-loading and aggregation logic for reports/run_sets/
bring-work-trips-closer-to-home's summary.qmd and slides.qmd.

Retirement-aware at the leaf loaders only (load_trips, load_shares,
load_segid, load_taz_metrics, load_transit_route, load_hh): each prefers a
frozen snapshot (written by `tdmruns snapshot-run-set`, read via
report_data.is_retired()) once one exists, falling back to a live read from
whatever `tdmruns import-manual-run` most recently curated under runs/.
Everything above that -- aggregation, deltas, chart-ready tables -- is
unchanged business logic shared by both the live and retired cases.

load() discovers which scenarios actually have a curated run and builds
every table from just those -- so this module works unmodified as more of
Closer01..Closer09 land runs; nothing here needs to change as the run set
fills in beyond adding a scenario's row to SCENARIO_META once it's designed.
"""
import os
import sys

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.join(_HERE, "..", "..")
sys.path.insert(0, os.path.join(REPO_ROOT, "reports"))
import report_data as rd  # noqa: E402

RUN_SET_ID = "bring-work-trips-closer-to-home"

# scenario_id -> geography type / shift level, per run_set.yaml's scenario
# design (3 geography types x 3 shift levels, plus a no-shift baseline).
SCENARIO_META = pd.DataFrame([
    {"scenario_id": "Closer00", "geography_label": "Baseline",         "shift_pct":  0},
    {"scenario_id": "Closer01", "geography_label": "City Area",        "shift_pct": 10},
    {"scenario_id": "Closer02", "geography_label": "Medium District",  "shift_pct": 10},
    {"scenario_id": "Closer03", "geography_label": "Workshop Area",    "shift_pct": 10},
    {"scenario_id": "Closer04", "geography_label": "City Area",        "shift_pct":  5},
    {"scenario_id": "Closer05", "geography_label": "Medium District",  "shift_pct":  5},
    {"scenario_id": "Closer06", "geography_label": "Workshop Area",    "shift_pct":  5},
    {"scenario_id": "Closer07", "geography_label": "City Area",        "shift_pct": 25},
    {"scenario_id": "Closer08", "geography_label": "Medium District",  "shift_pct": 25},
    {"scenario_id": "Closer09", "geography_label": "Workshop Area",    "shift_pct": 25},
])
BASELINE_SCENARIO = "Closer00"

# City Area leads the narrative per the scoping memo's confirmed decision
# (section 7); Medium District and Workshop Area are robustness checks.
GEO_ORDER = ["City Area", "Medium District", "Workshop Area"]

CORRIDOR_CROSSWALK_CSV = os.path.join(_HERE, "inputs", "corridor_segid_crosswalk.csv")

# Curated filenames actually written by outputs.py -- column-filtered entries
# get a "_filtered" suffix (see run_set.yaml's outputs.include), plain-copy
# entries keep their original name.
_SUFFIX_TRIPS = "_ZoneSummary_TripsByMode_filtered.csv"
_SUFFIX_SHARES = "Shares_Summary_long.csv"
_SUFFIX_SEGID = "Summary_SEGID_filtered.csv"
_SUFFIX_TAZ_METRICS = "TAZ-Based Metrics_filtered.csv"
_SUFFIX_TRANSIT_ROUTE = "_transit_brding_summary_route.csv"
_SUFFIX_SE_FILE = "SE_File.dbf"
_SUFFIX_SKIM = "Skm_DY.omx"
_SUFFIX_HBW_MATRIX = "HBW_trips_allsegs_pkok.omx"

# HBW_trips_allsegs_pkok.mtx's "motor"/"nonmotor" tables (and every other
# table in it) are stored at 100x scale -- confirmed empirically: (motor +
# nonmotor summed across the whole matrix) / 100 matches
# _ZoneSummary_TripsByMode.csv's HBW/Dy/P region total (1,879,445) within
# 0.001% (raw sum was 187,947,222). A Cube Voyager fixed-point convention
# for this mode-choice output step, confirmed with the run set's author.
HBW_MATRIX_SCALE = 100

# Cube's NOACCESS sentinel for unconnected zone pairs (see
# tdm/2_ModelScripts/5_AssignHwy/07_PerformFinalNetSkim.s's PATHLOAD
# NOACCESS=9999) -- excluded from the trip-length distribution so a handful
# of technically-unconnected cells can't masquerade as extreme-long trips.
SKIM_NOACCESS_SENTINEL = 9999

DISTANCE_BIN_EDGES = [0, 1, 2, 3, 5, 7, 10, 15, 20, 30, float("inf")]
DISTANCE_BIN_LABELS = [
    "0-1 mi", "1-2 mi", "2-3 mi", "3-5 mi", "5-7 mi", "7-10 mi",
    "10-15 mi", "15-20 mi", "20-30 mi", "30+ mi",
]

# Only routes the scoping memo asks for (TRAX lines + FrontRunner) -- the
# route file itself carries ~170 route codes, most of them local/express bus.
TRANSIT_ROUTE_LABELS = {
    "Blue": "TRAX Blue Line",
    "Green": "TRAX Green Line",
    "Red": "TRAX Red Line",
    "RCRT_OGPN": "FrontRunner",
}

# "Free time added back to households" (memo section 6) is scoped to the two
# peak periods, not the full day.
PEAK_PERIODS = ["AM", "PM"]


def _latest_runs() -> dict:
    return {r["scenario_id"]: r for r in rd.latest_run_per_scenario(RUN_SET_ID)}


def available_scenario_ids() -> list:
    """Scenario ids that actually have a curated run right now, in
    SCENARIO_META's declared order. Callers should build every table from
    just this list -- it grows on its own as more scenarios finish running,
    with no code change needed here."""
    have_runs = set(_latest_runs())
    return [s for s in SCENARIO_META["scenario_id"] if s in have_runs]


def _curated_path(scenario_id: str, suffix: str) -> str:
    run = _latest_runs().get(scenario_id)
    if run is None:
        raise FileNotFoundError(
            f"No imported run found for {RUN_SET_ID}/{scenario_id} -- run "
            f"`tdmruns import-manual-run --run-set {RUN_SET_ID} --scenario {scenario_id}` first."
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


def load_distance_skim_from_runs(scenario_id: str) -> np.ndarray:
    """Full TAZ x TAZ GP_Dist array (daily) from the curated single-tab
    skim OMX -- see run_set.yaml's matrix:/tabs: entry for how this got
    curated down from the ~400 MB source Skm_DY.mtx."""
    import openmatrix as omx
    f = omx.open_file(_curated_path(scenario_id, _SUFFIX_SKIM), "r")
    try:
        return np.array(f["GP_Dist"])
    finally:
        f.close()


def load_distance_skim(scenario_id: str) -> np.ndarray:
    if rd.is_retired(RUN_SET_ID):
        return np.load(_snapshot_path(f"{scenario_id}_gp_dist.npy"))
    return load_distance_skim_from_runs(scenario_id)


def load_hbw_trip_matrix_from_runs(scenario_id: str) -> np.ndarray:
    """Full TAZ x TAZ HBW trip-volume array (all modes, both periods
    combined), from the curated two-tab OMX ("motor" + "nonmotor" --
    together they cover every mode in HBW_trips_allsegs_pkok.mtx), scaled
    down by HBW_MATRIX_SCALE."""
    import openmatrix as omx
    f = omx.open_file(_curated_path(scenario_id, _SUFFIX_HBW_MATRIX), "r")
    try:
        motor = np.array(f["motor"])
        nonmotor = np.array(f["nonmotor"])
    finally:
        f.close()
    return (motor + nonmotor) / HBW_MATRIX_SCALE


def load_hbw_trip_matrix(scenario_id: str) -> np.ndarray:
    if rd.is_retired(RUN_SET_ID):
        return np.load(_snapshot_path(f"{scenario_id}_hbw_matrix.npy"))
    return load_hbw_trip_matrix_from_runs(scenario_id)


def build_hbw_trip_length_distribution(scenario_ids: list) -> dict:
    """Trip-volume-weighted HBW trip-length frequency distribution (O-D
    skim distance x O-D trip volume, binned), one curve per scenario, plus
    a weighted-average trip length as a cross-check against
    build_hbw_trip_length()'s independent PMT/trips-based average -- the two
    are computed from entirely different sources (full O-D skim x matrix
    here, production-side PMT/trip totals there) and should be close, not
    identical. Built region-wide only (not by county): the point of this
    view is the shape of the curve, not another county breakdown.

    Only scenarios with both curated matrix outputs are included -- silently
    skips any that haven't been backfilled yet, matching
    available_scenario_ids()'s "grows as more scenarios land" philosophy.
    NOACCESS-sentinel (9999) skim cells are excluded before binning so a
    handful of technically-unconnected zone pairs can't masquerade as
    extreme-long trips.
    """
    have_matrices = []
    for scenario_id in scenario_ids:
        run = _latest_runs().get(scenario_id)
        paths = rd.curated_output_paths(run) if run else []
        if any(p.endswith(_SUFFIX_SKIM) for p in paths) and any(
            p.endswith(_SUFFIX_HBW_MATRIX) for p in paths
        ):
            have_matrices.append(scenario_id)

    dist_rows = []
    avg_rows = []
    for scenario_id in have_matrices:
        dist = load_distance_skim(scenario_id)
        trips = load_hbw_trip_matrix(scenario_id)

        valid = dist < SKIM_NOACCESS_SENTINEL
        flat_dist = dist[valid]
        flat_trips = trips[valid]
        total_trips = flat_trips.sum()

        bin_trips, _ = np.histogram(flat_dist, bins=DISTANCE_BIN_EDGES, weights=flat_trips)
        for label, t in zip(DISTANCE_BIN_LABELS, bin_trips):
            dist_rows.append({
                "scenario_id": scenario_id, "bin_label": label, "trips": t,
                "share_pct": (t / total_trips * 100) if total_trips else float("nan"),
            })

        weighted_avg = (flat_dist * flat_trips).sum() / total_trips if total_trips else float("nan")
        avg_rows.append({"scenario_id": scenario_id, "weighted_avg_trip_length": weighted_avg})

    distribution = _add_delta(_with_meta(pd.DataFrame(dist_rows)), ["bin_label"], ["trips", "share_pct"])
    average = _add_delta(_with_meta(pd.DataFrame(avg_rows)), [], ["weighted_avg_trip_length"])
    return {"distribution": distribution, "average": average}


def _with_meta(df: pd.DataFrame) -> pd.DataFrame:
    return df.merge(SCENARIO_META, on="scenario_id")


def _add_delta(df: pd.DataFrame, group_cols: list, value_cols: list) -> pd.DataFrame:
    """Adds delta_<col> = <col> - baseline's <col>, matched on group_cols
    (excluding scenario_id/geography_label/shift_pct, which differ from the
    baseline row by definition)."""
    join_cols = [c for c in group_cols if c not in ("scenario_id", "geography_label", "shift_pct")]
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


def _segid_by_county(segid_df: pd.DataFrame) -> pd.DataFrame:
    """Summary_SEGID rows with a friendly CO_NAME joined on (from load_hh's
    CO_FIPS/CO_NAME pairs, since Summary_SEGID itself only carries CO_FIPS)."""
    return segid_df


def build_corridor_volumes(segid_df: pd.DataFrame, crosswalk: pd.DataFrame) -> pd.DataFrame:
    """Volume/VMT/VHD by named corridor and scenario -- memo section 6's
    corridor detail. Only SEGIDs matched to a named corridor are kept."""
    merged = segid_df.merge(crosswalk[["SEGID", "corridor_label"]], on="SEGID", how="inner")
    agg = merged.groupby(["scenario_id", "corridor_label"], as_index=False).agg(
        AM_Vol=("AM_Vol", "sum"), MD_Vol=("MD_Vol", "sum"), PM_Vol=("PM_Vol", "sum"),
        EV_Vol=("EV_Vol", "sum"), DY_Vol=("DY_Vol", "sum"),
        DY_VMT=("DY_VMT", "sum"), DY_VHD=("DY_VHD", "sum"),
    )
    agg = _with_meta(agg)
    return _add_delta(agg, ["corridor_label"], ["AM_Vol", "MD_Vol", "PM_Vol", "EV_Vol", "DY_Vol", "DY_VMT", "DY_VHD"])


def build_vmt_vhd_by_county_facility(segid_df: pd.DataFrame, hh_df: pd.DataFrame) -> pd.DataFrame:
    """VMT/VHD by county + facility type, plus a Region row per facility
    type -- memo section 6's headline (VHD) and explanatory (VMT) tables."""
    fips_to_name = hh_df[["CO_FIPS", "CO_NAME"]].drop_duplicates().set_index("CO_FIPS")["CO_NAME"]
    df = segid_df.copy()
    df["CO_NAME"] = df["CO_FIPS"].map(fips_to_name)

    by_county = df.groupby(["scenario_id", "CO_NAME", "FTCLASS"], as_index=False).agg(
        DY_VMT=("DY_VMT", "sum"), DY_VHD=("DY_VHD", "sum"),
    )
    region = df.groupby(["scenario_id", "FTCLASS"], as_index=False).agg(
        DY_VMT=("DY_VMT", "sum"), DY_VHD=("DY_VHD", "sum"),
    )
    region["CO_NAME"] = "Region"
    combined = pd.concat([by_county, region], ignore_index=True)
    combined = _with_meta(combined)
    return _add_delta(combined, ["CO_NAME", "FTCLASS"], ["DY_VMT", "DY_VHD"])


def build_vht_per_household(segid_df: pd.DataFrame, hh_df: pd.DataFrame) -> pd.DataFrame:
    """Peak-period (AM+PM) VHT per household, by county + region -- memo's
    'free time added back to households' metric."""
    fips_to_name = hh_df[["CO_FIPS", "CO_NAME"]].drop_duplicates().set_index("CO_FIPS")["CO_NAME"]
    df = segid_df.copy()
    df["CO_NAME"] = df["CO_FIPS"].map(fips_to_name)
    df["PEAK_VHT"] = df[[f"{p}_VHT" for p in PEAK_PERIODS]].sum(axis=1)

    by_county = df.groupby(["scenario_id", "CO_NAME"], as_index=False)["PEAK_VHT"].sum()
    region = df.groupby("scenario_id", as_index=False)["PEAK_VHT"].sum()
    region["CO_NAME"] = "Region"
    combined = pd.concat([by_county, region], ignore_index=True)

    hh = build_county_hh(hh_df)[["CO_NAME", "TOTHH"]]
    combined = combined.merge(hh, on="CO_NAME", how="left")
    combined["VHT_PER_HH"] = combined["PEAK_VHT"] / combined["TOTHH"]
    combined = _with_meta(combined)
    return _add_delta(combined, ["CO_NAME"], ["PEAK_VHT", "VHT_PER_HH"])


def build_transit_ridership(route_df: pd.DataFrame) -> pd.DataFrame:
    """Daily (pk+ok) boardings for TRAX + FrontRunner -- memo's transit
    ridership deliverable."""
    df = route_df[route_df["Name"].isin(TRANSIT_ROUTE_LABELS)].copy()
    df["line_label"] = df["Name"].map(TRANSIT_ROUTE_LABELS)
    agg = df.groupby(["scenario_id", "line_label"], as_index=False)["Boardings"].sum()
    agg = _with_meta(agg)
    return _add_delta(agg, ["line_label"], ["Boardings"])


def build_hbw_trip_length(taz_metrics_df: pd.DataFrame, trips_df: pd.DataFrame, hh_df: pd.DataFrame) -> pd.DataFrame:
    """Average HBW trip length (PMT / trips) by county + region -- joins
    TAZ-Based Metrics' person-miles (4-period AM/MD/PM/EV, summed to a daily
    total) against ZoneSummary's daily HBW production trips. TAZID->county
    comes from load_hh's SE_File read (same TAZ/county assignment used for
    the household normalization), not from either metrics file directly."""
    taz_to_county = hh_df[["TAZID", "CO_FIPS", "CO_NAME"]].drop_duplicates()

    pmt = taz_metrics_df[
        (taz_metrics_df["Metric"] == "PMT") & (taz_metrics_df["Purpose"] == "HBW") & (taz_metrics_df["PA"] == "P")
    ]
    pmt_daily = pmt.groupby(["scenario_id", "TAZID"], as_index=False)["Total"].sum().rename(columns={"Total": "PMT"})

    trips = trips_df[
        (trips_df["Purpose"] == "HBW") & (trips_df["Period"] == "Dy") & (trips_df["PA"] == "P")
    ][["scenario_id", "TAZID", "All"]].rename(columns={"All": "Trips"})

    df = pmt_daily.merge(trips, on=["scenario_id", "TAZID"], how="inner").merge(taz_to_county, on="TAZID", how="left")

    by_county = df.groupby(["scenario_id", "CO_NAME"], as_index=False)[["PMT", "Trips"]].sum()
    region = df.groupby("scenario_id", as_index=False)[["PMT", "Trips"]].sum()
    region["CO_NAME"] = "Region"
    combined = pd.concat([by_county, region], ignore_index=True)
    combined["trip_length"] = combined["PMT"] / combined["Trips"]
    combined = _with_meta(combined)
    return _add_delta(combined, ["CO_NAME"], ["trip_length"])


def build_mode_share(shares_df: pd.DataFrame) -> pd.DataFrame:
    """Supporting context only (not a memo-mandated headline) -- daily
    (pk+ok) mode share by trip purpose, region-wide (Shares_Summary_long
    only reports a single regionwide SUBAREAID, not by county)."""
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
        "vmt_vhd_by_county_facility": build_vmt_vhd_by_county_facility(segid_df, hh_df),
        "vht_per_household": build_vht_per_household(segid_df, hh_df),
        "transit_ridership": build_transit_ridership(transit_route_df),
        "hbw_trip_length": build_hbw_trip_length(taz_metrics_df, trips_df, hh_df),
        "hbw_trip_length_distribution": trip_length_dist["distribution"],
        "hbw_trip_length_weighted_average": trip_length_dist["average"],
        "mode_share": build_mode_share(shares_df),
    }
