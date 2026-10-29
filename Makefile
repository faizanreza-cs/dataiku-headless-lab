.PHONY: data reference test score

data:  ## download and cut the public inputs again
	python data/prepare.py

reference:  ## rebuild the answer key from the legacy pipeline
	python legacy/pipeline.py

test:
	python -m pytest -q

score:  ## make score RUN=2026-11-03-claude-code-blind
	python score/compare.py runs/$(RUN)/output --out runs/$(RUN)/RESULTS.md
