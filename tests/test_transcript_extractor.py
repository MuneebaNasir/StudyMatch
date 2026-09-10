import io

from PIL import Image

from daad_search.transcript import extractor as extractor_module
from daad_search.transcript.schema import ExtractedCourse, TranscriptExtraction


def _fake_png_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (1, 1)).save(buffer, format="PNG")
    return buffer.getvalue()


class _FakeChain:
    def __init__(self, result=None, should_raise=False):
        self._result = result
        self._should_raise = should_raise

    def invoke(self, messages):
        if self._should_raise:
            raise RuntimeError("all vision providers failed")
        return self._result


def test_extract_transcript_uses_vision_chain_result_when_available(monkeypatch):
    expected = TranscriptExtraction(
        courses=[ExtractedCourse(name="Algorithms", grade="A")], extraction_confidence="high",
    )
    monkeypatch.setattr(extractor_module, "get_vision_fallback_llm", lambda schema: _FakeChain(result=expected))

    result = extractor_module.extract_transcript(_fake_png_bytes(), "image/png")

    assert result == expected


def test_extract_transcript_falls_back_to_local_vlm_when_vision_chain_fails(monkeypatch):
    monkeypatch.setattr(
        extractor_module, "get_vision_fallback_llm", lambda schema: _FakeChain(should_raise=True)
    )
    monkeypatch.setattr(extractor_module.settings, "enable_local_vlm_fallback", True)
    fallback_result = TranscriptExtraction(extraction_confidence="medium")
    monkeypatch.setattr(extractor_module, "extract_with_local_vlm", lambda images: fallback_result)

    result = extractor_module.extract_transcript(_fake_png_bytes(), "image/png")

    assert result == fallback_result


def test_extract_transcript_returns_low_confidence_when_everything_fails(monkeypatch):
    monkeypatch.setattr(
        extractor_module, "get_vision_fallback_llm", lambda schema: _FakeChain(should_raise=True)
    )
    monkeypatch.setattr(extractor_module.settings, "enable_local_vlm_fallback", True)

    def _raise(images):
        raise RuntimeError("local vlm broke")

    monkeypatch.setattr(extractor_module, "extract_with_local_vlm", _raise)

    result = extractor_module.extract_transcript(_fake_png_bytes(), "image/png")

    assert result.extraction_confidence == "low"
    assert result.courses == []


def test_extract_transcript_skips_local_vlm_when_fallback_disabled_by_default(monkeypatch):
    """With enable_local_vlm_fallback off (the default), a full vision-chain
    failure must skip straight to the existing low-confidence total-failure
    result WITHOUT ever invoking the local VLM -- loading it is what risks
    OOMing a scale-to-zero Cloud Run instance."""
    monkeypatch.setattr(
        extractor_module, "get_vision_fallback_llm", lambda schema: _FakeChain(should_raise=True)
    )
    assert extractor_module.settings.enable_local_vlm_fallback is False  # confirms the real default

    calls: list[list[bytes]] = []

    def _track(images):
        calls.append(images)
        return TranscriptExtraction(extraction_confidence="medium")

    monkeypatch.setattr(extractor_module, "extract_with_local_vlm", _track)

    result = extractor_module.extract_transcript(_fake_png_bytes(), "image/png")

    assert calls == []
    assert result.extraction_confidence == "low"
    assert result.courses == []


def test_extract_transcript_returns_low_confidence_when_rasterization_fails(monkeypatch):
    def _raise(file_bytes, content_type):
        raise RuntimeError("corrupt pdf")

    monkeypatch.setattr(extractor_module, "file_to_page_images", _raise)

    result = extractor_module.extract_transcript(_fake_png_bytes(), "application/pdf")

    assert result.extraction_confidence == "low"
    assert result.courses == []
