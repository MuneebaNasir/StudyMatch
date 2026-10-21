import base64
from typing import TypeVar

from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableLambda
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from langchain_mistralai import ChatMistralAI
from pydantic import BaseModel

from ..config import settings
from .schema import TranscriptExtraction

# Vision-capable variants -- distinct from the text-only models in
# query_understanding/llm.py (GROQ_MODEL/MISTRAL_MODEL there cannot see
# images). Verify current availability against each provider's model list
# before deploying; vision model names/tiers change more often than the
# text ones. Last verified against a real 49-course scanned transcript on
# 2026-10-21, which is also what set the chain order below:
# - Gemini read every course and grade correctly, but its free tier allows
#   only ~20 requests/day -- hence first, with the others behind it.
# - ministral-14b found ~42/49 courses with ~1 in 4 grades misread. It is what
#   the retired pixtral-12b-2409 silently resolved to; the stronger Mistral
#   vision/OCR models aren't available on the free plan.
# - Groq's qwen returned schema-valid but empty course lists every time.
GEMINI_VISION_MODEL = "gemini-3.5-flash"
MISTRAL_VISION_MODEL = "ministral-14b-2512"
GROQ_VISION_MODEL = "qwen/qwen3.8-27b"

T = TypeVar("T", bound=BaseModel)

_vision_chains: dict[type[BaseModel], object] = {}


class UnusableExtractionError(Exception):
    """A provider returned a schema-valid transcript extraction with no usable
    course list. Raised so with_fallbacks() moves on to the next provider --
    it only falls through on exceptions, so a well-formed empty answer would
    otherwise be returned as a success."""


def _reject_unusable_extraction(result):
    if isinstance(result, TranscriptExtraction):
        graded = sum(1 for course in result.courses if course.grade)
        # Half rather than all: in-progress courses legitimately have no grade.
        if not result.courses or graded * 2 < len(result.courses):
            raise UnusableExtractionError(
                f"{len(result.courses)} courses extracted, {graded} with a grade"
            )
    return result


def get_vision_fallback_llm(schema: type[T]):
    """Gemini -> Mistral -> Groq vision-capable structured-output fallback chain.

    Mirrors query_understanding/llm.py's get_fallback_llm, but each provider
    uses its vision-capable model so the chain can accept image content
    blocks, not just text. Each provider's answer is also checked for a usable
    course list, so a provider that "succeeds" with an empty one falls through
    like a failed one.
    """
    if schema not in _vision_chains:
        check = RunnableLambda(_reject_unusable_extraction)
        primary = ChatGoogleGenerativeAI(
            model=GEMINI_VISION_MODEL, api_key=settings.gemini_api_key, temperature=0, max_retries=2
        ).with_structured_output(schema) | check
        secondary = ChatMistralAI(
            model=MISTRAL_VISION_MODEL, api_key=settings.mistral_api_key, temperature=0, max_retries=2
        ).with_structured_output(schema) | check
        tertiary = ChatGroq(
            model=GROQ_VISION_MODEL, api_key=settings.groq_api_key, temperature=0, max_retries=2
        ).with_structured_output(schema) | check
        _vision_chains[schema] = primary.with_fallbacks([secondary, tertiary])
    return _vision_chains[schema]


def build_image_message(prompt: str, page_images: list[bytes]) -> HumanMessage:
    content: list[dict] = [{"type": "text", "text": prompt}]
    for image_bytes in page_images:
        b64 = base64.b64encode(image_bytes).decode("ascii")
        content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}})
    return HumanMessage(content=content)
