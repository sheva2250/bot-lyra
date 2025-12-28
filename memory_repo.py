# memory_repo.py
from db import get_pool

MAX_HISTORY = 10

async def load_history(user_id: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            select role, content
            from conversation_history
            where user_id = $1
            order by created_at asc
            limit $2
            """,
            user_id,
            MAX_HISTORY * 2
        )

    return [
        {"role": r["role"], "parts": [{"text": r["content"]}]}
        for r in rows
    ]


async def append_message(user_id: str, role: str, content: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            insert into conversation_history (user_id, role, content)
            values ($1, $2, $3)
            """,
            user_id,
            role,
            content
        )


async def trim_history(user_id: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            delete from conversation_history
            where id not in (
                select id from conversation_history
                where user_id = $1
                order by created_at desc
                limit $2
            )
            and user_id = $1
            """,
            user_id,
            MAX_HISTORY * 2
        )

async def delete_old_history(user_id: str, keep_last: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            delete from conversation_history
            where user_id = $1
            and id not in (
                select id from conversation_history
                where user_id = $1
                order by created_at desc
                limit $2
            )
            """,
            user_id,
            keep_last
        )