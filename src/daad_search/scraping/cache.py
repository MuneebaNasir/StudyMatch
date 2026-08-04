from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Optional


class ResponseCache:
    def __init__(self, cache_dir: str) -> None:
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _path_for(self, key: str) -> Path:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self.cache_dir / f"{digest}.txt"

    def get(self, key: str) -> Optional[str]:
        path = self._path_for(key)
        if path.exists():
            return path.read_text(encoding="utf-8")
        return None

    def set(self, key: str, value: str) -> None:
        self._path_for(key).write_text(value, encoding="utf-8")
