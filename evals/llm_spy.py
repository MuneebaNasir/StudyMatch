"""Watches the app's real LLM provider calls during an eval run.

LlmSpy temporarily wraps `_generate` on each provider's LangChain chat class,
so the app's own fallback chains, prompts and schemas run unchanged while the
spy records which provider answered, latency and token usage. It can also
block a provider by raising ProviderBlockedError, which `.with_fallbacks()`
treats like any provider failure and moves on to the next tier:

- the Gemini quota guard blocks Gemini after `gemini_cap` invocations, so an
  eval run can't exhaust the free-tier quota it shares with the live site;
- `only_provider` blocks every other provider, so the production chain falls
  through to the single provider under test.

Counts are per model invocation. HTTP retries inside each provider SDK
(`max_retries=2` in the app) happen below `_generate` and are not counted.
"""
import time
from dataclasses import dataclass


class ProviderBlockedError(Exception):
    pass


@dataclass
class CallRecord:
    provider: str
    ok: bool
    latency_s: float
    input_tokens: int | None
    output_tokens: int | None
    blocked: bool


def default_provider_classes() -> dict[str, type]:
    from langchain_google_genai import ChatGoogleGenerativeAI
    from langchain_groq import ChatGroq
    from langchain_mistralai import ChatMistralAI

    return {"groq": ChatGroq, "mistral": ChatMistralAI, "gemini": ChatGoogleGenerativeAI}


class LlmSpy:
    def __init__(self, provider_classes: dict[str, type], gemini_cap: int | None = 5, only_provider: str | None = None):
        self._provider_classes = provider_classes
        self._gemini_cap = gemini_cap
        self.only_provider = only_provider
        self._saved: dict[str, object] = {}
        self.case_records: list[CallRecord] = []
        self.gemini_calls = 0
        self.gemini_guard_blocks = 0

    def start_case(self) -> None:
        self.case_records = []

    def answered_by(self) -> str | None:
        answered = [r.provider for r in self.case_records if r.ok]
        return answered[-1] if answered else None

    def _blocked(self, provider: str) -> bool:
        if self.only_provider is not None and provider != self.only_provider:
            return True
        if provider == "gemini" and self._gemini_cap is not None and self.gemini_calls >= self._gemini_cap:
            self.gemini_guard_blocks += 1
            return True
        return False

    def _wrap(self, provider: str, original):
        spy = self

        def _generate(model_self, *args, **kwargs):
            if spy._blocked(provider):
                spy.case_records.append(CallRecord(provider, False, 0.0, None, None, blocked=True))
                raise ProviderBlockedError(provider)
            if provider == "gemini":
                spy.gemini_calls += 1
            start = time.perf_counter()
            try:
                result = original(model_self, *args, **kwargs)
            except Exception:
                spy.case_records.append(CallRecord(provider, False, time.perf_counter() - start, None, None, False))
                raise
            usage = getattr(result.generations[0].message, "usage_metadata", None) or {}
            spy.case_records.append(CallRecord(
                provider, True, time.perf_counter() - start,
                usage.get("input_tokens"), usage.get("output_tokens"), False,
            ))
            return result

        return _generate

    def __enter__(self):
        for provider, cls in self._provider_classes.items():
            self._saved[provider] = cls.__dict__.get("_generate")
            cls._generate = self._wrap(provider, cls._generate)
        return self

    def __exit__(self, *exc):
        for provider, cls in self._provider_classes.items():
            original = self._saved.pop(provider)
            if original is None:
                del cls._generate
            else:
                cls._generate = original
        return False
