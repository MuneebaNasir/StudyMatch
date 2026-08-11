import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import Eligibility
from ..query_understanding.parser import parse_query
from ..query_understanding.reasoner import convert_to_german_scale, reason_about_eligibility
from ..query_understanding.schema import (
    CandidateForReasoning,
    EligibilityVerdict,
    QueryResponse,
    QueryResult,
)
from . import search as search_module
from .schemas import SearchFilters

logger = logging.getLogger(__name__)

REASONING_CANDIDATE_CAP = 1


async def handle_query(session: AsyncSession, query: str, limit: int, offset: int = 0) -> QueryResponse:
    parsed = parse_query(query)

    if parsed is not None:
        filters = parsed.filters
        semantic_query = parsed.semantic_query
        profile = parsed.student_profile
    else:
        # Layer 2 degradation: parsing failed on every provider -- fall back
        # to a pure semantic search over the raw query text.
        filters = SearchFilters()
        semantic_query = query
        profile = None

    if profile is not None and profile.grade_value is not None:
        profile.grade_value_on_german_scale = convert_to_german_scale(profile.grade_value, profile.grade_scale)

    if semantic_query:
        results, total = await search_module.hybrid_search(session, filters, semantic_query, limit, offset)
    else:
        results, total = await search_module.filtered_search(session, filters, limit, offset)

    logger.info("RESULTS  total_matched=%d returned_ids=%s", total, [r.id for r in results])

    reasoning_pool = results[:REASONING_CANDIDATE_CAP]
    remainder = results[REASONING_CANDIDATE_CAP:]

    verdicts_by_id: dict[int, EligibilityVerdict] = {}
    reasoned_ids: set[int] = set()

    if profile is not None and reasoning_pool:
        pool_ids = [r.id for r in reasoning_pool]
        eligibility_rows = (
            (await session.execute(select(Eligibility).where(Eligibility.program_id.in_(pool_ids))))
            .scalars()
            .all()
        )
        eligibility_by_id = {row.program_id: row for row in eligibility_rows}

        candidates = [
            CandidateForReasoning(
                program_id=r.id, course_name=r.course_name,
                structured_eligibility=eligibility_by_id[r.id].structured_eligibility,
            )
            for r in reasoning_pool
            if r.id in eligibility_by_id
        ]
        reasoned_ids = {c.program_id for c in candidates}

        raw_verdicts = reason_about_eligibility(profile, candidates) if candidates else []
        if raw_verdicts is not None:
            verdicts_by_id = {v.program_id: v for v in raw_verdicts}
        # else: Layer 2 degradation -- reasoning failed on every provider.
        # verdicts_by_id stays empty; every id in reasoned_ids falls through
        # to "unclear" below.

    query_results: list[QueryResult] = []
    for r in reasoning_pool:
        if r.id in verdicts_by_id:
            v = verdicts_by_id[r.id]
            verdict, reasoning = v.verdict, v.reasoning
        elif r.id in reasoned_ids:
            # Had eligibility data and was sent to the LLM, but no verdict
            # came back for it -- either the whole call failed (Layer 2), or
            # the LLM's response omitted this specific id.
            verdict, reasoning = "unclear", "Eligibility reasoning was unavailable for this program."
        else:
            verdict, reasoning = "no_data", None
        query_results.append(
            QueryResult(**r.model_dump(), eligibility_verdict=verdict, eligibility_reasoning=reasoning)
        )

    for r in remainder:
        query_results.append(
            QueryResult(**r.model_dump(), eligibility_verdict="no_data", eligibility_reasoning=None)
        )

    return QueryResponse(
        results=query_results,
        total_matched=total,
        extracted_filters=filters if parsed is not None else None,
        extracted_profile=profile,
        semantic_query=semantic_query if parsed is not None else None,
    )
