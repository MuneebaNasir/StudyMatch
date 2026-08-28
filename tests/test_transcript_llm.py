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


def test_vision_fallback_chain_falls_through_to_secondary_when_primary_fails(monkeypatch):
    from daad_search.transcript import llm as llm_module

    primary, primary_calls = _fake_llm("primary", should_fail=True)
    secondary, secondary_calls = _fake_llm("secondary", should_fail=False)
    tertiary, tertiary_calls = _fake_llm("tertiary", should_fail=False)

    monkeypatch.setattr(llm_module, "ChatGroq", lambda **kw: _FakeChatModel(primary))
    monkeypatch.setattr(llm_module, "ChatMistralAI", lambda **kw: _FakeChatModel(secondary))
    monkeypatch.setattr(llm_module, "ChatGoogleGenerativeAI", lambda **kw: _FakeChatModel(tertiary))
    monkeypatch.setattr(llm_module, "_vision_chains", {})

    chain = llm_module.get_vision_fallback_llm(DummySchema)
    result = chain.invoke("test prompt")

    assert primary_calls == ["test prompt"]
    assert secondary_calls == ["test prompt"]
    assert tertiary_calls == []
    assert result == "secondary result"


def test_build_image_message_includes_text_and_each_page_as_a_data_url():
    from daad_search.transcript.llm import build_image_message

    message = build_image_message("extract this", [b"page-one-bytes", b"page-two-bytes"])

    assert message.content[0] == {"type": "text", "text": "extract this"}
    assert len(message.content) == 3
    assert message.content[1]["type"] == "image_url"
    assert message.content[1]["image_url"]["url"].startswith("data:image/png;base64,")
