import pytest

from daad_search.ingestion import embeddings as embeddings_module
from daad_search.ingestion.embeddings import build_embedding_text


def test_build_embedding_text_combines_all_fields():
    text = build_embedding_text("Data Science MSc", "Computer Science", "Focus on ML and statistics.")
    assert text == "Data Science MSc. Computer Science. Focus on ML and statistics."


def test_build_embedding_text_omits_missing_optional_fields():
    assert build_embedding_text("Data Science MSc", None, None) == "Data Science MSc"
    assert build_embedding_text("Data Science MSc", "Computer Science", None) == (
        "Data Science MSc. Computer Science"
    )


def test_get_qdrant_client_returns_a_singleton(monkeypatch):
    monkeypatch.setattr(embeddings_module, "_qdrant_client", None)
    first = embeddings_module.get_qdrant_client()
    assert embeddings_module.get_qdrant_client() is first


def test_with_retry_retries_then_succeeds(monkeypatch):
    monkeypatch.setattr(embeddings_module.time, "sleep", lambda _: None)
    calls = []

    def flaky():
        calls.append(1)
        if len(calls) < 3:
            raise RuntimeError("transient")
        return "ok"

    assert embeddings_module.with_retry(flaky) == "ok"
    assert len(calls) == 3


def test_with_retry_reraises_after_exhausting_attempts(monkeypatch):
    monkeypatch.setattr(embeddings_module.time, "sleep", lambda _: None)

    def always_fails():
        raise RuntimeError("down")

    with pytest.raises(RuntimeError):
        embeddings_module.with_retry(always_fails)


@pytest.mark.integration
def test_ensure_collection_and_upsert_embedding_roundtrip(test_qdrant):
    from daad_search.ingestion.embeddings import EMBEDDING_DIM, upsert_embedding

    vector = [0.1] * EMBEDDING_DIM
    upsert_embedding(test_qdrant, 999, vector, {"program_id": 999, "subject": "Test"})

    points = test_qdrant.retrieve(
        collection_name=embeddings_module.COLLECTION_NAME, ids=[999]
    )
    assert len(points) == 1
    assert points[0].payload["subject"] == "Test"
