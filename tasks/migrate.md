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

## Without Cobuild: the Free Edition and the Python API

Cobuild needs an LLM connection, through Dataiku's AI Services or your own model provider. Without
one (for example on the self-hosted Free Edition, which is how the first runs here were done), the
agent can build the Flow itself through Dataiku's Python API, `dataikuapi`. That tests the same
migration, with the agent writing the recipes instead of Cobuild.

The prompts change in four ways:

- The agent gets the instance URL, an API key file and a Python interpreter with `dataikuapi`,
  instead of Headless.
- Step 2 asks for visual recipes (Prepare, Join, Group, Window, Filter, Distinct, Stack and so on)
  for every step a visual recipe can do, and a code recipe only where none can, with the reason.
  Otherwise one Python recipe holding the legacy code would pass every check without migrating
  anything.
- Variant A also says not to run `legacy/pipeline.py` or reproduce its outputs outside Dataiku,
  so it can't compare.
- Each agent works in its own folder holding only `data/raw/`, `legacy/pipeline.py` and the key
  file, so it can't read this repo's README, `reference/` or the scorer.

The exact prompts are in each run's `prompt.md`.

To install the Free Edition on Linux (Dataiku asks for 32 GB of RAM; the runs here used a machine
with 15 GB, which the small data allows):

```bash
wget https://cdn.downloads.dataiku.com/public/dss/15.2.1/dataiku-dss-15.2.1.tar.gz
tar xzf dataiku-dss-15.2.1.tar.gz
dataiku-dss-15.2.1/installer.sh -d ~/dss_data -p 11000   # prints the command for missing packages
~/dss_data/bin/dss start
```

Open http://localhost:11000, register for the Free Edition, then create an API key with
`~/dss_data/bin/dsscli api-key-create --admin true`. If `JAVA_TOOL_OPTIONS` is set on the machine,
unset it for the installer: Java prints it with its version number and the installer can't parse
the version.
