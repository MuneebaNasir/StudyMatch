import logging
from datetime import datetime, timezone

from ..config import settings
from ..db.models import Program
from ..db.session import async_session_factory
from ..db.upsert import upsert_program
from ..scraping.cache import ResponseCache
from ..scraping.daad_client import DaadClient
from ..scraping.detail_parser import parse_detail_sections
from ..scraping.list_parser import ProgramSummary, parse_search_response
from .embeddings import (
    build_embedding_text,
    embed_texts,
    ensure_collection,
    get_qdrant_client,
    upsert_embedding,
)

logger = logging.getLogger(__name__)

PAGE_SIZE = 100


async def fetch_all_summaries(client: DaadClient) -> list[ProgramSummary]:
    summaries: list[ProgramSummary] = []
    offset = 0
    while True:
        payload = await client.fetch_search_page(offset=offset, limit=PAGE_SIZE)
        page = parse_search_response(payload)
        summaries.extend(page)
        if len(page) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
    return summaries


async def ingest_program(client: DaadClient, summary: ProgramSummary) -> tuple[int, bool]:
    try:
        html = await client.fetch_detail_html(summary.id)

        sections = parse_detail_sections(html)
        missing = [k for k in ("description", "admission_requirements") if k not in sections]
        if missing:
            logger.warning("Program %s missing sections: %s", summary.id, missing)

        values = dict(
            course_name=summary.course_name,
            course_name_short=summary.course_name_short,
            university=summary.university,
            city=summary.city,
            languages=summary.languages,
            subject=summary.subject,
            course_type=summary.course_type,
            degree=sections.get("degree"),
            duration=summary.duration,
            beginning=summary.beginning,
            tuition_fees_text=summary.tuition_fees_text,
            has_tuition_fees=summary.has_tuition_fees,
            application_deadline_text=sections.get("application_deadline"),
            link=summary.link,
            raw_sections=sections,
            scraped_at=datetime.now(timezone.utc),
        )

        async with async_session_factory() as session:
            await upsert_program(session, summary.id, values)

        return summary.id, True
    except Exception:
        logger.exception("Failed to ingest program %s", summary.id)
        return summary.id, False


async def run_ingestion(limit_ids: list[int] | None = None) -> dict:
    cache = ResponseCache(settings.cache_dir)
    client = DaadClient(cache=cache)
    try:
        summaries = await fetch_all_summaries(client)
        if limit_ids is not None:
            summaries = [s for s in summaries if s.id in limit_ids]

        failed_ids: list[int] = []
        succeeded_ids: list[int] = []
        for summary in summaries:
            program_id, ok = await ingest_program(client, summary)
            (succeeded_ids if ok else failed_ids).append(program_id)

        qdrant = get_qdrant_client()
        ensure_collection(qdrant)

        rows: list[Program] = []
        for program_id in succeeded_ids:
            async with async_session_factory() as session:
                row = await session.get(Program, program_id)
                rows.append(row)

        texts = [
            build_embedding_text(row.course_name, row.subject, row.raw_sections.get("description"))
            for row in rows
        ]
        vectors: list[list[float]] = []
        if texts:
            try:
                vectors = embed_texts(texts)
            except Exception as exc:
                logger.warning(
                    "Embedding failed for %d programs; skipping embeddings for this run: %s",
                    len(texts), exc,
                )
                vectors = []

        if vectors and len(vectors) != len(rows):
            logger.warning(
                "Embedding count mismatch: expected %d vectors, got %d; only upserting matched rows",
                len(rows), len(vectors),
            )

        for row, vector in zip(rows, vectors):
            payload = {
                "program_id": row.id,
                "subject": row.subject,
                "languages": row.languages,
                "has_tuition_fees": row.has_tuition_fees,
                "course_type": row.course_type,
            }
            upsert_embedding(qdrant, row.id, vector, payload)

        return {"total": len(summaries), "succeeded": len(succeeded_ids), "failed_ids": failed_ids}
    finally:
        await client.close()
