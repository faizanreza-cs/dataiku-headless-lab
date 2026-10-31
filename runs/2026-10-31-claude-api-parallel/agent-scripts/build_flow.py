"""Builds the GLP1_MEDICAID_B Flow (port of legacy/pipeline.py) with visual recipes only.

Idempotent: deletes every recipe and every non-input dataset, then recreates them.
"""
from common import *
from dataikuapi.dss.utils import DSSFilter, DSSFilterOperator

p = proj()
INPUTS = {"sdud_2024_2025", "fda_product", "fda_package"}
GLP1_CLASS = "GLP-1 Receptor Agonist [EPC]"

# ---------------------------------------------------------------- teardown
for r in p.list_recipes():
    p.get_recipe(r["name"]).delete()
for d in p.list_datasets():
    if d["name"] not in INPUTS:
        p.get_dataset(d["name"]).delete(drop_data=True)


# ---------------------------------------------------------------- helpers
def managed(name):
    b = p.new_managed_dataset(name)
    b.with_store_into("filesystem_managed", format_option_id="CSV")
    return b.create()


def create(rtype, name, inputs, output):
    b = p.new_recipe(rtype, name)
    for i in inputs:
        b.with_input(i)
    if hasattr(b, "with_new_output"):
        b.with_new_output(output, "filesystem_managed", format_option_id="CSV")
    else:  # Top N creator has no with_new_output
        managed(output)
        b.with_output(output)
    return b.create()


def propagate(r):
    upd = r.compute_schema_updates()
    if upd.any_action_required():
        upd.apply()


def set_types(ds, **types):
    d = p.get_dataset(ds)
    sch = d.get_schema()
    for c in sch["columns"]:
        if c["name"] in types:
            c["type"] = types[c["name"]]
    d.set_schema(sch)


def describe(r, text):
    s = r.get_settings()
    s.get_recipe_raw_definition()["shortDesc"] = text
    s.save()


def join(name, left, right, out, on, left_cols, right_cols, jtype="LEFT", unmatched_left=None, desc=""):
    r = create("join", name, [left, right], out)
    s = r.get_settings()
    pl = s.get_json_payload()
    pl["joins"] = []
    s.set_json_payload(pl)
    j = s.add_join(jtype, 0, 1)
    for c in on:
        s.add_condition_to_join(j, "EQ", c, c)
    for vi in s.raw_virtual_inputs:
        vi["outputColumnsSelectionMode"] = "MANUAL"
    pl = s.get_json_payload()
    pl["selectedColumns"] = [{"name": c, "table": 0} for c in left_cols] + [{"name": c, "table": 1} for c in right_cols]
    s.set_json_payload(pl)
    if unmatched_left:
        managed(unmatched_left)
        s.set_unmatched_output(unmatched_left, side="left")
    s.get_recipe_raw_definition()["shortDesc"] = desc
    s.save()
    propagate(r)
    return r


def group(name, inp, out, keys, aggs, renames, global_count=False, desc="", computed=None):
    r = create("grouping", name, [inp], out)
    s = r.get_settings()
    s.clear_grouping_keys()
    for k in keys:
        s.add_grouping_key(k)
    pl = s.get_json_payload()
    pl["computedColumns"] = computed or []
    for cc in pl["computedColumns"]:
        pl["values"].append({"column": cc["name"], "type": cc["type"]})
    for v in pl["values"]:
        for f in ("min", "max", "count", "countDistinct", "sum", "concat", "stddev", "avg", "mode",
                  "first", "last", "median", "sum2"):
            v[f] = False
    order = [c for c, _ in aggs]
    pl["values"].sort(key=lambda v: order.index(v["column"]) if v["column"] in order else len(order))
    s.set_json_payload(pl)
    for col, fn in aggs:
        s.get_or_create_column_settings(col)[fn] = True
    s.set_global_count_enabled(global_count)
    pl = s.get_json_payload()
    pl["outputColumnNameOverrides"] = renames
    s.set_json_payload(pl)
    s.get_recipe_raw_definition()["shortDesc"] = desc
    s.save()
    propagate(r)
    return r


