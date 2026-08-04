import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient
import asyncio
from unittest.mock import AsyncMock, patch

from daad_search.db.models import Base, Program
from daad_search.db.session import engine, async_session_factory
from daad_search.api.main import app, get_session
from sqlalchemy.pool import NullPool
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

pytestmark = pytest.mark.integration

# Global test engine and session factory
_test_engine = None
_test_session_factory = None


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


@pytest.fixture(scope="session", autouse=True)
def setup_db():
    global _test_engine, _test_session_factory

    async def _setup():
        # Use NullPool for tests to avoid connection pooling issues
        test_engine = create_async_engine(
            engine.url, echo=False, poolclass=NullPool
        )

        async with test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)

        test_session_factory = async_sessionmaker(test_engine, expire_on_commit=False)
        async with test_session_factory() as session:
            session.add_all([
                _program(id=1, course_name="Data Science MSc", link="https://example.com/1"),
                _program(
                    id=2, course_name="Mechanical Engineering MSc", link="https://example.com/2",
                    languages=["German"], subject="Mechanical Engineering",
                    tuition_fees_text="1500 EUR/semester", has_tuition_fees=True,
                ),
            ])
            await session.commit()

        return test_engine, test_session_factory

    _test_engine, _test_session_factory = asyncio.run(_setup())

    # Override the app's dependency
    async def override_get_session():
        async with _test_session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session

    yield

    # Cleanup
    asyncio.run(_test_engine.dispose())


def test_search_filters_by_language_and_tuition():
    client = TestClient(app)
    response = client.post("/search", json={
        "filters": {"languages": ["English"], "max_tuition_free_only": True},
        "limit": 20,
    })
    assert response.status_code == 200
    body = response.json()
    assert body["total_matched"] == 1
    assert body["results"][0]["id"] == 1


def test_search_with_no_filters_returns_all():
    client = TestClient(app)
    response = client.post("/search", json={"limit": 20})
    assert response.status_code == 200
    assert response.json()["total_matched"] == 2


def test_get_program_returns_full_detail():
    client = TestClient(app)
    response = client.get("/programs/1")
    assert response.status_code == 200
    assert response.json()["course_name"] == "Data Science MSc"


def test_get_program_not_found_returns_404():
    client = TestClient(app)
    response = client.get("/programs/999")
    assert response.status_code == 404
