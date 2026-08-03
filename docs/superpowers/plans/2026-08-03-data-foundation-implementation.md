# Data Foundation & Hybrid Retrieval Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a repeatable pipeline that ingests German study-program data from DAAD's undocumented JSON API into Postgres and Qdrant, and expose a hybrid (filter + semantic) search API over it.

**Architecture:** An async Python pipeline scrapes DAAD's `search.json`/`count.json` list endpoint and per-program detail pages, upserts structured rows into Postgres (raw eligibility text kept as unparsed `jsonb`), embeds each program via Voyage AI into Qdrant, and serves both through a FastAPI `/search` endpoint that intersects Postgres hard filters with Qdrant semantic ranking.

**Tech Stack:** Python 3.11+, httpx, BeautifulSoup4, SQLAlchemy 2.0 (async, asyncpg), Postgres 16, qdrant-client, Voyage AI (`voyage-3`), FastAPI, Docker Compose.

## Global Constraints

- Python 3.11+, `src/` package layout (`src/daad_search/...`).
- I/O is async throughout (httpx.AsyncClient, SQLAlchemy async engine) except the `qdrant-client` and `voyageai` SDKs, which are synchronous and called directly — both run fast, batched calls, so no `asyncio.to_thread` wrapping is needed at this scale.
- Scraping etiquette per the design spec: descriptive `User-Agent`, `REQUEST_DELAY_SECONDS` pacing, `MAX_CONCURRENCY` cap, on-disk response caching so re-runs don't re-hit unchanged DAAD pages.
- DAAD's numeric program `id` is always the primary key — ingestion is idempotent (upsert, never insert-duplicate).
- Tests are split by a `pytest.mark.integration` marker:
  - **Unit tests** (no marker) use only local fixtures/mocks — no live network, no Postgres, no Qdrant, no Voyage calls. Run with `pytest -m "not integration"`.
  - **Integration tests** require `docker compose up -d` (Postgres + Qdrant) and a `.env` with a real `VOYAGE_API_KEY`; one test (Task 6) also makes live requests to DAAD. Run with `pytest -m integration`.
- No placeholder eligibility parsing — raw detail-page text is stored verbatim in `raw_sections`; structured extraction is a separate, later spec.

---

### Task 1: Project scaffolding & configuration

**Files:**
- Create: `pyproject.toml`
- Create: `docker-compose.yml`
- Create: `.env.example`
- Modify: `.gitignore`
- Create: `src/daad_search/__init__.py`
- Create: `src/daad_search/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `daad_search.config.Settings` (pydantic-settings class) and `daad_search.config.settings` (module-level instance) with fields `database_url: str`, `qdrant_url: str`, `qdrant_api_key: str | None`, `voyage_api_key: str`, `daad_base_url: str`, `http_user_agent: str`, `request_delay_seconds: float`, `max_concurrency: int`, `cache_dir: str`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'daad_search'`

- [ ] **Step 3: Create the project scaffolding**

```toml
# pyproject.toml
[project]
name = "daad-search"
version = "0.1.0"
description = "Data foundation and hybrid retrieval pipeline for German study programs sourced from DAAD"
requires-python = ">=3.11"
dependencies = [
    "httpx>=0.27",
    "beautifulsoup4>=4.12",
    "sqlalchemy>=2.0",
    "asyncpg>=0.29",
    "pydantic>=2.0",
    "pydantic-settings>=2.0",
    "qdrant-client>=1.9",
    "voyageai>=0.2",
    "fastapi>=0.110",
    "uvicorn[standard]>=0.29",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
markers = [
    "integration: requires docker compose services (Postgres/Qdrant) and/or live network and API keys",
]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]
```

```yaml
# docker-compose.yml
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_USER: daad
      POSTGRES_PASSWORD: daad
      POSTGRES_DB: daad
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data

  qdrant:
    image: qdrant/qdrant:latest
    ports:
      - "6333:6333"
      - "6334:6334"

volumes:
  pgdata:
```

```
# .env.example
DATABASE_URL=postgresql+asyncpg://daad:daad@localhost:5432/daad
QDRANT_URL=http://localhost:6333
VOYAGE_API_KEY=replace-with-your-voyage-api-key
DAAD_BASE_URL=https://www2.daad.de/deutschland/studienangebote/international-programmes
HTTP_USER_AGENT=daad-search-portfolio-project/0.1 (contact: you@example.com)
REQUEST_DELAY_SECONDS=0.3
MAX_CONCURRENCY=5
CACHE_DIR=.cache/daad
```

Append to `.gitignore`:

```
.venv/
__pycache__/
*.pyc
.env
.cache/
.pytest_cache/
*.egg-info/
```

```python
# src/daad_search/config.py
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
```

`src/daad_search/__init__.py` is empty.

- [ ] **Step 4: Install the project in editable mode**