def prepare(name, inp, out, steps, desc=""):
    if inp not in INPUTS:  # a Prepare recipe infers its output schema from a sample of built input data
        p.get_dataset(inp).build(job_type="RECURSIVE_BUILD")
    r = create("shaker", name, [inp], out)
    s = r.get_settings()
    for t, params in steps:
        s.add_processor_step(t, params)
    s.get_recipe_raw_definition()["shortDesc"] = desc
    s.save()
    propagate(r)
    return r


def sort(name, inp, out, keys, desc=""):
    r = create("sort", name, [inp], out)
    s = r.get_settings()
    s.clear_sorting_keys()
    for k in keys:
        s.add_sorting_key(k, ascending=True)
    s.get_recipe_raw_definition()["shortDesc"] = desc
    s.save()
    propagate(r)
    return r


def formula(col, expr):
    return ("CreateColumnWithGREL", {"column": col, "expression": expr, "errorColumn": ""})


def keep(cols):
    return ("ColumnsSelector", {"appliesTo": "COLUMNS", "columns": cols, "keep": True})


def zfill(col, n):
    # Python str.zfill(n): left-pad with zeros to width n, never truncate
    return f'if(length({col}) >= {n}, {col}, substring(concat("{"0" * n}", {col}), length({col})))'


# ================================================================ FDA NDC lookup
# 1. package -> product on PRODUCTID (not PRODUCTNDC: a product NDC can be listed more than once)
join("join_fda_package_product", "fda_package", "fda_product", "fda_package_product", ["PRODUCTID"],
     ["PRODUCTID", "NDCPACKAGECODE"], ["PROPRIETARYNAME", "NONPROPRIETARYNAME", "PHARM_CLASSES"], jtype="INNER",
     desc="Inner join FDA packages to products on PRODUCTID")

# 2. 11-digit NDC (each 4-4-2 / 5-3-2 / 5-4-1 segment padded on its own), normalised brand / generic, GLP-1 flag
r = prepare("prepare_ndc_lookup", "fda_package_product", "fda_ndc_candidates", [
    ("ColumnSplitter", {"inCol": "NDCPACKAGECODE", "separator": "-", "outColPrefix": "ndc_seg_", "target": "COLUMNS",
                        "limitOutput": False, "limit": 0, "startFrom": "beginning"}),
    formula("ndc", "concat(" + ", ".join([zfill("ndc_seg_0", 5), zfill("ndc_seg_1", 4), zfill("ndc_seg_2", 2)]) + ")"),
    formula("brand", "toUppercase(trim(PROPRIETARYNAME))"),
    formula("generic_name", "toLowercase(trim(NONPROPRIETARYNAME))"),
    formula("is_glp1", f'contains(PHARM_CLASSES, "{GLP1_CLASS}")'),
    keep(["PRODUCTID", "ndc", "brand", "generic_name", "is_glp1"]),
], desc="NDC package code -> 11-digit NDC; brand upper-cased, generic lower-cased; GLP-1 class flag")
set_types("fda_ndc_candidates", ndc="string", is_glp1="boolean")

# 3. one row per NDC: the one with the smallest PRODUCTID (sort_values(["ndc","PRODUCTID"]).drop_duplicates("ndc"))
r = create("topn", "topn_ndc_lookup", ["fda_ndc_candidates"], "ndc_lookup")
s = r.get_settings()
pl = s.get_json_payload()
pl.update({"keys": ["ndc"], "orders": [{"column": "PRODUCTID", "desc": False}], "firstRows": 1, "lastRows": 0})
s.set_json_payload(pl)
s.get_recipe_raw_definition()["shortDesc"] = "Deduplicate NDCs: keep the row with the lowest PRODUCTID per ndc"
s.save()
propagate(r)

# ================================================================ SDUD
ren = {"State": "state", "NDC": "ndc", "Year": "year", "Quarter": "quarter", "Suppression Used": "suppressed",
       "Product Name": "sdud_product_name", "Units Reimbursed": "units", "Number of Prescriptions": "rx_count",
       "Total Amount Reimbursed": "spend"}
