# Prompt given to the agent

Exactly as sent. The agent worked in a folder holding only `data/raw/`, `legacy/pipeline.py` and
an API key file, so it couldn't see the README, the reference outputs or the scorer. Running the
legacy pipeline (step 5) gave it the same three tables as `reference/`, which is the point of a
parallel run.

```text
You are migrating a legacy analytics pipeline into Dataiku DSS. You're working alone in the background: there is nobody to ask, so make reasonable decisions and note them.

Ground rules:
- Work only inside /home/user/migration-workspace-b and the Dataiku instance below. Don't open, list or search any other folder on this machine (nothing else under /home/user, no other workspaces).
- You may read Dataiku's own documentation online (doc.dataiku.com, developer.dataiku.com). Don't look up anything else about this dataset or task.

Dataiku: DSS 15.2.1 (Free Edition) at http://localhost:11000. An admin API key is in /home/user/migration-workspace-b/.dss_api_key. Use the Dataiku Python API client (dataikuapi), which is importable with this interpreter:
  PYTHONPATH=/opt/dss/dataiku-dss-15.2.1/python /opt/dss/data/bin/python
The system python3 has pandas, which the legacy pipeline needs.

Task:
1. Create a Dataiku project with key GLP1_MEDICAID_B and upload the three input files in data/raw/ as datasets: sdud_2024_2025.csv, fda_product.txt and fda_package.txt. The two FDA files are tab-separated.
2. Rebuild the logic of legacy/pipeline.py as a Dataiku Flow. Use visual recipes (Prepare, Join, Group, Window, Filter, Distinct, Stack and so on) for every step a visual recipe can do. Use a code recipe only for a step no visual recipe can do, and say which step and why.
3. The Flow must produce three datasets with exactly these names and columns:
   - glp1_state_quarter: state, year, quarter, brand, generic_name, rx_count, units, spend, share_of_class_rx, rx_qoq_growth
   - glp1_national_quarter: year, quarter, brand, rx_count, units, spend, share_of_class_rx
   - unmatched_ndcs: ndc, sdud_product_name, rows, rx_count, spend
4. Build the three datasets in Dataiku, then export each one as a CSV file with a header row to /home/user/migration-workspace-b/output/, named after the dataset (for example glp1_state_quarter.csv). The CSVs must be the data Dataiku computed, read back from the Dataiku datasets.
5. Run the legacy pipeline with `python3 legacy/pipeline.py /home/user/migration-workspace-b/legacy_out` and compare its three tables with your exported ones, row by row. Fix the Flow (not the exported files) until they match, rebuild, and export again.

When you're done, reply with:
- every recipe in the Flow, in order: name, type, and what it does
- any step you did with a code recipe instead of a visual one, and why
- every difference the comparison found, what caused it, and how you fixed it
- anything you weren't sure about, and the choice you made
- problems you hit with Dataiku or its API, and how you got past them
```
