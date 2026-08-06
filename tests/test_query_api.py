import asyncio
from datetime import datetime, timezone

import pytest

from daad_search.api import query as query_module
from daad_search.api.schemas import SearchFilters
from daad_search.db.models import Eligibility
from daad_search.query_understanding.schema import ParsedQuery, StudentProfile

pytestmark = pytest.mark.integration


def _seed_eligibility(session_factory, program_id: int, structured_eligibility: dict) -> None:
    async def _seed() -> None:
        async with session_factory() as session:
            session.add(Eligibility(
                program_id=program_id, extraction_confidence="high",
                structured_eligibility=structured_eligibility,
                extracted_at=datetime.now(timezone.utc),
            ))
            await session.commit()

    asyncio.run(_seed())


@pytest.mark.seed_programs([
    {"id": 1, "course_name": "Robotics Engineering MSc", "subject": "Mechanical Engineering",
     "languages": ["English"], "has_tuition_fees": False, "link": "https://example.com/1"},
])
def test_query_reasoning_failure_returns_unclear_verdicts(api_client, seeded_session_factory, monkeypatch):
    _seed_eligibility(seeded_session_factory, 1, {"grade_requirement": {"value": 2.5}})

    monkeypatch.setattr(
        query_module, "parse_query",
        lambda q: ParsedQuery(
            filters=SearchFilters(subject="Mechanical Engineering"), semantic_query=None,
            student_profile=StudentProfile(nationality="Pakistan"),
        ),
    )
    monkeypatch.setattr(query_module, "reason_about_eligibility", lambda profile, candidates: None)

    response = api_client.post("/query", json={"query": "robotics masters"})

    assert response.status_code == 200
    body = response.json()
    result = next(r for r in body["results"] if r["id"] == 1)
    assert result["eligibility_verdict"] == "unclear"
    assert body["extracted_filters"] is not None
    assert body["extracted_profile"]["nationality"] == "Pakistan"


@pytest.mark.seed_programs([
    {"id": 1, "course_name": "Robotics Engineering MSc", "subject": "Mechanical Engineering",
     "languages": ["English"], "has_tuition_fees": False, "link": "https://example.com/1"},
])
def test_query_candidate_with_no_eligibility_row_gets_no_data(api_client, monkeypatch):
    monkeypatch.setattr(
        query_module, "parse_query",
        lambda q: ParsedQuery(
            filters=SearchFilters(subject="Mechanical Engineering"), semantic_query=None,
            student_profile=StudentProfile(nationality="Pakistan"),
        ),
    )

    response = api_client.post("/query", json={"query": "robotics masters"})

    assert response.status_code == 200
    body = response.json()
    result = next(r for r in body["results"] if r["id"] == 1)
    assert result["eligibility_verdict"] == "no_data"
    assert result["eligibility_reasoning"] is None


# Append to tests/test_query_api.py -- exercises the parse-failure fallback
# path, which needs the semantic-search machinery (Qdrant), matching the
# existing tests/test_hybrid_search.py pattern.
from qdrant_client.models import PointStruct

from daad_search.api import search as search_module
from daad_search.ingestion import embeddings as embeddings_module


@pytest.mark.seed_programs([
    {"id": 1, "course_name": "Robotics Engineering MSc", "link": "https://example.com/1"},
])
def test_query_parse_failure_falls_back_to_semantic_search(api_client, test_qdrant, monkeypatch):
    test_qdrant.upsert(
        collection_name=embeddings_module.COLLECTION_NAME,
        points=[PointStruct(id=1, vector=[1.0, 0.0] + [0.0] * 1022, payload={"program_id": 1})],
        wait=True,
    )

    def fake_embed(texts: list[str], input_type: str = "document") -> list[list[float]]:
        return [[1.0, 0.0] + [0.0] * 1022 for _ in texts]

    monkeypatch.setattr(query_module, "parse_query", lambda q: None)
    monkeypatch.setattr(search_module, "embed_texts", fake_embed)

    response = api_client.post("/query", json={"query": "Robotics Engineering MSc"})

    assert response.status_code == 200
    body = response.json()
    assert body["extracted_filters"] is None
    assert body["extracted_profile"] is None
    assert any(r["id"] == 1 for r in body["results"])
    assert all(r["eligibility_verdict"] == "no_data" for r in body["results"])
