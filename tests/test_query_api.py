import asyncio
import logging
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
    {"id": 1, "course_name": "A Course", "link": "https://example.com/1"},
    {"id": 2, "course_name": "B Course", "link": "https://example.com/2"},
    {"id": 3, "course_name": "C Course", "link": "https://example.com/3"},
])
def test_query_offset_skips_earlier_pages(api_client, monkeypatch):
    monkeypatch.setattr(
        query_module, "parse_query",
        lambda q: ParsedQuery(filters=SearchFilters(), semantic_query=None, student_profile=StudentProfile()),
    )

    response = api_client.post("/query", json={"query": "any course", "limit": 2, "offset": 1})

    assert response.status_code == 200
    body = response.json()
    assert body["total_matched"] == 3
    assert [r["course_name"] for r in body["results"]] == ["B Course", "C Course"]


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
    assert body["semantic_query"] is None  # this test's ParsedQuery mock never sets it


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


from daad_search.api import main as main_module
from daad_search.query_understanding.schema import EligibilityVerdict


@pytest.mark.seed_programs([
    {"id": 1, "course_name": "Robotics Engineering MSc", "link": "https://example.com/1"},
])
def test_evaluate_eligibility_returns_no_data_without_structured_eligibility(api_client):
    response = api_client.post(
        "/programs/1/evaluate-eligibility",
        json={"profile": {"nationality": "Pakistan"}},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["eligibility_verdict"] == "no_data"
    assert body["eligibility_reasoning"] is None


def test_evaluate_eligibility_returns_404_for_unknown_program(api_client):
    response = api_client.post(
        "/programs/999999/evaluate-eligibility",
        json={"profile": {"nationality": "Pakistan"}},
    )
    assert response.status_code == 404


@pytest.mark.seed_programs([
    {"id": 1, "course_name": "Robotics Engineering MSc", "link": "https://example.com/1"},
])
def test_evaluate_eligibility_returns_unclear_when_reasoning_fails(api_client, seeded_session_factory, monkeypatch):
    _seed_eligibility(seeded_session_factory, 1, {"grade_requirement": {"value": 2.5}})
    monkeypatch.setattr(main_module, "reason_about_eligibility", lambda profile, candidates: None)

    response = api_client.post(
        "/programs/1/evaluate-eligibility",
        json={"profile": {"nationality": "Pakistan"}},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["eligibility_verdict"] == "unclear"
    assert body["eligibility_reasoning"] == "Eligibility reasoning was unavailable for this program."


@pytest.mark.seed_programs([
    {"id": 1, "course_name": "Robotics Engineering MSc", "link": "https://example.com/1"},
])
def test_evaluate_eligibility_returns_real_verdict(api_client, seeded_session_factory, monkeypatch):
    _seed_eligibility(seeded_session_factory, 1, {"grade_requirement": {"value": 2.5}})
    monkeypatch.setattr(
        main_module, "reason_about_eligibility",
        lambda profile, candidates: [EligibilityVerdict(program_id=1, verdict="eligible", reasoning="Meets requirements.")],
    )

    response = api_client.post(
        "/programs/1/evaluate-eligibility",
        json={"profile": {"nationality": "Pakistan"}},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["eligibility_verdict"] == "eligible"
    assert body["eligibility_reasoning"] == "Meets requirements."


@pytest.mark.seed_programs([
    {"id": 1, "course_name": "Robotics Engineering MSc", "link": "https://example.com/1"},
])
def test_query_populates_german_scale_grade_conversion(api_client, monkeypatch):
    monkeypatch.setattr(
        query_module, "parse_query",
        lambda q: ParsedQuery(
            filters=SearchFilters(), semantic_query=None,
            student_profile=StudentProfile(grade_value=2.0, grade_scale="4.0 GPA scale (USA)"),
        ),
    )

    response = api_client.post("/query", json={"query": "robotics masters"})

    assert response.status_code == 200
    body = response.json()
    assert body["extracted_profile"]["grade_value_on_german_scale"] == pytest.approx(3.0)


@pytest.mark.seed_programs([
    {"id": 1, "course_name": "Robotics Engineering MSc", "link": "https://example.com/1"},
])
def test_query_leaves_german_scale_conversion_null_for_unrecognized_scale(api_client, monkeypatch):
    monkeypatch.setattr(
        query_module, "parse_query",
        lambda q: ParsedQuery(
            filters=SearchFilters(), semantic_query=None,
            student_profile=StudentProfile(grade_value=7.5, grade_scale="some obscure national scale"),
        ),
    )

    response = api_client.post("/query", json={"query": "robotics masters"})

    assert response.status_code == 200
    body = response.json()
    assert body["extracted_profile"]["grade_value_on_german_scale"] is None


@pytest.mark.seed_programs([
    {"id": 1, "course_name": "Robotics Engineering MSc", "link": "https://example.com/1"},
])
def test_query_logs_the_results_outcome(api_client, monkeypatch, caplog):
    monkeypatch.setattr(
        query_module, "parse_query",
        lambda q: ParsedQuery(filters=SearchFilters(), semantic_query=None, student_profile=StudentProfile()),
    )

    with caplog.at_level(logging.INFO, logger="daad_search.api.query"):
        response = api_client.post("/query", json={"query": "robotics masters"})

    assert response.status_code == 200
    messages = [record.getMessage() for record in caplog.records]
    assert any("RESULTS" in m and "total_matched=1" in m for m in messages)
