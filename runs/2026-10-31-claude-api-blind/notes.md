# Run notes

- Date: 31 October 2026
- Agent: Claude, run as a Claude Code subagent, with no person in the loop
- How it built the Flow: Dataiku's Python API (`dataikuapi`). No Headless and no Cobuild: this
  instance has no LLM connection, which Cobuild needs.
- Dataiku: DSS 15.2.1, Free Edition, self-hosted on a 4-CPU, 15 GB machine
- Variant: A, blind. The agent wasn't allowed to run the legacy pipeline or reproduce its outputs.
- Started 14:10 UTC, finished 14:27 UTC (17 minutes)
- Interventions: none
- Score: 13 of 13 (see `RESULTS.md`)

## Was it blind?

The agent worked in a folder holding only `data/raw/`, `legacy/pipeline.py` and an API key file.
Afterwards I went through every command it ran: it read files only in that folder, Dataiku's
documentation online, and the helper scripts it wrote itself in its scratch folder. It never opened
this repo, `reference/` or the scorer.

## What it built

18 visual recipes, no code recipes:

1. Join FDA packages to products on PRODUCTID
2. Prepare: split each package code on "-", pad each segment (5-4-2) to the 11-digit NDC; upper-case
   brand, lower-case generic name, flag GLP-1 by pharmacologic class
3. Top N: one row per NDC, the smallest PRODUCTID (the legacy sort-then-dedupe)
4. Prepare the SDUD rows: rename, drop state XX, drop suppressed rows, trim product names
5. Join to the lookup on NDC, with unmatched rows sent to their own output
6. Filter to GLP-1 drugs
7. Group by state, year, quarter and brand
8. Window: total prescriptions per state and quarter
9. Window: the previous row's prescriptions and period, per state and brand
10. Prepare: class share; growth only when the previous row is the previous calendar quarter
11. Sort into `glp1_state_quarter`
12. to 15. Group, Window, Prepare and Sort for `glp1_national_quarter`
16. to 18. Group, Prepare and Sort for `unmatched_ndcs`

## What it ran into

- **Window recipes returned running totals.** A Window recipe summing within a group, with no
  ordering, gave a running sum instead of the group total. Turning on an unbounded frame didn't
  change it; setting the recipe's `legacyUnboundedWindowStreamBehavior` flag to true did. The agent
  caught it by checking the window totals against plain sums. Reproduced independently with
  [`findings/window_running_sum.py`](../../findings/window_running_sum.py).
- **A Filter recipe ignored its condition.** The first version put the condition in the sampling
  settings, where it was silently ignored and every row passed. It moved the condition to the main
  settings and checked the row count.
- **Prescription counts were typed as text.** Their zero padding made Dataiku's type detection read
  them as strings, so it set the column to a whole-number type by hand.
- **Undocumented settings.** The API reference doesn't describe the Window and Top N settings, so
  it created throwaway recipes to read their default settings, then deleted them.

It also kept one detail of the old code that doesn't change these outputs: pandas treats a product
name of only spaces as an empty string, which wins a minimum, while Dataiku skips it. It added a flag
to reproduce the old behaviour, though in this data every such row is a national or suppressed row.
