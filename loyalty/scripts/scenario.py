"""Сквозной сценарий из отчёта (таблица 10). Только стандартная библиотека Python."""
import argparse
import json
import time
import urllib.error
import urllib.request

ap = argparse.ArgumentParser()
ap.add_argument("--api", default="http://localhost:8000")
ap.add_argument("--suffix", default="")
args = ap.parse_args()
S = args.suffix


def call(method, url, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url, data=data, method=method, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, None


def op(n, type_, check, customer="C1042", store="S12", amount=None, points=None):
    body = {
        "operation_id": f"o{n}{S}",
        "type": type_,
        "customer_id": customer + S,
        "store_id": store,
        "check_number": check + S,
        "occurred_at": "2026-11-10T14:32:05+07:00",
    }
    if amount is not None:
        body["amount"] = amount
    if points is not None:
        body["points"] = points
    return body


OPS = [
    op(1, "purchase", "CH-1", amount="2490.00"),
    op(2, "purchase", "CH-1", amount="100.00"),
    op(3, "redeem", "CH-2", amount="300.00", points=91),
    op(4, "redeem", "CH-3", amount="500.00", points=100),
    op(5, "redeem", "CH-4", amount="500.00", points=100),
    op(6, "return", "CH-1"),
    op(7, "return", "CH-1"),
    op(8, "return", "CH-999"),
    op(9, "return", "CH-1", customer="C7"),
    op(10, "purchase", "CH-5", amount="1000.00"),
    op(11, "purchase", "CH-6", customer="C9", store="S20", amount="500.00"),
]

for o in OPS:
    code, _ = call("POST", f"{args.api}/operations", o)
    assert code == 202, (o["operation_id"], code)
print("Отправлено операций:", len(OPS), "(все 202 Accepted)\n")
print(f"{'операция':9}{'вид':10}{'статус':10}{'Δ':>6}{'баланс':>8}  причина")
for o in OPS:
    for _ in range(100):
        code, r = call("GET", f"{args.api}/operations/{o['operation_id']}")
        if code == 200:
            break
        time.sleep(0.2)
    else:
        raise SystemExit(f"{o['operation_id']}: не обработана за 20 с")
    print(
        f"{r['operation_id']:9}{r['type']:10}{r['status']:10}"
        f"{r['points_delta']:>6}{r['balance_after']:>8}  {r['reject_reason'] or '-'}"
    )
