"""Reproduce: a Window recipe summing within a group, with no ordering, returns running totals.

Found by the agent in the 2026-10-31 blind run, and reproduced with this script on Dataiku DSS
15.2.1 (Free Edition). The recipes are created through the Python API; recipes created in the
Dataiku interface weren't checked.

Usage (with dataikuapi importable, for example via Dataiku's own interpreter):
    python findings/window_running_sum.py http://localhost:11000 <api-key-file>
"""

import sys
import tempfile
from pathlib import Path

import dataikuapi

ROWS = "g,v\na,1\na,2\na,3\nb,10\nb,20\n"  # group totals: a -> 6, b -> 30
PROJECT = "WINDOW_RUNNING_SUM_CHECK"


def window(project, name, legacy=None, frame=None):
    builder = project.new_recipe("window", name)
    builder.with_input("w_in").with_new_output(f"{name}_out", "filesystem_managed")
    recipe = builder.create()
    settings = recipe.get_settings()
    payload = settings.get_json_payload()
    w = payload["windows"][0]
    w.update({"enablePartitioning": True, "partitioningColumns": ["g"], "enableOrdering": False, "orders": []})
    if frame:
        w.update(frame)
    payload["values"] = [{"column": "v", "type": "bigint", "sum": True, "$idx": 0}]
    if legacy is not None:
        payload["legacyUnboundedWindowStreamBehavior"] = legacy
    settings.set_json_payload(payload)
    settings.save()
    recipe.compute_schema_updates().apply()
    recipe.run(wait=True)
    return sorted(tuple(r) for r in project.get_dataset(f"{name}_out").iter_rows())


def main(url: str, key_file: str) -> None:
    client = dataikuapi.DSSClient(url, Path(key_file).read_text().strip())
    if PROJECT in client.list_project_keys():
        client.get_project(PROJECT).delete(clear_managed_datasets=True)
    project = client.create_project(PROJECT, "Window running sum check", "admin")
    try:
        dataset = project.create_upload_dataset("w_in")
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as f:
            f.write(ROWS)
        with open(f.name, "rb") as data:
            dataset.uploaded_add_file(data, "w.csv")
        dataset.autodetect_settings().save()
        schema = dataset.get_schema()
        for col in schema["columns"]:
            if col["name"] == "v":
                col["type"] = "bigint"
        dataset.set_schema(schema)

        print("default settings:      ", window(project, "default"))
        print("unbounded frame:       ", window(project, "unbounded", frame={
            "enableLimits": True, "limitPreceding": False, "limitFollowing": False}))
        print("legacy flag set to true:", window(project, "legacy", legacy=True))
        print("expected group totals: a -> 6, b -> 30")
    finally:
        project.delete(clear_managed_datasets=True)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
