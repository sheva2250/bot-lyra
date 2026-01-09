import asyncio
from db import get_pool

_write_queue: asyncio.Queue | None = None
_worker_task: asyncio.Task | None = None

async def init_db_queue():
    global _write_queue, _worker_task
    if _write_queue is None:
        _write_queue = asyncio.Queue(maxsize=1000)
        _worker_task = asyncio.create_task(_worker())
        print("[DB QUEUE] Worker started")

async def enqueue(sql: str, *args):
    if _write_queue is None:
        raise RuntimeError("DB queue not initialized")
    await _write_queue.put((sql, args))

async def _worker():
    while True:
        sql, args = await _write_queue.get()
        try:
            pool = await get_pool()
            async with pool.acquire() as conn:
                await conn.execute(sql, *args)
        except Exception as e:
            print("[DB QUEUE ERROR]", e)
        finally:
            _write_queue.task_done()
