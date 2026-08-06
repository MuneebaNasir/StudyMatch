import pytest
from pydantic import ValidationError

from daad_search.api.schemas import SearchFilters
from daad_search.query_understanding.schema import (
    BatchEligibilityReasoning,
    CandidateForReasoning,
    EligibilityVerdict,
    ParsedQuery,
    StudentProfile,
)


def test_parsed_query_constructs_from_full_payload():
    parsed = ParsedQuery(
        filters=SearchFilters(languages=["English"], max_tuition_free_only=True),
        semantic_query="machine learning and robotics",
        student_profile=StudentProfile(
            degree_field="Artificial Intelligence",
            grade_value=3.2,
            grade_scale="4.0 GPA scale (USA)",
            nationality="Pakistan",
        ),
    )
    assert parsed.filters.languages == ["English"]
    assert parsed.student_profile.grade_value == 3.2


def test_student_profile_defaults_all_fields_to_none():
    profile = StudentProfile()
    assert profile.degree_field is None
    assert profile.grade_value is None
    assert profile.nationality is None


def test_eligibility_verdict_rejects_invalid_verdict_value():
    with pytest.raises(ValidationError):
        EligibilityVerdict(program_id=1, verdict="maybe", reasoning="unsure")


def test_eligibility_verdict_rejects_no_data_as_llm_value():
    """no_data is assigned by the orchestration layer, never by the LLM."""
    with pytest.raises(ValidationError):
        EligibilityVerdict(program_id=1, verdict="no_data", reasoning="n/a")


def test_batch_eligibility_reasoning_defaults_to_empty_list():
    batch = BatchEligibilityReasoning()
    assert batch.verdicts == []


def test_candidate_for_reasoning_constructs():
    candidate = CandidateForReasoning(
        program_id=10396, course_name="Additive Manufacturing",
        structured_eligibility={"grade_requirement": {"value": 2.5}},
    )
    assert candidate.program_id == 10396
    assert candidate.structured_eligibility["grade_requirement"]["value"] == 2.5
