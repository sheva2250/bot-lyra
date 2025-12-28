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
        try:
            _pool = await asyncpg.create_pool(
                DATABASE_URL,
                min_size=1,
                max_size=5,
                
                timeout=10,
                command_timeout=10,
                
                # CONN LIFETIME
                max_inactive_connection_lifetime=300,
                
                # SSL
                ssl="require",
                
                # TCP Keepalives (Biar koneksi gak diputus diem-diem sama firewall)
                server_settings={
                    "application_name": "LyraBot",
                    # Paksa kirim sinyal 'ping' TCP tiap 10 detik
                    "tcp_keepalives_idle": "10", 
                    "tcp_keepalives_interval": "5",
                    "tcp_keepalives_count": "3"
                }
            )
            print("[DB] Pool created successfully with aggressive timeouts.")
        except Exception as e:
            print(f"[DB CRITICAL ERROR] Gagal connect ke Supabase: {e}")
            # Biarkan _pool None, nanti error akan ditangkap di bot-main.py
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
