from daad_search.config import Settings


def test_settings_uses_defaults_when_env_not_set(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    settings = Settings(_env_file=None)
    assert settings.database_url == "postgresql+asyncpg://daad:daad@localhost:5432/daad"
    assert settings.max_concurrency == 5


def test_settings_reads_from_environment(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@host:5432/db")
    monkeypatch.setenv("VOYAGE_API_KEY", "test-key")
    settings = Settings(_env_file=None)
    assert settings.database_url == "postgresql+asyncpg://u:p@host:5432/db"
    assert settings.voyage_api_key == "test-key"
