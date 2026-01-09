from db import get_pool
from db_queue import enqueue

async def get_profile(uid: str):
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            return await conn.fetchrow(
                "SELECT summary, last_updated FROM user_profiles WHERE user_id=$1",
                uid
            )
    except Exception as e:
        print("[DB WARN] get_profile failed:", e)
        return None


async def save_profile(uid: str, summary: str):
    await enqueue(
        """
        INSERT INTO user_profiles (user_id, summary, last_updated)
        VALUES ($1, $2, now())
        ON CONFLICT (user_id)
        DO UPDATE SET
            summary = excluded.summary,
            last_updated = excluded.last_updated
        """,
        uid,
        summary
    )
