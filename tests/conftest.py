"""Shared test fixtures.

Every fixture here is isolated from production data: Postgres work happens in
`settings.test_database_url` (default: the main database name suffixed with
`_test`) and Qdrant work happens in `settings.test_collection_name`. No test
should import `daad_search.db.session.engine` / `async_session_factory` or
`embeddings.COLLECTION_NAME` directly.
"""

import asyncio
from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from daad_search.config import settings
from daad_search.db.models import Base, Program
from daad_search.ingestion import embeddings as embeddings_module

TEST_COLLECTION_NAME = settings.test_collection_name


@pytest.fixture
def make_program():
    """Factory for a fully-populated Program row; override any field by kwarg."""

    def _make(**overrides) -> Program:
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

    return _make


@pytest.fixture
def test_engine():
    """Engine bound to the *test* database.

    NullPool because fixtures and FastAPI's TestClient run on different event
    loops, and a pooled connection cannot be reused across loops.
    """
    engine = create_async_engine(settings.test_database_url, echo=False, poolclass=NullPool)
    yield engine
    asyncio.run(engine.dispose())


@pytest.fixture
def test_session_factory(test_engine):
    """Session factory against a freshly created schema in the test database."""

    async def _reset() -> None:
        async with test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(_reset())
    return async_sessionmaker(test_engine, expire_on_commit=False)


@pytest.fixture
def seeded_session_factory(test_session_factory, make_program, request):
    """`test_session_factory` pre-loaded with the rows in the `seed_programs` marker.

    Usage: `@pytest.mark.seed_programs([{...overrides...}, ...])`
    """
    marker = request.node.get_closest_marker("seed_programs")
    specs = marker.args[0] if marker else []

    async def _seed() -> None:
        async with test_session_factory() as session:
            session.add_all([make_program(**spec) for spec in specs])
            await session.commit()

    asyncio.run(_seed())
    return test_session_factory


@pytest.fixture
def test_qdrant(monkeypatch):
    """A clean Qdrant test collection; redirects all code under test onto it."""
    monkeypatch.setattr(embeddings_module, "COLLECTION_NAME", TEST_COLLECTION_NAME)

    client = embeddings_module.get_qdrant_client()
    if client.collection_exists(TEST_COLLECTION_NAME):
        client.delete_collection(TEST_COLLECTION_NAME)
    embeddings_module.ensure_collection(client)

    yield client

    if client.collection_exists(TEST_COLLECTION_NAME):
        client.delete_collection(TEST_COLLECTION_NAME)


@pytest.fixture
def api_client(seeded_session_factory):
    """FastAPI TestClient whose session dependency points at the test database."""
    from fastapi.testclient import TestClient

    from daad_search.api.main import app, get_session

    async def override_get_session():
        async with seeded_session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.pop(get_session, None)


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "seed_programs(specs): rows to insert via the make_program factory"
    )
