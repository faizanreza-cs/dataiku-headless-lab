"""Legacy pipeline: GLP-1 prescriptions and spend in Medicaid, by state and quarter.

This is the "before" in the migration test. It reads Medicaid State Drug Utilization Data and
the FDA NDC directory, and writes three tables to reference/. Whatever replaces it has to
produce the same three tables.

Usage: python legacy/pipeline.py [output_dir]
"""

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"

GLP1_CLASS = "GLP-1 Receptor Agonist [EPC]"


def to_ndc11(package_code: str) -> str:
    # FDA writes package codes as 4-4-2, 5-3-2 or 5-4-1; SDUD uses 11 digits (5-4-2),
    # so each segment is padded on its own
    labeler, product, package = package_code.split("-")
    return labeler.zfill(5) + product.zfill(4) + package.zfill(2)


def load_ndc_lookup() -> pd.DataFrame:
    product = pd.read_csv(RAW / "fda_product.txt", sep="\t", dtype=str, keep_default_na=False)
    package = pd.read_csv(RAW / "fda_package.txt", sep="\t", dtype=str, keep_default_na=False)

    # Join on PRODUCTID, not PRODUCTNDC: a product NDC can be listed more than once
    lookup = package.merge(
        product[["PRODUCTID", "PROPRIETARYNAME", "NONPROPRIETARYNAME", "PHARM_CLASSES"]],
        on="PRODUCTID",
    )
    lookup["ndc"] = lookup["NDCPACKAGECODE"].map(to_ndc11)
    lookup = lookup.sort_values(["ndc", "PRODUCTID"]).drop_duplicates("ndc")

    # The FDA lists the same brand as "Ozempic" and "OZEMPIC"
    lookup["brand"] = lookup["PROPRIETARYNAME"].str.strip().str.upper()
    lookup["generic_name"] = lookup["NONPROPRIETARYNAME"].str.strip().str.lower()
    lookup["is_glp1"] = lookup["PHARM_CLASSES"].str.contains(GLP1_CLASS, regex=False)
    return lookup[["ndc", "brand", "generic_name", "is_glp1"]]


def load_sdud() -> pd.DataFrame:
    sdud = pd.read_csv(
        RAW / "sdud_2024_2025.csv",
        dtype={"State": str, "NDC": str, "Suppression Used": str, "Product Name": str},
    )
    sdud = sdud.rename(columns={
        "State": "state", "NDC": "ndc", "Year": "year", "Quarter": "quarter",
        "Suppression Used": "suppressed", "Product Name": "sdud_product_name",
        "Units Reimbursed": "units", "Number of Prescriptions": "rx_count",
        "Total Amount Reimbursed": "spend",
    })
    # "XX" rows are national totals, already the sum of the states
    sdud = sdud[sdud["state"] != "XX"]
    # Suppressed rows (fewer than 11 prescriptions) have no counts
    sdud = sdud[sdud["suppressed"].str.lower() != "true"]
    sdud["sdud_product_name"] = sdud["sdud_product_name"].str.strip()
    # Fee-for-service (FFSU) and managed care (MCOU) rows are both kept and summed below
    return sdud[["state", "ndc", "year", "quarter", "sdud_product_name", "units", "rx_count", "spend"]]


def unmatched_ndcs(sdud: pd.DataFrame, lookup: pd.DataFrame) -> pd.DataFrame:
    # NDCs the FDA directory doesn't list (mostly discontinued products) can't be classed,
    # so they're reported instead of silently dropped
    missing = sdud[~sdud["ndc"].isin(lookup["ndc"])]
    return (
        missing.groupby("ndc", as_index=False)
        .agg(sdud_product_name=("sdud_product_name", "min"), rows=("ndc", "size"),
             rx_count=("rx_count", "sum"), spend=("spend", "sum"))
        .sort_values("ndc")
    )


def state_quarter(sdud: pd.DataFrame, lookup: pd.DataFrame) -> pd.DataFrame:
    glp1 = sdud.merge(lookup[lookup["is_glp1"]], on="ndc")
    out = (
        glp1.groupby(["state", "year", "quarter", "brand"], as_index=False)
        .agg(generic_name=("generic_name", "min"), rx_count=("rx_count", "sum"),
             units=("units", "sum"), spend=("spend", "sum"))
    )
    class_rx = out.groupby(["state", "year", "quarter"])["rx_count"].transform("sum")
    out["share_of_class_rx"] = out["rx_count"] / class_rx

    # Growth against the previous calendar quarter. If the brand has no row for that quarter
    # in that state, growth is empty rather than measured against an older quarter.
    out["period"] = out["year"] * 4 + out["quarter"] - 1
    prev = out[["state", "brand", "period", "rx_count"]].rename(columns={"rx_count": "prev_rx"})
    prev["period"] += 1
    out = out.merge(prev, on=["state", "brand", "period"], how="left")
    out["rx_qoq_growth"] = (out["rx_count"] - out["prev_rx"]) / out["prev_rx"].where(out["prev_rx"] > 0)

    return out.drop(columns=["period", "prev_rx"]).sort_values(["state", "year", "quarter", "brand"])


def national_quarter(state_rows: pd.DataFrame) -> pd.DataFrame:
    out = state_rows.groupby(["year", "quarter", "brand"], as_index=False)[["rx_count", "units", "spend"]].sum()
    class_rx = out.groupby(["year", "quarter"])["rx_count"].transform("sum")
    out["share_of_class_rx"] = out["rx_count"] / class_rx
    return out.sort_values(["year", "quarter", "brand"])


def main(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    lookup = load_ndc_lookup()
    sdud = load_sdud()
    state_rows = state_quarter(sdud, lookup)
    tables = {
        "glp1_state_quarter": state_rows,
        "glp1_national_quarter": national_quarter(state_rows),
        "unmatched_ndcs": unmatched_ndcs(sdud, lookup),
    }
    for name, table in tables.items():
        table.to_csv(out_dir / f"{name}.csv", index=False)
        print(f"{name}: {len(table):,} rows")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "reference")
