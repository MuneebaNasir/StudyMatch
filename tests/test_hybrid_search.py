import asyncio
import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from qdrant_client.models import PointStruct
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from daad_search.db.models import Base, Program
from daad_search.db.session import engine
from daad_search.ingestion.embeddings import COLLECTION_NAME, ensure_collection, get_qdrant_client
from daad_search.api import search as search_module
from daad_search.api.main import app, get_session

pytestmark = pytest.mark.integration


def _program(**overrides) -> Program:
    defaults = dict(
        course_name_short="Test", university="Test University", city="Berlin",
        languages=["English"], subject="Computer Science", course_type=2,
        degree="Master of Science", duration="4 semesters", beginning="Winter semester",
        tuition_fees_text="No tuition fees", has_tuition_fees=False,
        application_deadline_text="15 July", raw_sections={},
        scraped_at=datetime.now(timezone.utc),
    )
    defaults.update(overrides)
    return Program(**defaults)


@pytest.fixture(autouse=True)
def setup_db_and_qdrant(monkeypatch):
    # TestClient below drives the FastAPI app from a separate thread/event
    # loop. The module-level `engine` from db.session is a pooled engine
    # whose connections get bound to whichever loop first uses them, so
    # reusing it across the fixture's loop and TestClient's loop raises
    # "Future attached to a different loop". Use a dedicated NullPool
    # engine (never reuses a connection across loops) and override the
    # app's get_session dependency to use it, mirroring the established
    # pattern in tests/test_search_api.py.
    test_engine = create_async_engine(engine.url, echo=False, poolclass=NullPool)
    test_session_factory = async_sessionmaker(test_engine, expire_on_commit=False)

    async def _setup():
        async with test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)

        async with test_session_factory() as session:
            session.add_all([
                _program(id=1, course_name="Data Science MSc", link="https://example.com/1"),
                _program(
                    id=2, course_name="Literature MA", link="https://example.com/2",
                    subject="Literature", degree="Master of Arts",
                ),
            ])
            await session.commit()

    asyncio.run(_setup())

    async def override_get_session():
        async with test_session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session

    qdrant = get_qdrant_client()
    ensure_collection(qdrant)
    qdrant.upsert(collection_name=COLLECTION_NAME, points=[
        PointStruct(id=1, vector=[1.0, 0.0] + [0.0] * 1022, payload={"program_id": 1}),
        PointStruct(id=2, vector=[0.0, 1.0] + [0.0] * 1022, payload={"program_id": 2}),
    ])

    def fake_embed(texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] + [0.0] * 1022 for _ in texts]

    monkeypatch.setattr(search_module, "embed_texts", fake_embed)

    yield

    app.dependency_overrides.pop(get_session, None)
    asyncio.run(test_engine.dispose())


def test_hybrid_search_ranks_semantically_closest_first():
    client = TestClient(app)
    response = client.post("/search", json={
        "filters": {"languages": ["English"]},
        "semantic_query": "machine learning and data analysis",
        "limit": 20,
    })
    assert response.status_code == 200
    body = response.json()
    assert body["results"][0]["id"] == 1
    assert body["results"][0]["score"] > body["results"][1]["score"]
