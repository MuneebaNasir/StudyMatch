import pytest
from pydantic import ValidationError

from daad_search.extraction.schema import (
    AcceptedTest,
    DegreePrerequisite,
    EligibilityExtraction,
    GradeRequirement,
    LanguageRequirement,
    StandardizedTest,
    SubScore,
)


def test_eligibility_extraction_constructs_from_full_payload():
    extraction = EligibilityExtraction(
        requires_gre=True,
        requires_gmat=None,
        min_german_level=None,
        min_english_level="B2",
        extraction_confidence="high",
        degree_prerequisite=DegreePrerequisite(
            description="Three-year German Bachelor's degree",
            source_quote="University studies equivalent to a three-year German Bachelor's degree",
        ),
        grade_requirement=GradeRequirement(
            value=2.5, scale="German grading scale", source_quote="final grade 2.5 minimum"
        ),
        standardized_tests=[
            StandardizedTest(
                test="GRE",
                required=True,
                eligibility_condition="only for applicants from non-EU/EEA countries",
                subscores=[SubScore(section="Quantitative Reasoning", min_score=157.0)],
                waiver="Not required if CGPA better than 1.3",
                source_quote="GRE Revised General Test with at least 157 points",
            )
        ],
        language_requirements=[
            LanguageRequirement(
                language="English",
                level="B2",
                accepted_tests=[AcceptedTest(test_name="IELTS Academic", min_score="6.5")],
                source_quote="B2 required, please provide an official language certificate",
            )
        ],
        notes=None,
    )
    assert extraction.requires_gre is True
    assert extraction.standardized_tests[0].subscores[0].min_score == 157.0
    assert extraction.language_requirements[0].accepted_tests[0].test_name == "IELTS Academic"


def test_eligibility_extraction_defaults_optional_fields():
    extraction = EligibilityExtraction(extraction_confidence="low")
    assert extraction.requires_gre is None
    assert extraction.standardized_tests == []
    assert extraction.language_requirements == []
    assert extraction.degree_prerequisite is None


def test_extraction_confidence_rejects_invalid_value():
    with pytest.raises(ValidationError):
        EligibilityExtraction(extraction_confidence="very_high")


def test_language_requirement_allows_null_level():
    """Groq's structured-output validator rejects the whole tool call when a
    required string field comes back null -- and the LLM legitimately has no
    level to report when the source text says e.g. "No minimum language
    level required". A required str was simply the wrong type for this
    field; None must be a valid, first-class value here."""
    requirement = LanguageRequirement(
        language="English", level=None, source_quote="No minimum language level required",
    )
    assert requirement.level is None


def test_accepted_test_allows_null_min_score():
    """Some accepted "tests" are verification methods with no numeric/graded
    score (e.g. a placement test or interview) -- None must be valid here
    too, for the same reason as LanguageRequirement.level above."""
    test = AcceptedTest(test_name="placement test", min_score=None)
    assert test.min_score is None
