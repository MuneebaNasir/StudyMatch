# src/daad_search/query_understanding/llm.py
from typing import TypeVar

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from langchain_mistralai import ChatMistralAI
from pydantic import BaseModel

from ..config import settings

GROQ_MODEL = "llama-3.3-70b-versatile"
MISTRAL_MODEL = "mistral-small-latest"
GEMINI_MODEL = "gemini-2.0-flash"


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
    """Groq -> Mistral -> Gemini structured-output fallback chain for `schema`.

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
        secondary = ChatMistralAI(
            model=MISTRAL_MODEL, api_key=settings.mistral_api_key, temperature=0, max_retries=2
        ).with_structured_output(schema)
        tertiary = ChatGoogleGenerativeAI(
            model=GEMINI_MODEL, api_key=settings.gemini_api_key, temperature=0, max_retries=2
        ).with_structured_output(schema)
        _chains[schema] = primary.with_fallbacks([secondary, tertiary])
    return _chains[schema]
