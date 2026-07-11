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

# HBW_trips_allsegs_*.mtx's "motor"/"nonmotor" tables (and every other
# table in them) are stored at 100x scale -- confirmed empirically: (motor +
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

DISTANCE_BIN_EDGES = list(range(0, 52, 2)) + [float("inf")]
DISTANCE_BIN_LABELS = [f"{e}-{e + 2} mi" for e in range(0, 50, 2)] + ["50+ mi"]

# Named routes the scoping memo specifically asks for (TRAX lines +
# FrontRunner) -- the route file itself carries ~170 route codes, most of
# them local/express bus. RAIL_MODES are the route file's own "Mode" codes
# for TRAX/streetcar (7) and FrontRunner commuter rail (8); every other
# mode (4=local bus, 5=BRT, 6=express, 9=premium/other) gets rolled into
# one "Bus" aggregate in build_transit_ridership(), rather than enumerating
# ~160 individual bus route codes by name.
TRANSIT_ROUTE_LABELS = {
    "Blue": "TRAX Blue Line",
    "Green": "TRAX Green Line",
    "Red": "TRAX Red Line",
    "RCRT_OGPN": "FrontRunner",
}
RAIL_MODES = {7, 8}
BUS_LABEL = "Bus (all non-rail)"

# Manual classification of each named corridor's predominant real-world
# orientation -- not derivable from Summary_SEGID itself (its own
# "DIRECTION" field is always "Both", a region-wide aggregate artifact,
# not a per-link heading). I-215 loops around Salt Lake County and doesn't
# fit either category cleanly, so it gets its own "Loop" bucket instead of
# being forced into N/S or E/W.
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

# Corridors carrying regional freeway/expressway traffic (FTCLASS in
# {Freeway, Expressway} for most of their length -- verified against
# Summary_SEGID; matches the scoping memo's own grouping, which lists
# these separately from its "N/S arterials"/"E/W arterials"). "2100 N
# Lehi" has a couple of Freeway-classified interchange segments but is
# listed as an arterial in the memo and stays there.
FREEWAY_CORRIDORS = {
    "I-15", "I-80", "I-215", "US-89 (north Davis)", "Legacy Parkway",
    "Mountain View Corridor", "Bangerter Highway", "SR-201", "West Davis Corridor",
}

# The cities picked out for city-level results -> their WFv1000_TAZ.dbf
# CITY_UGRC code (confirmed against tdm/1_Inputs/1_TAZ/Districts/City.dbf's
# CITY_NAME field). Only meaningful under the City Area scenarios: that's
# the one geography type whose redistribution is actually scoped by these
# same city boundaries. Roy, North Salt Lake, Mill Creek, Provo, and Payson
# were added alongside the original five to broaden the size/geography
# spread (small/mid-size Davis and Utah County cities weren't represented).
TARGET_CITIES = {
    "Ogden": "OGD", "Layton": "LAY", "Salt Lake City": "SLC",
    "West Jordan": "WJC", "Saratoga Springs": "SAR",
    "Roy": "ROY", "North Salt Lake": "NSL", "Mill Creek": "MLC",
    "Provo": "PVO", "Payson": "PAY",
}
TAZ_DBF = os.path.join(REPO_ROOT, "tdm", "1_Inputs", "1_TAZ", "WFv1000_TAZ.dbf")

# Peak = the two commute peaks (AM+PM); Off-Peak = midday + evening/night
# (MD+EV); Daily = all four sub-periods. Used to give VMT/VHD/VHT/Volume
# charts a Peak/Off-Peak/Daily toggle (chart_utils.figure_with_shift_toggle's
# period_col) -- confirmed with the run set's author as the standard WFRC
# 4-period convention. Dict order drives PERIOD_ORDER below.
PERIOD_GROUPS = {"Peak": ["AM", "PM"], "Off-Peak": ["MD", "EV"], "Daily": ["AM", "MD", "PM", "EV"]}

