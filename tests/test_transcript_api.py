import io

import pytest

from daad_search.api import main as main_module
from daad_search.transcript.schema import ExtractedCourse, TranscriptExtraction

pytestmark = pytest.mark.integration


def test_upload_transcript_returns_session_token_and_extraction(api_client, monkeypatch):
    monkeypatch.setattr(
        main_module, "extract_transcript",
        lambda file_bytes, content_type: TranscriptExtraction(
            courses=[ExtractedCourse(name="Linear Algebra", grade="A")],
            grade_value=3.8, grade_scale="4.0 GPA", nationality="Pakistan",
            degree_field="Computer Science", extraction_confidence="high",
        ),
    )

    response = api_client.post(
        "/transcript", files={"file": ("transcript.pdf", io.BytesIO(b"%PDF-1.4 fake"), "application/pdf")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["session_token"]
    assert body["nationality"] == "Pakistan"
    assert body["courses"] == [{"name": "Linear Algebra", "grade": "A"}]
    assert body["extraction_confidence"] == "high"


def test_upload_transcript_rejects_unsupported_file_type(api_client):
    response = api_client.post(
        "/transcript", files={"file": ("notes.txt", io.BytesIO(b"plain text"), "text/plain")},
    )

    assert response.status_code == 415


def test_upload_transcript_rejects_a_file_over_the_size_cap(api_client, monkeypatch):
    monkeypatch.setattr(main_module, "MAX_TRANSCRIPT_UPLOAD_BYTES", 10)

    response = api_client.post(
        "/transcript",
        files={"file": ("transcript.pdf", io.BytesIO(b"%PDF-1.4 way more than ten bytes"), "application/pdf")},
    )

    assert response.status_code == 413


def test_upload_transcript_rejects_content_that_does_not_match_declared_type(api_client):
    # Claims PNG but the bytes are plainly not a PNG -- content_type is a
    # client-supplied multipart header and not to be trusted on its own.
    response = api_client.post(
        "/transcript", files={"file": ("transcript.png", io.BytesIO(b"not a real png"), "image/png")},
    )

    assert response.status_code == 415


def test_upload_transcript_runs_extraction_off_the_event_loop(api_client, monkeypatch):
    """extract_transcript must be called via run_in_threadpool, not inline on
    the event loop -- otherwise a slow vision-LLM call blocks every other
    concurrent request on the instance, including health checks."""
    calls = []

    def _fake_extract(file_bytes, content_type):
        import asyncio

        # run_in_threadpool (anyio.to_thread) executes on a worker thread
        # with no running event loop bound to it. If this were instead
        # called inline on the async endpoint, this thread WOULD have a
        # running loop.
        try:
            asyncio.get_running_loop()
            calls.append("ran_on_event_loop_thread")
        except RuntimeError:
            calls.append("ran_on_worker_thread")
        return TranscriptExtraction(
            courses=[ExtractedCourse(name="Linear Algebra", grade="A")], extraction_confidence="high",
        )

    monkeypatch.setattr(main_module, "extract_transcript", _fake_extract)

    response = api_client.post(
        "/transcript", files={"file": ("transcript.pdf", io.BytesIO(b"%PDF-1.4 fake"), "application/pdf")},
    )

    assert response.status_code == 200
    assert calls == ["ran_on_worker_thread"]
