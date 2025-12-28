# profile_repo.py
from db import get_pool

async def get_profile(uid: str):
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            return await conn.fetchrow(
                "select summary, last_updated from user_profiles where user_id=$1",
                uid
            )
    except Exception as e:
        print("[DB WARN] get_profile failed:", e)
        return None


async def save_profile(uid: str, summary: str):
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                insert into user_profiles (user_id, summary, last_updated)
                values ($1, $2, now())
                on conflict (user_id)
                do update set
                    summary = excluded.summary,
                    last_updated = excluded.last_updated
                """,
                uid,
                summary
            )
    except Exception as e:
        print("[DB WARN] save_profile failed:", e)
