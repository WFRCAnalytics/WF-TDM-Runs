"""Shared data-loading and aggregation logic for reports/run_sets/non-motorized-2023's
summary.qmd and slides.qmd -- previously duplicated verbatim between the two.

Retirement-aware at exactly two leaf functions, load_scenario() and load_se():
each prefers a frozen snapshot (written by `tdmruns snapshot-run-set`, read via
report_data.is_retired()) once one exists, falling back to a live read from
whatever tdmruns import-manual-run(-set) most recently curated under runs/.
Everything else here -- aggregation, deltas, chart-ready tables -- is unchanged
business logic shared by both the live and retired cases.

The base year (test_id 0) and the TAZ/district shapefiles are always read live
from the (gitignored) tdm/ working tree, never frozen -- see CLAUDE.md's note
on this run set's retirement for why that's an accepted limitation.
"""
import os
import sys

import geopandas as gpd
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.join(_HERE, "..", "..")
sys.path.insert(0, os.path.join(REPO_ROOT, "reports"))
import report_data as rd  # noqa: E402

RUN_SET_ID = "non-motorized-2023"
TDM_ROOT = os.path.join(REPO_ROOT, "tdm")
TDM_BASELINE_DIR = os.path.join(TDM_ROOT, "Scenarios", RUN_SET_ID)
SMLDST_LST = [22, 16, 46, 88, 102]
KEEP_COLS = ["Purpose", "TAZID", "All", "Walk", "Bike", "NonM"]

SCENARIO_META = pd.DataFrame([
    {"test_id":  0, "description": "Base 2019",                 "hh_mult": 1,  "emp_mult": 1,  "scope": "smldst"},
    {"test_id":  1, "description": "2019 HH x2",                "hh_mult": 2,  "emp_mult": 1,  "scope": "smldst"},
    {"test_id":  2, "description": "2019 HH x4",                "hh_mult": 4,  "emp_mult": 1,  "scope": "smldst"},
    {"test_id":  3, "description": "2019 HH x12",                "hh_mult": 12, "emp_mult": 1,  "scope": "smldst"},
    {"test_id":  4, "description": "2019 EMP x2",                "hh_mult": 1,  "emp_mult": 2,  "scope": "smldst"},
    {"test_id":  5, "description": "2019 EMP x4",                "hh_mult": 1,  "emp_mult": 4,  "scope": "smldst"},
    {"test_id":  6, "description": "2019 EMP x12",               "hh_mult": 1,  "emp_mult": 12, "scope": "smldst"},
    {"test_id":  7, "description": "2019 HH+EMP x2",             "hh_mult": 2,  "emp_mult": 2,  "scope": "smldst"},
    {"test_id":  8, "description": "2019 HH+EMP x4",             "hh_mult": 4,  "emp_mult": 4,  "scope": "smldst"},
    {"test_id":  9, "description": "2019 HH+EMP x12",            "hh_mult": 12, "emp_mult": 12, "scope": "smldst"},
    {"test_id": 10, "description": "Future Today",               "hh_mult": -1, "emp_mult": -1, "scope": "smldst"},
    {"test_id": 11, "description": "Future Today - Centerized",  "hh_mult": -1, "emp_mult": -1, "scope": "smldst"},
    {"test_id": 12, "description": "Future Today",               "hh_mult": -1, "emp_mult": -1, "scope": "region"},
    {"test_id": 13, "description": "Future Today - Centerized",  "hh_mult": -1, "emp_mult": -1, "scope": "region"},
])

PURPOSES = ["HBW", "HBO", "NHB"]

LABEL_ORDER = [
    "HH only 2x", "HH only 4x", "HH only 12x",
    "EMP only 2x", "EMP only 4x", "EMP only 12x",
    "HH + EMP 2x", "HH + EMP 4x", "HH + EMP 12x",
]

GROUP_COLS = ["test_id", "description", "hh_mult", "emp_mult", "Purpose"]
SUM_COLS = ["All", "Walk", "Bike", "NonM"]


def series_label(row):
    if row["hh_mult_n"] > 1 and row["emp_mult_n"] == 1:
        return "HH only"
    elif row["hh_mult_n"] == 1 and row["emp_mult_n"] > 1:
        return "EMP only"
    return "HH + EMP"


def smldst_tazs() -> set:
    taz_gdf = gpd.read_file(os.path.join(TDM_ROOT, "1_Inputs", "1_TAZ", "WFv910_TAZ.shp"))
    return set(taz_gdf[taz_gdf["DISTSML"].isin(SMLDST_LST)]["TAZID"].astype(int).tolist())