# Explicit display order for figure_with_shift_toggle(period_order=...) --
# PERIOD_GROUPS itself is insertion-ordered the same way, but call sites
# pass this so the button row's order doesn't silently depend on dict
# iteration order elsewhere.
PERIOD_ORDER = list(PERIOD_GROUPS.keys())

# "Free time added back to households" (memo section 6) is scoped to the
# peak periods specifically, not toggle-able -- kept as its own name (rather
# than always reading PERIOD_GROUPS["Peak"]) since build_hbw_trip_length()'s
# TAZ-Based Metrics filter (a different, unrelated metric) also uses it.
PEAK_PERIODS = PERIOD_GROUPS["Peak"]


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


def load_city_taz_lookup() -> pd.DataFrame:
    """TAZID -> city_label + CO_NAME for TARGET_CITIES only, via
    WFv1000_TAZ.dbf's CITY_UGRC code (CO_NAME straight from the same file
    -- every TARGET_CITIES city sits entirely within one county, confirmed
    empirically) -- always read live from tdm/ (static model geometry
    input, not a per-run output), matching non-motorized-2023's TAZ/district
    shapefile precedent and this run set's own corridor-geometry lookup."""
    import geopandas as gpd
    gdf = gpd.read_file(TAZ_DBF)
    out = pd.DataFrame(gdf[["TAZID", "CITY_UGRC", "CO_NAME"]])
    out["TAZID"] = out["TAZID"].astype(int)
    out["CO_NAME"] = out["CO_NAME"].str.title()
    code_to_label = {code: label for label, code in TARGET_CITIES.items()}
    out["city_label"] = out["CITY_UGRC"].map(code_to_label)
    return out[out["city_label"].notna()][["TAZID", "city_label", "CO_NAME"]]


# 5_AssignHwy/5_FinalNetSkims/*Skm_<sub_period>.mtx, one file per
# final-assignment time period, each carrying a GP_Dist table.
_SUFFIX_SKIM_SUB_PERIOD = {"AM": "Skm_AM.omx", "MD": "Skm_MD.omx", "PM": "Skm_PM.omx", "EV": "Skm_EV.omx"}

# 4_ModeChoice/2_DetailedTripMatrices/*HBW_trips_allsegs_<Pk|Ok>.mtx -- HBW
# trips are only ever split this coarsely (Peak/Off-Peak), never down to
# individual AM/MD/PM/EV the way the final skims above are.
_SUFFIX_HBW_MATRIX_PERIOD = {"Peak": "HBW_trips_allsegs_Pk.omx", "Off-Peak": "HBW_trips_allsegs_Ok.omx"}


def load_distance_skim_sub_period_from_runs(scenario_id: str, sub_period: str) -> np.ndarray:
    """Full TAZ x TAZ GP_Dist array for one of the 4 final-skim time periods
    (sub_period in "AM"/"MD"/"PM"/"EV") -- the period-correct distance
    source, as opposed to load_distance_skim_from_runs's single all-day
    (DY) skim reused for every trip regardless of when it travels."""
    import openmatrix as omx
    f = omx.open_file(_curated_path(scenario_id, _SUFFIX_SKIM_SUB_PERIOD[sub_period]), "r")
    try:
        return np.array(f["GP_Dist"])
    finally:
        f.close()


def load_distance_skim_for_period_from_runs(scenario_id: str, period: str) -> np.ndarray:
    """Peak (AM+PM) or Off-Peak (MD+EV) distance skim -- an unweighted
    average of its two constituent sub-periods' GP_Dist arrays (see
    PERIOD_GROUPS). Unweighted because the HBW trip matrices are only ever
    split Peak/Off-Peak, not further into AM/MD/PM/EV, so there's no
    period-specific trip volume to weight by; this is a deliberate
    simplification, reasonable in practice since AM/MD/PM/EV/DY skim means
    all fall within about 1% of each other (GP_Dist barely varies by
    period -- distance is a largely static network attribute along
    whichever path was assigned, confirmed empirically for this run set)."""
    parts = [load_distance_skim_sub_period_from_runs(scenario_id, p) for p in PERIOD_GROUPS[period]]
    return np.mean(parts, axis=0)


