import asyncio
import json
import logging
import os
import signal
from datetime import datetime, timezone
from decimal import Decimal

import aio_pika
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from . import config
from .broker import connect_with_retry, declare_topology
from .domain import Operation, OperationType
from .models import Base
from .service import process_operation

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("worker")


def parse_operation(body: bytes) -> Operation:
    data = json.loads(body.decode("utf-8"))
    occurred_at = datetime.fromisoformat(data["occurred_at"])
    if occurred_at.tzinfo is None:
        occurred_at = occurred_at.replace(tzinfo=timezone.utc)
    return Operation(
        operation_id=data["operation_id"],
        type=OperationType(data["type"]),
        customer_id=data["customer_id"],
        store_id=data["store_id"],
        check_number=data["check_number"],
        occurred_at=occurred_at,
        amount=Decimal(str(data["amount"])) if data.get("amount") is not None else None,
        points=int(data["points"]) if data.get("points") is not None else None,
    )


async def init_database(engine):
    for attempt in range(1, 31):
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            return
        except Exception as exc:
            log.warning("БД недоступна (%s/30): %s", attempt, exc)
            await asyncio.sleep(2)
    raise RuntimeError("Не удалось подключиться к PostgreSQL")


async def handle_message(message, session_factory, events_exchange):
    try:
        op = parse_operation(message.body)
    except (ValueError, KeyError, TypeError, ArithmeticError) as exc:
        # Некорректное сообщение повторная доставка не исправит.
        log.error("Некорректное сообщение %s: %s", message.message_id, exc)
        await message.reject(requeue=False)
        return

    try:
        event = await process_operation(session_factory, op)          # commit
        await events_exchange.publish(                                # publisher confirm
            aio_pika.Message(
                body=json.dumps(event).encode("utf-8"),
                content_type="application/json",
                message_id=event["operation_id"],
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            ),
            routing_key="",
            mandatory=True,
        )
        await message.ack()                                           # только теперь ack
        log.info("Обработана %s: %s %+d, баланс %d (%s)", op.operation_id,
                 event["status"], event["points_delta"], event["balance_after"],
                 event["reject_reason"])
    except Exception:
        log.exception("Ошибка обработки %s, сообщение возвращается в очередь", op.operation_id)
        await asyncio.sleep(1)
        try:
            await message.nack(requeue=True)
        except Exception:
            log.exception("Не удалось вернуть сообщение в очередь")


async def main():
    engine = create_async_engine(config.DATABASE_URL, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    await init_database(engine)

    connection = await connect_with_retry(config.RABBITMQ_URL)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    async with connection:
        channel = await connection.channel(publisher_confirms=True, on_return_raises=True)
        await channel.set_qos(prefetch_count=1)
        queue, events_exchange = await declare_topology(channel)

        open(config.READY_FILE, "w").close()
        log.info("Worker готов, ожидание операций")

        async def consume():
            async with queue.iterator() as messages:
                async for message in messages:
                    await handle_message(message, session_factory, events_exchange)

        consumer = asyncio.create_task(consume())
        stopper = asyncio.create_task(stop.wait())
        await asyncio.wait({consumer, stopper}, return_when=asyncio.FIRST_COMPLETED)
        consumer.cancel()
        await asyncio.gather(consumer, return_exceptions=True)
    await engine.dispose()
    if os.path.exists(config.READY_FILE):
        os.remove(config.READY_FILE)


if __name__ == "__main__":
    asyncio.run(main())
