import pytest
from datetime import datetime, timezone
from sqlalchemy import select

from daad_search.db.models import Base, Program
from daad_search.db.session import engine, async_session_factory
from daad_search.db.upsert import upsert_program

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
async def setup_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


def _values(course_name: str) -> dict:
    return dict(
        course_name=course_name,
        course_name_short="Test",
        university="Test University",
        city="Berlin",
        languages=["English"],
        subject="Computer Science",
        course_type=2,
        degree="Master of Science",
        duration="4 semesters",
        beginning="Winter semester",
        tuition_fees_text="No tuition fees",
        has_tuition_fees=False,
        application_deadline_text="15 July",
        link="https://example.com/1",
        raw_sections={},
        scraped_at=datetime.now(timezone.utc),
    )


async def test_upsert_inserts_then_updates_without_duplicating():
    async with async_session_factory() as session:
        await upsert_program(session, 1, _values("Test Program"))

    async with async_session_factory() as session:
        row = (await session.execute(select(Program).where(Program.id == 1))).scalar_one()
        assert row.course_name == "Test Program"

    async with async_session_factory() as session:
        await upsert_program(session, 1, _values("Updated Name"))

    async with async_session_factory() as session:
        rows = (await session.execute(select(Program).where(Program.id == 1))).scalars().all()
        assert len(rows) == 1
        assert rows[0].course_name == "Updated Name"
