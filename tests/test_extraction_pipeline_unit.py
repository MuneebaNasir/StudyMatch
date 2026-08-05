from datetime import datetime, timezone

from daad_search.db.models import Program
from daad_search.extraction import pipeline as pipeline_module


def _program(program_id: int) -> Program:
    return Program(
        id=program_id, course_name="Test", course_name_short="Test", university="Test University",
        city="Berlin", languages=["English"], subject="Computer Science", course_type=2,
        degree="Master of Science", duration="4 semesters", beginning="Winter semester",
        tuition_fees_text="No tuition fees", has_tuition_fees=False,
        application_deadline_text="15 July", link="https://example.com",
        raw_sections={"admission_requirements": "Bachelor's degree"},
        scraped_at=datetime.now(timezone.utc),
    )


async def test_extract_program_isolates_extraction_failure(monkeypatch):
    def fake_extract_eligibility(course_name, university, raw_sections):
        raise RuntimeError("LLM error")

    monkeypatch.setattr(pipeline_module, "extract_eligibility", fake_extract_eligibility)

    program_id, ok = await pipeline_module.extract_program(_program(1))
    assert ok is False
    assert program_id == 1


async def test_process_candidates_stops_after_consecutive_failure_limit(monkeypatch):
    programs = [_program(i) for i in range(1, 11)]
    call_count = {"n": 0}

    async def fake_extract_program(program):
        call_count["n"] += 1
        return program.id, False

    monkeypatch.setattr(pipeline_module, "extract_program", fake_extract_program)

    result = await pipeline_module._process_candidates(programs)

    assert result["stopped_early"] is True
    assert call_count["n"] == pipeline_module.CONSECUTIVE_FAILURE_LIMIT
    assert len(result["failed_ids"]) == pipeline_module.CONSECUTIVE_FAILURE_LIMIT


async def test_process_candidates_resets_consecutive_count_on_success(monkeypatch):
    programs = [_program(i) for i in range(1, 8)]
    # Fail, fail, succeed, fail, fail, succeed, fail -- never 5 in a row.
    outcomes = [False, False, True, False, False, True, False]

    async def fake_extract_program(program):
        return program.id, outcomes[program.id - 1]

    monkeypatch.setattr(pipeline_module, "extract_program", fake_extract_program)

    result = await pipeline_module._process_candidates(programs)

    assert result["stopped_early"] is False
    assert result["succeeded"] == 2
    assert len(result["failed_ids"]) == 5
    assert result["total_candidates"] == 7