prepare("prepare_sdud", "sdud_2024_2025", "sdud_clean", [
    ("ColumnRenamer", {"renamings": [{"from": k, "to": v} for k, v in ren.items()]}),
    # "XX" rows are national totals, already the sum of the states
    ("FilterOnValue", {"appliesTo": "SINGLE_COLUMN", "columns": ["state"], "action": "REMOVE_ROW", "values": ["XX"],
                       "matchingMode": "FULL_STRING", "normalizationMode": "EXACT", "booleanMode": "AND"}),
    # suppressed rows (fewer than 11 prescriptions) have no counts; case-insensitive like str.lower() != "true"
    ("FilterOnValue", {"appliesTo": "SINGLE_COLUMN", "columns": ["suppressed"], "action": "REMOVE_ROW",
                       "values": ["true"], "matchingMode": "FULL_STRING", "normalizationMode": "LOWERCASE",
                       "booleanMode": "AND"}),
    formula("sdud_product_name", "trim(sdud_product_name)"),
    # counts are zero-padded ("000000108"): make them numbers, otherwise the column is inferred as string
    formula("rx_count", "toNumber(rx_count)"),
    keep(["state", "ndc", "year", "quarter", "sdud_product_name", "units", "rx_count", "spend"]),
], desc="Rename SDUD columns, drop national XX rows and suppressed rows, trim product name")
# rx_count is double, as in the legacy tables (pandas reads it as float64 because suppressed rows are empty);
# the values are whole numbers, so sums and ratios are unaffected
set_types("sdud_clean", ndc="string", rx_count="double", year="bigint", quarter="bigint", units="double", spend="double")

# matched rows -> sdud_matched, SDUD rows whose NDC the FDA directory doesn't list -> sdud_unmatched
join("join_sdud_ndc_lookup", "sdud_clean", "ndc_lookup", "sdud_matched", ["ndc"],
     ["state", "ndc", "year", "quarter", "sdud_product_name", "units", "rx_count", "spend"],
     ["brand", "generic_name", "is_glp1"], jtype="INNER", unmatched_left="sdud_unmatched",
     desc="Attach FDA brand/generic/GLP-1 flag by ndc; unmatched SDUD rows go to sdud_unmatched")

r = create("sampling", "filter_glp1", ["sdud_matched"], "sdud_glp1")
s = r.get_settings()
f = DSSFilter.of_single_condition("is_glp1", DSSFilterOperator.IS_TRUE)
f["distinct"] = False
s.set_json_payload(f)
s.get_recipe_raw_definition()["shortDesc"] = "Keep GLP-1 Receptor Agonist rows"
s.save()
propagate(r)

# ================================================================ glp1_state_quarter
group("group_state_quarter", "sdud_glp1", "glp1_sq_totals", ["state", "year", "quarter", "brand"],
      [("generic_name", "min"), ("rx_count", "sum"), ("units", "sum"), ("spend", "sum")],
      {"generic_name_min": "generic_name", "rx_count_sum": "rx_count", "units_sum": "units", "spend_sum": "spend"},
      desc="Sum FFSU+MCOU rows per state, quarter and brand")
group("group_sq_class_rx", "glp1_sq_totals", "glp1_sq_class_totals", ["state", "year", "quarter"],
      [("rx_count", "sum")], {"rx_count_sum": "class_rx"},
      desc="GLP-1 class prescriptions per state and quarter")
join("join_sq_class_rx", "glp1_sq_totals", "glp1_sq_class_totals", "glp1_sq_with_class",
     ["state", "year", "quarter"],
     ["state", "year", "quarter", "brand", "generic_name", "rx_count", "units", "spend"], ["class_rx"],
     jtype="LEFT", desc="Attach the state-quarter class total to each brand row")

# previous row of the same state+brand, ordered by period (year*4 + quarter - 1)
r = create("window", "window_sq_prev_quarter", ["glp1_sq_with_class"], "glp1_sq_with_prev")
s = r.get_settings()
pl = s.get_json_payload()
w = pl["windows"][0]
w.update({"enablePartitioning": True, "partitioningColumns": ["state", "brand"], "enableOrdering": True,
          "orders": [{"column": "period", "desc": False}], "enableLimits": False,
          "limitPreceding": False, "limitFollowing": False})
