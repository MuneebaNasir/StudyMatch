import asyncio
import json
import logging

import httpx

from ..config import settings
from .cache import ResponseCache

logger = logging.getLogger(__name__)

# Transient DAAD failures are retried with exponential backoff before the
# per-program failure isolation in the pipeline gives up on an ID.
MAX_ATTEMPTS = 3
BACKOFF_SECONDS = 1.0


class DaadClient:
    def __init__(self, cache: ResponseCache | None = None) -> None:
        self._client = httpx.AsyncClient(
            headers={"User-Agent": settings.http_user_agent}, timeout=30.0
        )
        self._cache = cache
        self._semaphore = asyncio.Semaphore(settings.max_concurrency)

    async def close(self) -> None:
        await self._client.aclose()

    async def _get(self, url: str) -> str:
        if self._cache is not None:
            cached = self._cache.get(url)
            if cached is not None:
                return cached

        text = await self._get_with_retry(url)

        if self._cache is not None:
            self._cache.set(url, text)
        return text

    async def _get_with_retry(self, url: str) -> str:
        delay = BACKOFF_SECONDS
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                async with self._semaphore:
                    response = await self._client.get(url)
                    response.raise_for_status()
                    await asyncio.sleep(settings.request_delay_seconds)
                return response.text
            except httpx.HTTPError as exc:
                status = getattr(getattr(exc, "response", None), "status_code", None)
                # 4xx (other than 429) will not succeed on retry.
                if status is not None and 400 <= status < 500 and status != 429:
                    raise
                if attempt == MAX_ATTEMPTS:
                    raise
                logger.warning(
                    "GET %s failed (attempt %d/%d), retrying in %.1fs: %s",
                    url, attempt, MAX_ATTEMPTS, delay, exc,
                )
                await asyncio.sleep(delay)
                delay *= 2
        raise AssertionError("unreachable")

    async def fetch_search_page(self, offset: int, limit: int) -> dict:
        url = f"{settings.daad_base_url}/api/solr/en/search.json?limit={limit}&offset={offset}"
        return json.loads(await self._get(url))

    async def fetch_count(self) -> int:
        url = f"{settings.daad_base_url}/api/solr/en/count.json"
        payload = json.loads(await self._get(url))
        return payload["numResults"]

    async def fetch_detail_html(self, program_id: int) -> str:
        url = f"{settings.daad_base_url}/en/detail/{program_id}/"
        return await self._get(url)
