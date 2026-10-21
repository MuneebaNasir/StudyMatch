import pytest
from langchain_core.runnables import RunnableLambda
from pydantic import BaseModel

from daad_search.transcript.schema import ExtractedCourse, TranscriptExtraction


class DummySchema(BaseModel):
    value: str


def _fake_llm(name: str, should_fail: bool, result=None):
    calls: list[str] = []

    def _invoke(prompt):
        calls.append(prompt)
        if should_fail:
            raise RuntimeError(f"{name} failed")
        return result if result is not None else f"{name} result"

    return RunnableLambda(_invoke), calls


class _FakeChatModel:
    def __init__(self, runnable):
        self._runnable = runnable

    def with_structured_output(self, schema):
        return self._runnable


def _patch_providers(
    monkeypatch, llm_module, primary_fails: bool, secondary_fails: bool,
    primary_result=None, secondary_result=None,
):
    primary, primary_calls = _fake_llm("primary", should_fail=primary_fails, result=primary_result)
    secondary, secondary_calls = _fake_llm("secondary", should_fail=secondary_fails, result=secondary_result)
    tertiary, tertiary_calls = _fake_llm("tertiary", should_fail=False)

    # Gemini is primary: the only free-tier vision model that reliably reads a
    # full transcript (see GEMINI_VISION_MODEL's comment in llm.py).
    monkeypatch.setattr(llm_module, "ChatGoogleGenerativeAI", lambda **kw: _FakeChatModel(primary))
    monkeypatch.setattr(llm_module, "ChatMistralAI", lambda **kw: _FakeChatModel(secondary))
    monkeypatch.setattr(llm_module, "ChatGroq", lambda **kw: _FakeChatModel(tertiary))
    monkeypatch.setattr(llm_module, "_vision_chains", {})

    return primary_calls, secondary_calls, tertiary_calls


def test_vision_fallback_chain_falls_through_to_secondary_when_primary_fails(monkeypatch):
    from daad_search.transcript import llm as llm_module

    primary_calls, secondary_calls, tertiary_calls = _patch_providers(
        monkeypatch, llm_module, primary_fails=True, secondary_fails=False
    )

    chain = llm_module.get_vision_fallback_llm(DummySchema)
    result = chain.invoke("test prompt")

    assert primary_calls == ["test prompt"]
    assert secondary_calls == ["test prompt"]
    assert tertiary_calls == []
    assert result == "secondary result"


def test_vision_fallback_chain_falls_through_to_tertiary_when_first_two_fail(monkeypatch):
    from daad_search.transcript import llm as llm_module

    primary_calls, secondary_calls, tertiary_calls = _patch_providers(
        monkeypatch, llm_module, primary_fails=True, secondary_fails=True
    )

    chain = llm_module.get_vision_fallback_llm(DummySchema)
    result = chain.invoke("test prompt")

    assert primary_calls == ["test prompt"]
    assert secondary_calls == ["test prompt"]
    assert tertiary_calls == ["test prompt"]
    assert result == "tertiary result"


def _graded(*grades):
    return TranscriptExtraction(
        courses=[ExtractedCourse(name=f"Course {i}", grade=g) for i, g in enumerate(grades)],
        extraction_confidence="high",
    )


@pytest.mark.parametrize(
    "bad_result",
    [
        # Schema-valid but useless: the shape Groq's qwen model really returned
        # for a legible 49-course transcript (only the overall GPA filled in).
        TranscriptExtraction(grade_value=3.24, extraction_confidence="medium"),
        # Course names read but grades left out.
        _graded(None, None, None, "A"),
    ],
)
def test_vision_fallback_chain_falls_through_on_an_unusable_extraction(monkeypatch, bad_result):
    from daad_search.transcript import llm as llm_module

    good = _graded("A", "B+", None)
    primary_calls, secondary_calls, tertiary_calls = _patch_providers(
        monkeypatch, llm_module, primary_fails=False, secondary_fails=False,
        primary_result=bad_result, secondary_result=good,
    )

    result = llm_module.get_vision_fallback_llm(TranscriptExtraction).invoke("test prompt")

    assert primary_calls == ["test prompt"]
    assert secondary_calls == ["test prompt"]
    assert tertiary_calls == []
    assert result == good


def test_vision_fallback_chain_accepts_a_mostly_graded_extraction(monkeypatch):
    from daad_search.transcript import llm as llm_module

    # Half graded is enough: in-progress courses legitimately have no grade yet.
    good = _graded("A", None)
    primary_calls, secondary_calls, _ = _patch_providers(
        monkeypatch, llm_module, primary_fails=False, secondary_fails=False, primary_result=good,
    )

    result = llm_module.get_vision_fallback_llm(TranscriptExtraction).invoke("test prompt")

    assert result == good
    assert secondary_calls == []


def test_get_vision_fallback_llm_caches_per_schema(monkeypatch):
    from daad_search.transcript import llm as llm_module

    _patch_providers(monkeypatch, llm_module, primary_fails=False, secondary_fails=False)

    first = llm_module.get_vision_fallback_llm(DummySchema)
    second = llm_module.get_vision_fallback_llm(DummySchema)
    assert first is second


def test_build_image_message_includes_text_and_each_page_as_a_data_url():
    from daad_search.transcript.llm import build_image_message

    message = build_image_message("extract this", [b"page-one-bytes", b"page-two-bytes"])

    assert message.content[0] == {"type": "text", "text": "extract this"}
    assert len(message.content) == 3
    assert message.content[1]["type"] == "image_url"
    assert message.content[1]["image_url"]["url"].startswith("data:image/png;base64,")
