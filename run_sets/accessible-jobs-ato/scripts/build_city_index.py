# /// script
# requires-python = ">=3.10"
# dependencies = ["geopandas>=0.13"]
# ///
"""
Build run_sets/accessible-jobs-ato/inputs/city_index.csv -- TAZID -> CityIdx,
one row per real TAZ in the TDM's own TAZ shapefile
(tdm/1_Inputs/1_TAZ/WFv1000_TAZ.shp).

This is a per-TAZ file, which an earlier version of this script deliberately
avoided in favor of a small ~82-row CITY_UGRC (text) -> CityIdx crosswalk,
read via a Cube LOOKUP against WFv1000_TAZ.dbf's own CITY_UGRC field loaded
directly. That approach was tried against real Cube Voyager and reverted
after two real failures, confirmed via TPPL1791.PRN (2026-09-07):

  1. Cube's LOOKUP command has no STRING=T option ("F(018): STRING is
     invalid key") -- a text-keyed exact-match lookup isn't available the
     way it was guessed to be.
  2. The numeric fallback (CITY_FIPS, already on WFv1000_TAZ.dbf) doesn't
     work either: CITY_FIPS=0 is shared by Hill AFB and unincorporated
     county land in the real data -- a genuine collision, not a syntax
     problem, discovered by checking the actual TAZ attribute values.

This TAZID-keyed file avoids both problems (TAZID is always unique) and is
loaded the same way this exact TDM's own production code already reads a
CSV zone file -- see tdm/2_ModelScripts/0_InputProcessing/b_SEProcessing/
1_DemographicsAnalysis.s's WFRC_SEFile/MAG_SEFile FILEI DBI lines
(DELIMITER=',', explicit column numbers) -- and populated into a
TAZID-indexed array the same way access_to_opportunity_detail.s (and the
original 08_Access_to_Opportunity.s) already populates Node_X/Node_Y from
scenario Node.dbf: a LOOP over records at i=1, not a LOOKUP() call.

Re-run this whenever WFv1000_TAZ.dbf's CITY_UGRC assignments change (a new
TDM vintage, annexation, etc.) -- NUM_CITIES printed at the end must match
the NUM_CITIES constant (and the ARRAY dimensions) hardcoded in
access_to_opportunity_detail.s.

Usage:
    uv run run_sets/accessible-jobs-ato/scripts/build_city_index.py
"""

import csv
from pathlib import Path

import geopandas as gpd

REPO_ROOT = Path(__file__).resolve().parents[3]
TAZ_SHP = REPO_ROOT / "tdm" / "1_Inputs" / "1_TAZ" / "WFv1000_TAZ.shp"
OUT_CSV = Path(__file__).resolve().parents[1] / "inputs" / "city_index.csv"


def main():
    taz = gpd.read_file(TAZ_SHP)
    taz = taz[["TAZID", "CITY_UGRC"]].copy()
    taz["TAZID"] = taz["TAZID"].astype(int)
    taz["CITY_UGRC"] = taz["CITY_UGRC"].fillna("").astype(str).str.strip()
    taz.loc[taz["CITY_UGRC"] == "", "CITY_UGRC"] = "[Unincorporated]"

    distinct_cities = sorted(taz["CITY_UGRC"].unique())
    city_to_idx = {name: i + 1 for i, name in enumerate(distinct_cities)}
    taz["CityIdx"] = taz["CITY_UGRC"].map(city_to_idx)

    taz = taz.sort_values("TAZID")[["TAZID", "CityIdx", "CITY_UGRC"]]
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    taz.to_csv(OUT_CSV, index=False, quoting=csv.QUOTE_NONNUMERIC)

    print(f"Wrote {OUT_CSV} ({len(taz):,} TAZ rows)")
    print(f"NUM_CITIES = {len(distinct_cities)}")
    print("(update the NUM_CITIES constant and ARRAY dimensions in "
          "access_to_opportunity_detail.s if this changed)")


if __name__ == "__main__":
    main()
