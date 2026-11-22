import asyncio
import logging

import aio_pika

log = logging.getLogger("notifier.broker")

EVENTS_EXCHANGE = "loyalty.events"
EVENTS_QUEUE = "notifier.events"


async def connect_with_retry(url: str, attempts: int = 30, delay: float = 2.0):
    for attempt in range(1, attempts + 1):
        try:
            return await aio_pika.connect_robust(url)
        except Exception as exc:
            log.warning("RabbitMQ недоступен (%s/%s): %s", attempt, attempts, exc)
            await asyncio.sleep(delay)
    raise RuntimeError("Не удалось подключиться к RabbitMQ")


async def declare_events_queue(channel):
    """Те же параметры, что и в worker: не зависим от порядка запуска."""
    exchange = await channel.declare_exchange(
        EVENTS_EXCHANGE, aio_pika.ExchangeType.FANOUT, durable=True
    )
    queue = await channel.declare_queue(
        EVENTS_QUEUE, durable=True, arguments={"x-queue-type": "quorum"}
    )
    await queue.bind(exchange)
    return queue
