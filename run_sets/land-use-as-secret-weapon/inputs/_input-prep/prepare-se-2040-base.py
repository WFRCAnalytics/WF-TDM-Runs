"""Prepare the combined 2040 base-year SE file for the land-use-as-secret-weapon run set.

Combines two sources by TAZID range (per WFRC/MAG jurisdiction boundaries
defined in tdm/1_Inputs/0_GlobalData/GeneralParameters.block -- WFRC covers
TAZID 1-2216 [BoxElder/Weber/Davis/SL], MAG covers TAZID 2217-3562 [Utah]):

- TAZID 1-2216: copied straight from data/WFRC_SE/SE_2040.csv (already the
  target year, no interpolation needed).
- TAZID 2217-3562: linearly interpolated to 2040 from data/MAG_SE/SE_2036.csv
  and SE_2046.csv.

Writes a single combined SE_2040_Base.csv into this run set's inputs/ folder.
"""

from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).parent / "data"
OUTPUT_DIR = Path(__file__).parent.parent

YEAR_BEFORE = 2036
YEAR_AFTER = 2046
YEAR_TARGET = 2040

TAZID_COL = ";TAZID"

WFRC_MAX_TAZID = 2216  # SLRange upper bound; MAG (UtahRange) starts at 2217


def load_wfrc_se() -> pd.DataFrame:
    return pd.read_csv(DATA_DIR / "WFRC_SE" / f"SE_{YEAR_TARGET}.csv")


def interpolate_mag_se() -> pd.DataFrame:
    mag_dir = DATA_DIR / "MAG_SE"
    before_df = pd.read_csv(mag_dir / f"SE_{YEAR_BEFORE}.csv")
    after_df = pd.read_csv(mag_dir / f"SE_{YEAR_AFTER}.csv")

    merged = before_df.merge(
        after_df, on=TAZID_COL, suffixes=("_before", "_after"), validate="one_to_one"
    )

    weight = (YEAR_TARGET - YEAR_BEFORE) / (YEAR_AFTER - YEAR_BEFORE)
    fields = [c for c in before_df.columns if c != TAZID_COL]

    result = pd.DataFrame({TAZID_COL: merged[TAZID_COL]})
    for field in fields:
        before_col = merged[f"{field}_before"]
        after_col = merged[f"{field}_after"]
        result[field] = before_col + (after_col - before_col) * weight

    return result


def main() -> None:
    wfrc_df = load_wfrc_se()
    mag_df = interpolate_mag_se()

    combined = pd.concat(
        [
            wfrc_df[wfrc_df[TAZID_COL] <= WFRC_MAX_TAZID],
            mag_df[mag_df[TAZID_COL] > WFRC_MAX_TAZID],
        ],
    ).sort_values(TAZID_COL)

    out_path = OUTPUT_DIR / f"SE_{YEAR_TARGET}_Base.csv"
    combined.to_csv(out_path, index=False)
    print(f"Wrote {out_path}  ({len(combined):,} rows)")


if __name__ == "__main__":
    main()
