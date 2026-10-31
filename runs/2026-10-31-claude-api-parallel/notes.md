# Run notes

- Date: 31 October 2026
- Agent: Claude, run as a Claude Code subagent, with no person in the loop
- How it built the Flow: Dataiku's Python API (`dataikuapi`). No Headless and no Cobuild: this
  instance has no LLM connection, which Cobuild needs.
- Dataiku: DSS 15.2.1, Free Edition, self-hosted on a 4-CPU, 15 GB machine
- Variant: B, parallel run. The agent ran the legacy pipeline and compared tables row by row.
- Started 14:10 UTC, finished 14:30 UTC (20 minutes)
- Interventions: none
- Score: 13 of 13 (see `RESULTS.md`)

## Was it blind?

The agent worked in a folder holding only `data/raw/`, `legacy/pipeline.py` and an API key file.
Afterwards I went through every command it ran: it read files only in that folder (including the
legacy outputs it was asked to produce), Dataiku's documentation online, and the scripts it wrote
itself in its scratch folder. It never opened this repo, `reference/`, the scorer or the blind run's
files.

## What it built

19 visual recipes, no code recipes. The main difference from the blind run: class totals come
from a Group recipe joined back onto the rows, not a Window recipe (see below).

1. Join FDA packages to products on PRODUCTID
2. Prepare: 11-digit NDC by padding each segment, upper-case brand, lower-case generic name, GLP-1
   flag from the pharmacologic class
3. Top N: one row per NDC, the smallest PRODUCTID
4. Prepare the SDUD rows: rename, drop state XX, drop suppressed rows, trim names, numeric counts
5. Join to the lookup on NDC, unmatched rows to their own output
6. Filter to GLP-1 drugs
7. to 12. Group by state, quarter and brand; Group the class total and Join it back; Window for the
   previous quarter; Prepare share and growth; Sort into `glp1_state_quarter`
13. to 17. The same for `glp1_national_quarter`
18. and 19. Group and Sort into `unmatched_ndcs`

[`agent-scripts/build_flow.py`](agent-scripts/build_flow.py) recreates the whole Flow through the
API. The paths in the scripts are the agent's own workspace.

## What the comparison with the legacy pipeline found

- **Counts written as `324` instead of `324.0`.** pandas reads the count column as decimal (the
  suppressed rows are empty), and the Flow had it as whole numbers. The values were equal; the agent
  changed the type anyway so the files match.
- **Rounding noise in sums.** For example `489045.19` against `489045.18999999994`: compared as
  numbers with `reference/`, 400 cells across the three tables differ, by at most 1.5 parts in
  10^15. pandas and Dataiku add floating-point numbers in a different order. The agent left it, and
  the scorer's tolerance accepts it.

## What it ran into

- **Window recipes returned running totals**, as in the blind run. It found that only the hidden
  `legacyUnboundedWindowStreamBehavior` setting changes this, and chose not to rely on an
  undocumented flag: the class totals are a Group recipe joined back instead.
- **A Filter recipe silently ignored its condition** until the condition was placed where the API
  expects it, also as in the blind run.
- **Counts typed as text** because of their zero padding.
- **The Top N recipe builder can't create its output dataset**, so it created the dataset first.