def _latest_runs() -> dict:
    return {r["scenario_id"]: r for r in rd.latest_run_per_scenario(RUN_SET_ID)}


def _curated_path(scenario_id: str, suffix: str) -> str:
    """Repo-root-relative path to the most recently imported curated output
    ending in suffix, for scenario_id -- e.g. suffix='.dbf' or
    '_ZoneSummary_TripsByMode.csv'. Raises if no import has been run yet."""
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


def load_scenario_from_runs(test_id: int) -> pd.DataFrame:
    """Reads and filters one scenario's ZoneSummary CSV straight from its
    curated runs/ output. Used for live rendering when not retired, and by
    report_snapshot.py to build the frozen snapshot -- the two must apply
    the exact same filter so the snapshot is a faithful freeze."""
    path = _curated_path(f"S{test_id:02d}", "_ZoneSummary_TripsByMode.csv")
    df = pd.read_csv(path)
    df = df[(df["Period"] == "Dy") & (df["PA"] == "P")][KEEP_COLS]
    df["test_id"] = test_id
    return df


def load_scenario(test_id: int) -> pd.DataFrame:
    if test_id == 0:
        path = os.path.join(
            TDM_BASELINE_DIR, "BY_2019", "4_ModeChoice",
            "2_DetailedTripMatrices", "BY_2019_ZoneSummary_TripsByMode.csv",
        )
        df = pd.read_csv(path)
        df = df[(df["Period"] == "Dy") & (df["PA"] == "P")][KEEP_COLS]
        df["test_id"] = 0
        return df
    if rd.is_retired(RUN_SET_ID):
        return pd.read_csv(_snapshot_path(f"S{test_id:02d}_trips.csv"))
    return load_scenario_from_runs(test_id)


def load_se_from_runs(scenario_id: str) -> pd.DataFrame:
    gdf = gpd.read_file(_curated_path(scenario_id, ".dbf"))
    out = pd.DataFrame(gdf[["DISTMED", "TOTHH"]])
    out["DISTMED"] = out["DISTMED"].astype(int)
    out["TOTHH"] = out["TOTHH"].astype(float)
    return out


def load_se(scenario_id: str) -> pd.DataFrame:
    if rd.is_retired(RUN_SET_ID):
        return pd.read_csv(_snapshot_path(f"{scenario_id}_se.csv"))
    return load_se_from_runs(scenario_id)


def build_raw_df() -> pd.DataFrame:
    raw_df = pd.concat([load_scenario(i) for i in range(14)], ignore_index=True)
    raw_df = raw_df.merge(SCENARIO_META, on="test_id")
    raw_df["TAZID"] = raw_df["TAZID"].astype(int)
    return raw_df


def _add_deltas(df: pd.DataFrame, geo: str) -> pd.DataFrame:
    base = df[(df["test_id"] == 0) & (df["geo_scope"] == geo)][[
        "Purpose", "NonM", "Walk", "Bike", "All", "nonm_share", "walk_share", "bike_share"
    ]].rename(columns={
        "NonM": "base_NonM", "Walk": "base_Walk", "Bike": "base_Bike", "All": "base_All",
        "nonm_share": "base_nonm_share", "walk_share": "base_walk_share", "bike_share": "base_bike_share",
    })
    merged = df[df["geo_scope"] == geo].merge(base, on="Purpose")
    for col in ["NonM", "Walk", "Bike"]:
        merged[f"delta_{col}"] = merged[col] - merged[f"base_{col}"]
    merged["delta_nonm_share"] = merged["nonm_share"] - merged["base_nonm_share"]
    merged["delta_walk_share"] = merged["walk_share"] - merged["base_walk_share"]
    merged["delta_bike_share"] = merged["bike_share"] - merged["base_bike_share"]
    return merged


