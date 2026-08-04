import hashlib
import time
from pathlib import Path

from ..config import settings


class ResponseCache:
    """On-disk cache of raw DAAD responses, keyed by URL.

    Entries older than `ttl_seconds` are treated as misses so re-runs pick up
    upstream changes. `refresh=True` ignores existing entries entirely for this
    run (they are still rewritten with the fresh response).
    """

    def __init__(
        self,
        cache_dir: str,
        ttl_seconds: int | None = None,
        refresh: bool = False,
    ) -> None:
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.ttl_seconds = settings.cache_ttl_seconds if ttl_seconds is None else ttl_seconds
        self.refresh = refresh

    def _path_for(self, key: str) -> Path:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self.cache_dir / f"{digest}.txt"

    def _is_expired(self, path: Path) -> bool:
        # A non-positive TTL means "never serve from cache" (writes still happen).
        if self.ttl_seconds <= 0:
            return True
        return (time.time() - path.stat().st_mtime) > self.ttl_seconds

    def get(self, key: str) -> str | None:
        if self.refresh:
            return None
        path = self._path_for(key)
        if path.exists() and not self._is_expired(path):
            return path.read_text(encoding="utf-8")
        return None

    def set(self, key: str, value: str) -> None:
        self._path_for(key).write_text(value, encoding="utf-8")
