import pytest

pytestmark = pytest.mark.integration

TWO_PROGRAMS = [
    dict(id=1, course_name="Data Science MSc", link="https://example.com/1"),
    dict(
        id=2, course_name="Mechanical Engineering MSc", link="https://example.com/2",
        languages=["German"], subject="Mechanical Engineering",
        tuition_fees_text="1500 EUR/semester", has_tuition_fees=True,
    ),
]


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
