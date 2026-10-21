import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from evals.llm_spy import LlmSpy


class _FakeProvider(BaseChatModel):
    reply: str = "ok"
    fail: bool = False

    @property
    def _llm_type(self) -> str:
        return "fake"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        if self.fail:
            raise RuntimeError("provider down")
        message = AIMessage(content=self.reply, usage_metadata={"input_tokens": 7, "output_tokens": 3, "total_tokens": 10})
        return ChatResult(generations=[ChatGeneration(message=message)])


class FakeGroq(_FakeProvider):
    pass


class FakeMistral(_FakeProvider):
    pass


class FakeGemini(_FakeProvider):
    pass


PROVIDERS = {"groq": FakeGroq, "mistral": FakeMistral, "gemini": FakeGemini}


def test_spy_records_answering_provider_and_latency():
    chain = FakeGroq(reply="g").with_fallbacks([FakeMistral()])
    with LlmSpy(PROVIDERS) as spy:
        spy.start_case()
        assert chain.invoke("hi").content == "g"

    assert spy.answered_by() == "groq"
    [record] = spy.case_records
    assert record.ok and not record.blocked
    assert record.latency_s >= 0
    assert (record.input_tokens, record.output_tokens) == (7, 3)


def test_gemini_cap_blocks_after_limit_so_chain_falls_through():
    chain = FakeGemini(reply="gem").with_fallbacks([FakeMistral(reply="mis")])
    with LlmSpy(PROVIDERS, gemini_cap=1) as spy:
        spy.start_case()
        assert chain.invoke("one").content == "gem"
        spy.start_case()
        assert chain.invoke("two").content == "mis"

    assert spy.answered_by() == "mistral"
    assert [(r.provider, r.blocked) for r in spy.case_records] == [("gemini", True), ("mistral", False)]
    assert spy.gemini_calls == 1
    assert spy.gemini_guard_blocks == 1


def test_only_provider_blocks_the_others():
    chain = FakeGroq().with_fallbacks([FakeGemini(), FakeMistral(reply="mis")])
    with LlmSpy(PROVIDERS, only_provider="mistral") as spy:
        spy.start_case()
        assert chain.invoke("hi").content == "mis"

    assert [(r.provider, r.blocked) for r in spy.case_records] == [
        ("groq", True), ("gemini", True), ("mistral", False),
    ]
    assert spy.gemini_calls == 0


def test_spy_restores_original_methods_on_exit():
    originals = {name: cls.__dict__.get("_generate") for name, cls in PROVIDERS.items()}
    with LlmSpy(PROVIDERS):
        assert FakeGroq.__dict__.get("_generate") is not originals["groq"]

    assert {name: cls.__dict__.get("_generate") for name, cls in PROVIDERS.items()} == originals


def test_failed_provider_call_is_recorded_and_reraised():
    chain = FakeGroq(fail=True).with_fallbacks([FakeMistral(reply="mis")])
    with LlmSpy(PROVIDERS) as spy:
        spy.start_case()
        assert chain.invoke("hi").content == "mis"

    assert [(r.provider, r.ok, r.error) for r in spy.case_records] == [
        ("groq", False, "RuntimeError"), ("mistral", True, None),
    ]
    with pytest.raises(RuntimeError), LlmSpy(PROVIDERS):
        FakeGroq(fail=True).invoke("hi")
