from db import get_pool

async def get_profile(user_id: str):
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            return await conn.fetchrow(
                """
                SELECT summary, last_updated
                FROM user_profiles
                WHERE user_id = $1
                """,
                user_id
            )
    except Exception as e:
        print("[DB WARN] get_profile:", e)
        return None


async def save_profile(user_id: str, summary: str):
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO user_profiles (user_id, summary, last_updated)
                VALUES ($1, $2, now())
                ON CONFLICT (user_id)
                DO UPDATE SET
                  summary = excluded.summary,
                  last_updated = excluded.last_updated
                """,
                user_id,
                summary
            )
    except Exception as e:
        print("[DB WARN] save_profile:", e)


async def get_memory_summary(user_id: str):
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT summary FROM memory_summaries WHERE user_id = $1",
                user_id
            )
            return row["summary"] if row else ""
    except Exception as e:
        print("[DB WARN] get_memory_summary:", e)
        return ""


async def save_memory_summary(user_id: str, summary: str):
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO memory_summaries (user_id, summary, updated_at)
                VALUES ($1, $2, now())
                ON CONFLICT (user_id)
                DO UPDATE SET
                  summary = excluded.summary,
                  updated_at = excluded.updated_at
                """,
                user_id,
                summary
            )
    except Exception as e:
        print("[DB WARN] save_memory_summary:", e)
