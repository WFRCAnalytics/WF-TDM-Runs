"""Interpolate MAG SE data for 2040 from the 2036 and 2046 vintages.

Reads data/MAG_SE/SE_2036.csv and SE_2046.csv, linearly interpolates every
numeric field to 2040, and writes SE_2040.csv into this run set's inputs/
folder.
"""

from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).parent / "data" / "MAG_SE"
OUTPUT_DIR = Path(__file__).parent.parent

YEAR_BEFORE = 2036
YEAR_AFTER = 2046
YEAR_TARGET = 2040

TAZID_COL = ";TAZID"


def main() -> None:
    before_df = pd.read_csv(DATA_DIR / f"SE_{YEAR_BEFORE}.csv")
    after_df = pd.read_csv(DATA_DIR / f"SE_{YEAR_AFTER}.csv")

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

    out_path = OUTPUT_DIR / f"SE_{YEAR_TARGET}_MAG.csv"
    result.to_csv(out_path, index=False)
    print(f"Wrote {out_path}  ({len(result):,} rows)")


if __name__ == "__main__":
    main()
