import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import delete, func, select

from ..config import settings
from ..db.models import Program
from ..db.session import async_session_factory
from ..db.upsert import upsert_program
from ..scraping.cache import ResponseCache
from ..scraping.daad_client import DaadClient
from ..scraping.detail_parser import parse_detail_sections
from ..scraping.list_parser import ProgramSummary, parse_search_response
from . import embeddings as embeddings_module
from .embeddings import (
    EMBED_BATCH_SIZE,
    build_embedding_text,
    embed_texts,
    ensure_collection,
    get_qdrant_client,
    upsert_embedding,
)

logger = logging.getLogger(__name__)

PAGE_SIZE = 100
# Tolerated drift between count.json's reported total and what pagination
# actually collected before we log a warning.
COUNT_MISMATCH_TOLERANCE = 0.02
# If the freshly-fetched live catalog is smaller than this fraction of what's
# already stored in Postgres, refuse to reconcile deletions — a genuine DAAD
# delisting wave is gradual, so a sharp drop is a strong signal of a
# truncated-but-200-OK response rather than real attrition.
RECONCILE_MIN_LIVE_RATIO = 0.9


async def fetch_all_summaries(client: DaadClient) -> list[ProgramSummary]:
    expected_count: int | None = None
    try:
        expected_count = await client.fetch_count()
    except Exception:
        logger.warning("count.json cross-check unavailable; paginating without an upper bound")

    # Hard upper bound on offsets so a misbehaving API (ignored offset, capped
    # limit) cannot spin this loop forever.
    max_offset = None if expected_count is None else expected_count + PAGE_SIZE

    summaries: list[ProgramSummary] = []
    offset = 0
    while True:
        payload = await client.fetch_search_page(offset=offset, limit=PAGE_SIZE)
        page = parse_search_response(payload)
        summaries.extend(page)
        if len(page) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
        if max_offset is not None and offset >= max_offset:
            logger.warning(
                "Stopping pagination at offset %d (expected %d results); "
                "DAAD's API kept returning full pages",
                offset, expected_count,
            )
            break

    if expected_count:
        drift = abs(len(summaries) - expected_count) / expected_count
        if drift > COUNT_MISMATCH_TOLERANCE:
            logger.warning(
                "Collected %d summaries but count.json reports %d (%.1f%% off)",
                len(summaries), expected_count, drift * 100,
            )

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


def embed_rows(rows: list[Program]) -> tuple[dict[int, list[float]], list[int]]:
    """Embed rows in Voyage-sized batches.

    Returns `(vectors_by_program_id, failed_program_ids)`. A failing batch only
    costs that batch's programs their embeddings — the rest of the run
    continues.
    """
    vectors_by_id: dict[int, list[float]] = {}
    failed_ids: list[int] = []

    for start in range(0, len(rows), EMBED_BATCH_SIZE):
        batch = rows[start:start + EMBED_BATCH_SIZE]
        texts = [
            build_embedding_text(row.course_name, row.subject, row.raw_sections.get("description"))
            for row in batch
        ]
        try:
            vectors = embed_texts(texts)
        except Exception as exc:
            logger.warning(
                "Embedding batch %d-%d failed (%d programs skipped): %s",
                start, start + len(batch), len(batch), exc,
            )
            failed_ids.extend(row.id for row in batch)
            continue

        if len(vectors) != len(batch):
            logger.warning(
                "Embedding count mismatch in batch %d-%d: expected %d vectors, got %d",
                start, start + len(batch), len(batch), len(vectors),
            )
            failed_ids.extend(row.id for row in batch[len(vectors):])

        for row, vector in zip(batch, vectors):
            vectors_by_id[row.id] = vector

    return vectors_by_id, failed_ids


