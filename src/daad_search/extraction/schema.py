from typing import Literal

from pydantic import BaseModel, Field


class SubScore(BaseModel):
    section: str
    min_score: float


class StandardizedTest(BaseModel):
    """GRE or GMAT only -- NOT language proficiency tests (those belong under
    LanguageRequirement.accepted_tests instead)."""

    test: str  # "GRE" or "GMAT"
    required: bool
    eligibility_condition: str | None = None  # WHO/WHEN this applies, e.g. "Only required for applicants from non-EU/EEA countries" -- NOT the score thresholds
    subscores: list[SubScore] = []
    waiver: str | None = None
    source_quote: str


class AcceptedTest(BaseModel):
    """One way to satisfy a language requirement, e.g. IELTS 6.5."""

    test_name: str
    # Kept as a string: scores vary in format (6.5, 72, "B2 First"). Null when
    # the named method has no numeric/graded score to report (e.g. a
    # placement test or interview) -- do not invent one.
    min_score: str | None = Field(
        None,
        description='The required score/level for this test, e.g. "6.5", "72", "B2 First". '
        "Null if this verification method (e.g. a placement test or interview) has no "
        "numeric or graded score.",
    )


class LanguageRequirement(BaseModel):
    language: str  # "German" or "English"
    level: str | None = Field(
        None,
        description="CEFR code (e.g. \"B2\"). Null if the text states no minimum level is "
        "required -- do not invent a level.",
    )
    # Alternatives -- the applicant needs to satisfy ONLY ONE of these tests,
    # not all of them. Do not treat this list as several separate mandatory
    # requirements.
    accepted_tests: list[AcceptedTest] = []
    source_quote: str


class GradeRequirement(BaseModel):
    value: float | None = None
    scale: str | None = None
    source_quote: str | None = None


class DegreePrerequisite(BaseModel):
    description: str
    source_quote: str


class EligibilityExtraction(BaseModel):
    """Structured eligibility criteria extracted from a DAAD program's raw
    admission-requirements and language-requirement text."""

    # KNOWN LIMITATION -- requires_gre/requires_gmat are a best-effort *flattened*
    # summary of what may be a conditional requirement (e.g. "GRE required only
    # for applicants from non-EU/EEA countries"). For such conditional cases the
    # flat boolean is not reliable: it has been observed to vary between
    # otherwise-identical extraction runs over the same input text.
    # The authoritative detail is standardized_tests[].required /
    # .eligibility_condition / .waiver -- stable across those same runs, and
    # persisted in the eligibility.structured_eligibility JSONB column. Any
    # consumer that must reason correctly about conditional GRE/GMAT
    # requirements has to read that nested detail, not just these booleans.
    requires_gre: bool | None = None
    requires_gmat: bool | None = None
    min_german_level: str | None = None
    min_english_level: str | None = None
    extraction_confidence: Literal["high", "medium", "low"]
    degree_prerequisite: DegreePrerequisite | None = None
    grade_requirement: GradeRequirement | None = None
    standardized_tests: list[StandardizedTest] = []
    language_requirements: list[LanguageRequirement] = []
    notes: str | None = None