def load_distance_skim_for_period(scenario_id: str, period: str) -> np.ndarray:
    if rd.is_retired(RUN_SET_ID):
        return np.load(_snapshot_path(f"{scenario_id}_gp_dist_{period}.npy"))
    return load_distance_skim_for_period_from_runs(scenario_id, period)


def load_hbw_trip_matrix_for_period_from_runs(scenario_id: str, period: str) -> np.ndarray:
    """Full TAZ x TAZ HBW trip-volume array for Peak, Off-Peak, or Daily,
    from the curated two-tab OMX, scaled down by HBW_MATRIX_SCALE. Only
    Peak (Pk) and Off-Peak (Ok) matrices are actually curated -- no separate
    all-day OMX exists -- so Daily is built as their sum rather than read
    from its own file."""
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


def build_hbw_trip_length_distribution(scenario_ids: list) -> dict:
    """Trip-volume-weighted HBW trip-length frequency distribution (O-D
    skim distance x O-D trip volume, binned), one curve per scenario x
    period (Peak/Off-Peak, see PERIOD_GROUPS -- a "period" column drives
    chart_utils.figure_with_shift_toggle's Peak/Off-Peak toggle), plus a
    weighted-average trip length per scenario x period as a cross-check
    against build_hbw_trip_length()'s independent PMT/trips-based average
    -- the two are computed from entirely different sources (full O-D skim
    x matrix here, production-side PMT/trip totals there) and should be
    close, not identical. Built region-wide only (not by county): the
    point of this view is the shape of the curve, not another county
    breakdown.

    Distance and trips are both period-correct: Peak rows pair the Peak
    HBW trip matrix (HBW_trips_allsegs_Pk.mtx) against the Peak (AM+PM
    average) distance skim, Off-Peak rows pair the Ok trip matrix against
    the Off-Peak (MD+EV average) skim -- see load_distance_skim_for_period/
    load_hbw_trip_matrix_for_period. Previously this used a single DY
    (all-4-period) distance skim applied uniformly to the combined
    Peak+Off-Peak (pkok) trip matrix, mismatching trips against a distance
    that wasn't specific to when they actually travel.

    Only scenarios with all four period skims and both Peak/Off-Peak
    matrices curated are included -- silently skips any that haven't been
    backfilled yet, matching available_scenario_ids()'s "grows as more
    scenarios land" philosophy. NOACCESS-sentinel (9999) skim cells are
    excluded before binning so a handful of technically-unconnected zone
    pairs can't masquerade as extreme-long trips.
    """
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
    """Expands one row per group_cols (already carrying summed AM_<m>/MD_<m>/
    PM_<m>/EV_<m> columns for each metric) into two rows per group -- one per
    PERIOD_GROUPS key -- adding a "period" column ("Peak"/"Off-Peak") for
    chart_utils.figure_with_shift_toggle's period_col to filter on.

    metric_cols maps each desired OUTPUT column name (e.g. "DY_VMT") to the
    underlying per-period metric suffix (e.g. "VMT", summing AM_VMT+PM_VMT
    for the Peak row, MD_VMT+EV_VMT for Off-Peak). Output columns keep their
    original DY_-prefixed names deliberately, even though they now hold a
    period-specific sum rather than a true all-day one, so every existing
    chart reading delta_DY_VMT/pct_DY_VMT/etc. keeps working unchanged --
    only the .qmd call site needs to add period_col="period"."""
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
    """Volume/VMT/VHD by named corridor and scenario, region-wide (summed
    across whichever counties a corridor passes through) -- memo section
    6's corridor detail. Only SEGIDs matched to a named corridor are kept.

    Adds a "period" column (Peak=AM+PM / Off-Peak=MD+EV, see PERIOD_GROUPS)
    for a Peak/Off-Peak chart toggle -- DY_Vol/DY_VMT/DY_VHD keep their
    original names but now hold period-specific sums, not true daily ones;
    see _add_period_dim."""
    merged = segid_df.merge(crosswalk[["SEGID", "corridor_label"]], on="SEGID", how="inner")
    period_agg_cols = {f"{p}_{m}": (f"{p}_{m}", "sum") for p in ("AM", "MD", "PM", "EV") for m in ("Vol", "VMT", "VHD")}
    agg = merged.groupby(["scenario_id", "corridor_label"], as_index=False).agg(**period_agg_cols)
    agg = _add_period_dim(agg, ["scenario_id", "corridor_label"], {"DY_Vol": "Vol", "DY_VMT": "VMT", "DY_VHD": "VHD"})
    agg = _with_meta(agg)
    return _add_delta(agg, ["corridor_label", "period"], ["DY_Vol", "DY_VMT", "DY_VHD"])