async def reconcile_deleted(live_ids: set[int], qdrant) -> list[int]:
    """Delete Postgres rows / Qdrant points for programs DAAD no longer lists."""
    if not live_ids:
        logger.warning("Live catalog came back empty; skipping reconciliation")
        return []

    async with async_session_factory() as session:
        stored_count = (
            await session.execute(select(func.count()).select_from(Program))
        ).scalar_one()
        if stored_count and len(live_ids) < RECONCILE_MIN_LIVE_RATIO * stored_count:
            logger.error(
                "Refusing to reconcile: live catalog has only %d programs vs %d "
                "stored in Postgres (%.1f%% of stored, below the %.0f%% floor). "
                "This looks like a truncated DAAD response, not real delistings — "
                "skipping deletion entirely this run.",
                len(live_ids), stored_count,
                100 * len(live_ids) / stored_count, 100 * RECONCILE_MIN_LIVE_RATIO,
            )
            return []

        stored_ids = set((await session.execute(select(Program.id))).scalars().all())
        stale_ids = sorted(stored_ids - live_ids)
        if not stale_ids:
            return []
        await session.execute(delete(Program).where(Program.id.in_(stale_ids)))
        await session.commit()

    try:
        qdrant.delete(
            collection_name=embeddings_module.COLLECTION_NAME, points_selector=stale_ids
        )
    except Exception as exc:
        logger.warning("Failed to delete %d stale Qdrant points: %s", len(stale_ids), exc)

    logger.info("Reconciled away %d programs no longer listed by DAAD", len(stale_ids))
    return stale_ids


async def run_ingestion(limit_ids: list[int] | None = None, refresh: bool = False) -> dict:
    cache = ResponseCache(settings.cache_dir, refresh=refresh)
    client = DaadClient(cache=cache)
    try:
        all_summaries = await fetch_all_summaries(client)
        summaries = all_summaries
        if limit_ids is not None:
            summaries = [s for s in all_summaries if s.id in limit_ids]

        # DaadClient's semaphore bounds live requests, but cache hits skip it —
        # bound the tasks themselves so a fully cached run doesn't stampede the
        # Postgres connection pool.
        task_limit = asyncio.Semaphore(settings.max_concurrency)

        async def _bounded(summary: ProgramSummary) -> tuple[int, bool]:
            async with task_limit:
                return await ingest_program(client, summary)

        results = await asyncio.gather(*(_bounded(summary) for summary in summaries))
        failed_ids = [program_id for program_id, ok in results if not ok]
        succeeded_ids = [program_id for program_id, ok in results if ok]

        qdrant = get_qdrant_client()
        ensure_collection(qdrant)

        rows: list[Program] = []
        async with async_session_factory() as session:
            for program_id in succeeded_ids:
                row = await session.get(Program, program_id)
                if row is not None:
                    rows.append(row)

        vectors_by_id, embedding_failed_ids = embed_rows(rows)

        for row in rows:
            vector = vectors_by_id.get(row.id)
            if vector is None:
                continue
            payload = {
                "program_id": row.id,
                "subject": row.subject,
                "languages": row.languages,
                "has_tuition_fees": row.has_tuition_fees,
                "course_type": row.course_type,
            }
            try:
                upsert_embedding(qdrant, row.id, vector, payload)
            except Exception as exc:
                logger.warning("Qdrant upsert failed for program %s: %s", row.id, exc)
                embedding_failed_ids.append(row.id)
                vectors_by_id.pop(row.id, None)

        # Only a full run knows the complete live catalog; an --ids run must
        # never delete the programs it did not look at.
        reconciled_ids: list[int] = []
        if limit_ids is None:
            reconciled_ids = await reconcile_deleted({s.id for s in all_summaries}, qdrant)

        return {
            "total": len(summaries),
            "succeeded": len(succeeded_ids),
            "failed_ids": failed_ids,
            "embedded": len(vectors_by_id),
            "embedding_failed_ids": embedding_failed_ids,
            "reconciled_ids": reconciled_ids,
        }
    finally:
        await client.close()
