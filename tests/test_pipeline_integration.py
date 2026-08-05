import logging
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from daad_search.db.models import Eligibility, Program
from daad_search.db.upsert import upsert_eligibility
from daad_search.ingestion import embeddings as embeddings_module
from daad_search.ingestion import pipeline as pipeline_module
from daad_search.ingestion.pipeline import reconcile_deleted, run_ingestion

pytestmark = pytest.mark.integration

# Actuarial and Financial Mathematics (RPTU Kaiserslautern-Landau), Additive Manufacturing (Paderborn)
REAL_TEST_IDS = [4722, 10396]


@pytest.fixture
def pipeline_env(monkeypatch, test_session_factory, test_qdrant):
    """Point run_ingestion at the test database and the test Qdrant collection."""
    monkeypatch.setattr(pipeline_module, "async_session_factory", test_session_factory)
    return test_session_factory, test_qdrant


async def test_run_ingestion_populates_postgres_and_qdrant(pipeline_env):
    session_factory, qdrant = pipeline_env

    result = await run_ingestion(limit_ids=REAL_TEST_IDS)

    assert result["total"] == len(REAL_TEST_IDS)
    assert result["succeeded"] == len(REAL_TEST_IDS)
    assert result["failed_ids"] == []
    assert result["embedded"] == len(REAL_TEST_IDS)
    assert result["embedding_failed_ids"] == []
    # An --ids-scoped run must never reconcile anything away.
    assert result["reconciled_ids"] == []

    async with session_factory() as session:
        rows = (await session.execute(select(Program))).scalars().all()
        ids = {row.id for row in rows}
        assert ids == set(REAL_TEST_IDS)

        additive = next(r for r in rows if r.id == 10396)
        assert additive.course_name == "Additive Manufacturing"
        assert "admission_requirements" in additive.raw_sections

    points = qdrant.retrieve(
        collection_name=embeddings_module.COLLECTION_NAME, ids=REAL_TEST_IDS
    )
    assert {p.id for p in points} == set(REAL_TEST_IDS)


async def test_reconcile_deleted_removes_programs_missing_upstream(pipeline_env, make_program):
    session_factory, qdrant = pipeline_env

    # 10 stored programs with only 1 delisted keeps the live/stored ratio (90%)
    # at the safety floor, so this still exercises a normal small-scale
    # reconciliation rather than tripping the truncated-response guard.
    async with session_factory() as session:
        session.add_all([
            make_program(id=i, course_name=f"Program {i}", link=f"https://example.com/{i}")
            for i in range(1, 10)
        ] + [
            make_program(id=10, course_name="Delisted", link="https://example.com/10"),
        ])
        await session.commit()

    removed = await reconcile_deleted(set(range(1, 10)), qdrant)

    assert removed == [10]
    async with session_factory() as session:
        ids = set((await session.execute(select(Program.id))).scalars().all())
        assert ids == set(range(1, 10))


async def test_reconcile_deleted_cascades_to_eligibility_rows(pipeline_env, make_program):
    """A delisted program that already has an extracted eligibility row must be
    deletable. Without ON DELETE CASCADE on eligibility.program_id, the bulk
    `delete(Program)` here raises a foreign-key violation and takes the whole
    `ingest` run down with it."""
    session_factory, qdrant = pipeline_env

    async with session_factory() as session:
        session.add_all([
            make_program(id=i, course_name=f"Program {i}", link=f"https://example.com/{i}")
            for i in range(1, 10)
        ] + [
            make_program(id=10, course_name="Delisted", link="https://example.com/10"),
        ])
        await session.commit()

    # The delisted program (and one surviving one) each carry an extraction.
    async with session_factory() as session:
        for program_id in (1, 10):
            await upsert_eligibility(session, program_id, dict(
                requires_gre=True, requires_gmat=None,
                min_german_level=None, min_english_level="B2",
                min_grade_value=2.5, min_grade_scale_note="German grading scale",
                extraction_confidence="high", structured_eligibility={"notes": "test"},
                extracted_at=datetime.now(timezone.utc),
            ))

    removed = await reconcile_deleted(set(range(1, 10)), qdrant)

    assert removed == [10]
    async with session_factory() as session:
        program_ids = set((await session.execute(select(Program.id))).scalars().all())
        eligibility_ids = set(
            (await session.execute(select(Eligibility.program_id))).scalars().all()
        )

    assert program_ids == set(range(1, 10))
    # The delisted program's extraction went with it; the surviving one stayed.
    assert eligibility_ids == {1}


async def test_reconcile_deleted_skips_empty_live_catalog(pipeline_env, make_program):
    session_factory, qdrant = pipeline_env

    async with session_factory() as session:
        session.add_all([
            make_program(id=1, course_name="Still Listed", link="https://example.com/1"),
        ])
        await session.commit()

    assert await reconcile_deleted(set(), qdrant) == []
    async with session_factory() as session:
        ids = set((await session.execute(select(Program.id))).scalars().all())
        assert ids == {1}


async def test_reconcile_deleted_skips_when_live_catalog_suspiciously_small(
    pipeline_env, make_program, caplog
):
    """A truncated-but-200-OK DAAD response must never mass-delete real rows."""
    session_factory, qdrant = pipeline_env

    async with session_factory() as session:
        session.add_all([
            make_program(id=i, course_name=f"Program {i}", link=f"https://example.com/{i}")
            for i in range(1, 11)
        ])
        await session.commit()

    # Live catalog only reports 2 of the 10 stored programs — well under the
    # 90% floor — which should look like a truncated response, not real
    # delistings.
    with caplog.at_level(logging.ERROR):
        removed = await reconcile_deleted({1, 2}, qdrant)

    assert removed == []
    assert any("Refusing to reconcile" in record.message for record in caplog.records)

    async with session_factory() as session:
        ids = set((await session.execute(select(Program.id))).scalars().all())
        assert ids == set(range(1, 11))