pl["computedColumns"] = [{"mode": "GREL", "name": "period", "type": "bigint", "expr": "year * 4 + quarter - 1"}]
pl["values"].append({"column": "period", "value": True, "lagValues": "1", "leadValues": "1", "dateDiffUnit": "DAY"})
for v in pl["values"]:
    for fl in ("last", "lagDiff", "max", "count", "sum", "concat", "lead", "concatDistinct", "min", "countDistinct",
               "avg", "lag", "stddev", "leadDiff", "first"):
        v[fl] = False
    v["value"] = True
    if v["column"] in ("rx_count", "period"):
        v["lag"] = True
        v["lagValues"] = "1"
pl["outputColumnNameOverrides"] = {"rx_count_lag": "prev_rx", "period_lag": "prev_period"}
s.set_json_payload(pl)
s.get_recipe_raw_definition()["shortDesc"] = "LAG(1) of rx_count and period within state+brand, ordered by period"
s.save()
propagate(r)

prepare("prepare_glp1_state_quarter", "glp1_sq_with_prev", "glp1_sq_final", [
    formula("share_of_class_rx", "rx_count / class_rx"),
    # growth against the previous calendar quarter only; empty if the brand had no row for it, or it had 0 rx
    formula("rx_qoq_growth",
            "if(prev_period == period - 1 && prev_rx > 0, (rx_count - prev_rx) / prev_rx, null)"),
    keep(["state", "year", "quarter", "brand", "generic_name", "rx_count", "units", "spend",
          "share_of_class_rx", "rx_qoq_growth"]),
], desc="share_of_class_rx and rx_qoq_growth")
set_types("glp1_sq_final", share_of_class_rx="double", rx_qoq_growth="double")
sort("sort_glp1_state_quarter", "glp1_sq_final", "glp1_state_quarter", ["state", "year", "quarter", "brand"],
     desc="Order by state, year, quarter, brand")

# ================================================================ glp1_national_quarter
group("group_national_quarter", "glp1_sq_totals", "glp1_nq_totals", ["year", "quarter", "brand"],
      [("rx_count", "sum"), ("units", "sum"), ("spend", "sum")],
      {"rx_count_sum": "rx_count", "units_sum": "units", "spend_sum": "spend"},
      desc="Sum the state rows per quarter and brand")
group("group_nq_class_rx", "glp1_nq_totals", "glp1_nq_class_totals", ["year", "quarter"],
      [("rx_count", "sum")], {"rx_count_sum": "class_rx"},
      desc="National GLP-1 class prescriptions per quarter")
join("join_nq_class_rx", "glp1_nq_totals", "glp1_nq_class_totals", "glp1_nq_with_class", ["year", "quarter"],
     ["year", "quarter", "brand", "rx_count", "units", "spend"], ["class_rx"], jtype="LEFT",
     desc="Attach the national quarter class total to each brand row")
prepare("prepare_glp1_national_quarter", "glp1_nq_with_class", "glp1_nq_final", [
    formula("share_of_class_rx", "rx_count / class_rx"),
    keep(["year", "quarter", "brand", "rx_count", "units", "spend", "share_of_class_rx"]),
], desc="share_of_class_rx")
set_types("glp1_nq_final", share_of_class_rx="double")
sort("sort_glp1_national_quarter", "glp1_nq_final", "glp1_national_quarter", ["year", "quarter", "brand"],
     desc="Order by year, quarter, brand")

# ================================================================ unmatched_ndcs
# rows = number of SDUD rows per NDC (pandas "size"): count of a constant pre-computed column, which is never
# null, so it equals the group size and sits in the legacy column position (the built-in record count is
# always appended as the last column)
group("group_unmatched_ndcs", "sdud_unmatched", "unmatched_ndc_totals", ["ndc"],
      [("sdud_product_name", "min"), ("record", "count"), ("rx_count", "sum"), ("spend", "sum")],
      {"sdud_product_name_min": "sdud_product_name", "record_count": "rows", "rx_count_sum": "rx_count",
       "spend_sum": "spend"},
      computed=[{"mode": "GREL", "name": "record", "type": "bigint", "expr": "1"}],
      desc="Per unmatched NDC: product name, row count, prescriptions, spend")
sort("sort_unmatched_ndcs", "unmatched_ndc_totals", "unmatched_ndcs", ["ndc"], desc="Order by ndc")

for ds in ["glp1_state_quarter", "glp1_national_quarter", "unmatched_ndcs"]:
    print(ds, [(c["name"], c["type"]) for c in p.get_dataset(ds).get_schema()["columns"]])
