from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, DateTime, Index, Numeric, String, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Account(Base):
    __tablename__ = "accounts"

    customer_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    balance: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)


class OperationRow(Base):
    __tablename__ = "operations"

    operation_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    customer_id: Mapped[str] = mapped_column(String(64), nullable=False)
    store_id: Mapped[str] = mapped_column(String(64), nullable=False)
    check_number: Mapped[str] = mapped_column(String(64), nullable=False)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    points_delta: Mapped[int] = mapped_column(BigInteger, nullable=False)
    balance_after: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    reject_reason: Mapped[str | None] = mapped_column(String(32))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_operations_customer_processed", "customer_id", "processed_at"),
        Index("ix_operations_check", "check_number", "type"),
        # Не более одной принятой покупки и одного принятого возврата на чек.
        Index(
            "uq_applied_purchase_check", "check_number", unique=True,
            postgresql_where=text("type = 'purchase' AND status = 'applied'"),
        ),
        Index(
            "uq_applied_return_check", "check_number", unique=True,
            postgresql_where=text("type = 'return' AND status = 'applied'"),
        ),
    )
