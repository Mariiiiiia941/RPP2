# Бонусная программа сети магазинов (лабораторная работа №5)

Микросервисы: `api` (FastAPI, :8000), `worker` (без веб-фреймворка), `notifier` (:8001), `analytics` (:8002),
`postgres:17`, `rabbitmq:4-management` (панель http://localhost:15672, логин/пароль из `.env`).

    docker compose up --build

Пример:

    curl -X POST localhost:8000/operations -H 'content-type: application/json' -d '{
      "operation_id":"S12-K03-000154","type":"purchase","customer_id":"C1042","store_id":"S12",
      "check_number":"S12-000154","amount":"2490.00","occurred_at":"2026-11-10T14:32:05+07:00"}'
    curl localhost:8000/operations/S12-K03-000154
    curl localhost:8000/accounts/C1042
    curl 'localhost:8001/notifications?customer_id=C1042'
    curl localhost:8002/stores

Тесты доменной логики: `pip install pytest && pytest tests`.
