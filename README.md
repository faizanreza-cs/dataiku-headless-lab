# Dataiku Headless migration test

Can a coding agent move a legacy analytics pipeline into Dataiku without losing its business
rules? This repo is a test with a known answer.

Dataiku released [Headless](https://github.com/dataiku/dataiku-headless) on 27 October 2026: an
MCP server and skills that let coding agents such as Claude Code, Codex, Cursor and GitHub Copilot
work in Dataiku, with Dataiku's Cobuild agent doing the building. One use Dataiku names is
migrating work built elsewhere, like an Alteryx workflow or an Excel workbook, into a Dataiku
project.

Migrations rarely fail on the big steps. They fail on the small rules someone added years ago and
never wrote down. So the legacy pipeline here has eight of them, each one measured on real data,
and a scorer checks the migrated output against the original, rule by rule.

**First results, 31 October 2026:** two agent runs, 13 of 13 checks each, and a Dataiku Window
recipe that quietly returns running totals. See [Results](#results).

## The legacy pipeline

[`legacy/pipeline.py`](legacy/pipeline.py) reads two public datasets:

- **Medicaid State Drug Utilization Data**, 2024 and 2025 (CMS): prescriptions, units and spend by
  state, quarter and 11-digit NDC
- **The FDA NDC Directory**: which product each NDC is, and its pharmacologic class

and writes three tables to [`reference/`](reference), the answer key:

| Table | Rows | What it is |
|---|---|---|
| `glp1_state_quarter` | 3,302 | GLP-1 prescriptions, units, spend, share of the class and growth on the previous quarter, by state, quarter and brand |
| `glp1_national_quarter` | 96 | The same, for the whole country |
| `unmatched_ndcs` | 101 | NDCs the FDA directory doesn't list, reported rather than dropped |

## The eight rules

| # | Rule | What happens if a migration loses it |
|---|---|---|
| 1 | Drop rows where the state is `XX`: they're national totals | National totals come out **2.0x** too high |
| 2 | Drop suppressed rows (under 11 prescriptions, counts withheld) | **959** extra state-quarter-brand rows with no prescriptions |
| 3 | Add fee-for-service and managed care rows together | **1,196 of 3,302** rows split in two |
| 4 | Pad each segment of the FDA package code (4-4-2, 5-3-2 or 5-4-1) to reach Medicaid's 11 digits | Padding the whole code instead loses **19,515** prescriptions: generic exenatide disappears and generic liraglutide shrinks |
| 5 | Define GLP-1 by the FDA class "GLP-1 Receptor Agonist [EPC]" | A filter on generic names ending in -glutide misses **22.1%** of prescriptions: Mounjaro, Zepbound, Byetta, generic exenatide and Soliqua |
| 6 | Spend is the total amount reimbursed, not just the Medicaid share | Spend comes out **1.9%** low |
| 7 | Growth compares with the previous calendar quarter, and is empty if the brand had no row then | Comparing with the previous row measures **25** rows against an older quarter |
| 8 | Report NDCs the FDA directory doesn't list | **101** NDCs disappear without a trace, among them both NDCs of the discontinued Bydureon BCise, with **79,268** prescriptions |

None of these are invented for the test. Each one is in the data, and each number above is what
breaks if that rule alone is lost.

## How a run is scored

[`score/compare.py`](score/compare.py) reads a run's three CSVs and checks them against
`reference/`:

| Check | Rule |
|---|---|
| All three tables, with the right columns | - |
| No national-total rows | 1 |
| Same state-quarter-brand rows | 2, 4 |
| One row per state, quarter and brand | 3 |
| Same brands | 4, 5 |
| Generic names match | - |
| Prescriptions, units, spend, class share and growth match, row by row (five checks) | 1-7 |
| National table matches | 1 |
| Unmatched NDCs reported | 8 |

That's 13 checks, always the same 13: a missing table or column fails the checks that need it
rather than dropping them, so scores from different runs can be compared. Column order,
column-name case and row order don't matter. Numbers must be within 0.001% of the reference value
(so values rounded to six significant digits still pass), and an empty growth value must stay
empty. A key that appears twice in the output counts as wrong.

The scorer has its own tests. It passes the reference against itself; each check fails when the
column or table it guards is broken, and only that check; and a full run of the pipeline with any
one of rules 1, 2, 4, 5, 6, 7 or 8 switched off fails that rule's checks. Rule 3 is covered by an
output with each row split in two.

```bash
pip install -e ".[dev]"
python -m pytest -q
```

## Running the test

You need:

- A Dataiku instance with Cobuild enabled (Dataiku 14.7 or later). Dataiku's 14-day free trial
  has every feature except Govern and advanced LLM Mesh; check that Cobuild is switched on before
  you start the clock.
- A personal API key for that instance.
- A coding agent with the Headless plugin. For Claude Code:

  ```bash
  claude plugin marketplace add https://github.com/dataiku/dataiku-headless.git
  claude plugin install dataiku-headless@dataiku
  ```

- Python 3.11+, then `pip install -e ".[dev]"` for pandas and pytest.

Then:

1. Connect Headless: ask the agent to "Set up Dataiku Headless" (in Claude Code,
   `/dataiku-headless:dataiku-headless-setup`). It opens a setup page on your machine; enter the
   instance URL and API key there, not in the chat. Headless saves them in plain text in
   `~/.dataiku/stdio-config.json`, outside this repo, so delete that file or revoke the key when
   you're done. `.dataiku/` and `.env` are in `.gitignore` as a precaution, in case you keep a
   local copy here.
2. Start a run folder: `cp -r runs/TEMPLATE runs/<date>-<agent>-<variant>`.
3. Give the agent one of the two prompts in [`tasks/migrate.md`](tasks/migrate.md), exactly as
   written: **A** gives it the code and the expected columns, **B** also asks it to run the old
   pipeline and compare.
4. Write down every time you step in, in the run's `interventions.csv`.
5. Score it: `python score/compare.py runs/<run>/output --out runs/<run>/RESULTS.md`.

No Cobuild? The runs so far used the self-hosted Free Edition, with the agent building through
Dataiku's Python API instead. [`tasks/migrate.md`](tasks/migrate.md) has the install steps and how
the prompts change.

## Results

Two runs so far, on 31 October 2026, both without Headless or Cobuild. The Dataiku Free Edition
used here has no LLM connection for Cobuild, so the agent (Claude, as a Claude Code subagent)
built the Flow itself through Dataiku's Python API. Nobody stepped in during either run.

| Run | Variant | Flow | Checks passed | Interventions | Time |
|---|---|---|---|---|---|
| [blind](runs/2026-10-31-claude-api-blind) | A: not allowed to run the old pipeline | 18 visual recipes, no code | **13 of 13** | 0 | 17 min |
| [parallel run](runs/2026-10-31-claude-api-parallel) | B: compared its tables with the old pipeline's | 19 visual recipes, no code | **13 of 13** | 0 | 20 min |

Both agents kept all eight rules. Afterwards I went through every command each one ran: neither
opened this repo, the reference outputs or the scorer.

What they ran into says more than the score:

- **Dataiku's Window recipe returned running totals.** Summing within a group, with no ordering,
  gave 1, 3, 6 instead of 6, 6, 6 on DSS 15.2.1, for recipes created through the API. An unbounded
  window frame doesn't change it; only the undocumented `legacyUnboundedWindowStreamBehavior`
  setting does. Both agents caught it by checking the totals against plain sums. The blind agent set
  the flag; the other replaced the Window with a Group and a Join, so nothing depends on a hidden
  setting. [`findings/window_running_sum.py`](findings/window_running_sum.py) reproduces it on five
  rows.
- **A Filter recipe silently ignored its condition** in both runs, letting every row through, until
  the condition was put where the API expects it.
- **The parallel run found what the scorer forgives:** counts written as `324` rather than `324.0`,
  and 400 sums that differ from pandas in the 15th significant digit, because the two add numbers in
  a different order.

What these runs don't show yet:

- **Cobuild.** These agents wrote the recipes themselves. A Headless run needs a Dataiku instance
  with an LLM connection.
- **Rules nobody wrote down.** The legacy script names each rule in a comment, and a careful reader
  keeps them. An Alteryx workflow, or the same script without comments, is a harder test.
- **Other agents.** Both runs used Claude.

Each run's folder has the exact prompt, notes, the exported tables, `RESULTS.md` and the Dataiku
project export (Flow only, no data), which imports into any Dataiku instance.

## Data

| Source | Where | Licence |
|---|---|---|
| State Drug Utilization Data [2024](https://data.medicaid.gov/dataset/61729e5a-7aa8-448c-8903-ba3e0cd0ea3c) and [2025](https://data.medicaid.gov/dataset/158a1baa-5506-400a-8ec3-97756f0b0536) | data.medicaid.gov | US public domain |
| NDC Directory | [FDA](https://www.fda.gov/drugs/drug-approvals-and-databases/national-drug-code-directory) | US public domain |

The files in `data/raw/` were cut down by [`data/prepare.py`](data/prepare.py) on 29 October 2026,
from the July 2026 Medicaid release. They hold every product under the main labeler code of Eli
Lilly (00002), Novo Nordisk (00169), Sanofi (00024) and AstraZeneca (00310): 115,927 rows,
insulins and other drugs included, so the pipeline still has to find the GLP-1 drugs. The
companies' other labeler codes, such as Sanofi's 00088 for Lantus, have no GLP-1 products and are
left out. On top of that come 2,158 rows of GLP-1 products from generic makers and repackagers,
for 118,085 rows in all.

These committed files are the inputs the answer key was built from. The FDA directory changes
every day and CMS renames its files every quarter, so a new download gives slightly different
inputs. `python data/prepare.py` writes one to `data/fresh/` and leaves `data/raw/` alone; if you
replace `data/raw/` with it, run `python legacy/pipeline.py` again and expect the numbers in this
README to move.

The FDA directory lists products currently on the market. That's why discontinued products such as
Bydureon BCise can't be classed and end up in `unmatched_ndcs`, which is rule 8 doing its job.

## Layout

```
data/prepare.py         downloads and cuts the public inputs (into data/fresh/)
data/raw/               the inputs the answer key was built from, used by the pipeline and the agent
legacy/pipeline.py      the pipeline to migrate
reference/              its outputs: the answer key
tasks/migrate.md        the prompts given to the agent
runs/                   one folder per run: notes, interventions, outputs, results
score/compare.py        scores a run against the reference
findings/               scripts that reproduce what the runs found in Dataiku
tests/                  tests for the scorer
```

Not affiliated with Dataiku. MIT licence for the code; the data is public domain.
