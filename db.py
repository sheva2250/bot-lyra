import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
_pool = None


async def init_pool():
    """Initialize the connection pool and create tables on startup"""
    global _pool
    if _pool is None:
        try:
            _pool = await asyncpg.create_pool(
                DATABASE_URL,
                min_size=1,
                max_size=20,
                timeout=10,
                command_timeout=10,
                max_inactive_connection_lifetime=300,
                statement_cache_size=0,
                ssl="require"
            )
            
            # Create tables if they don't exist
            async with _pool.acquire() as conn:
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS conversation_history (
                        id SERIAL PRIMARY KEY,
                        user_id TEXT NOT NULL,
                        role TEXT NOT NULL,
                        content TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT NOW()
                    );
                """)
                
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS memory_summaries (
                        user_id TEXT PRIMARY KEY,
                        summary TEXT,
                        updated_at TIMESTAMP DEFAULT NOW()
                    );
                """)
                
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS user_profiles (
                        user_id TEXT PRIMARY KEY,
                        summary TEXT,
                        last_updated TIMESTAMP DEFAULT NOW()
                    );
                """)
                
                await conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_conversation_user_time 
                    ON conversation_history(user_id, created_at DESC);
                """)
            
            print("[DB] Pool created successfully and tables initialized.")
        except Exception as e:
            print(f"[DB CRITICAL ERROR] Gagal connect ke Supabase: {e}")
            _pool = None
    return _pool


async def get_pool():
    global _pool
    if _pool is None or _pool._closed:
        _pool = await init_pool()
    return _pool


async def close_pool():
    """Close the connection pool gracefully"""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
