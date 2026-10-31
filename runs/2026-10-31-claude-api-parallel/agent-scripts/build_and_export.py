"""Build the three output datasets in Dataiku, then export each one to CSV by reading it back from Dataiku."""
import csv
import os
from common import *

OUT = "/home/user/migration-workspace-b/output"
TARGETS = ["glp1_state_quarter", "glp1_national_quarter", "unmatched_ndcs"]

p = proj()
job = p.new_job("RECURSIVE_FORCED_BUILD")
for t in TARGETS:
    job.with_output(t, object_type="DATASET")
res = job.start_and_wait()
print("build job:", res.get_status()["baseStatus"]["state"])


def fmt(v):
    if v is None:
        return ""
    if isinstance(v, float):
        return repr(v)  # shortest round-trip representation of the double Dataiku returned
    return str(v)


os.makedirs(OUT, exist_ok=True)
for t in TARGETS:
    d = p.get_dataset(t)
    cols = [c["name"] for c in d.get_schema()["columns"]]
    n = 0
    with open(os.path.join(OUT, t + ".csv"), "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(cols)
        for row in d.iter_rows():
            w.writerow([fmt(v) for v in row])
            n += 1
    print(f"{t}: {n:,} rows -> {OUT}/{t}.csv")
