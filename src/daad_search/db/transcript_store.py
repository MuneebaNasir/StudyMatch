import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from ..transcript.schema import TranscriptExtraction
from .models import TranscriptProfile

SESSION_TTL = timedelta(hours=24)


async def insert_transcript_profile(session: AsyncSession, extraction: TranscriptExtraction) -> str:
    token = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    # Opportunistic cleanup of expired rows. The read path
    # (get_valid_transcript_profile) only deletes an expired row when someone
    # tries to read that exact token again, which never happens for the
    # dominant usage pattern (upload once, never re-query). Piggybacking a
    # bulk delete on every insert makes cleanup self-amortizing with no cron
    # needed.
    await session.execute(delete(TranscriptProfile).where(TranscriptProfile.expires_at < now))
    session.add(TranscriptProfile(
        session_token=token,
        courses=[c.model_dump() for c in extraction.courses],
        grade_value=extraction.grade_value, grade_scale=extraction.grade_scale,
        nationality=extraction.nationality, degree_field=extraction.degree_field,
        created_at=now, expires_at=now + SESSION_TTL,
    ))
    await session.commit()
    return token


async def get_valid_transcript_profile(session: AsyncSession, token: str) -> TranscriptProfile | None:
    row = await session.get(TranscriptProfile, token)
    if row is None:
        return None
    if row.expires_at < datetime.now(timezone.utc):
        await session.execute(delete(TranscriptProfile).where(TranscriptProfile.session_token == token))
        await session.commit()
        return None
    return row
