import collections
import logging
import os
import threading
import time
from typing import Any, Callable, Literal, TypeVar

import voyageai
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from ..config import settings

logger = logging.getLogger(__name__)

COLLECTION_NAME = settings.collection_name
EMBEDDING_DIM = 1024
EMBEDDING_MODEL = "voyage-3"

# Voyage caps the number of texts (and total tokens) per request; 100 texts per
# call stays comfortably inside those limits for program-sized documents *when
# a paid-tier key is in use*. A cardless free-tier key is additionally capped
# at 10K tokens/minute — a single 100-text batch can exceed that on its own,
# no amount of request pacing fixes that. See EMBEDDING_PROVIDER=local below.
EMBED_BATCH_SIZE = 100
# voyageai.Client retries transient failures internally when max_retries > 0.
VOYAGE_MAX_RETRIES = 3
# Free-tier Voyage keys are capped at 3 requests/minute. embed_texts() throttles
# to this before every call so a full ingestion run backs off instead of
# burning its retry budget on 429s.
VOYAGE_REQUESTS_PER_MINUTE = 3
# BGE's retrieval instruction prefix: recommended on queries only, not on the
# documents/passages being searched. Doubles measured retrieval quality on
# BGE's own benchmarks; costs nothing to apply.
LOCAL_QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "
# Qdrant's client has no built-in retry knob, so calls go through with_retry.
QDRANT_ATTEMPTS = 3
QDRANT_BACKOFF_SECONDS = 0.5

T = TypeVar("T")
InputType = Literal["document", "query"]

_voyage_client: voyageai.Client | None = None
_qdrant_client: QdrantClient | None = None
_local_model: Any = None

_voyage_call_times: collections.deque[float] = collections.deque()
_voyage_rate_lock = threading.Lock()


def _throttle_to_voyage_rate_limit() -> None:
    """Block until fewer than VOYAGE_REQUESTS_PER_MINUTE calls happened in the last 60s.

    Sends up to VOYAGE_REQUESTS_PER_MINUTE requests back-to-back, then waits for
    the oldest of them to fall outside the 60s window before letting the next
    one through — i.e. "3 requests, wait a minute, 3 more" rather than an even
    20s spacing between every call.
    """
    with _voyage_rate_lock:
        while True:
            now = time.monotonic()
            while _voyage_call_times and now - _voyage_call_times[0] >= 60:
                _voyage_call_times.popleft()

            if len(_voyage_call_times) < VOYAGE_REQUESTS_PER_MINUTE:
                _voyage_call_times.append(now)
                return

            wait = 60 - (now - _voyage_call_times[0])
            logger.info(
                "Voyage rate limit (%d req/min) reached; waiting %.1fs",
                VOYAGE_REQUESTS_PER_MINUTE, wait,
            )
            time.sleep(wait)


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


def _configure_torch_threads() -> None:
    """Cap PyTorch's thread pool to the container's actual CPU quota.

    PyTorch sizes its default thread pool from the host machine's core
    count, not the cgroup CPU limit a container is actually granted. On
    Cloud Run (2 vCPUs allocated), this caused severe thread
    oversubscription: a single embedding computation that should take
    well under a second took ~26s on a real cold start, measured via
    Cloud Logging timestamps (2026-08-12). `os.sched_getaffinity` reports
    the cgroup-limited CPU set correctly on Linux (Cloud Run's runtime);
    it doesn't exist on macOS, hence the fallback to `os.cpu_count()` for
    local development.
    """
    import torch

    try:
        cpu_count = len(os.sched_getaffinity(0))
    except AttributeError:
        cpu_count = os.cpu_count() or 1
    torch.set_num_threads(cpu_count)


def get_local_model() -> Any:
    """Process-wide local embedding model — loaded lazily so `import
    sentence_transformers` (pulls in torch) never happens on the Voyage path."""
    global _local_model
    if _local_model is None:
        from sentence_transformers import SentenceTransformer

        _configure_torch_threads()

        try:
            # Already cached from a prior run: load fully offline, no Hub
            # round-trips to check for updates on every process start.
            _local_model = SentenceTransformer(
                settings.local_embedding_model, local_files_only=True
            )
        except Exception:
            logger.info(
                "Local embedding model %s not cached yet; downloading",
                settings.local_embedding_model,
            )
            _local_model = SentenceTransformer(settings.local_embedding_model)
    return _local_model


def _embed_texts_voyage(
    texts: list[str], input_type: InputType, client: voyageai.Client | None = None
) -> list[list[float]]:
    client = client or get_voyage_client()
    _throttle_to_voyage_rate_limit()
    result = client.embed(texts, model=EMBEDDING_MODEL, input_type=input_type)
    return result.embeddings


def _embed_texts_local(texts: list[str], input_type: InputType) -> list[list[float]]:
    model = get_local_model()
    if input_type == "query":
        texts = [LOCAL_QUERY_INSTRUCTION + text for text in texts]
    vectors = model.encode(texts, normalize_embeddings=True)
    return vectors.tolist()


def embed_texts(
    texts: list[str], input_type: InputType = "document", client: voyageai.Client | None = None
) -> list[list[float]]:
    """Embed one batch of texts. Callers must chunk to EMBED_BATCH_SIZE.

    Dispatches on `settings.embedding_provider` ("voyage" or "local"). `client`
    is only used on the Voyage path (test seam); ignored for "local".
    Vectors from the two providers are NOT interchangeable — don't mix them in
    the same Qdrant collection (re-embed everything after switching providers).
    """
    if settings.embedding_provider == "local":
        return _embed_texts_local(texts, input_type)
    return _embed_texts_voyage(texts, input_type, client)


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
