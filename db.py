# db.py
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable is not set!")

_pool = None
_init_lock = None


async def init_pool():
    """Initialize the connection pool and create tables on startup"""
    global _pool, _init_lock
    
    if _init_lock is None:
        import asyncio
        _init_lock = asyncio.Lock()
    
    async with _init_lock:
        if _pool is not None and not _pool._closed:
            return _pool
            
        try:
            print("[DB] Attempting to connect to database...")
            _pool = await asyncpg.create_pool(
                DATABASE_URL,
                min_size=1,
                max_size=20,
                timeout=30,
                command_timeout=30,
                max_inactive_connection_lifetime=300,
                statement_cache_size=0,
                ssl="require"
            )
            
            print("[DB] Connection pool created, initializing tables...")
            
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
            
            print("[DB] ✓ Pool created successfully and tables initialized.")
            return _pool
            
        except Exception as e:
            print(f"[DB CRITICAL ERROR] Failed to initialize database: {e}")
            print(f"[DB DEBUG] DATABASE_URL exists: {bool(DATABASE_URL)}")
            if DATABASE_URL:
                # Don't print full URL for security, just show if it's formatted correctly
                print(f"[DB DEBUG] URL format check: starts with 'postgres': {DATABASE_URL.startswith('postgres')}")
            _pool = None
            raise


async def get_pool():
    """Get the connection pool, initializing if necessary"""
    global _pool
    if _pool is None or _pool._closed:
        return await init_pool()
    return _pool


async def close_pool():
    """Close the connection pool gracefully"""
    global _pool
    if _pool is not None:
        try:
            await _pool.close()
            print("[DB] Connection pool closed")
        except Exception as e:
            print(f"[DB ERROR] Error closing pool: {e}")
        finally:
            _pool = None
