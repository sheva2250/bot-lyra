# db.py
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

    if _pool is not None:
        return _pool

    async with _lock:
        if _pool is not None:
            return _pool

        for attempt in range(5):
            try:
                _pool = await asyncpg.create_pool(
                    DATABASE_URL,
                    min_size=1,
                    max_size=5,
                    ssl="require",
                    statement_cache_size=0,
                    timeout=10
                )
                print("[DB] Pool connected")
                return _pool

            except Exception as e:
                print(f"[DB] Connect failed ({attempt+1}/5): {e}")
                await asyncio.sleep(2)

        raise RuntimeError("Database unreachable after retries")
