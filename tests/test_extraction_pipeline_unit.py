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


async def test_extract_program_isolates_failure_in_value_construction(monkeypatch):
    """Covers the window between the two original try/except blocks: a
    result that raises when its fields are read/dumped (e.g. a future
    schema change) must still be isolated as a per-program failure, not
    propagate out of extract_program."""

    class ExplodingResult:
        def __getattr__(self, name):
            raise AttributeError(f"unexpected attribute access: {name}")

    def fake_extract_eligibility(course_name, university, raw_sections):
        return ExplodingResult()

    monkeypatch.setattr(pipeline_module, "extract_eligibility", fake_extract_eligibility)

    program_id, ok = await pipeline_module.extract_program(_program(2))
    assert ok is False
    assert program_id == 2


async def test_process_candidates_cools_down_but_does_not_stop_after_failure_limit(monkeypatch):
    """A streak of CONSECUTIVE_FAILURE_LIMIT failures across the Groq->Mistral
    ->Gemini fallback chain is a transient rate-limit burst, not a permanent
    problem -- the run must cool down and keep going, not give up on the
    remaining candidates."""
    programs = [_program(i) for i in range(1, 11)]
    call_count = {"n": 0}
    sleep_calls: list[float] = []

    async def fake_extract_program(program):
        call_count["n"] += 1
        return program.id, False

    async def fake_sleep(seconds):
        sleep_calls.append(seconds)

    monkeypatch.setattr(pipeline_module, "extract_program", fake_extract_program)

    result = await pipeline_module._process_candidates(programs, sleep=fake_sleep)

    assert call_count["n"] == 10  # every candidate processed, not stopped at 5
    assert len(result["failed_ids"]) == 10
    assert result["total_candidates"] == 10
    assert pipeline_module.COOLDOWN_SECONDS in sleep_calls


async def test_process_candidates_paces_calls_with_a_delay(monkeypatch):
    programs = [_program(1), _program(2)]
    sleep_calls: list[float] = []

    async def fake_extract_program(program):
        return program.id, True

    async def fake_sleep(seconds):
        sleep_calls.append(seconds)

    monkeypatch.setattr(pipeline_module, "extract_program", fake_extract_program)

    await pipeline_module._process_candidates(programs, sleep=fake_sleep)

    assert sleep_calls == [pipeline_module.REQUEST_DELAY_SECONDS, pipeline_module.REQUEST_DELAY_SECONDS]


async def test_process_candidates_resets_consecutive_count_on_success(monkeypatch):
    programs = [_program(i) for i in range(1, 8)]
    # Fail, fail, succeed, fail, fail, succeed, fail -- never 5 in a row.
    outcomes = [False, False, True, False, False, True, False]

    async def fake_extract_program(program):
        return program.id, outcomes[program.id - 1]

    async def fake_sleep(seconds):
        pass

    monkeypatch.setattr(pipeline_module, "extract_program", fake_extract_program)

    result = await pipeline_module._process_candidates(programs, sleep=fake_sleep)

    assert result["succeeded"] == 2
    assert len(result["failed_ids"]) == 5
    assert result["total_candidates"] == 7


class _FakeSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


async def test_run_extraction_reselects_until_no_candidates_remain(monkeypatch):
    """A bare run must keep going on its own: once a pass leaves some
    candidates still without an eligibility row (e.g. they failed during a
    rate-limit burst), the next pass should pick them up automatically --
    no manual re-run of the command needed."""
    candidate_batches = [[_program(1), _program(2)], []]
    calls = {"select": 0, "process": 0}

    async def fake_select_candidates(session, limit_ids=None, limit=None):
        calls["select"] += 1
        return candidate_batches.pop(0)

    async def fake_process_candidates(candidates, sleep=None):
        calls["process"] += 1
        return {"total_candidates": len(candidates), "succeeded": len(candidates), "failed_ids": []}

    monkeypatch.setattr(pipeline_module, "async_session_factory", lambda: _FakeSession())
    monkeypatch.setattr(pipeline_module, "select_candidates", fake_select_candidates)
    monkeypatch.setattr(pipeline_module, "_process_candidates", fake_process_candidates)

    result = await pipeline_module.run_extraction()

    assert calls["select"] == 2
    assert calls["process"] == 1
    assert result["total_candidates"] == 2
    assert result["succeeded"] == 2


async def test_run_extraction_with_limit_processes_a_single_pass(monkeypatch):
    """--limit/--ids are a bounded, single-pass selection (used for manual
    testing/targeted re-extraction) -- they must not loop forever even if
    candidates remain unresolved."""
    calls = {"select": 0}

    async def fake_select_candidates(session, limit_ids=None, limit=None):
        calls["select"] += 1
        return [_program(1)]  # "still more available" every time

    async def fake_process_candidates(candidates, sleep=None):
        return {"total_candidates": len(candidates), "succeeded": 0, "failed_ids": [p.id for p in candidates]}

    monkeypatch.setattr(pipeline_module, "async_session_factory", lambda: _FakeSession())
    monkeypatch.setattr(pipeline_module, "select_candidates", fake_select_candidates)
    monkeypatch.setattr(pipeline_module, "_process_candidates", fake_process_candidates)

    result = await pipeline_module.run_extraction(limit=1)

    assert calls["select"] == 1
    assert result["total_candidates"] == 1
