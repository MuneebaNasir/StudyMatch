import io
import json
import logging

from PIL import Image

from .schema import ExtractedCourse, TranscriptExtraction

logger = logging.getLogger(__name__)

# Small enough to plausibly run on Cloud Run's free-tier CPU/memory limits --
# see the Docker-size/cold-start risk noted in this feature's plan. Verify
# the exact required extra packages against this model's current model card
# before deploying (moondream2's transformers integration has needed
# `einops` historically; that may change).
LOCAL_VLM_MODEL = "vikhyatk/moondream2"
LOCAL_VLM_REVISION = "2024-08-26"

_model = None
_tokenizer = None


def _load_model():
    global _model, _tokenizer
    if _model is None:
        from transformers import AutoModelForCausalLM, AutoTokenizer

        _model = AutoModelForCausalLM.from_pretrained(
            LOCAL_VLM_MODEL, revision=LOCAL_VLM_REVISION, trust_remote_code=True
        )
        _tokenizer = AutoTokenizer.from_pretrained(LOCAL_VLM_MODEL, revision=LOCAL_VLM_REVISION)
    return _model, _tokenizer


EXTRACTION_QUESTION = (
    "List every course name and its grade from this transcript page, plus the "
    "student's overall GPA/grade, grading scale, nationality if stated, and "
    "degree field. Respond as JSON only, matching this shape: "
    '{"courses": [{"name": "...", "grade": "..."}], "grade_value": 0.0, '
    '"grade_scale": "...", "nationality": "...", "degree_field": "..."}'
)


def extract_with_local_vlm(page_images: list[bytes]) -> TranscriptExtraction:
    """Last-resort extraction when every vision API in the fallback chain is
    unavailable. Runs a small local VLM per page and merges the results --
    courses accumulate across pages, scalar fields take the first non-null
    value seen."""
    model, tokenizer = _load_model()

    courses: list[ExtractedCourse] = []
    grade_value = None
    grade_scale = None
    nationality = None
    degree_field = None
    any_page_parsed = False

    for image_bytes in page_images:
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        try:
            answer = model.answer_question(model.encode_image(image), EXTRACTION_QUESTION, tokenizer)
            parsed = json.loads(answer)

            page_courses = []
            for course in parsed.get("courses", []):
                if course.get("name"):
                    page_courses.append(ExtractedCourse(name=course["name"], grade=course.get("grade")))
            page_grade_value = parsed.get("grade_value")
            page_grade_scale = parsed.get("grade_scale")
            page_nationality = parsed.get("nationality")
            page_degree_field = parsed.get("degree_field")
        except Exception:
            # Covers JSON-decode failure as well as syntactically valid JSON
            # that isn't shaped as documented (e.g. "courses" isn't a list,
            # a course entry isn't a dict, or a field's type fails pydantic
            # validation). The model's output is untrusted, and a single
            # malformed page must never crash the whole multi-page
            # extraction -- skip it and keep whatever earlier pages
            # contributed.
            logger.warning("Local VLM produced unparseable output for one transcript page")
            continue

        any_page_parsed = True
        courses.extend(page_courses)
        grade_value = grade_value if grade_value is not None else page_grade_value
        grade_scale = grade_scale or page_grade_scale
        nationality = nationality or page_nationality
        degree_field = degree_field or page_degree_field

    return TranscriptExtraction(
        courses=courses, grade_value=grade_value, grade_scale=grade_scale,
        nationality=nationality, degree_field=degree_field,
        extraction_confidence="medium" if any_page_parsed else "low",
    )
