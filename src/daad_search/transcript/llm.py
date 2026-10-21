import base64
from typing import TypeVar

from langchain_core.messages import HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from langchain_mistralai import ChatMistralAI
from pydantic import BaseModel

from ..config import settings

# Vision-capable variants -- distinct from the text-only models in
# query_understanding/llm.py (GROQ_MODEL/MISTRAL_MODEL there cannot see
# images). Verify current availability against each provider's model list
# before deploying; vision model names/tiers change more often than the
# text ones. Last verified with a real image on 2026-10-21.
GROQ_VISION_MODEL = "qwen/qwen3.8-27b"
MISTRAL_VISION_MODEL = "pixtral-12b-2409"
GEMINI_VISION_MODEL = "gemini-3.5-flash"

T = TypeVar("T", bound=BaseModel)

_vision_chains: dict[type[BaseModel], object] = {}


def get_vision_fallback_llm(schema: type[T]):
    """Groq -> Mistral -> Gemini vision-capable structured-output fallback chain.

    Mirrors query_understanding/llm.py's get_fallback_llm, but each provider
    uses its vision-capable model so the chain can accept image content
    blocks, not just text.
    """
    if schema not in _vision_chains:
        primary = ChatGroq(
            model=GROQ_VISION_MODEL, api_key=settings.groq_api_key, temperature=0, max_retries=2
        ).with_structured_output(schema)
        secondary = ChatMistralAI(
            model=MISTRAL_VISION_MODEL, api_key=settings.mistral_api_key, temperature=0, max_retries=2
        ).with_structured_output(schema)
        tertiary = ChatGoogleGenerativeAI(
            model=GEMINI_VISION_MODEL, api_key=settings.gemini_api_key, temperature=0, max_retries=2
        ).with_structured_output(schema)
        _vision_chains[schema] = primary.with_fallbacks([secondary, tertiary])
    return _vision_chains[schema]


def build_image_message(prompt: str, page_images: list[bytes]) -> HumanMessage:
    content: list[dict] = [{"type": "text", "text": prompt}]
    for image_bytes in page_images:
        b64 = base64.b64encode(image_bytes).decode("ascii")
        content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}})
    return HumanMessage(content=content)
