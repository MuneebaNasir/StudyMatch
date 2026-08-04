import pytest

from daad_search.ingestion.embeddings import build_embedding_text


def test_build_embedding_text_combines_all_fields():
    text = build_embedding_text("Data Science MSc", "Computer Science", "Focus on ML and statistics.")
    assert text == "Data Science MSc. Computer Science. Focus on ML and statistics."


def test_build_embedding_text_omits_missing_optional_fields():
    assert build_embedding_text("Data Science MSc", None, None) == "Data Science MSc"
    assert build_embedding_text("Data Science MSc", "Computer Science", None) == (
        "Data Science MSc. Computer Science"
    )


@pytest.mark.integration
def test_ensure_collection_and_upsert_embedding_roundtrip():
    from daad_search.ingestion.embeddings import (
        COLLECTION_NAME, EMBEDDING_DIM, ensure_collection, get_qdrant_client, upsert_embedding,
    )

    client = get_qdrant_client()
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass

    ensure_collection(client)
    vector = [0.1] * EMBEDDING_DIM
    upsert_embedding(client, 999, vector, {"program_id": 999, "subject": "Test"})

    points = client.retrieve(collection_name=COLLECTION_NAME, ids=[999])
    assert len(points) == 1
    assert points[0].payload["subject"] == "Test"
