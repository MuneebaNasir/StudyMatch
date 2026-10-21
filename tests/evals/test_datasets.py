import json

import pytest
from pydantic import ValidationError

from evals.datasets import (
    EligibilityCase,
    QueryCase,
    load_eligibility_cases,
    load_program_snapshots,
    load_query_cases,
    load_transcript_cases,
)


def _write(path, data):
    path.write_text(json.dumps(data))
    return path


def test_query_case_rejects_unknown_expected_field():
    with pytest.raises(ValidationError):
        QueryCase(id="q1", query="x", expected_filters={"town": "Bonn"}, expected_profile={})


def test_eligibility_case_requires_expected_in_acceptable():
    with pytest.raises(ValidationError):
        EligibilityCase(
            id="e1", profile={}, courses=None, program_id=1,
            expected_verdict="eligible", acceptable_verdicts=["likely_eligible"], label_rationale="r",
        )


def test_load_eligibility_cases_errors_on_missing_snapshot(tmp_path):
    snapshots = load_program_snapshots(_write(tmp_path / "snap.json", []))
    cases = _write(tmp_path / "cases.json", [{
        "id": "missing-program", "profile": {}, "courses": None, "program_id": 42,
        "expected_verdict": "unclear", "acceptable_verdicts": ["unclear"], "label_rationale": "r",
    }])

    with pytest.raises(ValueError, match="missing-program"):
        load_eligibility_cases(cases, snapshots)


def test_loaders_reject_duplicate_ids(tmp_path):
    case = {"id": "q1", "query": "x", "expected_filters": {}, "expected_profile": {}}
    with pytest.raises(ValueError, match="q1"):
        load_query_cases(_write(tmp_path / "q.json", [case, case]))


def test_load_transcript_cases_pairs_png_and_truth(tmp_path):
    _write(tmp_path / "a.json", {"courses": [{"name": "Algebra", "grade": "A"}], "grade_value": 3.5})
    (tmp_path / "a.png").write_bytes(b"png")

    cases = load_transcript_cases(tmp_path)

    assert len(cases) == 1
    assert cases[0].id == "a"
    assert cases[0].image_path.name == "a.png"
