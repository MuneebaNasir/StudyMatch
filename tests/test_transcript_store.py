import asyncio
from datetime import datetime, timezone

from daad_search.db.models import TranscriptProfile

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
