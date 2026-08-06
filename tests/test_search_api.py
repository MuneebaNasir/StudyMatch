import pytest
import asyncio
from datetime import datetime, timezone

from daad_search.db.models import Eligibility

pytestmark = pytest.mark.integration

TWO_PROGRAMS = [
    dict(id=1, course_name="Data Science MSc", link="https://example.com/1"),
    dict(
        id=2, course_name="Mechanical Engineering MSc", link="https://example.com/2",
        languages=["German"], subject="Mechanical Engineering",
        tuition_fees_text="1500 EUR/semester", has_tuition_fees=True,
    ),
]


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


@pytest.mark.seed_programs(TWO_PROGRAMS)
def test_search_filters_by_language_and_tuition(api_client):
    response = api_client.post("/search", json={
        "filters": {"languages": ["English"], "max_tuition_free_only": True},
        "limit": 20,
    })
    assert response.status_code == 200
    body = response.json()
    assert body["total_matched"] == 1
    assert body["results"][0]["id"] == 1


@pytest.mark.seed_programs(TWO_PROGRAMS)
def test_search_with_no_filters_returns_all(api_client):
    response = api_client.post("/search", json={"limit": 20})
    assert response.status_code == 200
    assert response.json()["total_matched"] == 2


@pytest.mark.seed_programs(TWO_PROGRAMS)
def test_search_paginates_with_offset(api_client):
    first = api_client.post("/search", json={"limit": 1, "offset": 0}).json()
    second = api_client.post("/search", json={"limit": 1, "offset": 1}).json()

    assert first["total_matched"] == second["total_matched"] == 2
    assert len(first["results"]) == len(second["results"]) == 1
    first_ids = {r["id"] for r in first["results"]}
    second_ids = {r["id"] for r in second["results"]}
    assert first_ids.isdisjoint(second_ids)
    assert first_ids | second_ids == {1, 2}

    # Offset past the end returns an empty page, not an error.
    beyond = api_client.post("/search", json={"limit": 20, "offset": 5}).json()
    assert beyond["results"] == []
    assert beyond["total_matched"] == 2


SAME_NAME_PROGRAMS = [
    dict(id=1, course_name="Data Science MSc", university="TU Berlin", link="https://example.com/1"),
    dict(id=2, course_name="Data Science MSc", university="TU Munich", link="https://example.com/2"),
]


@pytest.mark.seed_programs(SAME_NAME_PROGRAMS)
def test_search_paginates_deterministically_with_duplicate_course_names(api_client):
    """Program.id must be a secondary sort key so equal course_names don't produce
    unstable pagination (duplicate or skipped rows across pages)."""
    first = api_client.post("/search", json={"limit": 1, "offset": 0}).json()
    second = api_client.post("/search", json={"limit": 1, "offset": 1}).json()

    assert first["total_matched"] == second["total_matched"] == 2
    assert len(first["results"]) == len(second["results"]) == 1
    first_ids = {r["id"] for r in first["results"]}
    second_ids = {r["id"] for r in second["results"]}
    assert first_ids.isdisjoint(second_ids)
    assert first_ids | second_ids == {1, 2}


@pytest.mark.seed_programs(TWO_PROGRAMS)
@pytest.mark.parametrize(
    "payload",
    [
        {"limit": -1},
        {"limit": 0},
        {"limit": 10000000},
        {"offset": -5},
    ],
)
def test_search_rejects_out_of_bounds_pagination(api_client, payload):
    response = api_client.post("/search", json=payload)
    assert response.status_code == 422


@pytest.mark.seed_programs(TWO_PROGRAMS)
def test_search_empty_result_set(api_client):
    response = api_client.post("/search", json={"filters": {"city": "Nowhere"}})
    assert response.status_code == 200
    body = response.json()
    assert body["results"] == []
    assert body["total_matched"] == 0


@pytest.mark.seed_programs(TWO_PROGRAMS)
def test_get_program_returns_full_detail(api_client):
    response = api_client.get("/programs/1")
    assert response.status_code == 200
    assert response.json()["course_name"] == "Data Science MSc"


@pytest.mark.seed_programs(TWO_PROGRAMS)
def test_get_program_not_found_returns_404(api_client):
    response = api_client.get("/programs/999")
    assert response.status_code == 404


@pytest.mark.seed_programs(TWO_PROGRAMS)
def test_get_program_includes_structured_eligibility_when_present(api_client, seeded_session_factory):
    _seed_eligibility(seeded_session_factory, 1, {"grade_requirement": {"value": 2.5}})

    response = api_client.get("/programs/1")

    assert response.status_code == 200
    assert response.json()["structured_eligibility"] == {"grade_requirement": {"value": 2.5}}


@pytest.mark.seed_programs(TWO_PROGRAMS)
def test_get_program_structured_eligibility_is_none_when_absent(api_client):
    response = api_client.get("/programs/1")

    assert response.status_code == 200
    assert response.json()["structured_eligibility"] is None


def test_cors_allows_the_configured_frontend_origin(api_client):
    response = api_client.options(
        "/search",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
