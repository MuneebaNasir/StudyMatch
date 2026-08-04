from qdrant_client.models import Filter, HasIdCondition
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import Program
from ..ingestion.embeddings import COLLECTION_NAME, embed_texts, get_qdrant_client
from .schemas import SearchFilters, SearchResult


def apply_filters(stmt, filters: SearchFilters | None):
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


def to_search_result(row: Program, score: float | None = None) -> SearchResult:
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
    session: AsyncSession, filters: SearchFilters | None, limit: int
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


async def semantic_rank(
    candidate_ids: list[int], query: str, limit: int
) -> list[tuple[int, float]]:
    query_vector = embed_texts([query])[0]
    qdrant = get_qdrant_client()

    hits = qdrant.query_points(
        collection_name=COLLECTION_NAME,
        query=query_vector,
        query_filter=Filter(must=[HasIdCondition(has_id=candidate_ids)]),
        limit=limit,
    ).points

    return [(hit.id, hit.score) for hit in hits]


async def hybrid_search(
    session: AsyncSession,
    filters: SearchFilters | None,
    semantic_query: str,
    limit: int,
) -> tuple[list[SearchResult], int]:
    base = apply_filters(select(Program), filters)
    candidate_rows = (await session.execute(base)).scalars().all()
    candidates_by_id = {row.id: row for row in candidate_rows}

    if not candidates_by_id:
        return [], 0

    ranked = await semantic_rank(list(candidates_by_id.keys()), semantic_query, limit)
    results = [
        to_search_result(candidates_by_id[program_id], score=score)
        for program_id, score in ranked
    ]
    return results, len(candidates_by_id)
