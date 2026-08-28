from langchain_core.runnables import RunnableLambda
from pydantic import BaseModel


class DummySchema(BaseModel):
    value: str


def _fake_llm(name: str, should_fail: bool):
    calls: list[str] = []

    def _invoke(prompt):
        calls.append(prompt)
        if should_fail:
            raise RuntimeError(f"{name} failed")
        return f"{name} result"

    return RunnableLambda(_invoke), calls


class _FakeChatModel:
    def __init__(self, runnable):
        self._runnable = runnable

    def with_structured_output(self, schema):
        return self._runnable


def _patch_providers(monkeypatch, llm_module, primary_fails: bool, secondary_fails: bool):
    primary, primary_calls = _fake_llm("primary", should_fail=primary_fails)
    secondary, secondary_calls = _fake_llm("secondary", should_fail=secondary_fails)
    tertiary, tertiary_calls = _fake_llm("tertiary", should_fail=False)

    monkeypatch.setattr(llm_module, "ChatGroq", lambda **kw: _FakeChatModel(primary))
    monkeypatch.setattr(llm_module, "ChatMistralAI", lambda **kw: _FakeChatModel(secondary))
    monkeypatch.setattr(llm_module, "ChatGoogleGenerativeAI", lambda **kw: _FakeChatModel(tertiary))
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
