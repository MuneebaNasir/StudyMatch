from __future__ import annotations

import asyncio
import json
from typing import Optional

import httpx

from ..config import settings
from .cache import ResponseCache


class DaadClient:
    def __init__(self, cache: Optional[ResponseCache] = None) -> None:
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

        async with self._semaphore:
            response = await self._client.get(url)
            response.raise_for_status()
            await asyncio.sleep(settings.request_delay_seconds)

        text = response.text
        if self._cache is not None:
            self._cache.set(url, text)
        return text

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
