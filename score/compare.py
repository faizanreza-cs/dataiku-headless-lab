"""Score a migrated pipeline's outputs against the legacy reference, rule by rule.

Usage: python score/compare.py runs/<run>/output [--reference reference] [--out runs/<run>/RESULTS.md]
"""

import argparse
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]

# table -> (key columns, value columns)
TABLES = {
    "glp1_state_quarter": (
        ["state", "year", "quarter", "brand"],
        ["generic_name", "rx_count", "units", "spend", "share_of_class_rx", "rx_qoq_growth"],
    ),
    "glp1_national_quarter": (
        ["year", "quarter", "brand"],
        ["rx_count", "units", "spend", "share_of_class_rx"],
    ),
    "unmatched_ndcs": (
        ["ndc"],
        ["sdud_product_name", "rows", "rx_count", "spend"],
    ),
}
INT_KEYS = {"year", "quarter"}
TEXT_COLUMNS = {"state", "brand", "generic_name", "ndc", "sdud_product_name"}

# Numbers must be within 0.001% of the reference value. The tiny absolute floor only matters
# for values that should be exactly zero.
RTOL, ATOL = 1e-5, 1e-9


@dataclass
class Check:
    name: str
    rule: str
    passed: bool
    detail: str


@dataclass
class Table:
    df: pd.DataFrame | None
    problem: str = ""  # why the table can't be scored at all
    missing: tuple[str, ...] = ()  # value columns it doesn't have


