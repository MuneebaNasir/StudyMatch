from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from daad_search.db.models import Eligibility
from daad_search.db.upsert import upsert_eligibility

pytestmark = pytest.mark.integration


def _values(confidence: str) -> dict:
    return dict(
        requires_gre=True,
        requires_gmat=None,
        min_german_level=None,
        min_english_level="B2",
        min_grade_value=2.5,
        min_grade_scale_note="German grading scale",
        extraction_confidence=confidence,
        structured_eligibility={"notes": "test"},
        extracted_at=datetime.now(timezone.utc),
    )


@pytest.mark.seed_programs([{"id": 1, "course_name": "Test Program", "link": "https://example.com/1"}])
async def test_upsert_inserts_then_updates_without_duplicating(seeded_session_factory):
    async with seeded_session_factory() as session:
        await upsert_eligibility(session, 1, _values("high"))

    async with seeded_session_factory() as session:
        row = (
            await session.execute(select(Eligibility).where(Eligibility.program_id == 1))
        ).scalar_one()
        assert row.extraction_confidence == "high"

    async with seeded_session_factory() as session:
        await upsert_eligibility(session, 1, _values("low"))

    async with seeded_session_factory() as session:
        rows = (
            (await session.execute(select(Eligibility).where(Eligibility.program_id == 1)))
            .scalars()
            .all()
        )
        assert len(rows) == 1
        assert rows[0].extraction_confidence == "low"
