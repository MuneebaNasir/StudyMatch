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
    groq_api_key: str = ""
    mistral_api_key: str = ""
    gemini_api_key: str = ""
    # Available for a manual, explicit override only -- NEVER read by the
    # automatic Groq -> Mistral -> Gemini fallback chain in
    # query_understanding/llm.py. Wiring a paid provider into an automatic
    # chain risks incurring real charges the moment the free tiers are
    # exhausted, without anyone choosing that to happen.
    openai_api_key: str = ""
    # Origins allowed to call this API cross-origin. Vite's default dev port
    # is 5173 -- the frontend's dev server runs there unless overridden.
    cors_allowed_origins: list[str] = ["http://localhost:5173"]
    # "local" (default, sentence-transformers, runs on-device — no API key,
    # no rate limit, no cost) or "voyage" (needs VOYAGE_API_KEY). Both produce
    # EMBEDDING_DIM-sized vectors so the Qdrant collection schema is unaffected,
    # but vectors from different providers are NOT comparable to each other —
    # switching providers on an existing collection requires re-embedding
    # everything (see embeddings.py).
    embedding_provider: str = "local"
    local_embedding_model: str = "BAAI/bge-large-en-v1.5"
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
