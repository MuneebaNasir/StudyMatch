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


async def select_candidates(
    session: AsyncSession, limit_ids: list[int] | None = None, limit: int | None = None
) -> list[Program]:
    stmt = (
        select(Program)
        .outerjoin(Eligibility, Eligibility.program_id == Program.id)
        .where(Eligibility.program_id.is_(None))
        .where(
            Program.raw_sections.has_key("admission_requirements")
            | Program.raw_sections.has_key("german_language")
            | Program.raw_sections.has_key("english_language")
        )
        .order_by(Program.id)
    )
    if limit_ids is not None:
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
    except Exception:
        logger.exception("Failed to extract eligibility for program %s", program.id)
        return program.id, False

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

    try:
        async with async_session_factory() as session:
            await upsert_eligibility(session, program.id, values)
    except Exception:
        logger.exception("Failed to store eligibility for program %s", program.id)
        return program.id, False

    return program.id, True


async def _process_candidates(candidates: list[Program]) -> dict:
    """Extract eligibility for each candidate in order, stopping early after
    CONSECUTIVE_FAILURE_LIMIT failures in a row (a strong signal of quota
    exhaustion, not per-program bad luck)."""
    succeeded_ids: list[int] = []
    failed_ids: list[int] = []
    consecutive_failures = 0
    stopped_early = False

    for program in candidates:
        program_id, ok = await extract_program(program)
        if ok:
            succeeded_ids.append(program_id)
            consecutive_failures = 0
        else:
            failed_ids.append(program_id)
            consecutive_failures += 1
            if consecutive_failures >= CONSECUTIVE_FAILURE_LIMIT:
                logger.error(
                    "Stopping early after %d consecutive failures (likely quota exhausted)",
                    consecutive_failures,
                )
                stopped_early = True
                break

    return {
        "total_candidates": len(candidates),
        "succeeded": len(succeeded_ids),
        "failed_ids": failed_ids,
        "stopped_early": stopped_early,
    }


async def run_extraction(limit_ids: list[int] | None = None, limit: int | None = None) -> dict:
    async with async_session_factory() as session:
        candidates = await select_candidates(session, limit_ids=limit_ids, limit=limit)
    return await _process_candidates(candidates)
