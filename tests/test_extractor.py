import pytest

from daad_search.extraction import extractor as extractor_module
from daad_search.extraction.extractor import build_prompt, extract_eligibility
from daad_search.extraction.schema import EligibilityExtraction


def test_build_prompt_includes_course_and_university():
    prompt = build_prompt("Additive Manufacturing", "Paderborn University", {})
    assert "Additive Manufacturing" in prompt
    assert "Paderborn University" in prompt


def test_build_prompt_falls_back_when_sections_missing():
    prompt = build_prompt("Test Course", "Test University", {})
    assert "(not stated)" in prompt


def test_build_prompt_includes_provided_raw_sections():
    raw_sections = {
        "admission_requirements": "Bachelor's degree required",
        "german_language": "No minimum level",
        "english_language": "B2 required",
    }
    prompt = build_prompt("Test Course", "Test University", raw_sections)
    assert "Bachelor's degree required" in prompt
    assert "No minimum level" in prompt
    assert "B2 required" in prompt


def test_extract_eligibility_uses_the_shared_provider_fallback_chain(monkeypatch):
    """Groq's free tier is 100k tokens/day -- far too little to extract the
    full catalog in reasonable time. Extraction must go through the same
    Groq->Mistral->Gemini chain query understanding already uses (llm.py),
    not a Groq-only client, so it can lean on Mistral's much larger budget."""
    captured = {}
    stub_result = EligibilityExtraction(extraction_confidence="high")

    class FakeChain:
        def invoke(self, prompt):
            captured["prompt"] = prompt
            return stub_result

    def fake_get_fallback_llm(schema):
        captured["schema"] = schema
        return FakeChain()

    monkeypatch.setattr(extractor_module, "get_fallback_llm", fake_get_fallback_llm)

    result = extract_eligibility("Additive Manufacturing", "Paderborn University", {})

    assert captured["schema"] is EligibilityExtraction
    assert "Additive Manufacturing" in captured["prompt"]
    assert result is stub_result


@pytest.mark.integration
def test_extract_eligibility_captures_conditional_gre_waiver():
    raw_sections = {
        "admission_requirements": (
            "University studies equivalent to a three-year German Bachelor's degree, "
            "final grade 2.5 minimum\n"
            "Further requirements only for applicants from non-EU/EEA countries:\n"
            'GRE Revised General Test with at least 157 points in the "Quantitative '
            'Reasoning" section and at least 4.0 points in the "Analytical Writing" '
            "section\n"
            "Applicants with a CGPA in their Bachelor's degree better than 1.3 according "
            "to the German grading scale do not need to submit the GRE."
        ),
        "german_language": "No minimum language level required",
        "english_language": (
            "B2 required, please provide an official language certificate, e.g.: "
            "Cambridge English Qualifications: B2 First, IELTS Academic: 6.5"
        ),
    }
    result = extract_eligibility("Additive Manufacturing", "Paderborn University", raw_sections)

    assert result.grade_requirement.value == 2.5

    # No assertion on the top-level `requires_gre`: schema.py documents it as an
    # unreliable flattening of a *conditional* requirement, and this fixture is
    # exactly that case (GRE only for non-EU/EEA applicants). Nor on the nested
    # `gre.required` -- that is the same boolean judgement one level down. What
    # this test is named for, and what stays stable run to run, is whether the
    # condition and the waiver were captured as text.
    gre = next(t for t in result.standardized_tests if "GRE" in t.test.upper())
    assert gre.eligibility_condition is not None, "GRE's conditional scope was dropped"
    assert "eea" in gre.eligibility_condition.lower()
    assert gre.waiver is not None, "GRE's CGPA waiver was dropped"
    assert "1.3" in gre.waiver
    # Deliberately no assertion on the *number* of language requirements: the
    # German text ("No minimum language level required") maps to the schema's
    # own level=None, so both a 1-entry (English only) and a 2-entry (German
    # level=None + English B2) extraction are schema-conformant.
    english = next(lr for lr in result.language_requirements if lr.language == "English")
    assert english.level == "B2"


@pytest.mark.integration
def test_extract_eligibility_does_not_mark_alternative_tests_as_all_required():
    raw_sections = {
        "admission_requirements": "Bachelor's degree",
        "german_language": "No minimum language level required",
        "english_language": (
            "B2 required, please provide an official language certificate, e.g.: "
            "TOEIC: 785, TOEFL iBT (before 2026): 72, IELTS Academic: 6, "
            "Cambridge English Qualifications: B2 First"
        ),
    }
    result = extract_eligibility(
        "International Relations and Cultural Diplomacy", "Furtwangen University", raw_sections
    )

    assert result.standardized_tests == []
    english = next(lr for lr in result.language_requirements if lr.language == "English")
    assert len(english.accepted_tests) >= 2
