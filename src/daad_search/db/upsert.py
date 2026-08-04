from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Program


async def upsert_program(session: AsyncSession, program_id: int, values: dict) -> None:
    stmt = pg_insert(Program).values(id=program_id, **values)
    update_cols = {col: stmt.excluded[col] for col in values}
    stmt = stmt.on_conflict_do_update(index_elements=[Program.id], set_=update_cols)
    await session.execute(stmt)
    await session.commit()