Run: `pip install -e ".[dev]"`
Expected: install succeeds with no errors.

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_config.py -v`
Expected: PASS (2 passed)

- [ ] **Step 6: Verify Docker Compose services start**

Run: `docker compose up -d && docker compose ps`
Expected: both `postgres` and `qdrant` show state `running`/`healthy`. Leave them running — later tasks' integration tests depend on them.

Run: `curl -s http://localhost:6333/collections`
Expected: `{"result":{"collections":[]},"status":"ok","time":...}`

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml docker-compose.yml .env.example .gitignore src/daad_search/__init__.py src/daad_search/config.py tests/test_config.py
git commit -m "chore: project scaffolding and configuration"
```

---

### Task 2: Postgres schema, models & upsert

**Files:**
- Create: `src/daad_search/db/__init__.py`
- Create: `src/daad_search/db/models.py`
- Create: `src/daad_search/db/session.py`
- Create: `src/daad_search/db/upsert.py`
- Test: `tests/test_db_upsert.py`

**Interfaces:**
- Consumes: `daad_search.config.settings.database_url` (Task 1)
- Produces: `daad_search.db.models.Base` (DeclarativeBase), `daad_search.db.models.Program` (ORM class — columns: `id, course_name, course_name_short, university, city, languages, subject, course_type, degree, duration, beginning, tuition_fees_text, has_tuition_fees, application_deadline_text, link, raw_sections, scraped_at`); `daad_search.db.session.engine`, `daad_search.db.session.async_session_factory`, `async def daad_search.db.session.init_db() -> None`; `async def daad_search.db.upsert.upsert_program(session: AsyncSession, program_id: int, values: dict) -> None`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_db_upsert.py
import pytest
from datetime import datetime, timezone
from sqlalchemy import select

from daad_search.db.models import Base, Program
from daad_search.db.session import engine, async_session_factory
from daad_search.db.upsert import upsert_program

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
async def setup_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


def _values(course_name: str) -> dict:
    return dict(
        course_name=course_name,
        course_name_short="Test",
        university="Test University",
        city="Berlin",
        languages=["English"],
        subject="Computer Science",
        course_type=2,
        degree="Master of Science",
        duration="4 semesters",
        beginning="Winter semester",
        tuition_fees_text="No tuition fees",
        has_tuition_fees=False,
        application_deadline_text="15 July",
        link="https://example.com/1",
        raw_sections={},
        scraped_at=datetime.now(timezone.utc),
    )


async def test_upsert_inserts_then_updates_without_duplicating():
    async with async_session_factory() as session:
        await upsert_program(session, 1, _values("Test Program"))

    async with async_session_factory() as session:
        row = (await session.execute(select(Program).where(Program.id == 1))).scalar_one()
        assert row.course_name == "Test Program"

    async with async_session_factory() as session:
        await upsert_program(session, 1, _values("Updated Name"))

    async with async_session_factory() as session:
        rows = (await session.execute(select(Program).where(Program.id == 1))).scalars().all()
        assert len(rows) == 1
        assert rows[0].course_name == "Updated Name"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_db_upsert.py -v -m integration`
Expected: FAIL with `ModuleNotFoundError: No module named 'daad_search.db'`

- [ ] **Step 3: Write the implementation**

```python
# src/daad_search/db/models.py
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, Integer, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Program(Base):
    __tablename__ = "programs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    course_name: Mapped[str] = mapped_column(Text)
    course_name_short: Mapped[str | None] = mapped_column(Text, nullable=True)
    university: Mapped[str] = mapped_column(Text)
    city: Mapped[str | None] = mapped_column(Text, nullable=True)
    languages: Mapped[list[str]] = mapped_column(ARRAY(Text))
    subject: Mapped[str | None] = mapped_column(Text, nullable=True)
    course_type: Mapped[int] = mapped_column(Integer)
    degree: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration: Mapped[str | None] = mapped_column(Text, nullable=True)
    beginning: Mapped[str | None] = mapped_column(Text, nullable=True)
    tuition_fees_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    has_tuition_fees: Mapped[bool] = mapped_column(Boolean, default=True)
    application_deadline_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    link: Mapped[str] = mapped_column(Text)
    raw_sections: Mapped[dict] = mapped_column(JSONB, default=dict)
    scraped_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_programs_subject", "subject"),
        Index("ix_programs_languages", "languages", postgresql_using="gin"),
        Index("ix_programs_has_tuition_fees", "has_tuition_fees"),
        Index("ix_programs_course_type", "course_type"),
        Index("ix_programs_city", "city"),
    )
```

```python
# src/daad_search/db/session.py
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ..config import settings
from .models import Base

engine = create_async_engine(settings.database_url, echo=False)
async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
```

```python
# src/daad_search/db/upsert.py
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Program


async def upsert_program(session: AsyncSession, program_id: int, values: dict) -> None:
    stmt = pg_insert(Program).values(id=program_id, **values)
    update_cols = {col: stmt.excluded[col] for col in values}
    stmt = stmt.on_conflict_do_update(index_elements=[Program.id], set_=update_cols)
    await session.execute(stmt)
    await session.commit()
```

`src/daad_search/db/__init__.py` is empty.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_db_upsert.py -v -m integration`
Expected: PASS (requires `docker compose up -d` from Task 1 still running)

- [ ] **Step 5: Commit**

```bash
git add src/daad_search/db/ tests/test_db_upsert.py
git commit -m "feat: Postgres schema and idempotent upsert"
```

---

### Task 3: DAAD list client, parser & response cache

**Files:**
- Create: `src/daad_search/scraping/__init__.py`
- Create: `src/daad_search/scraping/cache.py`
- Create: `src/daad_search/scraping/daad_client.py`
- Create: `src/daad_search/scraping/list_parser.py`
- Create: `tests/fixtures/search_response.json` (already present — captured live from DAAD)
- Test: `tests/test_cache.py`
- Test: `tests/test_list_parser.py`

**Interfaces:**
- Consumes: `daad_search.config.settings` (Task 1)
- Produces: `daad_search.scraping.cache.ResponseCache` (methods `get(key: str) -> str | None`, `set(key: str, value: str) -> None`); `daad_search.scraping.daad_client.DaadClient` (methods `async fetch_search_page(offset: int, limit: int) -> dict`, `async fetch_count() -> int`, `async close() -> None`); `daad_search.scraping.list_parser.ProgramSummary` (dataclass — fields `id, course_name, course_name_short, university, city, languages, subject, course_type, duration, beginning, tuition_fees_text, has_tuition_fees, link`); `def parse_search_response(payload: dict) -> list[ProgramSummary]`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_cache.py
from daad_search.scraping.cache import ResponseCache


def test_cache_returns_none_for_missing_key(tmp_path):
    cache = ResponseCache(str(tmp_path))
    assert cache.get("https://example.com/a") is None


def test_cache_roundtrip(tmp_path):
    cache = ResponseCache(str(tmp_path))
    cache.set("https://example.com/a", "hello world")
    assert cache.get("https://example.com/a") == "hello world"
```

