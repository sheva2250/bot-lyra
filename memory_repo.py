# memory_repo.py
from db import get_pool

MAX_HISTORY = 10


async def load_history(user_id: str):
    pool = await get_pool()
    if pool is None:
        return []

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT role, content
            FROM conversation_history
            WHERE user_id = $1
            ORDER BY created_at ASC
            LIMIT $2
            """,
            user_id,
            MAX_HISTORY * 2
        )

    return [
        {"role": r["role"], "content": r["content"]}
        for r in rows
    ]


async def append_message(user_id: str, role: str, content: str):
    pool = await get_pool()
    if pool is None:
        return

    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO conversation_history (user_id, role, content)
            VALUES ($1, $2, $3)
            """,
            user_id,
            role,
            content
        )


async def delete_old_history(user_id: str, keep_last: int):
    pool = await get_pool()
    if pool is None:
        return

    async with pool.acquire() as conn:
        await conn.execute(
            """
            DELETE FROM conversation_history
            WHERE user_id = $1
              AND id NOT IN (
                SELECT id FROM conversation_history
                WHERE user_id = $1
                ORDER BY created_at DESC
                LIMIT $2
              )
            """,
            user_id,
            keep_last
        )
