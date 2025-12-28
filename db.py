# db.py
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()  # ← INI KUNCINYA

DATABASE_URL = os.getenv("DATABASE_URL")
print("[DB DEBUG] DATABASE_URL =", DATABASE_URL)

_pool = None

async def get_pool():
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            DATABASE_URL,
            min_size=1,
            max_size=5,
            ssl="require",
            statement_cache_size=0
        )
    return _pool
