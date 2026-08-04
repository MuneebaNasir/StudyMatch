from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False, extra="ignore")

    database_url: str = "postgresql+asyncpg://daad:daad@localhost:5432/daad"
    # Separate database used by the integration test suite so tests never touch
    # real ingested data. Defaults to `<database_url>_test` (e.g. .../daad_test)
    # unless TEST_DATABASE_URL is set explicitly.
    test_database_url: str = ""
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str | None = None
    collection_name: str = "programs"
    test_collection_name: str = "programs_test"
    voyage_api_key: str = ""
    daad_base_url: str = "https://www2.daad.de/deutschland/studienangebote/international-programmes"
    http_user_agent: str = "daad-search-portfolio-project/0.1 (contact: you@example.com)"
    request_delay_seconds: float = 0.3
    max_concurrency: int = 5
    cache_dir: str = ".cache/daad"
    # How long an on-disk cached DAAD response stays usable. One day keeps
    # re-runs cheap while still picking up upstream catalog changes daily.
    cache_ttl_seconds: int = 86400

    @model_validator(mode="after")
    def _default_test_database_url(self) -> "Settings":
        if not self.test_database_url:
            base, _, name = self.database_url.rpartition("/")
            self.test_database_url = f"{base}/{name}_test"
        return self


settings = Settings()
