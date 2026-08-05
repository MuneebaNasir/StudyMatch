import pytest
from sqlalchemy import select

from daad_search.db.models import Eligibility
from daad_search.extraction import pipeline as pipeline_module
from daad_search.extraction.pipeline import run_extraction

pytestmark = pytest.mark.integration

# Real DAAD admission text -- the same programs validated live during design:
# a complex conditional GRE waiver, and a plain CGPA-only case.
ADDITIVE_MANUFACTURING_SECTIONS = {
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
IOT_SECTIONS = {
    "admission_requirements": (
        "A completed Bachelor's degree in computer science, computer engineering or "
        "a related field\n"
        "A minimum CGPA (cumulative grade point average) of 2.5 (according to the "
        "German grading system) or higher\n"
        "English language skills at level B2 (see below)"
    ),
    "english_language": "PTE Academic: 60, IELTS Academic: 6",
}


@pytest.fixture
def extraction_env(monkeypatch, test_session_factory):
    """Point run_extraction at the test database."""
    monkeypatch.setattr(pipeline_module, "async_session_factory", test_session_factory)
    return test_session_factory


async def test_run_extraction_populates_eligibility_table(extraction_env, make_program):
    session_factory = extraction_env
    async with session_factory() as session:
        session.add_all([
            make_program(
                id=10396, course_name="Additive Manufacturing", university="Paderborn University",
                link="https://example.com/10396", raw_sections=ADDITIVE_MANUFACTURING_SECTIONS,
            ),
            make_program(
                id=9012, course_name="Computer Engineering for IoT Systems",
                university="Nordhausen University of Applied Sciences",
                link="https://example.com/9012", raw_sections=IOT_SECTIONS,
            ),
            make_program(
                id=1, course_name="No admission text", university="Test University",
                link="https://example.com/1",
                raw_sections={"description": "no eligibility text here"},
            ),
        ])
        await session.commit()

    result = await run_extraction()

    # Program 1 has none of the 3 relevant keys -- excluded as a candidate.
    assert result["total_candidates"] == 2
    assert result["succeeded"] == 2
    assert result["failed_ids"] == []

    async with session_factory() as session:
        rows = (await session.execute(select(Eligibility))).scalars().all()
        by_id = {row.program_id: row for row in rows}

    assert set(by_id.keys()) == {10396, 9012}
    assert by_id[10396].requires_gre is True
    assert by_id[10396].min_grade_value == 2.5
    assert "1.3" in by_id[10396].structured_eligibility["standardized_tests"][0]["waiver"]


async def test_run_extraction_is_idempotent_on_rerun(extraction_env, make_program):
    session_factory = extraction_env
    async with session_factory() as session:
        session.add_all([
            make_program(
                id=10396, course_name="Additive Manufacturing", university="Paderborn University",
                link="https://example.com/10396", raw_sections=ADDITIVE_MANUFACTURING_SECTIONS,
            ),
        ])
        await session.commit()

    first = await run_extraction()
    assert first["total_candidates"] == 1
    assert first["succeeded"] == 1

    second = await run_extraction()
    assert second["total_candidates"] == 0  # already has an eligibility row
