# db.py
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
_pool = None


async def init_pool():
    """
    Initialize asyncpg pool safely.
    Return None if connection fails (fail-soft).
    """
    global _pool

    if _pool is not None and not _pool._closed:
        return _pool

    try:
        _pool = await asyncpg.create_pool(
            DATABASE_URL,
            min_size=1,
            max_size=5,

            # PgBouncer compatibility
            statement_cache_size=0,

            # Timeouts
            command_timeout=15,
            timeout=15,

            # SSL (Supabase)
            ssl="require",
        )
        print("[DB] Pool initialized")
        return _pool

    except Exception as e:
        print("[DB ERROR] init_pool failed:", e)
        _pool = None
        return None


async def get_pool():
    global _pool
    if _pool is None or _pool._closed:
        return await init_pool()
    return _pool


async def close_pool():
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
        print("[DB] Pool closed")
