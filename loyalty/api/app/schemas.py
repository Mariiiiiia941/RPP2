from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Annotated

from pydantic import BaseModel, Field, StrictInt, model_validator

IdStr = Annotated[str, Field(min_length=1, max_length=64)]


class OperationType(str, Enum):
    PURCHASE = "purchase"
    RETURN = "return"
    REDEEM = "redeem"


class OperationIn(BaseModel):
    """Формат операции кассы (раздел I). Бизнес-правил здесь нет."""

    operation_id: IdStr
    type: OperationType
    customer_id: IdStr
    store_id: IdStr
    check_number: IdStr
    occurred_at: datetime
    amount: Decimal | None = None
    points: StrictInt | None = None

    @model_validator(mode="after")
    def check_format(self):
        if self.type in (OperationType.PURCHASE, OperationType.REDEEM):
            if self.amount is None:
                raise ValueError("amount обязательно для purchase и redeem")
            if self.amount <= 0:
                raise ValueError("amount должно быть положительным")
            if self.amount.as_tuple().exponent < -2 or self.amount >= Decimal(10) ** 12:
                raise ValueError("amount: не более 2 знаков после запятой, не более 12 цифр")
        elif self.amount is not None:
            raise ValueError("в возврате поле amount отсутствует")

        if self.type is OperationType.REDEEM:
            if self.points is None:
                raise ValueError("points обязательно для redeem")
            if self.points <= 0:
                raise ValueError("points должно быть положительным")
        elif self.points is not None:
            raise ValueError("points допускается только в redeem")

        if self.occurred_at.tzinfo is None:
            self.occurred_at = self.occurred_at.replace(tzinfo=timezone.utc)
        return self


class Accepted(BaseModel):
    operation_id: str


class OperationResult(BaseModel):
    operation_id: str
    type: str
    customer_id: str
    store_id: str
    status: str
    points_delta: int
    balance_after: int
    reject_reason: str | None
    processed_at: datetime


class AccountOut(BaseModel):
    customer_id: str
    balance: int
    operations: list[OperationResult]
