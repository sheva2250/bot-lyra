# db.py
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
_pool = None

async def init_pool():
    """Initialize the connection pool on startup"""
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            DATABASE_URL,
            min_size=2,
            max_size=10,  # Increased from 3
            timeout=60,  # Increased timeout
            command_timeout=60,
            ssl="require",
            statement_cache_size=0,
            max_inactive_connection_lifetime=300  # Close idle connections after 5 min
        )
    return _pool

async def get_pool():
    """Get or create the connection pool"""
    global _pool
    if _pool is None:
        _pool = await init_pool()
    return _pool

async def close_pool():
    """Close the connection pool gracefully"""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
