from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False, extra="ignore")

    database_url: str = "postgresql+asyncpg://daad:daad@localhost:5432/daad"
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str | None = None
    voyage_api_key: str = ""
    daad_base_url: str = "https://www2.daad.de/deutschland/studienangebote/international-programmes"
    http_user_agent: str = "daad-search-portfolio-project/0.1 (contact: you@example.com)"
    request_delay_seconds: float = 0.3
    max_concurrency: int = 5
    cache_dir: str = ".cache/daad"


settings = Settings()