```python
# tests/test_list_parser.py
import json
from pathlib import Path

from daad_search.scraping.list_parser import parse_search_response

FIXTURE = Path(__file__).parent / "fixtures" / "search_response.json"


def test_parse_search_response_returns_summaries_for_all_courses():
    payload = json.loads(FIXTURE.read_text())
    summaries = parse_search_response(payload)
    assert len(summaries) == 2


def test_parse_program_summary_maps_known_fields():
    payload = json.loads(FIXTURE.read_text())
    summaries = parse_search_response(payload)
    additive = next(s for s in summaries if s.id == 10396)

    assert additive.course_name == "Additive Manufacturing"
    assert additive.university == "Paderborn University"
    assert additive.city == "Paderborn"
    assert additive.languages == ["English"]
    assert additive.subject == "Mechanical Engineering"
    assert additive.course_type == 2
    assert additive.has_tuition_fees is False
    assert additive.link == (
        "https://www2.daad.de/deutschland/studienangebote/"
        "international-programmes/en/detail/10396/"
    )


def test_parse_program_summary_detects_paid_tuition():
    payload = {
        "courses": [{
            "id": 1, "courseName": "Test", "courseNameShort": "Test",
            "academy": "Test Uni", "city": "Berlin", "languages": ["English"],
            "subject": "Test Subject", "courseType": 2,
            "programmeDuration": "2 semesters", "beginning": "Winter",
            "tuitionFees": "1500 EUR per semester",
            "link": "/deutschland/studienangebote/international-programmes/en/detail/1/",
        }]
    }
    summaries = parse_search_response(payload)
    assert summaries[0].has_tuition_fees is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_cache.py tests/test_list_parser.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'daad_search.scraping'`

- [ ] **Step 3: Write the implementation**

```python
# src/daad_search/scraping/cache.py
import hashlib
from pathlib import Path


class ResponseCache:
    def __init__(self, cache_dir: str) -> None:
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _path_for(self, key: str) -> Path:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self.cache_dir / f"{digest}.txt"

    def get(self, key: str) -> str | None:
        path = self._path_for(key)
        if path.exists():
            return path.read_text(encoding="utf-8")
        return None

    def set(self, key: str, value: str) -> None:
        self._path_for(key).write_text(value, encoding="utf-8")
```

```python
# src/daad_search/scraping/daad_client.py
import asyncio
import json

import httpx

from ..config import settings
from .cache import ResponseCache


class DaadClient:
    def __init__(self, cache: ResponseCache | None = None) -> None:
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
```

```python
# src/daad_search/scraping/list_parser.py
from dataclasses import dataclass

DAAD_HOST = "https://www2.daad.de"


@dataclass
class ProgramSummary:
    id: int
    course_name: str
    course_name_short: str | None
    university: str
    city: str | None
    languages: list[str]
    subject: str | None
    course_type: int
    duration: str | None
    beginning: str | None
    tuition_fees_text: str | None
    has_tuition_fees: bool
    link: str


def _has_fees(tuition_text: str | None) -> bool:
    if not tuition_text:
        return True
    return "no tuition fees" not in tuition_text.lower()


def _absolute_link(link: str) -> str:
    if link.startswith("http"):
        return link
    return DAAD_HOST + link


def parse_program_summary(raw: dict) -> ProgramSummary:
    return ProgramSummary(
        id=raw["id"],
        course_name=raw["courseName"],
        course_name_short=raw.get("courseNameShort"),
        university=raw.get("academy", ""),
        city=raw.get("city"),
        languages=raw.get("languages") or [],
        subject=raw.get("subject"),
        course_type=raw["courseType"],
        duration=raw.get("programmeDuration"),
        beginning=raw.get("beginning"),
        tuition_fees_text=raw.get("tuitionFees"),
        has_tuition_fees=_has_fees(raw.get("tuitionFees")),
        link=_absolute_link(raw["link"]),
    )


def parse_search_response(payload: dict) -> list[ProgramSummary]:
    return [parse_program_summary(course) for course in payload.get("courses", [])]
```