def build_full_delta(raw_df: pd.DataFrame, smldst_taz_set: set) -> pd.DataFrame:
    filt_df = raw_df
    local_agg = (
        filt_df[filt_df["test_id"].isin(range(12)) & filt_df["TAZID"].isin(smldst_taz_set)]
        .groupby(GROUP_COLS)[SUM_COLS].sum().reset_index()
    )
    local_agg["geo_scope"] = "smldst"

    region_agg = (
        filt_df[filt_df["test_id"].isin([0, 12, 13])]
        .groupby(GROUP_COLS)[SUM_COLS].sum().reset_index()
    )
    region_agg["geo_scope"] = "region"

    summary = pd.concat([local_agg, region_agg], ignore_index=True)
    summary["nonm_share"] = summary["NonM"] / summary["All"] * 100
    summary["walk_share"] = summary["Walk"] / summary["All"] * 100
    summary["bike_share"] = summary["Bike"] / summary["All"] * 100

    local_delta = _add_deltas(summary, "smldst")
    region_delta = _add_deltas(summary, "region")
    return pd.concat([local_delta, region_delta], ignore_index=True)


def build_geo_centerization(raw_df: pd.DataFrame) -> pd.DataFrame:
    """The district-level table behind the 'Where Centerization Has an
    Effect' chart. taz_dist (TAZ->district name) and dist_areas (district
    geometry, for area_acres) are read live from tdm/ -- see module
    docstring. t10_se/t11_se (DISTMED/TOTHH) go through load_se(), so they
    come from the snapshot once retired."""
    t10_all = raw_df[raw_df["test_id"] == 10].groupby("TAZID")[["All", "NonM"]].sum().reset_index()
    t11_all = raw_df[raw_df["test_id"] == 11].groupby("TAZID")[["All", "NonM"]].sum().reset_index()

    taz_dist = gpd.read_file(os.path.join(
        TDM_BASELINE_DIR, "BY_2019", "0_InputProcessing", "SE_File_WFv920-E3_BY_2019.dbf"
    ))[["Z", "DISTMED", "DMED_NAME"]]
    taz_dist = taz_dist.rename(columns={"Z": "TAZID"})
    taz_dist["TAZID"] = taz_dist["TAZID"].astype(int)
    taz_dist["DISTMED"] = taz_dist["DISTMED"].astype(int)

    def district_nm(trips):
        df = trips.merge(taz_dist, on="TAZID", how="left")
        g = df.groupby(["DISTMED", "DMED_NAME"])[["All", "NonM"]].sum()
        g["share"] = g["NonM"] / g["All"] * 100
        return g.reset_index()

    t10_d = district_nm(t10_all)
    t11_d = district_nm(t11_all)

    t10_se = load_se("S10")
    t11_se = load_se("S11")

    dist_areas = gpd.read_file(os.path.join(
        TDM_ROOT, "1_Inputs", "1_TAZ", "Districts", "Dist_Medium.shp"
    ))[["DISTMED", "geometry"]]
    dist_areas["DISTMED"] = dist_areas["DISTMED"].astype(int)
    dist_areas["area_acres"] = dist_areas.geometry.area / 4046.86

    hh = t10_se.groupby("DISTMED")["TOTHH"].sum().rename("HH_T10").to_frame()
    hh["HH_T11"] = t11_se.groupby("DISTMED")["TOTHH"].sum()
    hh = hh.reset_index().merge(dist_areas[["DISTMED", "area_acres"]], on="DISTMED", how="left")
    hh["dens_diff"] = (hh["HH_T11"] - hh["HH_T10"]) / hh["area_acres"]

    geo = (
        t10_d[["DISTMED", "DMED_NAME", "share"]].rename(columns={"share": "share_T10"})
        .merge(t11_d[["DISTMED", "share"]].rename(columns={"share": "share_T11"}), on="DISTMED")
        .merge(hh[["DISTMED", "dens_diff"]], on="DISTMED")
    )
    geo["delta_share"] = geo["share_T11"] - geo["share_T10"]
    geo = geo[geo["dens_diff"].abs() > 0.02].copy()
    geo["direction"] = geo["dens_diff"].apply(lambda x: "Gaining density" if x > 0 else "Losing density")

    notable_ids = {12, 31, 10, 21, 18}
    geo["label"] = geo.apply(lambda r: r["DMED_NAME"] if r["DISTMED"] in notable_ids else "", axis=1)
    return geo


def load() -> dict:
    """Everything both summary.qmd and slides.qmd need. raw_df/full_delta
    prefer the frozen snapshot for test scenarios 1-13 once retired; the
    base year and geo_centerization's taz_dist/dist_areas pieces are always
    read live from tdm/."""
    raw_df = build_raw_df()
    tazs = smldst_tazs()
    full_delta = build_full_delta(raw_df, tazs)
    geo = build_geo_centerization(raw_df)
    return {"raw_df": raw_df, "full_delta": full_delta, "geo_centerization": geo}
