import asyncio
import json
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from . import config
from .broker import connect_with_retry, declare_events_queue
from .logic import StoreStats, apply_event

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("analytics")

stores: dict[str, StoreStats] = {}
stats = {"events_received": 0}


async def consume_events(queue):
    async with queue.iterator() as messages:
        async for message in messages:
            try:
                event = json.loads(message.body.decode("utf-8"))
                apply_event(stores, event)
                stats["events_received"] += 1
            except (ValueError, KeyError, TypeError) as exc:
                log.error("Некорректное событие: %s", exc)
                await message.reject(requeue=False)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("Ошибка обработки события")
                await message.reject(requeue=False)
            else:
                await message.ack()          # после обработки


def _log_task_result(task: asyncio.Task):
    if not task.cancelled() and task.exception() is not None:
        log.error("Фоновая задача остановилась", exc_info=task.exception())


@asynccontextmanager
async def lifespan(app: FastAPI):
    connection = await connect_with_retry(config.RABBITMQ_URL)
    channel = await connection.channel()
    await channel.set_qos(prefetch_count=1)
    queue = await declare_events_queue(channel)
    task = asyncio.create_task(consume_events(queue))     # не блокирует HTTP
    task.add_done_callback(_log_task_result)
    try:
        yield
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await connection.close()


app = FastAPI(title="Analytics", lifespan=lifespan)


@app.get("/stores")
async def list_stores():
    return [stores[k].to_dict() for k in sorted(stores)]


@app.get("/stores/{store_id}")
async def get_store(store_id: str):
    if store_id not in stores:
        raise HTTPException(status_code=404, detail="Нет событий по магазину")
    return stores[store_id].to_dict()


@app.get("/stats")
async def get_stats():
    return stats
