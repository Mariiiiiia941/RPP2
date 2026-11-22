import asyncio
import logging

import aio_pika
from aio_pika.abc import AbstractRobustChannel

from . import config

log = logging.getLogger("worker.broker")


async def connect_with_retry(url: str, attempts: int = 30, delay: float = 2.0):
    for attempt in range(1, attempts + 1):
        try:
            return await aio_pika.connect_robust(url)
        except Exception as exc:  # брокер ещё не готов
            log.warning("RabbitMQ недоступен (%s/%s): %s", attempt, attempts, exc)
            await asyncio.sleep(delay)
    raise RuntimeError("Не удалось подключиться к RabbitMQ")


async def declare_topology(channel: AbstractRobustChannel):
    """Объявить всё, что нужно worker: операции (direct) и события (fanout)."""
    ops_exchange = await channel.declare_exchange(
        config.OPERATIONS_EXCHANGE, aio_pika.ExchangeType.DIRECT, durable=True
    )
    ops_queue = await channel.declare_queue(
        config.OPERATIONS_QUEUE, durable=True, arguments={"x-queue-type": "quorum"}
    )
    await ops_queue.bind(ops_exchange, routing_key=config.OPERATIONS_KEY)

    events_exchange = await channel.declare_exchange(
        config.EVENTS_EXCHANGE, aio_pika.ExchangeType.FANOUT, durable=True
    )
    for name in config.EVENT_QUEUES:
        q = await channel.declare_queue(
            name, durable=True, arguments={"x-queue-type": "quorum"}
        )
        await q.bind(events_exchange)
    return ops_queue, events_exchange
