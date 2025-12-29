# memory_repo.py
from db import get_pool

MAX_HISTORY = 10
MAX_ROWS = MAX_HISTORY * 2

async def load_history(uid: str):
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT role, content
                FROM conversation_history
                WHERE user_id = $1
                ORDER BY created_at DESC
                LIMIT $2
                """,
                uid,
                MAX_ROWS
            )
        rows_reversed = list(reversed(rows))

        return [
            {"role": r["role"], "parts": [{"text": r["content"]}]}
            for r in rows_reversed
        ]

    except Exception as e:
        print("[DB WARN] load_history failed:", e)
        return []


async def append_message(uid: str, role: str, content: str):
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO conversation_history (user_id, role, content)
                VALUES ($1, $2, $3)
                """,
                uid,
                role,
                content
            )
    except Exception as e:
        print("[DB WARN] append_message failed:", e)


async def trim_history_if_needed(uid: str):
    """
    Trim HANYA jika jumlah row > MAX_ROWS
    """
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            count = await conn.fetchval(
                "SELECT count(*) FROM conversation_history WHERE user_id=$1",
                uid
            )

            if count <= MAX_ROWS:
                return

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
                uid,
                MAX_ROWS
            )

    except Exception as e:
        print("[DB WARN] trim_history failed:", e)


async def delete_old_history(uid: str, keep_last: int):
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
                uid,
                keep_last
            )
    except Exception as e:
        print("[DB WARN] delete_old_history failed:", e)
