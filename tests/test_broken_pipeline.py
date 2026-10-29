"""End to end: a pipeline with the most common NDC mistake must fail the right checks."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "legacy"))
sys.path.insert(0, str(ROOT / "score"))

import pipeline  # noqa: E402
from compare import score  # noqa: E402


def naive_ndc11(package_code: str) -> str:
    # Pads the whole code instead of each segment: right for 4-4-2, wrong for 5-3-2 and 5-4-1
    return package_code.replace("-", "").zfill(11)


def test_naive_ndc_padding_loses_generic_exenatide(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "to_ndc11", naive_ndc11)
    pipeline.main(tmp_path)
    checks = {c.name: c for c in score(tmp_path, ROOT / "reference")}

    assert checks["Same brands"].passed is False
    assert "EXENATIDE" in checks["Same brands"].detail
    assert checks["Prescriptions match"].passed is False
    assert checks["Unmatched NDCs reported"].passed is False
    assert checks["No national-total rows"].passed is True
