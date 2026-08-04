from daad_search.ingestion.pipeline import ingest_program
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
