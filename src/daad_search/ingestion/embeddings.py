import logging
import time
from typing import Any, Callable, TypeVar

import voyageai
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from ..config import settings

logger = logging.getLogger(__name__)

COLLECTION_NAME = settings.collection_name
EMBEDDING_DIM = 1024
EMBEDDING_MODEL = "voyage-3"

# Voyage caps the number of texts (and total tokens) per request; 100 texts per
# call stays comfortably inside those limits for program-sized documents.
EMBED_BATCH_SIZE = 100
# voyageai.Client retries transient failures internally when max_retries > 0.
VOYAGE_MAX_RETRIES = 3
# Qdrant's client has no built-in retry knob, so calls go through with_retry.
QDRANT_ATTEMPTS = 3
QDRANT_BACKOFF_SECONDS = 0.5

T = TypeVar("T")

_voyage_client: voyageai.Client | None = None
_qdrant_client: QdrantClient | None = None


def build_embedding_text(course_name: str, subject: str | None, description: str | None) -> str:
    parts = [course_name]
    if subject:
        parts.append(subject)
    if description:
        parts.append(description)
    return ". ".join(parts)


def get_voyage_client() -> voyageai.Client:
    """Process-wide Voyage client (constructing one per call leaks connections)."""
    global _voyage_client
    if _voyage_client is None:
        _voyage_client = voyageai.Client(
            api_key=settings.voyage_api_key, max_retries=VOYAGE_MAX_RETRIES
        )
    return _voyage_client


def embed_texts(texts: list[str], client: voyageai.Client | None = None) -> list[list[float]]:
    """Embed one batch of texts. Callers must chunk to EMBED_BATCH_SIZE."""
    client = client or get_voyage_client()
    result = client.embed(texts, model=EMBEDDING_MODEL, input_type="document")
    return result.embeddings


def get_qdrant_client() -> QdrantClient:
    """Process-wide Qdrant client (constructing one per request leaks connections)."""
    global _qdrant_client
    if _qdrant_client is None:
        _qdrant_client = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key)
    return _qdrant_client


def with_retry(fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """Retry a Qdrant call with exponential backoff; re-raises the last error."""
    delay = QDRANT_BACKOFF_SECONDS
    for attempt in range(1, QDRANT_ATTEMPTS + 1):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            if attempt == QDRANT_ATTEMPTS:
                raise
            logger.warning(
                "Qdrant call %s failed (attempt %d/%d), retrying in %.1fs: %s",
                getattr(fn, "__name__", fn), attempt, QDRANT_ATTEMPTS, delay, exc,
            )
            time.sleep(delay)
            delay *= 2
    raise AssertionError("unreachable")


def ensure_collection(client: QdrantClient) -> None:
    if not with_retry(client.collection_exists, COLLECTION_NAME):
        with_retry(
            client.create_collection,
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE),
        )


def upsert_embedding(
    client: QdrantClient, program_id: int, vector: list[float], payload: dict
) -> None:
    with_retry(
        client.upsert,
        collection_name=COLLECTION_NAME,
        points=[PointStruct(id=program_id, vector=vector, payload=payload)],
    )
