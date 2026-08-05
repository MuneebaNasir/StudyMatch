import pytest
from qdrant_client.models import PointStruct

from daad_search.api import search as search_module
from daad_search.ingestion import embeddings as embeddings_module

pytestmark = pytest.mark.integration

TWO_PROGRAMS = [
    dict(id=1, course_name="Data Science MSc", link="https://example.com/1"),
    dict(
        id=2, course_name="Literature MA", link="https://example.com/2",
        subject="Literature", degree="Master of Arts",
    ),
]

# Program 1 sits on the first axis, program 2 on the second; the fake query
# vector points at the first axis, so program 1 must always rank higher.
VECTOR_1 = [1.0, 0.0] + [0.0] * 1022
VECTOR_2 = [0.0, 1.0] + [0.0] * 1022


@pytest.fixture
def seeded_qdrant(monkeypatch, test_qdrant):
    test_qdrant.upsert(
        collection_name=embeddings_module.COLLECTION_NAME,
        points=[
            PointStruct(id=1, vector=VECTOR_1, payload={"program_id": 1}),
            PointStruct(id=2, vector=VECTOR_2, payload={"program_id": 2}),
        ],
        wait=True,
    )

    # Signature must mirror embeddings.embed_texts, which callers invoke as
    # embed_texts(texts, "query").
    def fake_embed(texts: list[str], input_type: str = "document") -> list[list[float]]:
        return [list(VECTOR_1) for _ in texts]

    monkeypatch.setattr(search_module, "embed_texts", fake_embed)
    return test_qdrant


@pytest.mark.seed_programs(TWO_PROGRAMS)
def test_hybrid_search_ranks_semantically_closest_first(api_client, seeded_qdrant):
    response = api_client.post("/search", json={
        "filters": {"languages": ["English"]},
        "semantic_query": "machine learning and data analysis",
        "limit": 20,
    })
    assert response.status_code == 200
    body = response.json()
    assert body["results"][0]["id"] == 1
    assert body["results"][0]["score"] > body["results"][1]["score"]


@pytest.mark.seed_programs(TWO_PROGRAMS)
def test_semantic_only_search_skips_candidate_id_filter(api_client, seeded_qdrant, monkeypatch):
    """With no active filters, Qdrant is queried unrestricted (no HasIdCondition)."""
    seen_candidate_ids = []
    real_rank = search_module.semantic_rank

    async def spy(candidate_ids, query, limit, offset=0):
        seen_candidate_ids.append(candidate_ids)
        return await real_rank(candidate_ids, query, limit, offset)

    monkeypatch.setattr(search_module, "semantic_rank", spy)

    response = api_client.post("/search", json={"semantic_query": "machine learning", "limit": 20})
    assert response.status_code == 200
    body = response.json()
    assert seen_candidate_ids == [None]
    assert body["results"][0]["id"] == 1
    assert body["total_matched"] == 2


@pytest.mark.seed_programs(TWO_PROGRAMS)
def test_semantic_search_paginates(api_client, seeded_qdrant):
    first = api_client.post(
        "/search", json={"semantic_query": "machine learning", "limit": 1, "offset": 0}
    ).json()
    second = api_client.post(
        "/search", json={"semantic_query": "machine learning", "limit": 1, "offset": 1}
    ).json()

    assert [r["id"] for r in first["results"]] == [1]
    assert [r["id"] for r in second["results"]] == [2]
    assert first["total_matched"] == second["total_matched"] == 2


@pytest.mark.seed_programs([])
def test_semantic_search_on_empty_catalog_returns_no_results(api_client, seeded_qdrant):
    response = api_client.post("/search", json={"semantic_query": "machine learning"})
    assert response.status_code == 200
    assert response.json() == {"results": [], "total_matched": 0}
