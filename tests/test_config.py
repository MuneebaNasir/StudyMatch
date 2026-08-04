from daad_search.config import Settings


def test_settings_uses_defaults_when_env_not_set(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    settings = Settings(_env_file=None)
    assert settings.database_url == "postgresql+asyncpg://daad:daad@localhost:5432/daad"
    assert settings.max_concurrency == 5
    assert settings.cache_ttl_seconds == 86400
    assert settings.collection_name == "programs"
    assert settings.test_collection_name == "programs_test"


def test_settings_reads_from_environment(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@host:5432/db")
    monkeypatch.setenv("VOYAGE_API_KEY", "test-key")
    settings = Settings(_env_file=None)
    assert settings.database_url == "postgresql+asyncpg://u:p@host:5432/db"
    assert settings.voyage_api_key == "test-key"


def test_test_database_url_defaults_to_suffixed_main_database(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)
    settings = Settings(_env_file=None)
    assert settings.test_database_url == "postgresql+asyncpg://daad:daad@localhost:5432/daad_test"
    assert settings.test_database_url != settings.database_url


def test_test_database_url_can_be_overridden(monkeypatch):
    monkeypatch.setenv("TEST_DATABASE_URL", "postgresql+asyncpg://u:p@host:5432/other")
    settings = Settings(_env_file=None)
    assert settings.test_database_url == "postgresql+asyncpg://u:p@host:5432/other"
