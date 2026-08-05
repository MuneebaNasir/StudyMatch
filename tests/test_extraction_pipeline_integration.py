from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from daad_search.db.models import Eligibility
from daad_search.db.upsert import upsert_eligibility
from daad_search.extraction import pipeline as pipeline_module
from daad_search.extraction.pipeline import run_extraction, select_candidates


def _eligibility_values() -> dict:
    return dict(
        requires_gre=None, requires_gmat=None,
        min_german_level=None, min_english_level=None,
        min_grade_value=None, min_grade_scale_note=None,
        extraction_confidence="low", structured_eligibility={},
        extracted_at=datetime.now(timezone.utc),
    )

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
    # Select the GRE entry by predicate rather than by position: nothing
    # guarantees the model orders standardized_tests any particular way, and a
    # missing waiver should read as a real failure, not a TypeError on None.
    gre_entries = [
        t for t in by_id[10396].structured_eligibility["standardized_tests"]
        if "GRE" in t["test"].upper()
    ]
    assert gre_entries, "expected a GRE entry in standardized_tests"
    assert gre_entries[0]["waiver"] is not None
    assert "1.3" in gre_entries[0]["waiver"]


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


# --- select_candidates (Postgres only, no LLM calls) ---


async def test_select_candidates_reextracts_explicitly_requested_program(
    extraction_env, make_program
):
    """`extract --ids 10396` is documented as *targeted re-extraction*: naming a
    program explicitly must select it even though it already has an eligibility
    row, while a bare run still skips it."""
    session_factory = extraction_env
    async with session_factory() as session:
        session.add_all([
            make_program(
                id=10396, course_name="Additive Manufacturing", university="Paderborn University",
                link="https://example.com/10396", raw_sections=ADDITIVE_MANUFACTURING_SECTIONS,
            ),
            make_program(
                id=9012, course_name="Computer Engineering for IoT Systems",
                link="https://example.com/9012", raw_sections=IOT_SECTIONS,
            ),
        ])
        await session.commit()

    async with session_factory() as session:
        await upsert_eligibility(session, 10396, _eligibility_values())

    async with session_factory() as session:
        targeted = await select_candidates(session, limit_ids=[10396])
        bare = await select_candidates(session)

    assert [p.id for p in targeted] == [10396]
    assert [p.id for p in bare] == [9012]


async def test_select_candidates_skips_textless_programs_even_when_named(
    extraction_env, make_program
):
    """The text-presence filter applies to --ids runs too: a program with none
    of the 3 relevant raw_sections keys can't produce an extraction, so it is
    never worth an LLM call however it was requested."""
    session_factory = extraction_env
    async with session_factory() as session:
        session.add_all([
            make_program(
                id=1, course_name="No admission text", link="https://example.com/1",
                raw_sections={"description": "no eligibility text here"},
            ),
        ])
        await session.commit()

    async with session_factory() as session:
        assert await select_candidates(session, limit_ids=[1]) == []


async def test_select_candidates_applies_limit_in_deterministic_id_order(
    extraction_env, make_program
):
    """`--limit` is the primary quota-control mechanism, so which candidates a
    capped run picks must be predictable: always the lowest program ids first,
    so successive runs tile through the catalog instead of re-rolling it."""
    session_factory = extraction_env
    async with session_factory() as session:
        # Inserted out of id order — ordering must come from the query, not
        # from insertion order.
        session.add_all([
            make_program(
                id=program_id, course_name=f"Program {program_id}",
                link=f"https://example.com/{program_id}",
                raw_sections={"admission_requirements": "Bachelor's degree"},
            )
            for program_id in (30, 10, 20)
        ])
        await session.commit()

    async with session_factory() as session:
        assert [p.id for p in await select_candidates(session)] == [10, 20, 30]
        assert [p.id for p in await select_candidates(session, limit=2)] == [10, 20]
        assert [p.id for p in await select_candidates(session, limit_ids=[20])] == [20]
        # limit and limit_ids compose: the cap applies within the named subset.
        assert [
            p.id for p in await select_candidates(session, limit_ids=[30, 20], limit=1)
        ] == [20]

    # Extracting the first slice makes the next capped run pick up where the
    # previous one stopped, rather than repeating the same two programs.
    async with session_factory() as session:
        for program_id in (10, 20):
            await upsert_eligibility(session, program_id, _eligibility_values())

    async with session_factory() as session:
        assert [p.id for p in await select_candidates(session, limit=2)] == [30]
