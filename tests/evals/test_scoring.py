from pathlib import Path

import pytest

from daad_search.api.schemas import SearchFilters
from daad_search.query_understanding.schema import EligibilityVerdict, ParsedQuery, StudentProfile
from daad_search.transcript.schema import ExtractedCourse, TranscriptExtraction
from evals.datasets import EligibilityCase, QueryCase, TranscriptCase
from evals.scoring import normalize_course_name, score_eligibility, score_query, score_transcript


def _parsed(filters=None, profile=None):
    return ParsedQuery(
        filters=SearchFilters(**(filters or {})), semantic_query=None, student_profile=StudentProfile(**(profile or {})),
    )


def _elig_case():
    return EligibilityCase(
        id="e1", profile={}, courses=None, program_id=7,
        expected_verdict="eligible", acceptable_verdicts=["eligible", "likely_eligible"], label_rationale="r",
    )


def test_normalize_course_name_strips_leading_code():
    assert normalize_course_name("CS2 01 Data Structures") == normalize_course_name("data structures")
    assert normalize_course_name("MT1 04 Linear Algebra") == "linearalgebra"


def test_score_query_only_scores_specified_fields():
    case = QueryCase(id="q", query="x", expected_filters={"city": "Bonn", "course_type": 2}, expected_profile={})

    scores = score_query(case, _parsed({"city": "Bonn", "course_type": 2, "languages": ["English"]}))

    assert set(scores) == {"failed", "filter.city", "filter.course_type", "all_correct"}
    assert scores["all_correct"] == 1.0


def test_score_query_languages_compare_as_sets():
    case = QueryCase(id="q", query="x", expected_filters={"languages": ["English"]}, expected_profile={})

    assert score_query(case, _parsed({"languages": ["english"]}))["filter.languages"] == 1.0


def test_score_query_expected_none_requires_none():
    case = QueryCase(id="q", query="x", expected_filters={"subject": None}, expected_profile={})

    scores = score_query(case, _parsed({"subject": "Artificial Intelligence"}))

    assert scores["filter.subject"] == 0.0
    assert scores["all_correct"] == 0.0


def test_score_query_compares_profile_floats_with_tolerance():
    case = QueryCase(id="q", query="x", expected_filters={}, expected_profile={"grade_value": 3.2})

    assert score_query(case, _parsed(profile={"grade_value": 3.2000001}))["profile.grade_value"] == 1.0


def test_score_query_marks_none_output_as_failure():
    case = QueryCase(id="q", query="x", expected_filters={"city": "Bonn"}, expected_profile={"nationality": "Pakistan"})

    scores = score_query(case, None)

    assert scores == {"failed": 1.0, "filter.city": 0.0, "profile.nationality": 0.0, "all_correct": 0.0}


def test_score_eligibility_exact_vs_acceptable():
    verdict = EligibilityVerdict(program_id=7, verdict="likely_eligible", reasoning="r")

    scores = score_eligibility(_elig_case(), [verdict])

    assert scores == {"failed": 0.0, "verdict_exact": 0.0, "verdict_acceptable": 1.0}


@pytest.mark.parametrize("verdicts", [None, [], [EligibilityVerdict(program_id=99, verdict="eligible", reasoning="r")]])
def test_score_eligibility_handles_missing_verdict(verdicts):
    assert score_eligibility(_elig_case(), verdicts) == {"failed": 1.0, "verdict_exact": 0.0, "verdict_acceptable": 0.0}


def test_score_transcript_recall_and_grade_accuracy():
    case = TranscriptCase(
        id="t", image_path=Path("t.png"), grade_value=3.1,
        courses=[{"name": n, "grade": g} for n, g in [("Algebra", "A"), ("Data Structures", "B+"), ("Physics", "C"), ("Ethics", "A-")]],
    )
    extraction = TranscriptExtraction(
        courses=[ExtractedCourse(name="MT1 01 Algebra", grade="A"), ExtractedCourse(name="data structures", grade="B"),
                 ExtractedCourse(name="Physics", grade="C")],
        grade_value=3.1, extraction_confidence="high",
    )

    scores = score_transcript(case, extraction)

    assert scores["course_recall"] == pytest.approx(0.75)
    assert scores["grade_accuracy"] == pytest.approx(2 / 3)
    assert scores["gpa_match"] == 1.0
    assert scores["usable"] == 1.0
    assert scores["failed"] == 0.0


def test_score_transcript_empty_extraction_is_failed_and_unusable():
    case = TranscriptCase(id="t", image_path=Path("t.png"), grade_value=None, courses=[{"name": "Algebra", "grade": "A"}])

    scores = score_transcript(case, TranscriptExtraction(extraction_confidence="low"))

    assert scores == {"course_recall": 0.0, "grade_accuracy": 0.0, "gpa_match": 1.0, "usable": 0.0, "failed": 1.0}