def load(path: Path, table: str) -> Table:
    file = path / f"{table}.csv"
    if not file.exists():
        return Table(None, f"{file.name} not found")
    try:
        df = pd.read_csv(file, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    except (pd.errors.EmptyDataError, pd.errors.ParserError, UnicodeDecodeError) as e:
        return Table(None, f"{file.name} can't be read as CSV ({e})")
    df.columns = [str(c).strip().lower() for c in df.columns]
    repeated = sorted(set(df.columns[df.columns.duplicated()]))
    if repeated:
        return Table(None, f"{file.name} has repeated columns: {', '.join(repeated)}")

    keys, values = TABLES[table]
    missing_keys = [c for c in keys if c not in df.columns]
    if missing_keys:
        return Table(None, f"{file.name} is missing key columns: {', '.join(missing_keys)}")
    present = [c for c in values if c in df.columns]
    for col in keys + present:
        if col in TEXT_COLUMNS:
            df[col] = df[col].str.strip()
        else:
            df[col] = pd.to_numeric(df[col].replace("", np.nan), errors="coerce")
    for col in INT_KEYS & set(keys):
        if (df[col].dropna() % 1 != 0).any():
            return Table(None, f"{file.name} has values in {col} that aren't whole numbers")
        df[col] = df[col].astype("Int64")
    return Table(df[keys + present], missing=tuple(c for c in values if c not in present))


def key_set(df: pd.DataFrame, keys: list[str]) -> set[tuple]:
    return set(map(tuple, df[keys].astype(str).values))


def compare_values(ref: pd.DataFrame, cand: pd.DataFrame, keys: list[str], col: str) -> tuple[int, int, str]:
    """(reference rows found in the output, how many of them differ, an example).

    A key that appears more than once in the output counts as different whatever its values,
    so the result doesn't depend on row order.
    """
    repeated = cand[cand.duplicated(keys, keep=False)]
    n_repeated = len(ref[keys].merge(repeated[keys].drop_duplicates(), on=keys))
    merged = ref[keys + [col]].merge(
        cand.drop(repeated.index)[keys + [col]], on=keys, suffixes=("_ref", "_cand")
    )
    expected, got = merged[f"{col}_ref"], merged[f"{col}_cand"]
    if col in TEXT_COLUMNS:
        same = expected == got
    else:
        close = np.isclose(got.astype(float), expected.astype(float), rtol=RTOL, atol=ATOL)
        same = (expected.isna() & got.isna()) | (close & expected.notna() & got.notna())
    bad = merged[~same]

    example = ""
    if len(bad):
        row = bad.iloc[0]
        where = ", ".join(f"{k}={row[k]}" for k in keys)
        example = f"e.g. {where}: expected {row[f'{col}_ref']}, got {row[f'{col}_cand']}"
    elif n_repeated:
        example = f"{n_repeated:,} of them appear more than once in the output"
    return len(merged) + n_repeated, len(bad) + n_repeated, example


def value_check(name: str, rule: str, ref: pd.DataFrame, cand: Table, keys: list[str], col: str) -> Check:
    if cand.df is None:
        return Check(name, rule, False, cand.problem)
    if col in cand.missing:
        return Check(name, rule, False, f"column {col} missing")
    n, bad, example = compare_values(ref, cand.df, keys, col)
    if n == 0:
        return Check(name, rule, False, "no rows in common with the reference")
    detail = f"all {n:,} matching rows agree" if bad == 0 else f"{bad:,} of {n:,} rows differ; {example}"
    return Check(name, rule, bad == 0, detail)


def state_checks(r: pd.DataFrame, cand: Table) -> list[Check]:
    keys, _ = TABLES["glp1_state_quarter"]
    structure = [
        ("No national-total rows", "1"),
        ("Same state-quarter-brand rows", "2, 4"),
        ("One row per state, quarter and brand", "3"),
        ("Same brands", "4, 5"),
    ]
    c = cand.df
    if c is None:
        checks = [Check(name, rule, False, cand.problem) for name, rule in structure]
    else:
        xx = int((c["state"] == "XX").sum())
        missing, extra = key_set(r, keys) - key_set(c, keys), key_set(c, keys) - key_set(r, keys)
        dupes = int(c.duplicated(keys).sum())
        ref_brands, cand_brands = set(r["brand"]), set(c["brand"])
        checks = [
            Check(*structure[0], xx == 0,
                  "none" if xx == 0 else f"{xx:,} rows with state XX; national totals are counted twice"),
            Check(*structure[1], not missing and not extra,
                  f"{len(r):,} rows as expected" if not missing and not extra
                  else f"{len(missing):,} missing, {len(extra):,} extra"),
            Check(*structure[2], dupes == 0,
                  "yes" if dupes == 0 else f"{dupes:,} repeated keys; payment types not summed?"),
            Check(*structure[3], ref_brands == cand_brands,
                  f"{len(ref_brands)} brands" if ref_brands == cand_brands else
                  f"missing: {sorted(ref_brands - cand_brands) or 'none'}; "
                  f"extra: {sorted(cand_brands - ref_brands) or 'none'}"),
        ]
    return checks + [
        value_check("Generic names match", "-", r, cand, keys, "generic_name"),
        value_check("Prescriptions match", "1-5", r, cand, keys, "rx_count"),
        value_check("Units match", "1-5", r, cand, keys, "units"),
        value_check("Spend matches", "6", r, cand, keys, "spend"),
        value_check("Class share matches", "5", r, cand, keys, "share_of_class_rx"),
        value_check("Growth matches, including empty values", "7", r, cand, keys, "rx_qoq_growth"),
    ]


def national_check(r: pd.DataFrame, cand: Table) -> Check:
    name, rule = "National table matches", "1"
    if cand.df is None:
        return Check(name, rule, False, cand.problem)
    keys, values = TABLES["glp1_national_quarter"]
    c = cand.df
    problems = [f"column {col} missing" for col in cand.missing]
    missing, extra = key_set(r, keys) - key_set(c, keys), key_set(c, keys) - key_set(r, keys)
    if missing or extra:
        problems.append(f"{len(missing):,} rows missing, {len(extra):,} extra")
    dupes = int(c.duplicated(keys).sum())
    if dupes:
        problems.append(f"{dupes:,} repeated rows")
    for col in values:
        if col in cand.missing:
            continue
        n, bad, example = compare_values(r, c, keys, col)
        if bad:
            problems.append(f"{col}: {bad:,} of {n:,} differ, {example}")
    return Check(name, rule, not problems, "; ".join(problems) or f"all {len(r)} rows agree")


def unmatched_check(r: pd.DataFrame, cand: Table) -> Check:
    name, rule = "Unmatched NDCs reported", "8"
    if cand.df is None:
        return Check(name, rule, False, cand.problem)
    c = cand.df
    problems = []
    ref_ndcs, cand_ndcs = set(r["ndc"]), set(c["ndc"])
    if ref_ndcs != cand_ndcs:
        message = f"{len(ref_ndcs - cand_ndcs)} missing, {len(cand_ndcs - ref_ndcs)} extra"
        if {n.zfill(11) for n in cand_ndcs} == ref_ndcs:
            message += "; NDCs lost their leading zeros (stored as numbers?)"
        problems.append(message)
    dupes = int(c["ndc"].duplicated().sum())
    if dupes:
        problems.append(f"{dupes:,} NDCs appear more than once")
    # The product name is required but not compared: SDUD truncates it, and any of an NDC's
    # spellings is a fair choice
    for col in ("rows", "rx_count", "spend"):
        if col in cand.missing:
            problems.append(f"column {col} missing")
            continue
        n, bad, example = compare_values(r, c, ["ndc"], col)
        if bad:
            problems.append(f"{col}: {bad:,} of {n:,} differ, {example}")
    return Check(name, rule, not problems,
                 "; ".join(problems) or f"all {len(ref_ndcs)} reported, with the same counts")


def score(candidate: Path, reference: Path) -> list[Check]:
    ref = {}
    for t in TABLES:
        table = load(reference, t)
        if table.df is None or table.missing:
            raise SystemExit(f"reference/{t}.csv is incomplete. Run python legacy/pipeline.py first.")
        ref[t] = table.df
    cand = {t: load(candidate, t) for t in TABLES}

    problems = []
    for t, table in cand.items():
        if table.df is None:
            problems.append(table.problem)
        elif table.missing:
            problems.append(f"{t}.csv is missing columns: {', '.join(table.missing)}")

    return [
        Check("All three tables, with the right columns", "-", not problems, "; ".join(problems) or "found"),
        *state_checks(ref["glp1_state_quarter"], cand["glp1_state_quarter"]),
        national_check(ref["glp1_national_quarter"], cand["glp1_national_quarter"]),
        unmatched_check(ref["unmatched_ndcs"], cand["unmatched_ndcs"]),
    ]


def render(checks: list[Check], title: str) -> str:
    passed = sum(1 for c in checks if c.passed)
    lines = [
        f"# Results: {title}",
        "",
        f"Scored {date.today().isoformat()} against `reference/`: **{passed} of {len(checks)} checks passed.**",
        "",
        "| Check | Rule | Result | Detail |",
        "|---|---|---|---|",
    ]
    for c in checks:
        lines.append(f"| {c.name} | {c.rule} | {'pass' if c.passed else '**fail**'} | {c.detail.replace('|', '/')} |")
    lines += ["", "Rules are numbered as in the README's table of business rules."]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("candidate", type=Path, help="folder with the migrated pipeline's CSV outputs")
    parser.add_argument("--reference", type=Path, default=ROOT / "reference")
    parser.add_argument("--out", type=Path, help="write the results as Markdown here")
    args = parser.parse_args()

    report = render(score(args.candidate, args.reference), args.candidate.parent.name or str(args.candidate))
    print(report)
    if args.out:
        args.out.write_text(report)


if __name__ == "__main__":
    main()
