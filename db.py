# db.py
import asyncpg
import os
import ssl
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

_pool: asyncpg.Pool | None = None


async def init_pool() -> asyncpg.Pool:
    """
    Initialize asyncpg connection pool.
    """
    global _pool

    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not set")

    if _pool is not None:
        return _pool

    try:
        ssl_ctx = ssl.create_default_context()

        _pool = await asyncpg.create_pool(
            dsn=DATABASE_URL,
            min_size=1,
            max_size=20,
            timeout=10,
            command_timeout=10,
            max_inactive_connection_lifetime=300,
            statement_cache_size=0,
            ssl=ssl_ctx,
            server_settings={
                "application_name": "LyraBot",
                "tcp_keepalives_idle": "10",
                "tcp_keepalives_interval": "5",
                "tcp_keepalives_count": "3",
            },
        )

        print("[DB] Pool initialized successfully")
        return _pool

    except Exception as e:
        _pool = None
        print(f"[DB FATAL] Failed to initialize pool: {e}")
        raise


async def get_pool() -> asyncpg.Pool:
    """
    Always returns a valid pool or raises.
    """
    global _pool

    if _pool is None:
        return await init_pool()

    if getattr(_pool, "_closed", False):
        _pool = None
        return await init_pool()

    return _pool

async def close_pool():
    """
    Graceful shutdown.
    """
    global _pool

    if _pool is not None:
        await _pool.close()
        _pool = None
        print("[DB] Pool closed")
