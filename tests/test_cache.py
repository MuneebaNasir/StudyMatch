import os
import time

from daad_search.scraping.cache import ResponseCache


def test_cache_returns_none_for_missing_key(tmp_path):
    cache = ResponseCache(str(tmp_path))
    assert cache.get("https://example.com/a") is None


def test_cache_roundtrip(tmp_path):
    cache = ResponseCache(str(tmp_path))
    cache.set("https://example.com/a", "hello world")
    assert cache.get("https://example.com/a") == "hello world"


def test_cache_entry_older_than_ttl_is_a_miss(tmp_path):
    cache = ResponseCache(str(tmp_path), ttl_seconds=60)
    cache.set("https://example.com/a", "stale")

    path = cache._path_for("https://example.com/a")
    old = time.time() - 3600
    os.utime(path, (old, old))

    assert cache.get("https://example.com/a") is None

    # A miss on an expired entry still gets overwritten by the next set().
    cache.set("https://example.com/a", "fresh")
    assert cache.get("https://example.com/a") == "fresh"


def test_refresh_mode_ignores_existing_entries_but_still_writes(tmp_path):
    ResponseCache(str(tmp_path)).set("https://example.com/a", "cached")

    cache = ResponseCache(str(tmp_path), refresh=True)
    assert cache.get("https://example.com/a") is None

    cache.set("https://example.com/a", "refetched")
    assert ResponseCache(str(tmp_path)).get("https://example.com/a") == "refetched"


def test_zero_ttl_disables_cache_hits(tmp_path):
    cache = ResponseCache(str(tmp_path), ttl_seconds=0)
    cache.set("https://example.com/a", "value")
    assert cache.get("https://example.com/a") is None
