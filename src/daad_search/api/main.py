from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import Program
from ..db.session import async_session_factory
from .schemas import ProgramDetail, SearchRequest, SearchResponse
from .search import filtered_search, to_search_result

app = FastAPI(title="DAAD Search API")


async def get_session() -> AsyncSession:
    async with async_session_factory() as session:
        yield session


@app.post("/search", response_model=SearchResponse)
async def search(
    request: SearchRequest, session: AsyncSession = Depends(get_session)
) -> SearchResponse:
    results, total = await filtered_search(session, request.filters, request.limit)
    return SearchResponse(results=results, total_matched=total)


@app.get("/programs/{program_id}", response_model=ProgramDetail)
async def get_program(
    program_id: int, session: AsyncSession = Depends(get_session)
) -> ProgramDetail:
    row = await session.get(Program, program_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Program not found")

    base = to_search_result(row)
    return ProgramDetail(
        **base.model_dump(),
        course_type=row.course_type,
        degree=row.degree,
        duration=row.duration,
        beginning=row.beginning,
        raw_sections=row.raw_sections,
    )