def build_freeway_corridors_by_county(segid_df: pd.DataFrame, crosswalk: pd.DataFrame, hh_df: pd.DataFrame) -> pd.DataFrame:
    """Volume/VMT/VHD for the named freeway/expressway corridors
    (FREEWAY_CORRIDORS), broken out by the county each segment actually
    sits in -- e.g. I-15 in Salt Lake County vs. I-15 in Davis County --
    rather than build_corridor_volumes()'s single region-wide total per
    corridor. Adds a "period" column, see build_corridor_volumes."""
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
    predominant orientation (CORRIDOR_ORIENTATION: N/S, E/W, or Loop for
    I-215 specifically) -- a region-wide rollup, not broken out by
    individual corridor or county. Adds a "period" column, see
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
    type -- memo section 6's headline (VHD) and explanatory (VMT) tables.
    Excludes FTCLASS == "Local" -- a tiny, incidental slice of SEGID rows
    (21 of ~4,500 in a typical scenario) not part of the facility-type
    breakdown the memo asks for. Adds a "period" column, see
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
    """Miles of roadway with volume/capacity (V/C) > 1.0 ("severe
    congestion"), by county + facility type (plus a Region row), for Peak,
    Off-Peak, and Daily -- a length-based capacity read, distinct from
    VHD/VMT: relevant to funding/capacity decisions since it answers "how
    many miles are over capacity," not "how much delay resulted." Peak V/C
    is the max of AM_VC/PM_VC per segment (a segment counts as congested if
    either commute peak pushes it over capacity); Off-Peak is the max of
    MD_VC/EV_VC; Daily reuses Summary_SEGID's own MAX_VC (already the max
    across all four sub-periods) rather than recomputing it. DISTANCE
    (segment length) is summed, not LANEMILES, since the metric describes
    route-miles over capacity regardless of lane count. Excludes FTCLASS ==
    "Local", matching build_vmt_vhd_by_county_facility's convention.

    Every (scenario, county, facility type, period) combination present in
    segid_df gets a row even when zero miles are congested (sum of a
    0/DISTANCE indicator column, not a pre-filtered groupby) -- so a
    scenario with no over-capacity segments in some county/facility type
    still lines up with the others for the toggle and for _add_delta,
    instead of silently going missing.
    """
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
    """Peak-period (AM+PM) VHT per household, by county + region -- memo's
    'free time added back to households' metric -- was previously fixed at
    Peak (AM+PM), now also builds the Off-Peak (MD+EV) counterpart and adds
    a "period" column, see build_corridor_volumes."""
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
    """Daily (pk+ok) boardings for TRAX + FrontRunner (memo's original ask)
    plus a "Bus" aggregate summing every route whose Mode isn't one of
    RAIL_MODES -- i.e. every local/BRT/express/premium route, without
    enumerating ~160 individual bus route codes by name."""
    named = route_df[route_df["Name"].isin(TRANSIT_ROUTE_LABELS)].copy()
    named["line_label"] = named["Name"].map(TRANSIT_ROUTE_LABELS)

    bus = route_df[~route_df["Mode"].round().astype(int).isin(RAIL_MODES)].copy()
    bus["line_label"] = BUS_LABEL

    df = pd.concat([named, bus], ignore_index=True)
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


