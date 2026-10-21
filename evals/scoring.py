"""Deterministic scorers. Each returns a flat {metric_name: float} dict so the
runner can hand individual keys to MLflow without this module importing it."""
import re

from daad_search.query_understanding.schema import EligibilityVerdict, ParsedQuery
from daad_search.transcript.schema import TranscriptExtraction

from .datasets import EligibilityCase, QueryCase, TranscriptCase

# Transcripts often prefix names with a course code, e.g. "CS2 01 Data Structures".
_LEADING_CODE = re.compile(r"^[A-Za-z]{2,4}\s?\d\s*\d+\s*")
_FLOAT_TOLERANCE = 0.01


def normalize_course_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", _LEADING_CODE.sub("", name.strip()).lower())


def _values_match(expected, actual) -> bool:
    if expected is None or actual is None:
        return expected is None and actual is None
    if isinstance(expected, list):
        return isinstance(actual, list) and {str(v).strip().lower() for v in expected} == {
            str(v).strip().lower() for v in actual
        }
    if isinstance(expected, bool) or isinstance(actual, bool):
        return expected == actual
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        return abs(expected - actual) < _FLOAT_TOLERANCE
    return str(expected).strip().lower() == str(actual).strip().lower()


def score_query(case: QueryCase, parsed: ParsedQuery | None) -> dict[str, float]:
    scores: dict[str, float] = {"failed": 1.0 if parsed is None else 0.0}
    for prefix, expected_fields, actual in (
        ("filter", case.expected_filters, parsed.filters if parsed else None),
        ("profile", case.expected_profile, parsed.student_profile if parsed else None),
    ):
        for field, expected in expected_fields.items():
            ok = actual is not None and _values_match(expected, getattr(actual, field))
            scores[f"{prefix}.{field}"] = 1.0 if ok else 0.0
    field_scores = [v for k, v in scores.items() if k != "failed"]
    scores["all_correct"] = 1.0 if parsed is not None and all(v == 1.0 for v in field_scores) else 0.0
    return scores


def score_eligibility(case: EligibilityCase, verdicts: list[EligibilityVerdict] | None) -> dict[str, float]:
    match = next((v for v in verdicts or [] if v.program_id == case.program_id), None)
    if match is None:
        return {"failed": 1.0, "verdict_exact": 0.0, "verdict_acceptable": 0.0}
    return {
        "failed": 0.0,
        "verdict_exact": 1.0 if match.verdict == case.expected_verdict else 0.0,
        "verdict_acceptable": 1.0 if match.verdict in case.acceptable_verdicts else 0.0,
    }


def score_transcript(case: TranscriptCase, extraction: TranscriptExtraction) -> dict[str, float]:
    extracted = {normalize_course_name(c.name): c.grade for c in extraction.courses}
    truth = {normalize_course_name(c["name"]): c.get("grade") for c in case.courses}
    matched = [name for name in truth if name in extracted]
    correct = [n for n in matched if (extracted[n] or "").strip().upper() == (truth[n] or "").strip().upper()]
    graded = sum(1 for c in extraction.courses if c.grade)
    return {
        "course_recall": len(matched) / len(truth) if truth else 0.0,
        "grade_accuracy": len(correct) / len(matched) if matched else 0.0,
        "gpa_match": 1.0 if _values_match(case.grade_value, extraction.grade_value) else 0.0,
        # Same rule as transcript/llm.py's _reject_unusable_extraction.
        "usable": 1.0 if extraction.courses and graded * 2 >= len(extraction.courses) else 0.0,
        "failed": 0.0 if extraction.courses else 1.0,
    }
