import pytest

from daad_search.extraction.extractor import build_prompt, extract_eligibility


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

    assert result.requires_gre is True
    assert result.grade_requirement.value == 2.5
    gre = result.standardized_tests[0]
    assert "GRE" in gre.test
    assert "1.3" in gre.waiver
    assert len(result.language_requirements) == 1
    assert result.language_requirements[0].level == "B2"


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
