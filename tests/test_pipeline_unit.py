import logging

from daad_search.db.models import Program
from daad_search.ingestion import pipeline as pipeline_module
from daad_search.ingestion.pipeline import (
    PAGE_SIZE,
    embed_rows,
    fetch_all_summaries,
    ingest_program,
)
from daad_search.scraping.list_parser import ProgramSummary


def _summary(program_id: int) -> ProgramSummary:
    return ProgramSummary(
        id=program_id,
        course_name="Test Program",
        course_name_short=None,
        university="Test University",
        city=None,
        languages=["English"],
        subject=None,
        course_type=2,
        duration=None,
        beginning=None,
        tuition_fees_text=None,
        has_tuition_fees=True,
        link="https://example.com/1",
    )


class _FakeClient:
    def __init__(self, html: str = "<html></html>") -> None:
        self._html = html

    async def fetch_detail_html(self, program_id: int) -> str:
        return self._html


class _FailingFetchClient:
    async def fetch_detail_html(self, program_id: int) -> str:
        raise RuntimeError("network error")


async def test_ingest_program_isolates_fetch_failure():
    program_id, ok = await ingest_program(_FailingFetchClient(), _summary(7))

    assert program_id == 7
    assert ok is False


async def test_ingest_program_isolates_parse_failure(monkeypatch):
    def _boom(html: str) -> dict:
        raise ValueError("malformed detail page")

    monkeypatch.setattr("daad_search.ingestion.pipeline.parse_detail_sections", _boom)

    program_id, ok = await ingest_program(_FakeClient(), _summary(42))

    assert program_id == 42
    assert ok is False


def _raw_course(program_id: int) -> dict:
    return {
        "id": program_id,
        "courseName": f"Program {program_id}",
        "academy": "Test University",
        "courseType": 2,
        "link": f"/detail/{program_id}/",
    }


class _PagingClient:
    """Fake list endpoint. `misbehaving=True` ignores offset and never runs dry."""

    def __init__(self, total: int, misbehaving: bool = False) -> None:
        self.total = total
        self.misbehaving = misbehaving
        self.pages_served = 0

    async def fetch_count(self) -> int:
        return self.total

    async def fetch_search_page(self, offset: int, limit: int) -> dict:
        self.pages_served += 1
        if self.misbehaving:
            return {"courses": [_raw_course(i) for i in range(limit)]}
        remaining = max(self.total - offset, 0)
        return {"courses": [_raw_course(offset + i) for i in range(min(limit, remaining))]}


async def test_fetch_all_summaries_paginates_to_the_end():
    client = _PagingClient(total=PAGE_SIZE * 2 + 5)

    summaries = await fetch_all_summaries(client)

    assert len(summaries) == PAGE_SIZE * 2 + 5
    assert client.pages_served == 3


async def test_fetch_all_summaries_terminates_when_api_ignores_offset(caplog):
    client = _PagingClient(total=PAGE_SIZE * 2, misbehaving=True)

    with caplog.at_level(logging.WARNING):
        summaries = await fetch_all_summaries(client)

    # Bounded by count.json rather than looping forever.
    assert client.pages_served <= 4
    assert len(summaries) <= PAGE_SIZE * 4
    assert any("Stopping pagination" in r.getMessage() for r in caplog.records)


async def test_fetch_all_summaries_warns_when_count_disagrees(caplog):
    # count.json reports a far larger total than pagination actually delivers.
    client = _PagingClient(total=1000)

    async def short_page(offset: int, limit: int) -> dict:
        return {"courses": [_raw_course(offset)]}

    client.fetch_search_page = short_page

    with caplog.at_level(logging.WARNING):
        summaries = await fetch_all_summaries(client)

    assert len(summaries) == 1
    assert any("count.json reports" in r.getMessage() for r in caplog.records)


def _row(program_id: int) -> Program:
    return Program(
        id=program_id, course_name=f"Program {program_id}", university="U",
        languages=["English"], subject="CS", course_type=2, has_tuition_fees=False,
        link=f"https://example.com/{program_id}", raw_sections={"description": "text"},
    )


def test_embed_rows_chunks_into_voyage_sized_batches(monkeypatch):
    monkeypatch.setattr(pipeline_module, "EMBED_BATCH_SIZE", 100)
    batch_sizes = []

    def fake_embed(texts):
        batch_sizes.append(len(texts))
        return [[0.1] for _ in texts]

    monkeypatch.setattr(pipeline_module, "embed_texts", fake_embed)

    rows = [_row(i) for i in range(250)]
    vectors, failed = embed_rows(rows)

    assert batch_sizes == [100, 100, 50]
    assert len(vectors) == 250
    assert failed == []


def test_embed_rows_isolates_a_failing_batch(monkeypatch):
    monkeypatch.setattr(pipeline_module, "EMBED_BATCH_SIZE", 2)

    def fake_embed(texts):
        if "Program 2" in texts[0]:
            raise RuntimeError("voyage exploded")
        return [[0.1] for _ in texts]

    monkeypatch.setattr(pipeline_module, "embed_texts", fake_embed)

    rows = [_row(i) for i in range(6)]
    vectors, failed = embed_rows(rows)

    assert sorted(vectors) == [0, 1, 4, 5]
    assert failed == [2, 3]