`src/daad_search/scraping/__init__.py` is empty.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_cache.py tests/test_list_parser.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add src/daad_search/scraping/__init__.py src/daad_search/scraping/cache.py src/daad_search/scraping/daad_client.py src/daad_search/scraping/list_parser.py tests/test_cache.py tests/test_list_parser.py tests/fixtures/search_response.json
git commit -m "feat: DAAD list API client, parser, and response cache"
```

---

### Task 4: DAAD detail-page fetch & section parser

**Files:**
- Modify: `src/daad_search/scraping/daad_client.py`
- Create: `src/daad_search/scraping/detail_parser.py`
- Create: `tests/fixtures/detail_page_10396.html` (already present — captured live from DAAD)
- Test: `tests/test_detail_parser.py`

**Interfaces:**
- Consumes: `daad_search.scraping.daad_client.DaadClient` (Task 3)
- Produces: `async DaadClient.fetch_detail_html(program_id: int) -> str`; `def daad_search.scraping.detail_parser.parse_detail_sections(html: str) -> dict[str, str]` — known keys: `description, admission_requirements, german_language, english_language, tuition_fees, application_deadline, degree` (only keys actually present on the page are included; missing sections are simply absent, not empty-string).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_detail_parser.py
from pathlib import Path

from daad_search.scraping.detail_parser import parse_detail_sections

FIXTURE = Path(__file__).parent / "fixtures" / "detail_page_10396.html"


def test_parse_detail_sections_extracts_known_labels():
    html = FIXTURE.read_text(encoding="utf-8")
    sections = parse_detail_sections(html)

    assert "description" in sections
    assert "Plastics Technologies in Additive Manufacturing" in sections["description"]

    assert "admission_requirements" in sections
    assert "three-year German Bachelor" in sections["admission_requirements"]
    assert "GRE Revised General Test" in sections["admission_requirements"]

    assert sections["german_language"] == "No minimum language level required"
    assert "B2" in sections["english_language"]

    assert sections["degree"] == "Master of Science"


def test_parse_detail_sections_ignores_unmapped_labels():
    html = (
        "<dl><dt class='c-description-list__content'>Some Unmapped Label</dt>"
        "<dd class='c-description-list__content'>value</dd></dl>"
    )
    assert parse_detail_sections(html) == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_detail_parser.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'daad_search.scraping.detail_parser'`

- [ ] **Step 3: Write the implementation**

```python
# src/daad_search/scraping/detail_parser.py
from bs4 import BeautifulSoup

_LABEL_TO_KEY = {
    "Description/content": "description",
    "Academic admission requirements": "admission_requirements",
    "German language skills": "german_language",
    "English language skills": "english_language",
    "Tuition fees per semester": "tuition_fees",
    "Application periods": "application_deadline",
    "Degree": "degree",
}


def parse_detail_sections(html: str) -> dict[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    sections: dict[str, str] = {}

    for dt in soup.select("dt.c-description-list__content"):
        label = dt.get_text(strip=True)
        key = _LABEL_TO_KEY.get(label)
        if key is None:
            continue

        dd = dt.find_next_sibling("dd")
        if dd is None:
            continue

        sections[key] = dd.get_text(separator="\n", strip=True)

    return sections
```

Add to `src/daad_search/scraping/daad_client.py`, inside the `DaadClient` class (after `fetch_count`):

```python
    async def fetch_detail_html(self, program_id: int) -> str:
        url = f"{settings.daad_base_url}/en/detail/{program_id}/"
        return await self._get(url)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_detail_parser.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/daad_search/scraping/daad_client.py src/daad_search/scraping/detail_parser.py tests/test_detail_parser.py tests/fixtures/detail_page_10396.html
git commit -m "feat: DAAD detail-page fetch and section parser"
```

---

### Task 5: Embeddings & Qdrant

**Files:**
- Create: `src/daad_search/ingestion/__init__.py`
- Create: `src/daad_search/ingestion/embeddings.py`
- Test: `tests/test_embeddings.py`

**Interfaces:**
- Consumes: `daad_search.config.settings` (Task 1)
- Produces: `daad_search.ingestion.embeddings.COLLECTION_NAME = "programs"`, `EMBEDDING_DIM = 1024`, `EMBEDDING_MODEL = "voyage-3"`; `def build_embedding_text(course_name: str, subject: str | None, description: str | None) -> str`; `def embed_texts(texts: list[str]) -> list[list[float]]`; `def get_qdrant_client() -> QdrantClient`; `def ensure_collection(client: QdrantClient) -> None`; `def upsert_embedding(client: QdrantClient, program_id: int, vector: list[float], payload: dict) -> None`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_embeddings.py
import pytest

from daad_search.ingestion.embeddings import build_embedding_text


def test_build_embedding_text_combines_all_fields():
    text = build_embedding_text("Data Science MSc", "Computer Science", "Focus on ML and statistics.")
    assert text == "Data Science MSc. Computer Science. Focus on ML and statistics."


def test_build_embedding_text_omits_missing_optional_fields():
    assert build_embedding_text("Data Science MSc", None, None) == "Data Science MSc"
    assert build_embedding_text("Data Science MSc", "Computer Science", None) == (
        "Data Science MSc. Computer Science"
    )


@pytest.mark.integration
def test_ensure_collection_and_upsert_embedding_roundtrip():
    from daad_search.ingestion.embeddings import (
        COLLECTION_NAME, EMBEDDING_DIM, ensure_collection, get_qdrant_client, upsert_embedding,
    )

    client = get_qdrant_client()
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass

    ensure_collection(client)
    vector = [0.1] * EMBEDDING_DIM
    upsert_embedding(client, 999, vector, {"program_id": 999, "subject": "Test"})

    points = client.retrieve(collection_name=COLLECTION_NAME, ids=[999])
    assert len(points) == 1
    assert points[0].payload["subject"] == "Test"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_embeddings.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'daad_search.ingestion'`

- [ ] **Step 3: Write the implementation**

```python
# src/daad_search/ingestion/embeddings.py
import voyageai
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from ..config import settings

COLLECTION_NAME = "programs"
EMBEDDING_DIM = 1024
EMBEDDING_MODEL = "voyage-3"


