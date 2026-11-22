import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "worker"))

from app.domain import (  # noqa: E402
    Operation, OperationType as T, PurchaseInfo, RejectReason as R, Status,
    calculate_accrual, decide,
)

NOW = datetime(2026, 11, 10, tzinfo=timezone.utc)


def op(t, amount=None, points=None, customer="C1", check="CH1"):
    return Operation("op", t, customer, "S1", check, NOW,
                     Decimal(amount) if amount is not None else None, points)


@pytest.mark.parametrize("amount,expected", [
    ("2490.00", 124), ("100.00", 5), ("19.99", 0), ("20.00", 1), ("0.01", 0), ("39.99", 1),
])
def test_accrual_floor(amount, expected):
    assert calculate_accrual(Decimal(amount)) == expected


def test_purchase_applied():
    r = decide(op(T.PURCHASE, "2490.00"), 1406, None, False)
    assert (r.status, r.points_delta, r.balance_after, r.reject_reason) == (Status.APPLIED, 124, 1530, None)


def test_purchase_duplicate():
    r = decide(op(T.PURCHASE, "100"), 10, PurchaseInfo("C2", 5), False)
    assert r.status is Status.REJECTED and r.reject_reason is R.DUPLICATE_PURCHASE
    assert r.points_delta == 0 and r.balance_after == 10


def test_return_applied_and_debt():
    r = decide(op(T.RETURN), 30, PurchaseInfo("C1", 124), False)
    assert r.status is Status.APPLIED and r.points_delta == -124 and r.balance_after == -94


def test_debt_is_repaid_by_next_accrual():
    r = decide(op(T.PURCHASE, "1000"), -94, None, False)
    assert r.points_delta == 50 and r.balance_after == -44


def test_return_reasons_order():
    assert decide(op(T.RETURN), 0, None, True).reject_reason is R.PURCHASE_NOT_FOUND
    assert decide(op(T.RETURN), 0, PurchaseInfo("C2", 5), True).reject_reason is R.CUSTOMER_MISMATCH
    assert decide(op(T.RETURN), 0, PurchaseInfo("C1", 5), True).reject_reason is R.ALREADY_RETURNED


def test_redeem_limit_boundary():
    assert decide(op(T.REDEEM, "1000", 300), 500, None, False).status is Status.APPLIED
    r = decide(op(T.REDEEM, "1000", 301), 500, None, False)
    assert r.reject_reason is R.LIMIT_EXCEEDED


def test_redeem_limit_checked_before_balance():
    r = decide(op(T.REDEEM, "100", 50), 10, None, False)
    assert r.reject_reason is R.LIMIT_EXCEEDED


def test_redeem_insufficient_balance():
    r = decide(op(T.REDEEM, "1000", 100), 99, None, False)
    assert r.reject_reason is R.INSUFFICIENT_BALANCE and r.balance_after == 99


def test_redeem_negative_balance_rejected():
    assert decide(op(T.REDEEM, "1000", 1), -5, None, False).reject_reason is R.INSUFFICIENT_BALANCE


def test_redeem_applied():
    r = decide(op(T.REDEEM, "1000", 100), 100, None, False)
    assert r.points_delta == -100 and r.balance_after == 0
