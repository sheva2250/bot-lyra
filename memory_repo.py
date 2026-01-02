# memory_summary_repo.py
from db import get_pool


async def get_memory_summary(user_id: str):
    pool = await get_pool()
    if pool is None:
        return ""

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT summary FROM memory_summaries WHERE user_id=$1",
            user_id
        )
        return row["summary"] if row else ""


async def save_memory_summary(user_id: str, summary: str):
    pool = await get_pool()
    if pool is None:
        return

    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO memory_summaries (user_id, summary, updated_at)
            VALUES ($1, $2, NOW())
            ON CONFLICT (user_id)
            DO UPDATE SET
              summary = EXCLUDED.summary,
              updated_at = EXCLUDED.updated_at
            """,
            user_id,
            summary
        )