def build_embedding_text(course_name: str, subject: str | None, description: str | None) -> str:
    parts = [course_name]
    if subject:
        parts.append(subject)
    if description:
        parts.append(description)
    return ". ".join(parts)


def embed_texts(texts: list[str]) -> list[list[float]]:
    client = voyageai.Client(api_key=settings.voyage_api_key)
    result = client.embed(texts, model=EMBEDDING_MODEL, input_type="document")
    return result.embeddings


def get_qdrant_client() -> QdrantClient:
    return QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key)


def ensure_collection(client: QdrantClient) -> None:
    if not client.collection_exists(COLLECTION_NAME):
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE),
        )


def upsert_embedding(
    client: QdrantClient, program_id: int, vector: list[float], payload: dict
) -> None:
    client.upsert(
        collection_name=COLLECTION_NAME,
        points=[PointStruct(id=program_id, vector=vector, payload=payload)],
    )
```

`src/daad_search/ingestion/__init__.py` is empty.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_embeddings.py -v -m "not integration"` (unit tests) then `pytest tests/test_embeddings.py -v -m integration` (requires `docker compose up -d`)
Expected: both PASS. If the integration test fails with a Qdrant dimension-mismatch error, Voyage's actual `voyage-3` output dimension differs from the `EMBEDDING_DIM = 1024` assumed here — update the constant to match and rerun.

- [ ] **Step 5: Commit**

```bash
git add src/daad_search/ingestion/ tests/test_embeddings.py
git commit -m "feat: Voyage AI embeddings and Qdrant collection helpers"
```

---

### Task 6: Ingestion pipeline orchestration & CLI

**Files:**
- Create: `src/daad_search/ingestion/pipeline.py`
- Create: `src/daad_search/cli.py`
- Test: `tests/test_pipeline_integration.py`

**Interfaces:**
- Consumes: everything from Tasks 1–5 (`DaadClient`, `ResponseCache`, `parse_search_response`, `parse_detail_sections`, `upsert_program`, `async_session_factory`, `Program`, `build_embedding_text`, `embed_texts`, `get_qdrant_client`, `ensure_collection`, `upsert_embedding`)
- Produces: `async def daad_search.ingestion.pipeline.run_ingestion(limit_ids: list[int] | None = None) -> dict` returning `{"total": int, "succeeded": int, "failed_ids": list[int]}`; CLI: `python -m daad_search.cli init-db` and `python -m daad_search.cli ingest [--ids ID ...]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_pipeline_integration.py
import pytest
from sqlalchemy import select

from daad_search.db.models import Base, Program
from daad_search.db.session import engine, async_session_factory
from daad_search.ingestion.embeddings import COLLECTION_NAME, get_qdrant_client
from daad_search.ingestion.pipeline import run_ingestion

pytestmark = pytest.mark.integration

# Actuarial and Financial Mathematics (RPTU Kaiserslautern-Landau), Additive Manufacturing (Paderborn)
REAL_TEST_IDS = [4722, 10396]


@pytest.fixture(autouse=True)
async def setup_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


async def test_run_ingestion_populates_postgres_and_qdrant():
    result = await run_ingestion(limit_ids=REAL_TEST_IDS)

    assert result["total"] == len(REAL_TEST_IDS)
    assert result["succeeded"] == len(REAL_TEST_IDS)
    assert result["failed_ids"] == []

    async with async_session_factory() as session:
        rows = (await session.execute(select(Program))).scalars().all()
        ids = {row.id for row in rows}
        assert ids == set(REAL_TEST_IDS)

        additive = next(r for r in rows if r.id == 10396)
        assert additive.course_name == "Additive Manufacturing"
        assert "admission_requirements" in additive.raw_sections

    qdrant = get_qdrant_client()
    points = qdrant.retrieve(collection_name=COLLECTION_NAME, ids=REAL_TEST_IDS)
    assert {p.id for p in points} == set(REAL_TEST_IDS)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_pipeline_integration.py -v -m integration`
Expected: FAIL with `ModuleNotFoundError: No module named 'daad_search.ingestion.pipeline'`

- [ ] **Step 3: Write the implementation**

