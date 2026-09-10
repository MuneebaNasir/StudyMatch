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
