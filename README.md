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
| 8 | Report NDCs the FDA directory doesn't list | **101** NDCs disappear without a trace, among them the discontinued Bydureon BCise with **79,208** prescriptions |

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
| Prescriptions, units, spend, class share and growth match, row by row | 1-7 |
| National table matches | 1 |
| Unmatched NDCs reported | 8 |

Column order, column-name case and row order don't matter; numbers must agree to six significant
digits, and an empty growth value must stay empty.

The scorer has its own tests: it passes the reference against itself, catches each kind of broken
output, and catches a full pipeline run with the wrong NDC padding.

```bash
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

- Python 3.11+ with pandas.

Then:

1. Connect Headless: ask the agent to "Set up Dataiku Headless" and give it the instance URL and
   API key. Headless saves the key in plain text in `.dataiku/stdio-config.json`; `.dataiku/` and
   `.env` are in `.gitignore` so the key can't be committed by accident.
2. Start a run folder: `cp -r runs/TEMPLATE runs/<date>-<agent>-<variant>`.
3. Give the agent one of the two prompts in [`tasks/migrate.md`](tasks/migrate.md), exactly as
   written: **A** gives it the code and the expected columns, **B** also asks it to run the old
   pipeline and compare.
4. Write down every time you step in, in the run's `interventions.csv`.
5. Score it: `python score/compare.py runs/<run>/output --out runs/<run>/RESULTS.md`.

## Results

No runs yet. Each run goes in [`runs/`](runs) with its `RESULTS.md`, and gets a line here with the
agent, the variant, the checks passed and the number of times I had to step in.

## Data

| Source | Where | Licence |
|---|---|---|
| State Drug Utilization Data 2024 and 2025 | [data.medicaid.gov](https://data.medicaid.gov/dataset/61729e5a-7aa8-448c-8903-ba3e0cd0ea3c) | US public domain |
| NDC Directory | [FDA](https://www.fda.gov/drugs/drug-approvals-and-databases/national-drug-code-directory) | US public domain |

The files in `data/raw/` were cut down by [`data/prepare.py`](data/prepare.py) on 29 October 2026,
from the July 2026 Medicaid release: every product of Eli Lilly, Novo Nordisk, Sanofi and
AstraZeneca (118,085 rows in total, insulins and all, so the pipeline still has to find the GLP-1
drugs), plus the GLP-1 products of generic makers and repackagers. `python data/prepare.py`
downloads them again; CMS updates the files every quarter and changes the file names, so the URLs
are at the top of the script.

The FDA directory lists products currently on the market. That's why discontinued products such as
Bydureon BCise can't be classed and end up in `unmatched_ndcs`, which is rule 8 doing its job.

## Layout

```
data/prepare.py         downloads and cuts the public inputs
data/raw/               the inputs the pipeline and the agent both use
legacy/pipeline.py      the pipeline to migrate
reference/              its outputs: the answer key
tasks/migrate.md        the prompts given to the agent
runs/                   one folder per run: notes, interventions, outputs, results
score/compare.py        scores a run against the reference
tests/                  tests for the scorer
```

Not affiliated with Dataiku. MIT licence for the code; the data is public domain.
