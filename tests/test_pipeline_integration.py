import pytest
from sqlalchemy import select

from daad_search.db.models import Program
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

    async with session_factory() as session:
        session.add_all([
            make_program(id=1, course_name="Still Listed", link="https://example.com/1"),
            make_program(id=2, course_name="Delisted", link="https://example.com/2"),
        ])
        await session.commit()

    removed = await reconcile_deleted({1}, qdrant)

    assert removed == [2]
    async with session_factory() as session:
        ids = set((await session.execute(select(Program.id))).scalars().all())
        assert ids == {1}


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
