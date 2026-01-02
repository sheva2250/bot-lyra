# profile_repo.py
from db import get_pool


async def get_profile(user_id: str):
    pool = await get_pool()
    if pool is None:
        return None

    try:
        async with pool.acquire() as conn:
            return await conn.fetchrow(
                "SELECT summary, last_updated FROM user_profiles WHERE user_id=$1",
                user_id
            )
    except Exception as e:
        print("[DB WARN] get_profile:", e)
        return None


async def save_profile(user_id: str, summary: str):
    pool = await get_pool()
    if pool is None:
        return

    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO user_profiles (user_id, summary, last_updated)
            VALUES ($1, $2, NOW())
            ON CONFLICT (user_id)
            DO UPDATE SET
                summary = EXCLUDED.summary,
                last_updated = EXCLUDED.last_updated
            """,
            user_id,
            summary
        )
