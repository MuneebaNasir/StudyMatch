import logging

from .llm import build_image_message, get_vision_fallback_llm
from .local_vlm import extract_with_local_vlm
from .rasterize import file_to_page_images
from .schema import TranscriptExtraction

logger = logging.getLogger(__name__)

EXTRACTION_PROMPT = (
    "You are extracting structured data from a student's academic transcript. "
    "List every course and its grade exactly as written, plus the student's "
    "overall GPA/grade, the grading scale it's on, their nationality if stated "
    "anywhere on the document, and their degree field. Do not invent values "
    "that aren't present -- leave them null instead."
)


def extract_transcript(file_bytes: bytes, content_type: str) -> TranscriptExtraction:
    page_images = file_to_page_images(file_bytes, content_type)
    message = build_image_message(EXTRACTION_PROMPT, page_images)

    try:
        result = get_vision_fallback_llm(TranscriptExtraction).invoke([message])
        if result is not None:
            return result
    except Exception:
        logger.exception("Vision fallback chain failed for transcript extraction; trying local VLM")

    try:
        return extract_with_local_vlm(page_images)
    except Exception:
        logger.exception("Local VLM extraction failed")
        return TranscriptExtraction(extraction_confidence="low")
