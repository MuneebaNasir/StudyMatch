from __future__ import annotations

from typing import Optional
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import Program
from .schemas import SearchFilters, SearchResult


def apply_filters(stmt, filters: Optional[SearchFilters]):
    if filters is None:
        return stmt
    if filters.languages:
        stmt = stmt.where(Program.languages.overlap(filters.languages))
    if filters.max_tuition_free_only:
        stmt = stmt.where(Program.has_tuition_fees.is_(False))
    if filters.subject:
        stmt = stmt.where(Program.subject == filters.subject)
    if filters.city:
        stmt = stmt.where(Program.city == filters.city)
    if filters.course_type is not None:
        stmt = stmt.where(Program.course_type == filters.course_type)
    return stmt


def to_search_result(row: Program, score: Optional[float] = None) -> SearchResult:
    return SearchResult(
        id=row.id,
        course_name=row.course_name,
        university=row.university,
        city=row.city,
        languages=row.languages,
        subject=row.subject,
        tuition_fees_text=row.tuition_fees_text,
        application_deadline_text=row.application_deadline_text,
        link=row.link,
        score=score,
    )


async def filtered_search(
    session: AsyncSession, filters: Optional[SearchFilters], limit: int
) -> tuple[list[SearchResult], int]:
    base = apply_filters(select(Program), filters)

    total = (
        await session.execute(select(func.count()).select_from(base.subquery()))
    ).scalar_one()

    rows = (
        (await session.execute(base.order_by(Program.course_name).limit(limit)))
        .scalars()
        .all()
    )

    return [to_search_result(row) for row in rows], total
