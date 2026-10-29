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


@dataclass
class Check:
    name: str
    rule: str
    passed: bool | None  # None: couldn't be checked
    detail: str


def load(path: Path, table: str) -> pd.DataFrame | str:
    """The table with normalised types, or a message saying why it can't be scored."""
    file = path / f"{table}.csv"
    if not file.exists():
        return f"{file.name} not found"
    df = pd.read_csv(file, dtype=str, keep_default_na=False)
    df.columns = [c.strip().lower() for c in df.columns]
    keys, values = TABLES[table]
    missing = [c for c in keys + values if c not in df.columns]
    if missing:
        return f"{file.name} is missing columns: {', '.join(missing)}"
    for col in keys + values:
        if col in TEXT_COLUMNS:
            df[col] = df[col].str.strip()
        else:
            df[col] = pd.to_numeric(df[col].replace("", np.nan), errors="coerce")
    for col in INT_KEYS & set(keys):
        df[col] = df[col].astype("Int64")
    return df[keys + values]


def compare_values(ref: pd.DataFrame, cand: pd.DataFrame, keys: list[str], col: str) -> tuple[int, int, str]:
    """(rows compared, rows that differ, an example) over the keys both tables have."""
    merged = ref[keys + [col]].merge(
        cand[keys + [col]].drop_duplicates(keys), on=keys, suffixes=("_ref", "_cand")
    )
    a, b = merged[f"{col}_ref"], merged[f"{col}_cand"]
    if col in TEXT_COLUMNS:
        same = (a == b)
    else:
        both_empty = a.isna() & b.isna()
        close = np.isclose(a.astype(float), b.astype(float), rtol=1e-6, atol=1e-6)
        same = both_empty | (close & a.notna() & b.notna())
    bad = merged[~same]
    example = ""
    if len(bad):
        row = bad.iloc[0]
        where = ", ".join(f"{k}={row[k]}" for k in keys)
        example = f"e.g. {where}: expected {row[f'{col}_ref']}, got {row[f'{col}_cand']}"
    return len(merged), len(bad), example


def value_check(name: str, rule: str, ref, cand, keys, col) -> Check:
    n, bad, example = compare_values(ref, cand, keys, col)
    if n == 0:
        return Check(name, rule, False, "no rows in common with the reference")
    detail = f"all {n:,} matching rows agree" if bad == 0 else f"{bad:,} of {n:,} rows differ; {example}"
    return Check(name, rule, bad == 0, detail)


def score(candidate: Path, reference: Path) -> list[Check]:
    ref = {t: load(reference, t) for t in TABLES}
    for t, df in ref.items():
        if isinstance(df, str):
            raise SystemExit(f"reference is incomplete: {df}. Run python legacy/pipeline.py first.")
    cand = {t: load(candidate, t) for t in TABLES}

    checks = [
        Check(
            "All three tables, with the right columns", "-",
            all(not isinstance(df, str) for df in cand.values()),
            "; ".join(df for df in cand.values() if isinstance(df, str)) or "found",
        )
    ]

    keys, _ = TABLES["glp1_state_quarter"]
    r, c = ref["glp1_state_quarter"], cand["glp1_state_quarter"]
    if isinstance(c, str):
        checks.append(Check("State table", "-", None, c))
    else:
        xx = int((c["state"] == "XX").sum())
        checks.append(Check(
            "No national-total rows", "1", xx == 0,
            "none" if xx == 0 else f"{xx:,} rows with state XX; national totals are counted twice",
        ))

        ref_keys = set(map(tuple, r[keys].astype(str).values))
        cand_keys = set(map(tuple, c[keys].astype(str).values))
        missing, extra = ref_keys - cand_keys, cand_keys - ref_keys
        checks.append(Check(
            "Same state-quarter-brand rows", "2, 4", not missing and not extra,
            f"{len(ref_keys):,} rows as expected" if not missing and not extra
            else f"{len(missing):,} missing, {len(extra):,} extra",
        ))

        dupes = int(c.duplicated(keys).sum())
        checks.append(Check(
            "One row per state, quarter and brand", "3", dupes == 0,
            "yes" if dupes == 0 else f"{dupes:,} repeated keys; payment types not summed?",
        ))

        ref_brands, cand_brands = set(r["brand"]), set(c["brand"])
        checks.append(Check(
            "Same brands", "4, 5", ref_brands == cand_brands,
            f"{len(ref_brands)} brands" if ref_brands == cand_brands else
            f"missing: {sorted(ref_brands - cand_brands) or 'none'}; extra: {sorted(cand_brands - ref_brands) or 'none'}",
        ))

        checks.append(value_check("Prescriptions match", "1-5", r, c, keys, "rx_count"))
        checks.append(value_check("Units match", "1-5", r, c, keys, "units"))
        checks.append(value_check("Spend matches", "6", r, c, keys, "spend"))
        checks.append(value_check("Class share matches", "5", r, c, keys, "share_of_class_rx"))
        checks.append(value_check("Growth matches, including empty values", "7", r, c, keys, "rx_qoq_growth"))

    nkeys, _ = TABLES["glp1_national_quarter"]
    r, c = ref["glp1_national_quarter"], cand["glp1_national_quarter"]
    if isinstance(c, str):
        checks.append(Check("National table", "-", None, c))
    else:
        parts = [compare_values(r, c, nkeys, col) for col in ("rx_count", "spend", "share_of_class_rx")]
        rows_ok = len(c) == len(r)
        ok = rows_ok and all(bad == 0 and n > 0 for n, bad, _ in parts)
        detail = f"{len(r)} rows agree" if ok else (
            f"{len(c)} rows (expected {len(r)}); " if not rows_ok else ""
        ) + "; ".join(ex for _, bad, ex in parts if bad)
        checks.append(Check("National table matches", "1", ok, detail.strip("; ") or "no rows in common"))

    r, c = ref["unmatched_ndcs"], cand["unmatched_ndcs"]
    if isinstance(c, str):
        checks.append(Check("Unmatched NDCs reported", "8", None, c))
    else:
        ref_ndcs, cand_ndcs = set(r["ndc"]), set(c["ndc"])
        detail = f"all {len(ref_ndcs)} reported"
        if ref_ndcs != cand_ndcs:
            detail = f"{len(ref_ndcs - cand_ndcs)} missing, {len(cand_ndcs - ref_ndcs)} extra"
            if {n.zfill(11) for n in cand_ndcs} == ref_ndcs:
                detail += "; NDCs lost their leading zeros (stored as numbers?)"
        checks.append(Check("Unmatched NDCs reported", "8", ref_ndcs == cand_ndcs, detail))

    return checks


def render(checks: list[Check], title: str) -> str:
    passed = sum(1 for c in checks if c.passed)
    mark = {True: "pass", False: "**fail**", None: "not checked"}
    lines = [
        f"# Results: {title}",
        "",
        f"Scored {date.today().isoformat()} against `reference/`: **{passed} of {len(checks)} checks passed.**",
        "",
        "| Check | Rule | Result | Detail |",
        "|---|---|---|---|",
    ]
    for c in checks:
        lines.append(f"| {c.name} | {c.rule} | {mark[c.passed]} | {c.detail.replace('|', '/')} |")
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
