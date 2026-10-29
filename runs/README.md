# Runs

One folder per run, named `<date>-<agent>-<variant>`, for example
`2026-11-03-claude-code-blind`. Start from the template:

```bash
cp -r runs/TEMPLATE runs/2026-11-03-claude-code-blind
```

Each run folder holds:

| File | What goes in it |
|---|---|
| `notes.md` | Agent, model, Headless and Dataiku versions, the variant, start and end time |
| `interventions.csv` | One line every time you step in: re-prompting, fixing something by hand, restarting |
| `output/` | The three CSVs exported from Dataiku |
| `RESULTS.md` | Written by the scorer |

Score a run with:

```bash
python score/compare.py runs/2026-11-03-claude-code-blind/output --out runs/2026-11-03-claude-code-blind/RESULTS.md
```

What counts as an intervention: anything you type after the first prompt, and anything you change
in Dataiku yourself. Answering a yes/no confirmation that Cobuild asks for doesn't count, but write
it in `notes.md`.
