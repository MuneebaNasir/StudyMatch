# src/daad_search/query_understanding/llm.py
from typing import TypeVar

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from langchain_mistralai import ChatMistralAI
from pydantic import BaseModel

from ..config import settings

# Verified against each provider's live model list on 2026-10-21 -- free-tier
# model IDs get retired without much notice, so re-check these if a whole
# tier starts failing with 404/model_not_found.
GROQ_MODEL = "openai/gpt-oss-120b"
GEMINI_MODEL = "gemini-3.5-flash"
# Mistral's stronger models are rate-limited or tier-gated on the free plan;
# ministral-8b is the one that reliably answers, so it goes last.
MISTRAL_MODEL = "ministral-8b-latest"


class ModelNameCapture(BaseCallbackHandler):
    """Records which provider answered a `.invoke()` call, via LangChain's
    on_llm_end callback. Read `.model_name` after the invoke returns."""

    def __init__(self) -> None:
        self.model_name: str | None = None

    def on_llm_end(self, response: LLMResult, **kwargs: object) -> None:
        try:
            message = response.generations[0][0].message
            metadata = message.response_metadata
        except (IndexError, AttributeError):
            return
        self.model_name = metadata.get("model_name") or metadata.get("model")


T = TypeVar("T", bound=BaseModel)

_chains: dict[type[BaseModel], object] = {}


def get_fallback_llm(schema: type[T]):
    """Groq -> Gemini -> Mistral structured-output fallback chain for `schema`.

    Cached per schema class (constructing 3 clients per call would leak
    connections). All three providers are free-tier; if the primary fails
    (rate limit, network error, malformed output), LangChain's
    `.with_fallbacks()` transparently tries the next one with the same
    prompt/schema.
    """
    if schema not in _chains:
        primary = ChatGroq(
            model=GROQ_MODEL, api_key=settings.groq_api_key, temperature=0, max_retries=2
        ).with_structured_output(schema)
        secondary = ChatGoogleGenerativeAI(
            model=GEMINI_MODEL, api_key=settings.gemini_api_key, temperature=0, max_retries=2
        ).with_structured_output(schema)
        tertiary = ChatMistralAI(
            model=MISTRAL_MODEL, api_key=settings.mistral_api_key, temperature=0, max_retries=2
        ).with_structured_output(schema)
        _chains[schema] = primary.with_fallbacks([secondary, tertiary])
    return _chains[schema]