```python
# src/daad_search/ingestion/pipeline.py
import logging
from datetime import datetime, timezone

from ..config import settings
from ..db.models import Program
from ..db.session import async_session_factory
from ..db.upsert import upsert_program
from ..scraping.cache import ResponseCache
from ..scraping.daad_client import DaadClient
from ..scraping.detail_parser import parse_detail_sections
from ..scraping.list_parser import ProgramSummary, parse_search_response
from .embeddings import (
    build_embedding_text,
    embed_texts,
    ensure_collection,
    get_qdrant_client,
    upsert_embedding,
)

logger = logging.getLogger(__name__)

PAGE_SIZE = 100


async def fetch_all_summaries(client: DaadClient) -> list[ProgramSummary]:
    summaries: list[ProgramSummary] = []
    offset = 0
    while True:
        payload = await client.fetch_search_page(offset=offset, limit=PAGE_SIZE)
        page = parse_search_response(payload)
        summaries.extend(page)
        if len(page) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
    return summaries


async def ingest_program(client: DaadClient, summary: ProgramSummary) -> tuple[int, bool]:
    try:
        html = await client.fetch_detail_html(summary.id)
    except Exception:
        logger.exception("Failed to fetch detail page for program %s", summary.id)
        return summary.id, False

    sections = parse_detail_sections(html)
    missing = [k for k in ("description", "admission_requirements") if k not in sections]
    if missing:
        logger.warning("Program %s missing sections: %s", summary.id, missing)

    values = dict(
        course_name=summary.course_name,
        course_name_short=summary.course_name_short,
        university=summary.university,
        city=summary.city,
        languages=summary.languages,
        subject=summary.subject,
        course_type=summary.course_type,
        degree=sections.get("degree"),
        duration=summary.duration,
        beginning=summary.beginning,
        tuition_fees_text=summary.tuition_fees_text,
        has_tuition_fees=summary.has_tuition_fees,
        application_deadline_text=sections.get("application_deadline"),
        link=summary.link,
        raw_sections=sections,
        scraped_at=datetime.now(timezone.utc),
    )

    async with async_session_factory() as session:
        await upsert_program(session, summary.id, values)

    return summary.id, True


async def run_ingestion(limit_ids: list[int] | None = None) -> dict:
    cache = ResponseCache(settings.cache_dir)
    client = DaadClient(cache=cache)
    try:
        summaries = await fetch_all_summaries(client)
        if limit_ids is not None:
            summaries = [s for s in summaries if s.id in limit_ids]

        failed_ids: list[int] = []
        succeeded_ids: list[int] = []
        for summary in summaries:
            program_id, ok = await ingest_program(client, summary)
            (succeeded_ids if ok else failed_ids).append(program_id)

        qdrant = get_qdrant_client()
        ensure_collection(qdrant)

        rows: list[Program] = []
        for program_id in succeeded_ids:
            async with async_session_factory() as session:
                row = await session.get(Program, program_id)
                rows.append(row)

        texts = [
            build_embedding_text(row.course_name, row.subject, row.raw_sections.get("description"))
            for row in rows
        ]
        vectors = embed_texts(texts) if texts else []

        for row, vector in zip(rows, vectors):
            payload = {
                "program_id": row.id,
                "subject": row.subject,
                "languages": row.languages,
                "has_tuition_fees": row.has_tuition_fees,
                "course_type": row.course_type,
            }
            upsert_embedding(qdrant, row.id, vector, payload)

        return {"total": len(summaries), "succeeded": len(succeeded_ids), "failed_ids": failed_ids}
    finally:
        await client.close()
```

```python
# src/daad_search/cli.py
import argparse
import asyncio
import logging

from .db.session import init_db
from .ingestion.pipeline import run_ingestion


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(prog="daad-search")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init-db", help="Create Postgres tables")

    ingest_parser = subparsers.add_parser("ingest", help="Run the full ingestion pipeline")
    ingest_parser.add_argument(
        "--ids", type=int, nargs="*", default=None,
        help="Only ingest these DAAD program IDs (for testing)",
    )

    args = parser.parse_args()

    if args.command == "init-db":
        asyncio.run(init_db())
    elif args.command == "ingest":
        result = asyncio.run(run_ingestion(limit_ids=args.ids))
        print(f"Ingested {result['succeeded']}/{result['total']} programs. Failed IDs: {result['failed_ids']}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_pipeline_integration.py -v -m integration`
Expected: PASS. This test makes live requests to DAAD and a real (tiny, ~2-text) Voyage AI embedding call — requires network access and a valid `VOYAGE_API_KEY` in `.env`.

- [ ] **Step 5: Commit**

```bash
git add src/daad_search/ingestion/pipeline.py src/daad_search/cli.py tests/test_pipeline_integration.py
git commit -m "feat: ingestion pipeline orchestration and CLI"
```

---

### Task 7: FastAPI search endpoint (filters + program detail)

**Files:**
- Create: `src/daad_search/api/__init__.py`
- Create: `src/daad_search/api/schemas.py`
- Create: `src/daad_search/api/search.py`
- Create: `src/daad_search/api/main.py`
- Test: `tests/test_search_api.py`

**Interfaces:**
- Consumes: `daad_search.db.models.Program`, `daad_search.db.session.async_session_factory` (Task 2)
- Produces: Pydantic models `SearchFilters, SearchRequest, SearchResult, SearchResponse, ProgramDetail` (`daad_search.api.schemas`); `def apply_filters(stmt, filters: SearchFilters | None)`, `def to_search_result(row: Program, score: float | None = None) -> SearchResult`, `async def filtered_search(session, filters, limit) -> tuple[list[SearchResult], int]` (`daad_search.api.search`); FastAPI app `daad_search.api.main.app` with `POST /search` and `GET /programs/{id}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_search_api.py
import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient

from daad_search.db.models import Base, Program
from daad_search.db.session import engine, async_session_factory
from daad_search.api.main import app

pytestmark = pytest.mark.integration


def _program(**overrides) -> Program:
    defaults = dict(
        course_name_short="Test", university="Test University", city="Berlin",
        languages=["English"], subject="Computer Science", course_type=2,
        degree="Master of Science", duration="4 semesters", beginning="Winter semester",
        tuition_fees_text="No tuition fees", has_tuition_fees=False,
        application_deadline_text="15 July", raw_sections={},
        scraped_at=datetime.now(timezone.utc),
    )
    defaults.update(overrides)
    return Program(**defaults)


@pytest.fixture(autouse=True)
async def setup_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async with async_session_factory() as session:
        session.add_all([
            _program(id=1, course_name="Data Science MSc", link="https://example.com/1"),
            _program(
                id=2, course_name="Mechanical Engineering MSc", link="https://example.com/2",
                languages=["German"], subject="Mechanical Engineering",
                tuition_fees_text="1500 EUR/semester", has_tuition_fees=True,
            ),
        ])
        await session.commit()
    yield


def test_search_filters_by_language_and_tuition():
    client = TestClient(app)
    response = client.post("/search", json={
        "filters": {"languages": ["English"], "max_tuition_free_only": True},
        "limit": 20,
    })
    assert response.status_code == 200
    body = response.json()
    assert body["total_matched"] == 1
    assert body["results"][0]["id"] == 1


def test_search_with_no_filters_returns_all():
    client = TestClient(app)
    response = client.post("/search", json={"limit": 20})
    assert response.status_code == 200
    assert response.json()["total_matched"] == 2


def test_get_program_returns_full_detail():
    client = TestClient(app)
    response = client.get("/programs/1")
    assert response.status_code == 200
    assert response.json()["course_name"] == "Data Science MSc"


def test_get_program_not_found_returns_404():
    client = TestClient(app)
    response = client.get("/programs/999")
    assert response.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_search_api.py -v -m integration`
