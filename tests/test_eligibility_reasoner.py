# tests/test_eligibility_reasoner.py
import pytest

from daad_search.query_understanding.reasoner import build_reasoning_prompt, reason_about_eligibility
from daad_search.query_understanding.schema import CandidateForReasoning, StudentProfile


def test_build_reasoning_prompt_includes_profile_and_candidates():
    profile = StudentProfile(grade_value=3.2, nationality="Pakistan")
    candidates = [
        CandidateForReasoning(
            program_id=10396, course_name="Additive Manufacturing",
            structured_eligibility={"foo": "bar"},
        ),
    ]
    prompt = build_reasoning_prompt(profile, candidates)
    assert "3.2" in prompt
    assert "Pakistan" in prompt
    assert "10396" in prompt
    assert "Additive Manufacturing" in prompt


def test_reason_about_eligibility_returns_empty_list_for_no_candidates():
    assert reason_about_eligibility(StudentProfile(), []) == []


def test_reason_about_eligibility_returns_none_when_all_providers_fail(monkeypatch):
    from daad_search.query_understanding import reasoner as reasoner_module

    class AlwaysFailsChain:
        def invoke(self, prompt):
            raise RuntimeError("all providers exhausted")

    monkeypatch.setattr(reasoner_module, "get_fallback_llm", lambda schema: AlwaysFailsChain())

    candidates = [
        CandidateForReasoning(program_id=1, course_name="Test", structured_eligibility={}),
    ]
    assert reason_about_eligibility(StudentProfile(), candidates) is None


@pytest.mark.integration
def test_reason_about_eligibility_produces_sensible_verdicts_for_real_data():
    # Real extracted eligibility for program 10396 (Additive Manufacturing):
    # grade 2.5 max (German scale), GRE required only for non-EU/EEA unless
    # CGPA better than 1.3, English B2.
    structured_eligibility = {
        "grade_requirement": {"value": 2.5, "scale": "German grading scale (1.0 best - 5.0 worst)"},
        "standardized_tests": [{
            "test": "GRE", "required": True,
            "eligibility_condition": "only for applicants from non-EU/EEA countries",
            "waiver": "Not required if CGPA better than 1.3 on the German grading scale",
        }],
        "min_english_level": "B2",
    }
    candidates = [
        CandidateForReasoning(
            program_id=10396, course_name="Additive Manufacturing",
            structured_eligibility=structured_eligibility,
        ),
    ]

    # Clearly strong profile: an excellent grade should convert well under
    # the 2.5 German-scale threshold, and be judged as waiving the GRE too.
    strong_profile = StudentProfile(
        degree_field="Mechanical Engineering", grade_value=3.9,
        grade_scale="4.0 GPA scale (USA)", nationality="Pakistan",
    )
    strong_verdicts = reason_about_eligibility(strong_profile, candidates)
    assert strong_verdicts is not None
    assert strong_verdicts[0].program_id == 10396
    assert strong_verdicts[0].verdict in ("eligible", "likely_eligible")

    # Clearly weak profile: a poor grade, well outside any waiver.
    weak_profile = StudentProfile(
        degree_field="Mechanical Engineering", grade_value=2.0,
        grade_scale="4.0 GPA scale (USA)", nationality="Pakistan",
    )
    weak_verdicts = reason_about_eligibility(weak_profile, candidates)
    assert weak_verdicts is not None
    assert weak_verdicts[0].verdict in ("not_eligible", "unclear")
