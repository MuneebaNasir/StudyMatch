from __future__ import annotations

from typing import Optional

import voyageai
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from ..config import settings

COLLECTION_NAME = "programs"
EMBEDDING_DIM = 1024
EMBEDDING_MODEL = "voyage-3"


def build_embedding_text(course_name: str, subject: Optional[str], description: Optional[str]) -> str:
    parts = [course_name]
    if subject:
        parts.append(subject)
    if description:
        parts.append(description)
    return ". ".join(parts)


def embed_texts(texts: list[str]) -> list[list[float]]:
    client = voyageai.Client(api_key=settings.voyage_api_key)
    result = client.embed(texts, model=EMBEDDING_MODEL, input_type="document")
    return result.embeddings


def get_qdrant_client() -> QdrantClient:
    return QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key)


def ensure_collection(client: QdrantClient) -> None:
    if not client.collection_exists(COLLECTION_NAME):
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE),
        )


def upsert_embedding(
    client: QdrantClient, program_id: int, vector: list[float], payload: dict
) -> None:
    client.upsert(
        collection_name=COLLECTION_NAME,
        points=[PointStruct(id=program_id, vector=vector, payload=payload)],
    )