Expected: FAIL with `ModuleNotFoundError: No module named 'daad_search.api'`

- [ ] **Step 3: Write the implementation**

```python
# src/daad_search/api/schemas.py
from pydantic import BaseModel


class SearchFilters(BaseModel):
    languages: list[str] | None = None
    max_tuition_free_only: bool | None = None
    subject: str | None = None
    city: str | None = None
    course_type: int | None = None


class SearchRequest(BaseModel):
    filters: SearchFilters | None = None
    semantic_query: str | None = None
    limit: int = 20


class SearchResult(BaseModel):
    id: int
    course_name: str
    university: str
    city: str | None
    languages: list[str]
    subject: str | None
    tuition_fees_text: str | None
    application_deadline_text: str | None
    link: str
    score: float | None = None


class SearchResponse(BaseModel):
    results: list[SearchResult]
    total_matched: int


class ProgramDetail(SearchResult):
    course_type: int
    degree: str | None
    duration: str | None
    beginning: str | None
    raw_sections: dict
```

```python
# src/daad_search/api/search.py
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import Program
from .schemas import SearchFilters, SearchResult


def apply_filters(stmt, filters: SearchFilters | None):
    if filters is None:
        return stmt
    if filters.languages:
        stmt = stmt.where(Program.languages.overlap(filters.languages))
    if filters.max_tuition_free_only:
        stmt = stmt.where(Program.has_tuition_fees.is_(False))
    if filters.subject:
        stmt = stmt.where(Program.subject == filters.subject)
    if filters.city:
        stmt = stmt.where(Program.city == filters.city)
    if filters.course_type is not None:
        stmt = stmt.where(Program.course_type == filters.course_type)
    return stmt


def to_search_result(row: Program, score: float | None = None) -> SearchResult:
    return SearchResult(
        id=row.id,
        course_name=row.course_name,
        university=row.university,
        city=row.city,
        languages=row.languages,
        subject=row.subject,
        tuition_fees_text=row.tuition_fees_text,
        application_deadline_text=row.application_deadline_text,
        link=row.link,
        score=score,
    )


async def filtered_search(
    session: AsyncSession, filters: SearchFilters | None, limit: int
) -> tuple[list[SearchResult], int]:
    base = apply_filters(select(Program), filters)

    total = (
        await session.execute(select(func.count()).select_from(base.subquery()))
    ).scalar_one()

    rows = (
        (await session.execute(base.order_by(Program.course_name).limit(limit)))
        .scalars()
        .all()
    )

    return [to_search_result(row) for row in rows], total
```

```python
# src/daad_search/api/main.py
from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import Program
from ..db.session import async_session_factory
from .schemas import ProgramDetail, SearchRequest, SearchResponse
from .search import filtered_search, to_search_result

app = FastAPI(title="DAAD Search API")


async def get_session() -> AsyncSession:
    async with async_session_factory() as session:
        yield session


@app.post("/search", response_model=SearchResponse)
async def search(
    request: SearchRequest, session: AsyncSession = Depends(get_session)
) -> SearchResponse:
    results, total = await filtered_search(session, request.filters, request.limit)
    return SearchResponse(results=results, total_matched=total)


@app.get("/programs/{program_id}", response_model=ProgramDetail)
async def get_program(
    program_id: int, session: AsyncSession = Depends(get_session)
) -> ProgramDetail:
    row = await session.get(Program, program_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Program not found")

    base = to_search_result(row)
    return ProgramDetail(
        **base.model_dump(),
        course_type=row.course_type,
        degree=row.degree,
        duration=row.duration,
        beginning=row.beginning,
        raw_sections=row.raw_sections,
    )
```

`src/daad_search/api/__init__.py` is empty.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_search_api.py -v -m integration`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add src/daad_search/api/ tests/test_search_api.py
git commit -m "feat: FastAPI search and program-detail endpoints"
```

---

### Task 8: Hybrid semantic search

**Files:**
- Modify: `src/daad_search/api/search.py`
- Modify: `src/daad_search/api/main.py`
- Test: `tests/test_hybrid_search.py`

**Interfaces:**
- Consumes: `daad_search.ingestion.embeddings.{COLLECTION_NAME, embed_texts, get_qdrant_client}` (Task 5), `apply_filters`/`to_search_result` (Task 7)
- Produces: `async def semantic_rank(candidate_ids: list[int], query: str, limit: int) -> list[tuple[int, float]]`, `async def hybrid_search(session, filters, semantic_query, limit) -> tuple[list[SearchResult], int]` (`daad_search.api.search`); `POST /search` now branches on `request.semantic_query`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_hybrid_search.py
import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from qdrant_client.models import PointStruct

