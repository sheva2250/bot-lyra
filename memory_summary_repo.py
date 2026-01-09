from db import get_pool
from db_queue import enqueue

async def get_memory_summary(uid: str):
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT summary FROM memory_summaries WHERE user_id=$1",
                uid
            )
            return row["summary"] if row else ""
    except Exception as e:
        print("[DB WARN] get_memory_summary failed:", e)
        return ""


async def save_memory_summary(uid: str, summary: str):
    await enqueue(
        """
        INSERT INTO memory_summaries (user_id, summary, updated_at)
        VALUES ($1, $2, now())
        ON CONFLICT (user_id)
        DO UPDATE SET
            summary = excluded.summary,
            updated_at = excluded.updated_at
        """,
        uid,
        summary
    )
