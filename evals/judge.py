"""LLM-as-judge for eligibility reasoning.

Built directly on Groq's text model rather than the app's fallback chain, so
judging never spends the Gemini quota shared with the live site. A failed
judge call returns None and is recorded as a skipped judgement.
"""
import json

from langchain_groq import ChatGroq
from pydantic import BaseModel

from daad_search.config import settings
from daad_search.query_understanding.llm import GROQ_MODEL
from daad_search.query_understanding.reasoner import convert_to_german_scale
from daad_search.query_understanding.schema import EligibilityVerdict

from .datasets import ProgramSnapshot

JUDGE_PROMPT = """You are reviewing an automated admissions-eligibility verdict.

Student profile:
{profile}
{conversion}
Program requirements ({course_name}):
{requirements}

Verdict given: {verdict}
Reasoning given: {reasoning}

Answer two questions strictly:
1. supports_verdict: does the reasoning, as written, actually justify the verdict given?
2. contradicts_case_facts: does the reasoning misstate any fact from the profile or the requirements
   (e.g. wrong grade, wrong threshold, treating a 10-point CGPA or a German grade -- where 1.0 is best --
   as if it were a 4.0 GPA)?
Explain briefly."""


class JudgeResult(BaseModel):
    supports_verdict: bool
    contradicts_case_facts: bool
    explanation: str


def build_judge_prompt(profile: dict, program: ProgramSnapshot, verdict: EligibilityVerdict) -> str:
    # Same deterministic conversion the app gives the reasoner, so the judge
    # doesn't flag a correct conversion as a factual error.
    converted = None
    if profile.get("grade_value") is not None:
        converted = convert_to_german_scale(profile["grade_value"], profile.get("grade_scale"))
    conversion = (
        f"Reference (computed in code, DAAD modified Bavarian formula): German-scale equivalent: {converted}\n"
        if converted is not None else ""
    )
    return JUDGE_PROMPT.format(
        profile=json.dumps(profile, indent=2),
        conversion=conversion,
        course_name=program.course_name,
        requirements=json.dumps(program.structured_eligibility, indent=2),
        verdict=verdict.verdict,
        reasoning=verdict.reasoning,
    )


def judge_reasoning(profile: dict, program: ProgramSnapshot, verdict: EligibilityVerdict) -> JudgeResult | None:
    prompt = build_judge_prompt(profile, program, verdict)
    try:
        judge = ChatGroq(model=GROQ_MODEL, api_key=settings.groq_api_key, temperature=0, max_retries=1)
        return judge.with_structured_output(JudgeResult, method="json_schema").invoke(prompt)
    except Exception:
        return None
