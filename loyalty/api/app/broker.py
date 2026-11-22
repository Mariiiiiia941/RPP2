import asyncio
import json
import logging

import aio_pika

from . import config

log = logging.getLogger("api.broker")


class BrokerUnavailable(Exception):
    pass


class Broker:
    def __init__(self, url: str):
        self.url = url
        self.connection = None
        self.channel = None
        self.exchange = None

    async def connect(self, attempts: int = 30, delay: float = 2.0):
        for attempt in range(1, attempts + 1):
            try:
                self.connection = await aio_pika.connect_robust(self.url)
                break
            except Exception as exc:
                log.warning("RabbitMQ недоступен (%s/%s): %s", attempt, attempts, exc)
                await asyncio.sleep(delay)
        else:
            raise RuntimeError("Не удалось подключиться к RabbitMQ")

        self.channel = await self.connection.channel(
            publisher_confirms=True, on_return_raises=True
        )
        self.exchange = await self.channel.declare_exchange(
            config.OPERATIONS_EXCHANGE, aio_pika.ExchangeType.DIRECT, durable=True
        )
        queue = await self.channel.declare_queue(
            config.OPERATIONS_QUEUE, durable=True, arguments={"x-queue-type": "quorum"}
        )
        await queue.bind(self.exchange, routing_key=config.OPERATIONS_KEY)

    async def close(self):
        if self.connection is not None:
            await self.connection.close()

    def is_alive(self) -> bool:
        return (
            self.connection is not None
            and not self.connection.is_closed
            and self.channel is not None
            and not self.channel.is_closed
        )

    async def publish_operation(self, payload: dict):
        message = aio_pika.Message(
            body=json.dumps(payload).encode("utf-8"),
            content_type="application/json",
            message_id=payload["operation_id"],
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        )
        try:
            # С publisher_confirms=True await возвращается после подтверждения брокера.
            await self.exchange.publish(
                message,
                routing_key=config.OPERATIONS_KEY,
                mandatory=True,
                timeout=config.PUBLISH_TIMEOUT,
            )
        except Exception as exc:  # нет подтверждения, обрыв, возврат mandatory и т. д.
            log.error("Публикация %s не подтверждена: %r", payload["operation_id"], exc)
            raise BrokerUnavailable(str(exc)) from exc
