from db import get_pool

MAX_HISTORY = 10

async def load_history(user_id: str):
    try:
        pool = await get_pool()
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
            {"role": r["role"], "parts": [{"text": r["content"]}]}
            for r in rows
        ]

    except Exception as e:
        print("[DB WARN] load_history:", e)
        return []


async def append_message(user_id: str, role: str, content: str):
    try:
        pool = await get_pool()
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
    except Exception as e:
        print("[DB WARN] append_message:", e)


async def trim_history(user_id: str):
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                DELETE FROM conversation_history
                WHERE id NOT IN (
                    SELECT id FROM conversation_history
                    WHERE user_id = $1
                    ORDER BY created_at DESC
                    LIMIT $2
                )
                AND user_id = $1
                """,
                user_id,
                MAX_HISTORY * 2
            )
    except Exception as e:
        print("[DB WARN] trim_history:", e)