from daad_search.db.models import Base, Program
from daad_search.db.session import engine, async_session_factory
from daad_search.ingestion.embeddings import COLLECTION_NAME, ensure_collection, get_qdrant_client
from daad_search.api import search as search_module
from daad_search.api.main import app

pytestmark = pytest.mark.integration


def _program(**overrides) -> Program:
    defaults = dict(
        course_name_short="Test", university="Test University", city="Berlin",
        languages=["English"], subject="Computer Science", course_type=2,
        degree="Master of Science", duration="4 semesters", beginning="Winter semester",
        tuition_fees_text="No tuition fees", has_tuition_fees=False,
        application_deadline_text="15 July", raw_sections={},
        scraped_at=datetime.now(timezone.utc),
    )
    defaults.update(overrides)
    return Program(**defaults)


@pytest.fixture(autouse=True)
async def setup_db_and_qdrant(monkeypatch):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async with async_session_factory() as session:
        session.add_all([
            _program(id=1, course_name="Data Science MSc", link="https://example.com/1"),
            _program(
                id=2, course_name="Literature MA", link="https://example.com/2",
                subject="Literature", degree="Master of Arts",
            ),
        ])
        await session.commit()

    qdrant = get_qdrant_client()
    ensure_collection(qdrant)
    qdrant.upsert(collection_name=COLLECTION_NAME, points=[
        PointStruct(id=1, vector=[1.0, 0.0] + [0.0] * 1022, payload={"program_id": 1}),
        PointStruct(id=2, vector=[0.0, 1.0] + [0.0] * 1022, payload={"program_id": 2}),
    ])

    def fake_embed(texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] + [0.0] * 1022 for _ in texts]

    monkeypatch.setattr(search_module, "embed_texts", fake_embed)
    yield


def test_hybrid_search_ranks_semantically_closest_first():
    client = TestClient(app)
    response = client.post("/search", json={
        "filters": {"languages": ["English"]},
        "semantic_query": "machine learning and data analysis",
        "limit": 20,
    })
    assert response.status_code == 200
    body = response.json()
    assert body["results"][0]["id"] == 1
    assert body["results"][0]["score"] > body["results"][1]["score"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_hybrid_search.py -v -m integration`
Expected: FAIL with `AttributeError: module 'daad_search.api.search' has no attribute 'embed_texts'` (or the request simply ignoring `semantic_query` and returning both results unranked)

- [ ] **Step 3: Write the implementation**

Add to the top of `src/daad_search/api/search.py` (alongside existing imports):

```python
from qdrant_client.models import Filter, HasIdCondition

from ..ingestion.embeddings import COLLECTION_NAME, embed_texts, get_qdrant_client
```

Append to `src/daad_search/api/search.py`:

```python
async def semantic_rank(
    candidate_ids: list[int], query: str, limit: int
) -> list[tuple[int, float]]:
    query_vector = embed_texts([query])[0]
    qdrant = get_qdrant_client()

    hits = qdrant.query_points(
        collection_name=COLLECTION_NAME,
        query=query_vector,
        query_filter=Filter(must=[HasIdCondition(has_id=candidate_ids)]),
        limit=limit,
    ).points

    return [(hit.id, hit.score) for hit in hits]


async def hybrid_search(
    session: AsyncSession,
    filters: SearchFilters | None,
    semantic_query: str,
    limit: int,
) -> tuple[list[SearchResult], int]:
    base = apply_filters(select(Program), filters)
    candidate_rows = (await session.execute(base)).scalars().all()
    candidates_by_id = {row.id: row for row in candidate_rows}

    if not candidates_by_id:
        return [], 0

    ranked = await semantic_rank(list(candidates_by_id.keys()), semantic_query, limit)
    results = [
        to_search_result(candidates_by_id[program_id], score=score)
        for program_id, score in ranked
    ]
    return results, len(candidates_by_id)
```

Modify `src/daad_search/api/main.py`: change the import and the `search` handler.

```python
from .search import filtered_search, hybrid_search, to_search_result
```

```python
@app.post("/search", response_model=SearchResponse)
async def search(
    request: SearchRequest, session: AsyncSession = Depends(get_session)
) -> SearchResponse:
    if request.semantic_query:
        results, total = await hybrid_search(
            session, request.filters, request.semantic_query, request.limit
        )
    else:
        results, total = await filtered_search(session, request.filters, request.limit)
    return SearchResponse(results=results, total_matched=total)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_hybrid_search.py -v -m integration`
Expected: PASS. Also re-run the full integration suite to confirm nothing regressed: `pytest -v -m integration`

- [ ] **Step 5: Commit**

```bash
git add src/daad_search/api/search.py src/daad_search/api/main.py tests/test_hybrid_search.py
git commit -m "feat: hybrid semantic search over Postgres-filtered candidates"
```

---

## Final Verification

After Task 8, run the whole suite:

```bash
pytest -v -m "not integration"   # fast unit tests, no services needed
pytest -v -m integration         # requires: docker compose up -d, .env with real VOYAGE_API_KEY
```

Then run a small real ingestion and query it end-to-end:

```bash
python -m daad_search.cli init-db
python -m daad_search.cli ingest --ids 4722 10396
uvicorn daad_search.api.main:app --reload
curl -X POST localhost:8000/search -H "content-type: application/json" \
  -d '{"filters": {"max_tuition_free_only": true}, "semantic_query": "additive manufacturing"}'
```

At this point the data foundation spec is fully implemented: DAAD ingestion, Postgres storage, Qdrant embeddings, and a hybrid search API ready for the query-understanding spec to call.
