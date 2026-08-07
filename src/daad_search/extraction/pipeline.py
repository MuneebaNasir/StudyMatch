import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import Eligibility, Program
from ..db.session import async_session_factory
from ..db.upsert import upsert_eligibility
from .extractor import extract_eligibility

logger = logging.getLogger(__name__)

CONSECUTIVE_FAILURE_LIMIT = 5
# Paces calls between candidates so free-tier per-minute limits (Mistral's
# ~60 RPM in particular) aren't bursted -- extract_program calls otherwise
# run back-to-back with nothing else throttling them.
REQUEST_DELAY_SECONDS = 1.2
# A streak of CONSECUTIVE_FAILURE_LIMIT failures in a row, across the whole
# Groq->Mistral->Gemini fallback chain, is treated as a transient rate-limit
# burst rather than a permanent problem: cool down long enough for a
# per-minute window to clear, then keep going.
COOLDOWN_SECONDS = 60


async def select_candidates(
    session: AsyncSession, limit_ids: list[int] | None = None, limit: int | None = None
) -> list[Program]:
    stmt = (
        select(Program)
        .outerjoin(Eligibility, Eligibility.program_id == Program.id)
        # Programs with none of the relevant text are never worth an LLM call,
        # even when named explicitly — the call cannot produce anything.
        .where(
            Program.raw_sections.has_key("admission_requirements")
            | Program.raw_sections.has_key("german_language")
            | Program.raw_sections.has_key("english_language")
        )
        .order_by(Program.id)
    )
    if limit_ids is None:
        # A bare run only picks up what hasn't been extracted yet, so it
        # resumes cleanly after a quota cutoff.
        stmt = stmt.where(Eligibility.program_id.is_(None))
    else:
        # An explicit --ids list is targeted re-extraction: process exactly
        # those programs regardless of prior extraction state (upsert_eligibility
        # is ON CONFLICT DO UPDATE, so re-extracting simply refreshes the row).
        stmt = stmt.where(Program.id.in_(limit_ids))
    if limit is not None:
        stmt = stmt.limit(limit)

    rows = (await session.execute(stmt)).scalars().all()
    return list(rows)


async def extract_program(program: Program) -> tuple[int, bool]:
    try:
        result = await asyncio.to_thread(
            extract_eligibility, program.course_name, program.university, program.raw_sections
        )

        values = dict(
            requires_gre=result.requires_gre,
            requires_gmat=result.requires_gmat,
            min_german_level=result.min_german_level,
            min_english_level=result.min_english_level,
            min_grade_value=result.grade_requirement.value if result.grade_requirement else None,
            min_grade_scale_note=result.grade_requirement.scale if result.grade_requirement else None,
            extraction_confidence=result.extraction_confidence,
            structured_eligibility=result.model_dump(),
            extracted_at=datetime.now(timezone.utc),
        )

        async with async_session_factory() as session:
            await upsert_eligibility(session, program.id, values)
    except Exception:
        logger.exception("Failed to extract/store eligibility for program %s", program.id)
        return program.id, False

    return program.id, True


async def _process_candidates(candidates: list[Program], sleep=asyncio.sleep) -> dict:
    """Extract eligibility for each candidate in order. A streak of
    CONSECUTIVE_FAILURE_LIMIT failures in a row cools down instead of
    stopping the run -- every candidate still gets attempted."""
    succeeded_ids: list[int] = []
    failed_ids: list[int] = []
    consecutive_failures = 0

    for program in candidates:
        program_id, ok = await extract_program(program)
        if ok:
            succeeded_ids.append(program_id)
            consecutive_failures = 0
        else:
            failed_ids.append(program_id)
            consecutive_failures += 1
            if consecutive_failures >= CONSECUTIVE_FAILURE_LIMIT:
                logger.warning(
                    "%d consecutive failures (likely a rate-limit burst across "
                    "the fallback chain) -- cooling down %ds before continuing",
                    consecutive_failures, COOLDOWN_SECONDS,
                )
                await sleep(COOLDOWN_SECONDS)
                consecutive_failures = 0
        await sleep(REQUEST_DELAY_SECONDS)

    return {
        "total_candidates": len(candidates),
        "succeeded": len(succeeded_ids),
        "failed_ids": failed_ids,
    }


async def run_extraction(
    limit_ids: list[int] | None = None, limit: int | None = None, sleep=asyncio.sleep
) -> dict:
    """A bare call (no limit_ids/limit) keeps re-selecting and processing
    until no candidates remain, so programs that failed during a rate-limit
    burst get retried automatically -- no manual re-run needed. A targeted
    (--ids) or capped (--limit) run processes exactly its selection once."""
    total_candidates = 0
    total_succeeded = 0
    failed_ids: list[int] = []

    while True:
        async with async_session_factory() as session:
            candidates = await select_candidates(session, limit_ids=limit_ids, limit=limit)
        if not candidates:
            break

        result = await _process_candidates(candidates, sleep=sleep)
        total_candidates += result["total_candidates"]
        total_succeeded += result["succeeded"]
        failed_ids = result["failed_ids"]

        if limit_ids is not None or limit is not None:
            break

    return {
        "total_candidates": total_candidates,
        "succeeded": total_succeeded,
        "failed_ids": failed_ids,
    }
