"""Row-by-row comparison of the legacy tables with the tables exported from Dataiku."""
import math
import sys
import pandas as pd

LEG = "/home/user/migration-workspace-b/legacy_out"
NEW = "/home/user/migration-workspace-b/output"
KEYS = {"glp1_state_quarter": ["state", "year", "quarter", "brand"],
        "glp1_national_quarter": ["year", "quarter", "brand"],
        "unmatched_ndcs": ["ndc"]}
STR = {"state": str, "ndc": str, "brand": str, "generic_name": str, "sdud_product_name": str}
REL, ABS = 1e-9, 1e-9

ok_all = True
for t, keys in KEYS.items():
    a = pd.read_csv(f"{LEG}/{t}.csv", dtype=STR, keep_default_na=False, na_values=[""], float_precision="round_trip")
    b = pd.read_csv(f"{NEW}/{t}.csv", dtype=STR, keep_default_na=False, na_values=[""], float_precision="round_trip")
    problems = []
    if list(a.columns) != list(b.columns):
        problems.append(f"columns differ: legacy={list(a.columns)} dataiku={list(b.columns)}")
    if len(a) != len(b):
        problems.append(f"row count differs: legacy={len(a)} dataiku={len(b)}")
    ka = set(map(tuple, a[keys].astype(str).values)); kb = set(map(tuple, b[keys].astype(str).values))
    if ka != kb:
        problems.append(f"keys only in legacy: {sorted(ka - kb)[:10]} ({len(ka - kb)}); "
                        f"only in dataiku: {sorted(kb - ka)[:10]} ({len(kb - ka)})")
    n_cells = n_bitexact_diff = 0
    max_rel = 0.0
    if not problems:
        for i in range(len(a)):
            for c in a.columns:
                x, y = a.at[i, c], b.at[i, c]
                n_cells += 1
                xnull = x is None or (isinstance(x, float) and math.isnan(x))
                ynull = y is None or (isinstance(y, float) and math.isnan(y))
                if xnull or ynull:
                    if xnull != ynull:
                        problems.append(f"row {i} {dict(a.loc[i, keys])} col {c}: legacy={x!r} dataiku={y!r}")
                    continue
                if isinstance(x, str) or isinstance(y, str):
                    if str(x) != str(y):
                        problems.append(f"row {i} {dict(a.loc[i, keys])} col {c}: legacy={x!r} dataiku={y!r}")
                    continue
                x, y = float(x), float(y)
                if x != y:
                    n_bitexact_diff += 1
                    rel = abs(x - y) / max(abs(x), abs(y))
                    max_rel = max(max_rel, rel)
                    if not math.isclose(x, y, rel_tol=REL, abs_tol=ABS):
                        problems.append(f"row {i} {dict(a.loc[i, keys])} col {c}: legacy={x!r} dataiku={y!r}")
    status = "MATCH" if not problems else f"{len(problems)} DIFFERENCES"
    ok_all &= not problems
    print(f"{t}: legacy {len(a)} rows, dataiku {len(b)} rows, {n_cells} cells compared -> {status}")
    if n_cells:
        print(f"   numeric cells not bit-identical: {n_bitexact_diff} (max relative diff {max_rel:.3g}, "
              f"tolerance rel={REL}, abs={ABS})")
    for pr in problems[:25]:
        print("   ", pr)
sys.exit(0 if ok_all else 1)
