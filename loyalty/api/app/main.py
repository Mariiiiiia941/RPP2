import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from . import config
from .broker import Broker, BrokerUnavailable
from .models import Account, OperationRow
from .schemas import AccountOut, Accepted, OperationIn, OperationResult

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    engine = create_async_engine(config.DATABASE_URL, pool_pre_ping=True)
    app.state.engine = engine
    app.state.sessions = async_sessionmaker(engine, expire_on_commit=False)
    app.state.broker = Broker(config.RABBITMQ_URL)
    await app.state.broker.connect()
    try:
        yield
    finally:
        await app.state.broker.close()
        await engine.dispose()


app = FastAPI(title="Loyalty API", lifespan=lifespan)


def to_result(row: OperationRow) -> OperationResult:
    return OperationResult(
        operation_id=row.operation_id, type=row.type, customer_id=row.customer_id,
        store_id=row.store_id, status=row.status, points_delta=row.points_delta,
        balance_after=row.balance_after, reject_reason=row.reject_reason,
        processed_at=row.processed_at,
    )


@app.post("/operations", status_code=202, response_model=Accepted)
async def accept_operation(op: OperationIn):
    payload = op.model_dump(mode="json", exclude_none=True)
    try:
        await app.state.broker.publish_operation(payload)
    except BrokerUnavailable:
        raise HTTPException(status_code=503, detail="Брокер не подтвердил публикацию")
    return Accepted(operation_id=op.operation_id)


@app.get("/operations/{operation_id}", response_model=OperationResult)
async def get_operation(operation_id: str):
    async with app.state.sessions() as session:
        row = await session.get(OperationRow, operation_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Операция ещё не обработана")
    return to_result(row)


@app.get("/accounts/{customer_id}", response_model=AccountOut)
async def get_account(customer_id: str):
    async with app.state.sessions() as session:
        account = await session.get(Account, customer_id)
        if account is None:
            raise HTTPException(status_code=404, detail="Счёт не найден")
        rows = (
            await session.execute(
                select(OperationRow)
                .where(OperationRow.customer_id == customer_id)
                .order_by(OperationRow.processed_at.desc(), OperationRow.operation_id.desc())
                .limit(20)
            )
        ).scalars().all()
    return AccountOut(
        customer_id=account.customer_id,
        balance=account.balance,
        operations=[to_result(r) for r in rows],
    )


@app.get("/health")
async def health():
    db_ok = True
    try:
        async with app.state.engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        db_ok = False
    broker_ok = app.state.broker.is_alive()
    body = {
        "status": "ok" if db_ok and broker_ok else "unavailable",
        "database": "ok" if db_ok else "down",
        "broker": "ok" if broker_ok else "down",
    }
    return JSONResponse(body, status_code=200 if db_ok and broker_ok else 503)
