from db import get_pool
from db_queue import enqueue

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

        rows.reverse()
        return [{"role": r["role"], "content": r["content"]} for r in rows]

    except Exception as e:
        print("[DB WARN] load_history failed:", e)
        return []


async def append_message(uid: str, role: str, content: str):
    await enqueue(
        """
        INSERT INTO conversation_history (user_id, role, content)
        VALUES ($1, $2, $3)
        """,
        uid,
        role,
        content
    )


async def trim_history_if_needed(uid: str):
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            count = await conn.fetchval(
                "SELECT count(*) FROM conversation_history WHERE user_id=$1",
                uid
            )

        if count <= MAX_ROWS:
            return

        await enqueue(
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
    await enqueue(
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
