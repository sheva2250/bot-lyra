import asyncio
from db import get_pool

_db_queue: asyncio.Queue = asyncio.Queue()
_worker_started = False

async def start_db_worker():
    global _worker_started
    if _worker_started:
        return
    _worker_started = True
    asyncio.create_task(_db_worker())
    print("[DB QUEUE] Worker started")

async def enqueue_db_write(query: str, *args):
    await _db_queue.put((query, args))

async def _db_worker():
    while True:
        query, args = await _db_queue.get()
        try:
            pool = await get_pool()
            if pool is None:
                raise RuntimeError("DB pool not ready")

            async with pool.acquire() as conn:
                await conn.execute(query, *args)

        except Exception as e:
            print("[DB QUEUE ERROR]", e)
            # retry dengan delay ringan
            await asyncio.sleep(2)
            await _db_queue.put((query, args))

        finally:
            _db_queue.task_done()
