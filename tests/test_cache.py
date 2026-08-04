from daad_search.scraping.cache import ResponseCache


def test_cache_returns_none_for_missing_key(tmp_path):
    cache = ResponseCache(str(tmp_path))
    assert cache.get("https://example.com/a") is None


def test_cache_roundtrip(tmp_path):
    cache = ResponseCache(str(tmp_path))
    cache.set("https://example.com/a", "hello world")
    assert cache.get("https://example.com/a") == "hello world"
