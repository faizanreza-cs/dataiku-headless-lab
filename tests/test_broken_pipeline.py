"""End to end: a full pipeline run that loses one rule must fail that rule's checks."""

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "legacy"))
sys.path.insert(0, str(ROOT / "score"))

import pipeline  # noqa: E402
from compare import score  # noqa: E402

ORIGINAL = {name: getattr(pipeline, name) for name in ("load_ndc_lookup", "state_quarter")}


def sdud_loader(keep_national=False, keep_suppressed=False, spend="Total Amount Reimbursed"):
    """pipeline.load_sdud with one of its rules switched off."""
    def load():
        sdud = pd.read_csv(pipeline.RAW / "sdud_2024_2025.csv",
                           dtype={"State": str, "NDC": str, "Suppression Used": str, "Product Name": str})
        if not keep_national:
            sdud = sdud[sdud["State"] != "XX"]
        if not keep_suppressed:
            sdud = sdud[sdud["Suppression Used"].str.lower() != "true"]
        sdud = sdud.rename(columns={
            "State": "state", "NDC": "ndc", "Year": "year", "Quarter": "quarter",
            "Product Name": "sdud_product_name", "Units Reimbursed": "units",
            "Number of Prescriptions": "rx_count", spend: "spend",
        })
        sdud["sdud_product_name"] = sdud["sdud_product_name"].str.strip()
        return sdud[["state", "ndc", "year", "quarter", "sdud_product_name", "units", "rx_count", "spend"]]
    return load


def naive_ndc11(package_code: str) -> str:
    # Pads the whole code instead of each segment: right for 4-4-2, wrong for 5-3-2 and 5-4-1
    return package_code.replace("-", "").zfill(11)


def glp1_by_name():
    lookup = ORIGINAL["load_ndc_lookup"]()
    lookup["is_glp1"] = lookup["generic_name"].str.endswith("glutide")
    return lookup


def growth_on_previous_row(sdud, lookup):
    out = ORIGINAL["state_quarter"](sdud, lookup).sort_values(["state", "brand", "year", "quarter"])
    prev = out.groupby(["state", "brand"])["rx_count"].shift()
    return out.assign(rx_qoq_growth=(out["rx_count"] - prev) / prev)


def no_unmatched_table(sdud, lookup):
    return pd.DataFrame(columns=["ndc", "sdud_product_name", "rows", "rx_count", "spend"])


BROKEN = {
    "1 keeps national totals": (
        "load_sdud", sdud_loader(keep_national=True),
        {"No national-total rows", "National table matches"}),
    "2 keeps suppressed rows": (
        "load_sdud", sdud_loader(keep_suppressed=True),
        {"Same state-quarter-brand rows"}),
    "4 pads the whole NDC": (
        "to_ndc11", naive_ndc11,
        {"Same brands", "Prescriptions match", "Unmatched NDCs reported"}),
    "5 finds GLP-1 drugs by name": (
        "load_ndc_lookup", glp1_by_name,
        {"Same brands", "Class share matches"}),
    "6 uses the Medicaid-only amount": (
        "load_sdud", sdud_loader(spend="Medicaid Amount Reimbursed"),
        {"Spend matches", "National table matches"}),
    "7 compares with the previous row": (
        "state_quarter", growth_on_previous_row,
        {"Growth matches, including empty values"}),
    "8 drops unmatched NDCs": (
        "unmatched_ndcs", no_unmatched_table,
        {"Unmatched NDCs reported"}),
}


def test_the_loader_above_matches_the_pipeline_with_no_rule_switched_off(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "load_sdud", sdud_loader())
    pipeline.main(tmp_path)
    assert all(c.passed for c in score(tmp_path, ROOT / "reference"))


@pytest.mark.parametrize("rule", BROKEN)
def test_losing_a_rule_fails_its_checks(tmp_path, monkeypatch, rule):
    name, replacement, expected = BROKEN[rule]
    monkeypatch.setattr(pipeline, name, replacement)
    pipeline.main(tmp_path)
    failed = {c.name for c in score(tmp_path, ROOT / "reference") if not c.passed}
    assert expected <= failed, failed


def test_naive_padding_loses_generic_exenatide(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "to_ndc11", naive_ndc11)
    pipeline.main(tmp_path)
    brands = next(c for c in score(tmp_path, ROOT / "reference") if c.name == "Same brands")
    assert "EXENATIDE" in brands.detail
