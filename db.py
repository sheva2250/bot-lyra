# db.py
import asyncpg
import os
import asyncio

DATABASE_URL = os.getenv("DATABASE_URL")
_pool = None
_pool_lock = asyncio.Lock()

async def get_pool():
    global _pool
    if _pool:
        return _pool

    async with _pool_lock:
        if _pool:
            return _pool

        for attempt in range(3):
            try:
                _pool = await asyncpg.create_pool(
                    DATABASE_URL,
                    min_size=1,
                    max_size=5,
                    timeout=10,
                    ssl="require",
                    statement_cache_size=0
                )
                return _pool
            except Exception as e:
                if attempt == 2:
                    raise
                await asyncio.sleep(2)
