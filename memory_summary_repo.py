from db import get_pool

async def get_memory_summary(user_id: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "select summary from memory_summaries where user_id=$1",
            user_id
        )
        return row["summary"] if row else ""

async def save_memory_summary(user_id: str, summary: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            insert into memory_summaries (user_id, summary, updated_at)
            values ($1, $2, now())
            on conflict (user_id)
            do update set
              summary = excluded.summary,
              updated_at = excluded.updated_at
            """,
            user_id,
            summary
        )
