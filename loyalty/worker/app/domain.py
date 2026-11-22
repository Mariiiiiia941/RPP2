"""Доменный слой: расчёт баллов бонусной программы.

Модуль не импортирует aio-pika и SQLAlchemy и не обращается к базе данных:
все необходимые факты (баланс, найденная покупка и т. д.) передаются
в функцию decide() готовыми значениями.
"""
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_FLOOR, Decimal
from enum import Enum

ACCRUAL_RATE = Decimal("0.05")        # 5 % от суммы чека
REDEEM_LIMIT_RATE = Decimal("0.30")   # не более 30 % суммы чека


class OperationType(str, Enum):
    PURCHASE = "purchase"
    RETURN = "return"
    REDEEM = "redeem"


class Status(str, Enum):
    APPLIED = "applied"
    REJECTED = "rejected"


class RejectReason(str, Enum):
    DUPLICATE_PURCHASE = "duplicate_purchase"
    PURCHASE_NOT_FOUND = "purchase_not_found"
    CUSTOMER_MISMATCH = "customer_mismatch"
    ALREADY_RETURNED = "already_returned"
    LIMIT_EXCEEDED = "limit_exceeded"
    INSUFFICIENT_BALANCE = "insufficient_balance"


@dataclass(frozen=True)
class Operation:
    operation_id: str
    type: OperationType
    customer_id: str
    store_id: str
    check_number: str
    occurred_at: datetime
    amount: Decimal | None = None
    points: int | None = None


@dataclass(frozen=True)
class PurchaseInfo:
    """Принятая ранее покупка."""
    customer_id: str
    points_awarded: int


@dataclass(frozen=True)
class Outcome:
    status: Status
    points_delta: int
    balance_after: int
    reject_reason: RejectReason | None = None


def calculate_accrual(amount: Decimal) -> int:
    """5 % от суммы чека, дробная часть отбрасывается."""
    return int((amount * ACCRUAL_RATE).to_integral_value(rounding=ROUND_FLOOR))


def _reject(balance: int, reason: RejectReason) -> Outcome:
    return Outcome(Status.REJECTED, 0, balance, reason)


def _apply(balance: int, delta: int) -> Outcome:
    # Баланс может уйти в минус; следующие начисления сначала погашают долг,
    # поскольку просто прибавляются к отрицательному балансу.
    return Outcome(Status.APPLIED, delta, balance + delta)


def decide(
    op: Operation,
    balance: int,
    purchase: PurchaseInfo | None,
    return_exists: bool,
) -> Outcome:
    """Применить операцию к текущему балансу.

    purchase      - принятая покупка с номером op.check_number (или None);
    return_exists - по этой покупке уже был принятый возврат.
    Причины отказа проверяются в порядке таблицы 3.
    """
    if op.type is OperationType.PURCHASE:
        if purchase is not None:
            return _reject(balance, RejectReason.DUPLICATE_PURCHASE)
        return _apply(balance, calculate_accrual(op.amount))

    if op.type is OperationType.RETURN:
        if purchase is None:
            return _reject(balance, RejectReason.PURCHASE_NOT_FOUND)
        if purchase.customer_id != op.customer_id:
            return _reject(balance, RejectReason.CUSTOMER_MISMATCH)
        if return_exists:
            return _reject(balance, RejectReason.ALREADY_RETURNED)
        return _apply(balance, -purchase.points_awarded)

    # REDEEM
    if Decimal(op.points) > op.amount * REDEEM_LIMIT_RATE:
        return _reject(balance, RejectReason.LIMIT_EXCEEDED)
    if op.points > balance:
        return _reject(balance, RejectReason.INSUFFICIENT_BALANCE)
    return _apply(balance, -op.points)
