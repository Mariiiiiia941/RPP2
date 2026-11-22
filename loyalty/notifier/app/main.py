import asyncio
import json
import logging
import random
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Query

from . import config
from .broker import connect_with_retry, declare_events_queue
from .logic import build_text

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("notifier")

notifications: list[dict] = []
stats = {"events_received": 0, "notifications_sent": 0}


async def handle_event(event: dict):
    customer_id = event["customer_id"]
    if customer_id in config.UNSUBSCRIBED:
        stats["events_received"] += 1
        log.info("Покупатель %s отписан, уведомление не отправляется", customer_id)
        return
    text = build_text(event)
    await asyncio.sleep(random.uniform(config.MIN_DELAY_MS, config.MAX_DELAY_MS) / 1000)
    log.info("Уведомление для %s: %s", customer_id, text)
    notifications.append({
        "customer_id": customer_id,
        "operation_id": event["operation_id"],
        "text": text,
        "sent_at": datetime.now(timezone.utc).isoformat(),
    })
    stats["events_received"] += 1
    stats["notifications_sent"] += 1


async def consume_events(queue):
    async with queue.iterator() as messages:
        async for message in messages:
            try:
                event = json.loads(message.body.decode("utf-8"))
                await handle_event(event)
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


app = FastAPI(title="Notifier", lifespan=lifespan)


@app.get("/notifications")
async def get_notifications(customer_id: str = Query(...)):
    return [n for n in notifications if n["customer_id"] == customer_id]


@app.get("/stats")
async def get_stats():
    return stats
