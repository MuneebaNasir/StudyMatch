FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

# Copy dependency manifests first so this layer only rebuilds when
# dependencies actually change, not on every source edit.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
RUN uv sync --frozen --no-dev

# Pre-download the local embedding model into the image so Cloud Run's
# scale-to-zero cold starts don't re-fetch ~1.3GB from HuggingFace on every
# first request after an idle period.
RUN uv run python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-large-en-v1.5')"

ENV PORT=8080
ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8080

# Invoke uvicorn directly from the venv rather than via `uv run`, which
# re-checks the project against uv.lock (and re-syncs if it sees drift,
# e.g. from Docker COPY resetting file mtimes) on every single invocation --
# wasted latency on every Cloud Run cold start when the build already froze
# the environment.
CMD uvicorn daad_search.api.main:app --host 0.0.0.0 --port ${PORT}
