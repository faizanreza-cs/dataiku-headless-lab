# The task

Give the agent one of the two prompts below, from the root of this repository, with Dataiku
Headless installed and connected. Paste it as written: the point is to see which rules the agent
finds by itself, so don't add hints about them.

Replace `RUN_NAME` with the run's folder name, for example `2026-11-03-claude-code-blind`.

## Variant A: blind

The agent gets the legacy code and the expected columns, and nothing else.

```text
Use Dataiku Headless to migrate the pipeline in legacy/pipeline.py into a new Dataiku project
called GLP1_MEDICAID.

1. Create the project and upload the three input files in data/raw/ as datasets:
   sdud_2024_2025.csv, fda_product.txt and fda_package.txt. The two FDA files are tab-separated.
2. Rebuild the logic of legacy/pipeline.py as a Dataiku Flow, with visual recipes where they fit.
3. The Flow must produce three datasets with exactly these names and columns:
   - glp1_state_quarter: state, year, quarter, brand, generic_name, rx_count, units, spend,
     share_of_class_rx, rx_qoq_growth
   - glp1_national_quarter: year, quarter, brand, rx_count, units, spend, share_of_class_rx
   - unmatched_ndcs: ndc, sdud_product_name, rows, rx_count, spend
4. Build the three datasets, then export each one as a CSV file to runs/RUN_NAME/output/,
   named after the dataset (for example glp1_state_quarter.csv).
5. Don't read anything in reference/, score/ or tests/. Work from legacy/pipeline.py only.
```

## Variant B: with a parallel run

The same task, plus the step a careful migration includes: run the old pipeline and compare.

```text
Use Dataiku Headless to migrate the pipeline in legacy/pipeline.py into a new Dataiku project
called GLP1_MEDICAID.

1. Create the project and upload the three input files in data/raw/ as datasets:
   sdud_2024_2025.csv, fda_product.txt and fda_package.txt. The two FDA files are tab-separated.
2. Rebuild the logic of legacy/pipeline.py as a Dataiku Flow, with visual recipes where they fit.
3. The Flow must produce three datasets with exactly these names and columns:
   - glp1_state_quarter: state, year, quarter, brand, generic_name, rx_count, units, spend,
     share_of_class_rx, rx_qoq_growth
   - glp1_national_quarter: year, quarter, brand, rx_count, units, spend, share_of_class_rx
   - unmatched_ndcs: ndc, sdud_product_name, rows, rx_count, spend
4. Build the three datasets, then export each one as a CSV file to runs/RUN_NAME/output/,
   named after the dataset (for example glp1_state_quarter.csv).
5. Run the legacy pipeline with `python legacy/pipeline.py runs/RUN_NAME/legacy` and compare
   its three tables with yours, row by row. Fix the Flow until they match, and list every
   difference you found and how you fixed it.
6. Don't read anything in reference/, score/ or tests/.
```

## If the export step fails

Headless can export datasets, but if the agent can't write the files, download each dataset from
Dataiku as CSV (dataset > Export > CSV) into `runs/RUN_NAME/output/` and note it in the log.
