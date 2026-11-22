"""Прикладной слой: обработка операции в одной транзакции БД."""
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from . import domain
from .domain import Operation, OperationType, PurchaseInfo, Status
from .models import Account, OperationRow


def event_from_row(row: OperationRow) -> dict:
    """Событие «операция обработана» (формат раздела III)."""
    return {
        "operation_id": row.operation_id,
        "type": row.type,
        "customer_id": row.customer_id,
        "store_id": row.store_id,
        "status": row.status,
        "points_delta": row.points_delta,
        "balance_after": row.balance_after,
        "reject_reason": row.reject_reason,
        "processed_at": row.processed_at.isoformat(),
    }


async def process_operation(
    session_factory: async_sessionmaker[AsyncSession], op: Operation
) -> dict:
    """Рассчитать баллы, сохранить операцию и изменить баланс (одна транзакция).

    Если операция с таким номером уже обработана (повторная доставка после
    сбоя между фиксацией и ack), заново она не применяется, возвращается
    событие по сохранённой записи.
    """
    async with session_factory() as session:
        async with session.begin():
            existing = await session.get(OperationRow, op.operation_id)
            if existing is not None:
                return event_from_row(existing)

            # Счёт создаётся при первой операции покупателя.
            await session.execute(
                pg_insert(Account)
                .values(customer_id=op.customer_id, balance=0)
                .on_conflict_do_nothing()
            )
            account = (
                await session.execute(
                    select(Account)
                    .where(Account.customer_id == op.customer_id)
                    .with_for_update()
                )
            ).scalar_one()

            purchase = None
            return_exists = False
            if op.type in (OperationType.PURCHASE, OperationType.RETURN):
                prow = (
                    await session.execute(
                        select(OperationRow).where(
                            OperationRow.check_number == op.check_number,
                            OperationRow.type == OperationType.PURCHASE.value,
                            OperationRow.status == Status.APPLIED.value,
                        )
                    )
                ).scalar_one_or_none()
                if prow is not None:
                    purchase = PurchaseInfo(prow.customer_id, prow.points_delta)
            if op.type is OperationType.RETURN and purchase is not None:
                return_exists = (
                    await session.execute(
                        select(OperationRow.operation_id).where(
                            OperationRow.check_number == op.check_number,
                            OperationRow.type == OperationType.RETURN.value,
                            OperationRow.status == Status.APPLIED.value,
                        )
                    )
                ).first() is not None

            outcome = domain.decide(op, account.balance, purchase, return_exists)

            row = OperationRow(
                operation_id=op.operation_id,
                type=op.type.value,
                customer_id=op.customer_id,
                store_id=op.store_id,
                check_number=op.check_number,
                amount=op.amount,
                points_delta=outcome.points_delta,
                balance_after=outcome.balance_after,
                status=outcome.status.value,
                reject_reason=outcome.reject_reason.value if outcome.reject_reason else None,
                occurred_at=op.occurred_at,
                processed_at=datetime.now(timezone.utc),
            )
            session.add(row)
            account.balance = outcome.balance_after
            await session.flush()
            return event_from_row(row)
