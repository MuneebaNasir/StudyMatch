import asyncio

from qdrant_client.models import Filter, HasIdCondition
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import Program
from ..ingestion import embeddings as embeddings_module
from ..ingestion.embeddings import embed_texts, get_qdrant_client, with_retry
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


def has_active_filters(filters: SearchFilters | None) -> bool:
    """True when at least one filter field actually narrows the candidate set."""
    if filters is None:
        return False
    return any(
        value not in (None, False, [], "")
        for value in filters.model_dump().values()
    )


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
    session: AsyncSession, filters: SearchFilters | None, limit: int, offset: int = 0
) -> tuple[list[SearchResult], int]:
    base = apply_filters(select(Program), filters)

    total = (
        await session.execute(select(func.count()).select_from(base.subquery()))
    ).scalar_one()

    rows = (
        (
            await session.execute(
                base.order_by(Program.course_name, Program.id).offset(offset).limit(limit)
            )
        )
        .scalars()
        .all()
    )

    return [to_search_result(row) for row in rows], total


def _query_qdrant(
    query_vector: list[float], candidate_ids: list[int] | None, limit: int, offset: int
) -> list[tuple[int, float]]:
    query_filter = (
        Filter(must=[HasIdCondition(has_id=candidate_ids)])
        if candidate_ids is not None
        else None
    )
    hits = with_retry(
        get_qdrant_client().query_points,
        collection_name=embeddings_module.COLLECTION_NAME,
        query=query_vector,
        query_filter=query_filter,
        limit=limit,
        offset=offset,
    ).points
    return [(hit.id, hit.score) for hit in hits]


async def semantic_rank(
    candidate_ids: list[int] | None, query: str, limit: int, offset: int = 0
) -> list[tuple[int, float]]:
    """Rank by semantic similarity. `candidate_ids=None` searches the whole collection.

    Both the Voyage and Qdrant SDKs are synchronous, so their calls run in a
    worker thread to keep the event loop free.
    """
    query_vector = (await asyncio.to_thread(embed_texts, [query], "query"))[0]
    return await asyncio.to_thread(_query_qdrant, query_vector, candidate_ids, limit, offset)


async def hybrid_search(
    session: AsyncSession,
    filters: SearchFilters | None,
    semantic_query: str,
    limit: int,
    offset: int = 0,
) -> tuple[list[SearchResult], int]:
    if not has_active_filters(filters):
        # Nothing narrows the catalog: let Qdrant search everything and only
        # look up the handful of rows it returns.
        total = (
            await session.execute(select(func.count()).select_from(Program))
        ).scalar_one()
        if total == 0:
            return [], 0
        ranked = await semantic_rank(None, semantic_query, limit, offset)
    else:
        candidate_ids = list(
            (await session.execute(apply_filters(select(Program.id), filters))).scalars().all()
        )
        total = len(candidate_ids)
        if not candidate_ids:
            return [], 0
        ranked = await semantic_rank(candidate_ids, semantic_query, limit, offset)

    if not ranked:
        return [], total

    ranked_ids = [program_id for program_id, _ in ranked]
    rows = (
        (await session.execute(select(Program).where(Program.id.in_(ranked_ids))))
        .scalars()
        .all()
    )
    rows_by_id = {row.id: row for row in rows}

    results = [
        to_search_result(rows_by_id[program_id], score=score)
        for program_id, score in ranked
        if program_id in rows_by_id
    ]
    return results, total
