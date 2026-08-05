from langchain_groq import ChatGroq

from ..config import settings
from .schema import EligibilityExtraction

EXTRACTION_MODEL = "llama-3.3-70b-versatile"

_llm: ChatGroq | None = None

PROMPT_TEMPLATE = """You are extracting structured eligibility criteria for a German university master's program, from DAAD's own program description text. Extract ONLY what is stated or clearly implied in the text below -- do not invent requirements. If something is not mentioned, leave it null/empty rather than guessing.

Every claim you extract must include a verbatim source_quote copied exactly from the text below. A source_quote must be a SELF-CONTAINED excerpt long enough to stand on its own as a citation -- include the surrounding sentence or list block it came from, not just an isolated word or number. For example, for a language requirement, quote the whole line listing the level and the accepted certificates together (e.g. "B2 required, please provide an official language certificate, e.g.: IELTS Academic: 6.5"), not just "B2" alone.

IMPORTANT distinctions:
- standardized_tests is ONLY for academic aptitude tests (GRE, GMAT). Language proficiency tests (IELTS, TOEFL, TOEIC, Cambridge, PTE, DSH, TestDaF, etc.) belong under language_requirements.accepted_tests instead, never in standardized_tests.
- When a language section lists several accepted tests (e.g. "TOEIC: 785, TOEFL: 72, IELTS: 6"), these are ALTERNATIVES -- the applicant only needs ONE of them, not all. List each as one entry in accepted_tests; do not imply they are all separately required.
- On a StandardizedTest, eligibility_condition means WHO or WHEN this test applies (e.g. "only for applicants from non-EU/EEA countries"), NOT the score thresholds themselves (those go in subscores).

Course: {course_name}
University: {university}

--- Academic admission requirements ---
{admission_requirements}

--- German language skills ---
{german_language}

--- English language skills ---
{english_language}
"""


def build_prompt(course_name: str, university: str, raw_sections: dict) -> str:
    return PROMPT_TEMPLATE.format(
        course_name=course_name,
        university=university,
        admission_requirements=raw_sections.get("admission_requirements", "(not stated)"),
        german_language=raw_sections.get("german_language", "(not stated)"),
        english_language=raw_sections.get("english_language", "(not stated)"),
    )


def get_extraction_llm() -> ChatGroq:
    """Process-wide Groq client (constructing one per call leaks connections)."""
    global _llm
    # An empty key 401s on every request — not retryable — which looks exactly
    # like quota exhaustion to the consecutive-failure circuit breaker. Name the
    # real cause on the first program instead of after 5 opaque failures.
    if not settings.groq_api_key:
        raise RuntimeError("GROQ_API_KEY is not set (see .env.example)")
    if _llm is None:
        _llm = ChatGroq(
            model=EXTRACTION_MODEL, api_key=settings.groq_api_key, temperature=0, max_retries=3
        )
    return _llm


def extract_eligibility(course_name: str, university: str, raw_sections: dict) -> EligibilityExtraction:
    prompt = build_prompt(course_name, university, raw_sections)
    structured_llm = get_extraction_llm().with_structured_output(EligibilityExtraction)
    return structured_llm.invoke(prompt)
