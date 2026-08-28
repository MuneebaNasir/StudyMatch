import asyncio
from datetime import datetime, timedelta, timezone

from daad_search.db.models import TranscriptProfile
from daad_search.db.transcript_store import get_valid_transcript_profile, insert_transcript_profile
from daad_search.transcript.schema import ExtractedCourse, TranscriptExtraction

pytestmark = __import__("pytest").mark.integration


def test_transcript_profile_table_is_created(test_session_factory):
    async def _run():
        async with test_session_factory() as session:
            now = datetime.now(timezone.utc)
            row = TranscriptProfile(
                session_token="smoke-test-token", courses=[], created_at=now, expires_at=now,
            )
            session.add(row)
            await session.commit()
            return await session.get(TranscriptProfile, "smoke-test-token")

    row = asyncio.run(_run())
    assert row is not None
    assert row.courses == []


def test_insert_and_read_back_a_transcript_profile(test_session_factory):
    extraction = TranscriptExtraction(
        courses=[ExtractedCourse(name="Linear Algebra", grade="A")],
        grade_value=3.8, grade_scale="4.0 GPA", nationality="Pakistan",
        degree_field="Computer Science", extraction_confidence="high",
    )

    async def _run():
        async with test_session_factory() as session:
            token = await insert_transcript_profile(session, extraction)
            row = await get_valid_transcript_profile(session, token)
            return token, row

    token, row = asyncio.run(_run())

    assert row is not None
    assert row.session_token == token
    assert row.courses == [{"name": "Linear Algebra", "grade": "A"}]
    assert row.nationality == "Pakistan"


def test_expired_transcript_profile_reads_back_as_none(test_session_factory):
    async def _run():
        async with test_session_factory() as session:
            now = datetime.now(timezone.utc)
            session.add(TranscriptProfile(
                session_token="expired-token", courses=[],
                created_at=now - timedelta(hours=48), expires_at=now - timedelta(hours=24),
            ))
            await session.commit()
            return await get_valid_transcript_profile(session, "expired-token")

    assert asyncio.run(_run()) is None


def test_unknown_token_reads_back_as_none(test_session_factory):
    async def _run():
        async with test_session_factory() as session:
            return await get_valid_transcript_profile(session, "does-not-exist")

    assert asyncio.run(_run()) is None
