import asyncpg
import asyncio
import os
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

        for attempt in range(5):
            try:
                _pool = await asyncpg.create_pool(
                    DATABASE_URL,
                    min_size=1,
                    max_size=3,
                    ssl="require",
                    statement_cache_size=0,
                    command_timeout=30,
                )
                print("[DB] Connected")
                return _pool

            except Exception as e:
                print(f"[DB] Connect failed ({attempt+1}/5):", e)
                await asyncio.sleep(2)

        raise RuntimeError("Database unavailable after retries")
