# src/daad_search/query_understanding/parser.py
import logging

from .llm import ModelNameCapture, get_fallback_llm
from .schema import ParsedQuery

logger = logging.getLogger(__name__)

QUERY_PROMPT_TEMPLATE = """You are parsing a prospective international student's free-text search query for German university study programs into structured data.

Extract THREE things from the query below:

1. filters -- hard constraints explicitly stated (only set a field if the query actually states it; leave others null):
   - languages: list of teaching languages requested, e.g. ["English"]
   - max_tuition_free_only: true if the student wants only tuition-free programs
   - subject: ONLY set this if the query names an exact, narrow academic subject that is likely to match a university subject label directly (e.g. "Mechanical Engineering"). If the subject is broad, colloquial, or might not match an exact label (e.g. "robotics", "AI", "data stuff"), leave subject null and put it in semantic_query instead -- it will be matched by meaning, not exact text.
   - city: a specific city name if mentioned, e.g. "Berlin" or "Munich". Every program in this catalog is already in Germany, so "Germany"/"germany" is never a valid value here -- leave city null when the query only names the country, not a city.
   - course_type: the DAAD numeric course type code, ONLY if the query clearly implies one: 1=Bachelor's, 2=Master's, 3=PhD, 4=Graduate school, 5=Language course, 6=Short course, 7=Preparatory course, 9=Various. Most queries about "masters" should set this to 2.

2. semantic_query -- the substantive topic/subject-matter part of the query that isn't captured as a hard filter above (e.g. "robotics", "machine learning and business analytics"). Leave null if there's no such topic beyond the filters.

3. student_profile -- facts about the STUDENT THEMSELVES (not the programs they want), only if explicitly stated:
   - degree_field: their own prior degree's field, e.g. "Artificial Intelligence"
   - grade_value: their stated grade/CGPA/GPA as a number, e.g. 3.2
   - grade_scale: how they described the scale, e.g. "4.0 GPA scale (USA)" or "percentage" -- describe it in their own terms, do not convert it
   - nationality: their stated nationality/country of origin
   - other_notes: any other fact about the student relevant to eligibility (e.g. work experience, existing test scores) that doesn't fit the above

Query: {query}
"""


def build_query_prompt(query: str) -> str:
    return QUERY_PROMPT_TEMPLATE.format(query=query)


def parse_query(query: str) -> ParsedQuery | None:
    prompt = build_query_prompt(query)
    capture = ModelNameCapture()
    try:
        parsed = get_fallback_llm(ParsedQuery).invoke(prompt, config={"callbacks": [capture]})
    except Exception:
        logger.exception("Failed to parse query across all LLM providers: %r", query)
        return None
    if parsed is None:
        logger.warning("Query parsing returned no structured output: %r", query)
        return None
    logger.info(
        "QUERY    raw_query=%r model=%s\n"
        "         filters=%s semantic_query=%r\n"
        "         profile=%s",
        query, capture.model_name,
        parsed.filters.model_dump(), parsed.semantic_query,
        parsed.student_profile.model_dump() if parsed.student_profile else None,
    )
    return parsed
