"""The scorer must pass the reference against itself and fail each check when what it guards breaks."""

import shutil
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "score"))

from compare import score  # noqa: E402

REFERENCE = ROOT / "reference"
STATE, NATIONAL, UNMATCHED = "glp1_state_quarter", "glp1_national_quarter", "unmatched_ndcs"
N_CHECKS = 13


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
    return {c.name for c in checks if not c.passed}


def check(checks, name):
    return next(c for c in checks if c.name == name)


def test_reference_scores_itself_perfectly(candidate):
    checks = score(candidate, REFERENCE)
    assert len(checks) == N_CHECKS
    assert not failed(checks), [c for c in checks if not c.passed]


def test_column_order_case_and_row_order_dont_matter(candidate):
    df = read(candidate, STATE)
    df = df[list(reversed(df.columns))].sample(frac=1, random_state=0)
    df.columns = [c.upper() for c in df.columns]
    write(df, candidate, STATE)
    assert not failed(score(candidate, REFERENCE))


def test_values_rounded_to_six_significant_digits_pass(candidate):
    for table in (STATE, NATIONAL, UNMATCHED):
        df = read(candidate, table)
        for col in df.select_dtypes("number").columns:
            df[col] = df[col].map(lambda x: float(f"{x:.6g}"))
        write(df, candidate, table)
    assert not failed(score(candidate, REFERENCE))


def test_years_written_as_decimals_pass(candidate):
    df = read(candidate, STATE)
    write(df.assign(year=df["year"].astype(float)), candidate, STATE)
    assert not failed(score(candidate, REFERENCE))


def test_national_total_rows_are_caught(candidate):
    df = read(candidate, STATE)
    xx = df[df["state"] == "CA"].assign(state="XX")
    write(pd.concat([df, xx]), candidate, STATE)
    assert {"No national-total rows", "Same state-quarter-brand rows"} <= failed(score(candidate, REFERENCE))


def test_unsummed_payment_types_are_caught(candidate):
    df = read(candidate, STATE)
    half = df.assign(rx_count=df["rx_count"] / 2)
    write(pd.concat([half, half]), candidate, STATE)
    assert {"One row per state, quarter and brand", "Prescriptions match"} <= failed(score(candidate, REFERENCE))


def test_repeated_keys_score_the_same_in_any_row_order(candidate):
    df = read(candidate, STATE)
    df = pd.concat([df, df.head(50).assign(rx_count=1.0)])
    results = []
    for seed in (0, 1):
        write(df.sample(frac=1, random_state=seed), candidate, STATE)
        results.append([(c.name, c.passed, c.detail) for c in score(candidate, REFERENCE)])
    assert results[0] == results[1]


def test_a_missing_brand_is_caught(candidate):
    df = read(candidate, STATE)
    write(df[df["brand"] != "EXENATIDE"], candidate, STATE)
    assert {"Same brands", "Same state-quarter-brand rows"} <= failed(score(candidate, REFERENCE))


@pytest.mark.parametrize("column, change, check_name", [
    ("generic_name", lambda s: s.str.upper(), "Generic names match"),
    ("rx_count", lambda s: s + 1, "Prescriptions match"),
    ("units", lambda s: s * 1.01, "Units match"),
    ("spend", lambda s: s * 0.98, "Spend matches"),
    ("share_of_class_rx", lambda s: s * 1.01, "Class share matches"),
    ("rx_qoq_growth", lambda s: s.fillna(0), "Growth matches, including empty values"),
])
def test_each_state_value_is_checked(candidate, column, change, check_name):
    df = read(candidate, STATE)
    write(df.assign(**{column: change(df[column])}), candidate, STATE)
    assert failed(score(candidate, REFERENCE)) == {check_name}


def test_small_shares_are_checked_relatively(candidate):
    df = read(candidate, STATE)
    smallest = df["share_of_class_rx"].idxmin()
    df.loc[smallest, "share_of_class_rx"] *= 1.07
    write(df, candidate, STATE)
    assert "Class share matches" in failed(score(candidate, REFERENCE))


@pytest.mark.parametrize("break_it", [
    lambda df: df.assign(rx_count=df["rx_count"] * 2),
    lambda df: df.assign(units=df["units"] + 5),
    lambda df: df.assign(share_of_class_rx=df["share_of_class_rx"] * 1.01),
    # a brand replaced by a repeat of another row: same row count, wrong keys
    lambda df: pd.concat([df[df["brand"] != "EXENATIDE"], df[df["brand"] == "OZEMPIC"].head((df["brand"] == "EXENATIDE").sum())]),
])
def test_a_broken_national_table_is_caught(candidate, break_it):
    write(break_it(read(candidate, NATIONAL)), candidate, NATIONAL)
    assert failed(score(candidate, REFERENCE)) == {"National table matches"}


def test_unmatched_counts_are_checked(candidate):
    df = read(candidate, UNMATCHED)
    write(df.assign(rx_count=df["rx_count"] + 1), candidate, UNMATCHED)
    assert failed(score(candidate, REFERENCE)) == {"Unmatched NDCs reported"}


def test_unmatched_ndcs_split_into_several_rows_are_caught(candidate):
    df = read(candidate, UNMATCHED)
    first = df.head(1)
    split = pd.concat([df.iloc[1:], first.assign(rows=1), first.assign(rows=first["rows"] - 1)])
    write(split, candidate, UNMATCHED)
    assert failed(score(candidate, REFERENCE)) == {"Unmatched NDCs reported"}


def test_ndcs_without_leading_zeros_are_caught(candidate):
    df = read(candidate, UNMATCHED)
    write(df.assign(ndc=df["ndc"].astype(int)), candidate, UNMATCHED)
    result = check(score(candidate, REFERENCE), "Unmatched NDCs reported")
    assert not result.passed
    assert "leading zeros" in result.detail


def test_a_missing_table_fails_its_checks_without_changing_the_count(candidate):
    (candidate / f"{UNMATCHED}.csv").unlink()
    checks = score(candidate, REFERENCE)
    assert len(checks) == N_CHECKS
    assert failed(checks) == {"All three tables, with the right columns", "Unmatched NDCs reported"}


def test_a_missing_column_fails_only_its_own_check(candidate):
    write(read(candidate, STATE).drop(columns="generic_name"), candidate, STATE)
    checks = score(candidate, REFERENCE)
    assert len(checks) == N_CHECKS
    assert failed(checks) == {"All three tables, with the right columns", "Generic names match"}


@pytest.mark.parametrize("contents", [
    "",  # an export that wrote nothing
    "state,STATE,year,quarter,brand\nCA,CA,2024,1,OZEMPIC\n",  # columns repeated after lower-casing
    None,  # a year that isn't a whole number
])
def test_unreadable_tables_are_reported_not_crashed(candidate, contents):
    if contents is None:
        df = read(candidate, STATE)
        write(df.assign(year=df["year"] + 0.5), candidate, STATE)
    else:
        (candidate / f"{STATE}.csv").write_text(contents)
    checks = score(candidate, REFERENCE)
    assert len(checks) == N_CHECKS
    assert not check(checks, "All three tables, with the right columns").passed
    assert not check(checks, "Prescriptions match").passed