def build_city_results(
    taz_metrics_df: pd.DataFrame, trips_df: pd.DataFrame, hh_df: pd.DataFrame, city_lookup: pd.DataFrame
) -> pd.DataFrame:
    """Production-side daily VMT, peak-period VHT/household, and average
    HBW trip length for TARGET_CITIES, under the City Area scenarios only
    -- the one geography type whose redistribution is actually scoped by
    these same city boundaries (CITY_UGRC). Available at whichever City
    Area shift levels (5%/10%/25%) have a curated run, same as everywhere
    else in this module. Also carries each city's CO_NAME (from
    city_lookup, one county per city) for county-colored city-level charts
    -- there's no per-city VHD here (VHD is a link-level network summary
    with a county code, not a city one, so a genuine per-city VHD would
    need a new link-to-city spatial join that doesn't exist yet)."""
    city_scenarios = SCENARIO_META[
        (SCENARIO_META["geography_label"] == "City Area") | (SCENARIO_META["scenario_id"] == BASELINE_SCENARIO)
    ]["scenario_id"].tolist()

    vmt = taz_metrics_df[
        (taz_metrics_df["Metric"] == "VMT") & (taz_metrics_df["Purpose"] == "HBW") & (taz_metrics_df["PA"] == "P")
    ]
    vmt_daily = vmt.groupby(["scenario_id", "TAZID"], as_index=False)["Total"].sum().rename(columns={"Total": "VMT"})

    vht = taz_metrics_df[
        (taz_metrics_df["Metric"] == "VHT") & (taz_metrics_df["Purpose"] == "HBW") &
        (taz_metrics_df["PA"] == "P") & (taz_metrics_df["Period"].isin(PEAK_PERIODS))
    ]
    vht_peak = vht.groupby(["scenario_id", "TAZID"], as_index=False)["Total"].sum().rename(columns={"Total": "PEAK_VHT"})

    pmt = taz_metrics_df[
        (taz_metrics_df["Metric"] == "PMT") & (taz_metrics_df["Purpose"] == "HBW") & (taz_metrics_df["PA"] == "P")
    ]
    pmt_daily = pmt.groupby(["scenario_id", "TAZID"], as_index=False)["Total"].sum().rename(columns={"Total": "PMT"})

    trips = trips_df[
        (trips_df["Purpose"] == "HBW") & (trips_df["Period"] == "Dy") & (trips_df["PA"] == "P")
    ][["scenario_id", "TAZID", "All"]].rename(columns={"All": "Trips"})

    df = (
        vmt_daily.merge(vht_peak, on=["scenario_id", "TAZID"], how="outer")
        .merge(pmt_daily, on=["scenario_id", "TAZID"], how="outer")
        .merge(trips, on=["scenario_id", "TAZID"], how="outer")
    )
    df = df[df["scenario_id"].isin(city_scenarios)]
    df = df.merge(city_lookup, on="TAZID", how="inner")  # only TARGET_CITIES' TAZs survive
    df = df.merge(hh_df[["TAZID", "TOTHH"]], on="TAZID", how="left")

    agg = df.groupby(["scenario_id", "city_label"], as_index=False).agg(
        VMT=("VMT", "sum"), PEAK_VHT=("PEAK_VHT", "sum"), PMT=("PMT", "sum"),
        Trips=("Trips", "sum"), TOTHH=("TOTHH", "sum"), CO_NAME=("CO_NAME", "first"),
    )
    agg["VHT_PER_HH"] = agg["PEAK_VHT"] / agg["TOTHH"]
    agg["trip_length"] = agg["PMT"] / agg["Trips"]
    agg = _with_meta(agg)
    return _add_delta(agg, ["city_label"], ["VMT", "VHT_PER_HH", "trip_length"])


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
    city_lookup = load_city_taz_lookup()
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
        "city_results": build_city_results(taz_metrics_df, trips_df, hh_df, city_lookup),
        "mode_share": build_mode_share(shares_df),
    }
