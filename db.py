import asyncpg
import os
import asyncio
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

_pool = None
_lock = asyncio.Lock()

async def get_pool():
    global _pool

    if _pool:
        return _pool

    async with _lock:
        if _pool:
            return _pool

        _pool = await asyncpg.create_pool(
            DATABASE_URL,
            min_size=1,
            max_size=3,
            ssl="require",
            statement_cache_size=0,
            command_timeout=30,
            timeout=30
        )
        return _pool


async def close_pool():
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
