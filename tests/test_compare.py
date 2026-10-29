"""The scorer must pass the reference against itself and catch each kind of broken migration."""

import shutil
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "score"))

from compare import score  # noqa: E402

REFERENCE = ROOT / "reference"


@pytest.fixture
def candidate(tmp_path: Path) -> Path:
    out = tmp_path / "output"
    shutil.copytree(REFERENCE, out)
    return out


def read(path: Path, table: str) -> pd.DataFrame:
    return pd.read_csv(path / f"{table}.csv", dtype={"ndc": str})


def write(df: pd.DataFrame, path: Path, table: str) -> None:
    df.to_csv(path / f"{table}.csv", index=False)


def failed(checks) -> set[str]:
    return {c.name for c in checks if c.passed is False}


def test_reference_scores_itself_perfectly(candidate):
    checks = score(candidate, REFERENCE)
    assert all(c.passed for c in checks), [c for c in checks if not c.passed]


def test_column_order_case_and_row_order_dont_matter(candidate):
    df = read(candidate, "glp1_state_quarter")
    df = df[list(reversed(df.columns))].sample(frac=1, random_state=0)
    df.columns = [c.upper() for c in df.columns]
    write(df, candidate, "glp1_state_quarter")
    assert not failed(score(candidate, REFERENCE))


def test_national_total_rows_are_caught(candidate):
    df = read(candidate, "glp1_state_quarter")
    xx = df[df["state"] == "CA"].assign(state="XX")
    write(pd.concat([df, xx]), candidate, "glp1_state_quarter")
    assert {"No national-total rows", "Same state-quarter-brand rows"} <= failed(score(candidate, REFERENCE))


def test_unsummed_payment_types_are_caught(candidate):
    df = read(candidate, "glp1_state_quarter")
    half = df.assign(rx_count=df["rx_count"] / 2)
    write(pd.concat([half, half]), candidate, "glp1_state_quarter")
    assert {"One row per state, quarter and brand", "Prescriptions match"} <= failed(score(candidate, REFERENCE))


def test_a_missing_brand_is_caught(candidate):
    df = read(candidate, "glp1_state_quarter")
    write(df[df["brand"] != "EXENATIDE"], candidate, "glp1_state_quarter")
    assert {"Same brands", "Same state-quarter-brand rows"} <= failed(score(candidate, REFERENCE))


def test_growth_filled_with_zero_is_caught(candidate):
    df = read(candidate, "glp1_state_quarter")
    write(df.fillna({"rx_qoq_growth": 0}), candidate, "glp1_state_quarter")
    assert "Growth matches, including empty values" in failed(score(candidate, REFERENCE))


def test_medicaid_only_spend_is_caught(candidate):
    df = read(candidate, "glp1_state_quarter")
    write(df.assign(spend=df["spend"] * 0.98), candidate, "glp1_state_quarter")
    assert "Spend matches" in failed(score(candidate, REFERENCE))


def test_ndcs_without_leading_zeros_are_caught(candidate):
    df = read(candidate, "unmatched_ndcs")
    write(df.assign(ndc=df["ndc"].astype(int)), candidate, "unmatched_ndcs")
    check = next(c for c in score(candidate, REFERENCE) if c.name == "Unmatched NDCs reported")
    assert check.passed is False
    assert "leading zeros" in check.detail


def test_a_missing_table_is_reported(candidate):
    (candidate / "unmatched_ndcs.csv").unlink()
    checks = score(candidate, REFERENCE)
    assert "All three tables, with the right columns" in failed(checks)
    assert next(c for c in checks if c.name == "Unmatched NDCs reported").passed is None
