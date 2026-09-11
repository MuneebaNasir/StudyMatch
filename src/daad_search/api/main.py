import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

from typing import Literal

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from ..config import settings
from ..db.models import Eligibility, Program
from ..db.session import async_session_factory
from ..db.transcript_store import insert_transcript_profile
from ..query_understanding.reasoner import reason_about_eligibility
from ..query_understanding.schema import CandidateForReasoning, QueryRequest, QueryResponse, StudentProfile
from ..transcript.extractor import extract_transcript
from ..transcript.schema import TranscriptUploadResponse
from .query import handle_query
from .schemas import ProgramDetail, SearchRequest, SearchResponse
from .search import filtered_search, hybrid_search, to_search_result

app = FastAPI(title="DAAD Search API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def get_session() -> AsyncSession:
    async with async_session_factory() as session:
        yield session


@app.post("/search", response_model=SearchResponse)
async def search(
    request: SearchRequest, session: AsyncSession = Depends(get_session)
) -> SearchResponse:
    if request.semantic_query:
        results, total = await hybrid_search(
            session, request.filters, request.semantic_query, request.limit, request.offset
        )
    else:
        results, total = await filtered_search(
            session, request.filters, request.limit, request.offset
        )
    return SearchResponse(results=results, total_matched=total)


@app.post("/query", response_model=QueryResponse)
async def query(
    request: QueryRequest, session: AsyncSession = Depends(get_session)
) -> QueryResponse:
    return await handle_query(session, request.query, request.limit, request.offset, request.session_token)


ALLOWED_TRANSCRIPT_CONTENT_TYPES = {"application/pdf", "image/png", "image/jpeg"}

# Hard cap on upload size. A crafted PDF/image well past this can force a
# huge pixmap allocation during rasterization or a slow vision-LLM call;
# 10MB is generous for a transcript scan and keeps worst-case per-request
# memory bounded on a Cloud Run instance shared with other in-flight
# requests. Checked twice below: against the Content-Length header (a fast
# reject when present) and again against the actual bytes read (authoritative
# -- Content-Length is client-supplied and not guaranteed to be present or
# accurate).
MAX_TRANSCRIPT_UPLOAD_BYTES = 10 * 1024 * 1024

# Leading bytes that verify a file's content actually matches its claimed
# content-type, since `file.content_type` is a client-supplied multipart
# header and fully attacker-controlled.
TRANSCRIPT_MAGIC_BYTES = {
    "application/pdf": b"%PDF-",
    "image/png": b"\x89PNG",
    "image/jpeg": b"\xff\xd8\xff",
}


@app.post("/transcript", response_model=TranscriptUploadResponse)
async def upload_transcript(
    request: Request, file: UploadFile = File(...), session: AsyncSession = Depends(get_session)
) -> TranscriptUploadResponse:
    if file.content_type not in ALLOWED_TRANSCRIPT_CONTENT_TYPES:
        raise HTTPException(status_code=415, detail="Unsupported file type; upload a PDF, PNG, or JPEG.")

    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            if int(content_length) > MAX_TRANSCRIPT_UPLOAD_BYTES:
                raise HTTPException(status_code=413, detail="File too large; max 10MB.")
        except ValueError:
            pass  # malformed header; fall through to the authoritative check below

    file_bytes = await file.read(MAX_TRANSCRIPT_UPLOAD_BYTES + 1)
    if len(file_bytes) > MAX_TRANSCRIPT_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large; max 10MB.")

    magic = TRANSCRIPT_MAGIC_BYTES[file.content_type]
    if not file_bytes.startswith(magic):
        raise HTTPException(status_code=415, detail="File content does not match its declared type.")

    extraction = await run_in_threadpool(extract_transcript, file_bytes, file.content_type)
    token = await insert_transcript_profile(session, extraction)

    return TranscriptUploadResponse(
        session_token=token,
        courses=extraction.courses,
        grade_value=extraction.grade_value,
        grade_scale=extraction.grade_scale,
        nationality=extraction.nationality,
        degree_field=extraction.degree_field,
        extraction_confidence=extraction.extraction_confidence,
    )


@app.get("/programs/{program_id}", response_model=ProgramDetail)
async def get_program(
    program_id: int, session: AsyncSession = Depends(get_session)
) -> ProgramDetail:
    row = await session.get(Program, program_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Program not found")

    eligibility = await session.get(Eligibility, program_id)

    base = to_search_result(row)
    return ProgramDetail(
        **base.model_dump(),
        course_type=row.course_type,
        degree=row.degree,
        duration=row.duration,
        beginning=row.beginning,
        raw_sections=row.raw_sections,
        structured_eligibility=eligibility.structured_eligibility if eligibility else None,
    )


class EvaluateEligibilityRequest(BaseModel):
    profile: StudentProfile


class EvaluateEligibilityResponse(BaseModel):
    eligibility_verdict: Literal["eligible", "likely_eligible", "not_eligible", "unclear", "no_data"]
    eligibility_reasoning: str | None


@app.post("/programs/{program_id}/evaluate-eligibility", response_model=EvaluateEligibilityResponse)
async def evaluate_eligibility(
    program_id: int, request: EvaluateEligibilityRequest, session: AsyncSession = Depends(get_session)
) -> EvaluateEligibilityResponse:
    row = await session.get(Program, program_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Program not found")

    eligibility = await session.get(Eligibility, program_id)
    if eligibility is None or not eligibility.structured_eligibility:
        return EvaluateEligibilityResponse(eligibility_verdict="no_data", eligibility_reasoning=None)

    candidate = CandidateForReasoning(
        program_id=program_id, course_name=row.course_name,
        structured_eligibility=eligibility.structured_eligibility,
    )
    verdicts = reason_about_eligibility(request.profile, [candidate])
    if not verdicts:
        return EvaluateEligibilityResponse(
            eligibility_verdict="unclear",
            eligibility_reasoning="Eligibility reasoning was unavailable for this program.",
        )
    v = verdicts[0]
    return EvaluateEligibilityResponse(eligibility_verdict=v.verdict, eligibility_reasoning=v.reasoning)
