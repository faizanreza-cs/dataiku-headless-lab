.PHONY: data reference test score

data:  ## download today's inputs into data/fresh/ (data/raw/ is what the answer key was built from)
	python data/prepare.py data/fresh

reference:  ## rebuild the answer key from the legacy pipeline
	python legacy/pipeline.py

test:
	python -m pytest -q

score:  ## make score RUN=2026-11-03-claude-code-blind
	python score/compare.py runs/$(RUN)/output --out runs/$(RUN)/RESULTS.md
