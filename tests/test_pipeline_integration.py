import pytest
from sqlalchemy import select

from daad_search.db.models import Base, Program
from daad_search.db.session import engine, async_session_factory
from daad_search.ingestion.embeddings import COLLECTION_NAME, get_qdrant_client
from daad_search.ingestion.pipeline import run_ingestion

pytestmark = pytest.mark.integration

# Actuarial and Financial Mathematics (RPTU Kaiserslautern-Landau), Additive Manufacturing (Paderborn)
REAL_TEST_IDS = [4722, 10396]


@pytest.fixture(autouse=True)
async def setup_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


async def test_run_ingestion_populates_postgres_and_qdrant():
    result = await run_ingestion(limit_ids=REAL_TEST_IDS)

    assert result["total"] == len(REAL_TEST_IDS)
    assert result["succeeded"] == len(REAL_TEST_IDS)
    assert result["failed_ids"] == []

    async with async_session_factory() as session:
        rows = (await session.execute(select(Program))).scalars().all()
        ids = {row.id for row in rows}
        assert ids == set(REAL_TEST_IDS)

        additive = next(r for r in rows if r.id == 10396)
        assert additive.course_name == "Additive Manufacturing"
        assert "admission_requirements" in additive.raw_sections

    qdrant = get_qdrant_client()
    points = qdrant.retrieve(collection_name=COLLECTION_NAME, ids=REAL_TEST_IDS)
    assert {p.id for p in points} == set(REAL_TEST_IDS)
