import io

import pytest

from daad_search.api import main as main_module
from daad_search.transcript.schema import ExtractedCourse, TranscriptExtraction

pytestmark = pytest.mark.integration


def test_upload_transcript_returns_extraction_without_storing_it(api_client, monkeypatch):
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
    assert "session_token" not in body
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


def test_upload_transcript_read_is_bounded_by_size_argument(api_client, monkeypatch):
    """The actual body read must be bounded via `UploadFile.read(size=...)`,
    not an unbounded `file.read()` -- otherwise an attacker who omits or
    understates Content-Length can still force an arbitrarily large
    in-memory allocation before the length check ever runs. This asserts
    the read call itself is passed a fixed, bounded size (one more than the
    cap, to distinguish "at the cap" from "over"), independent of whatever
    Content-Length the client claims."""
    from starlette.datastructures import UploadFile

    captured_sizes = []
    original_read = UploadFile.read

    async def _tracking_read(self, size=-1):
        captured_sizes.append(size)
        return await original_read(self, size)

    monkeypatch.setattr(UploadFile, "read", _tracking_read)

    response = api_client.post(
        "/transcript", files={"file": ("transcript.pdf", io.BytesIO(b"%PDF-1.4 fake"), "application/pdf")},
    )

    assert response.status_code == 200
    assert captured_sizes == [main_module.MAX_TRANSCRIPT_UPLOAD_BYTES + 1]


def test_upload_transcript_rejects_oversized_body_with_understated_content_length(api_client, monkeypatch):
    """An attacker can send a Content-Length header that understates (or
    omits) the true body size -- the fast-reject check above the read only
    catches an honestly-declared oversized upload. The authoritative check
    is the bounded read itself, so this must still 413 even when
    Content-Length lies about being small."""
    monkeypatch.setattr(main_module, "MAX_TRANSCRIPT_UPLOAD_BYTES", 10)

    oversized_body = b"%PDF-1.4 way more than ten bytes"
    response = api_client.post(
        "/transcript",
        files={"file": ("transcript.pdf", io.BytesIO(oversized_body), "application/pdf")},
        # Lies: claims 1 byte while the actual multipart body carrying the
        # file is far larger than the 10-byte cap set above.
        headers={"content-length": "1"},
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
